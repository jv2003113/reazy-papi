import math
import json
from datetime import datetime
from decimal import Decimal
from typing import List, Dict, Any, Optional
from uuid import UUID

from sqlmodel import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    User,
    RetirementPlan,
    AnnualSnapshot,
    UserMilestone
)
from app.models.retirement import RetirementPlanBase
from app.services.financial_assumptions_service import FinancialAssumptionsService

class RetirementService:
    """
    Service class responsible for business logic related to retirement planning.
    
    This service handles:
    1. Orchestrating the generation of retirement plans.
    2. Calculating year-by-year financial projections (income, expenses, assets, liabilities).
    3. Persisting these projections as 'snapshots' in the database.
    4. Managing lifecycle of plan data (clearing old data before regeneration).
    """
    def __init__(self, session: AsyncSession):
        self.session = session
        self.assumptions_service = FinancialAssumptionsService()
        
    async def get_user_by_id(self, user_id: UUID) -> Optional[User]:
        result = await self.session.execute(select(User).where(User.id == user_id))
        return result.scalars().first()

    async def clear_plan_data(self, plan_id: UUID):
        # SQLModel delete doesn't support cascade automatically in python unless configured in DB.
        # But we have cascade="all, delete-orphan" in relationships.
        # However, to be safe and efficient, we can delete snapshots which cascade to children.
        # Actually snapshots cascade to children. Plan cascades to snapshots.
        # If we just want to clear data but keep plan, we delete snapshots.
        stmt = select(AnnualSnapshot).where(AnnualSnapshot.planId == plan_id)
        result = await self.session.execute(stmt)
        snapshots = result.scalars().all()
        
        for snapshot in snapshots:
            await self.session.delete(snapshot)
            
        # Also delete personal milestones for this plan
        stmt_milestones = select(UserMilestone).where(UserMilestone.planId == plan_id)
        result_milestones = await self.session.execute(stmt_milestones)
        milestones = result_milestones.scalars().all()
        for m in milestones:
            await self.session.delete(m)
            
        await self.session.commit()

    async def generate_retirement_plan(self, plan: RetirementPlan):
        """
        Main entry point for generating a retirement plan.

        Steps:
        1. Validates the user exists.
        2. Clears any existing snapshot/milestone data for this plan ID to ensure a clean slate.
        3. Calls `calculate_financial_projections` to run the simulation in memory.
        4. Calls `create_annual_snapshots` to save the results to the database.
        5. Updates the parent Plan record with summary stats (e.g. Total Lifetime Tax).
        
        Args:
            plan (RetirementPlan): The plan object containing parameters (ages, rates, etc.).
            
        Returns:
            RetirementPlan: The updated plan object.
        """
        # Fetch user
        user = await self.get_user_by_id(plan.userId)
        if not user:
            raise ValueError(f"User {plan.userId} not found")

        # Clear existing data
        await self.clear_plan_data(plan.id)

        # Calculate projections
        projections = self.calculate_financial_projections(plan, user)

        # Persistence
        await self.create_annual_snapshots(plan, projections)
        # await self.create_standard_milestones(plan)
        
        # Update plan totalLifetimeTax
        total_lifetime_tax = sum(p['taxesPaid'] for p in projections)
        plan.totalLifetimeTax = Decimal(total_lifetime_tax)
        self.session.add(plan)
        await self.session.commit()
        await self.session.refresh(plan)
        
        return plan

    @staticmethod
    def _resolve_inputs(plan: RetirementPlan, user: User) -> Dict[str, Any]:
        """
        Resolves the effective plan configuration.
        Priority: Plan Overrides > User Profile (JSONB) > System Defaults
        """
        overrides = plan.planOverrides or {}
        
        # Helper to safely get from nested JSONB
        def val(key, category, attr, default):
            if key in overrides:
                return overrides[key]
            
            # Access user category (dict)
            cat_dict = getattr(user, category, {}) or {}
            u_val = cat_dict.get(attr)
            return u_val if u_val is not None else default

        # Map inputs
        return {
            "inflationRate": float(val("inflationRate", "risk", "inflationRateAssumption", 3.0)) / 100,
            "portfolioGrowthRate": float(val("portfolioGrowthRate", "risk", "investmentReturnAssumption", 7.0)) / 100,
            "bondGrowthRate": float(val("bondGrowthRate", "risk", "bondGrowthRateAssumption", 4.0)) / 100,
            
            "retirementAge": int(val("retirementAge", "personal_info", "targetRetirementAge", 65)),
            
            "socialSecurityStartAge": int(val("socialSecurityStartAge", "income", "socialSecurityStartAge", 67)),
            "estimatedSocialSecurityBenefit": float(val("estimatedSocialSecurityBenefit", "income", "socialSecurityAmount", 0)),
            
            "pensionIncome": float(val("pensionIncome", "income", "pensionIncome", 0)),
            
            "desiredAnnualRetirementSpending": float(val("desiredAnnualRetirementSpending", "expenses", "desiredRetirementSpending", 80000)),

            # Note: startAge/endAge are still on Plan model.
            "startAge": int(overrides.get("startAge", plan.startAge)), 
            "endAge": int(overrides.get("endAge", plan.endAge)),

            # Spouse Fields
            "spouseStartAge": int(val("spouseStartAge", "personal_info", "spouseCurrentAge", 30)) if val("spouseStartAge", "personal_info", "spouseCurrentAge", None) else None,
            "spouseRetirementAge": int(val("spouseRetirementAge", "personal_info", "spouseTargetRetirementAge", 65)) if val("spouseRetirementAge", "personal_info", "spouseTargetRetirementAge", None) else None,
            "spouseEndAge": int(overrides.get("spouseEndAge", 95)),
            
            "spouseSocialSecurityStartAge": int(val("spouseSocialSecurityStartAge", "income", "spouseSocialSecurityStartAge", 67)),
            "spouseEstimatedSocialSecurityBenefit": float(val("spouseEstimatedSocialSecurityBenefit", "income", "spouseSocialSecurityAmount", 0)),
            "spousePensionIncome": float(overrides.get("spousePensionIncome", 0))
        }

    def calculate_financial_projections(self, plan: RetirementPlan, user: User) -> List[Dict[str, Any]]:
        """
        Advanced Quant Simulation Engine.
        Year 0: Current Snapshot (No calculations).
        Year 1+: Growth, Flows, and Tax-Efficient Withdrawals.
        """
        projections = []
        current_year = datetime.now().year
        
        # 1. Resolve effective inputs
        inputs = RetirementService._resolve_inputs(plan, user)
        
        inflation_rate = inputs["inflationRate"]
        portfolio_growth_rate = inputs["portfolioGrowthRate"]
        bond_growth_rate = inputs["bondGrowthRate"]
        
        retirement_age = inputs["retirementAge"]
        start_age = inputs["startAge"]
        end_age = inputs["endAge"]
        
        # Tax Assumptions
        tax_rates = self.assumptions_service.get_tax_rates(current_year)
        TAX_RATE_ORDINARY = tax_rates.ordinary_income # Effective rate for 401k/Salary
        TAX_RATE_CAP_GAINS = tax_rates.capital_gains # Long term cap gains for Brokerage
        TAX_RATE_SS = tax_rates.social_security # Simplified SS taxability
        
        # 2. Initialize Current Balances (Year 0 State)
        def get_d(category, key, default=0):
            d = getattr(user, category, {}) or {}
            val = d.get(key)
            try:
                return float(val) if val is not None else float(default)
            except (ValueError, TypeError):
                return float(default)

        # Asset Buckets
        bal_401k = get_d("assets", "retirementAccount401k") + get_d("assets", "retirementAccountIRA")
        bal_roth = get_d("assets", "retirementAccountRoth")
        bal_brokerage = get_d("assets", "investmentBalance")
        bal_savings = get_d("assets", "savingsBalance") + get_d("assets", "checkingBalance")
        bal_hsa = get_d("assets", "hsaBalance") + get_d("assets", "spouseHsaBalance") # Treated as triple-tax-advantaged, effectively Roth-like for health or Pre-tax in
        
        # Liabilities
        bal_mortgage = get_d("liabilities", "mortgageBalance")
        bal_other_debt = get_d("liabilities", "creditCardDebt") + get_d("liabilities", "studentLoanDebt") + get_d("liabilities", "otherDebt")

        cumulative_tax = 0.0

        # --- LOOP ---
        for age in range(start_age, end_age + 1):
            year = current_year + (age - start_age)
            years_from_start = age - start_age
            
            is_retired = age >= retirement_age
            
            # --- YEAR 0: SNAPSHOT ONLY ---
            if years_from_start == 0:
                # Just return current state, no operations
                total_assets = bal_401k + bal_roth + bal_brokerage + bal_savings + bal_hsa
                total_liabilities = bal_mortgage + bal_other_debt
                net_worth = total_assets - total_liabilities
                
                # Gross Income (Current)
                curr_salary = get_d("income", "currentIncome")
                curr_spouse_salary = get_d("income", "spouseCurrentIncome")
                gross_income = curr_salary + curr_spouse_salary
                
                snapshots_assets = [
                    {"name": "401(k) / IRA", "type": "retirement", "balance": bal_401k},
                    {"name": "Roth IRA", "type": "retirement", "balance": bal_roth},
                    {"name": "Brokerage", "type": "investment", "balance": bal_brokerage},
                    {"name": "Savings", "type": "cash", "balance": bal_savings},
                    {"name": "HSA", "type": "hsa", "balance": bal_hsa},
                ]
                
                projections.append({
                    "year": year,
                    "age": age,
                    "grossIncome": gross_income,
                    "netIncome": gross_income * (1 - TAX_RATE_ORDINARY), # Rough net
                    "totalExpenses": 0, # Placeholder for Year 0 or use current expenses
                    "totalAssets": total_assets,
                    "totalLiabilities": total_liabilities,
                    "netWorth": net_worth,
                    "taxesPaid": 0,
                    "cumulativeTax": 0,
                    "assets": snapshots_assets,
                    "liabilities": [],
                    "income": [],
                    "expenses": []
                })
                continue

            # --- YEAR 1+: CALCULATIONS ---
            
            # 1. Inflation Adjustments
            inflator = (1 + inflation_rate) ** years_from_start
            
            # 2. Income Sources
            income_salary = 0.0
            income_spouse_salary = 0.0
            income_ss = 0.0
            income_spouse_ss = 0.0
            income_pension = 0.0
            income_other = 0.0
            
            # Employment Income
            if not is_retired:
                income_salary = get_d("income", "currentIncome") * inflator
                income_spouse_salary = get_d("income", "spouseCurrentIncome") * inflator
            
            # Retirement Income
            if age >= inputs["socialSecurityStartAge"]:
                income_ss = inputs["estimatedSocialSecurityBenefit"] * inflator
            
            # Spouse SS (Assuming spouse is similar age or using spouse age logic if complex, but here simplifying to Age check based on inputs)
            # We don't track spouse age increment separately in this simplified loop, assuming aligned timeline or approximation.
            # Ideally we track spouse_age = spouse_start_age + years_from_start.
            spouse_current_age = get_d("personal_info", "spouseCurrentAge", 0)
            spouse_age_now = spouse_current_age + years_from_start if spouse_current_age else age
            if spouse_current_age and spouse_age_now >= inputs["spouseSocialSecurityStartAge"]:
                income_spouse_ss = inputs["spouseEstimatedSocialSecurityBenefit"] * inflator

            if is_retired or age >= 65: # Pension typically starts at retirement
                income_pension = inputs["pensionIncome"] * inflator + inputs["spousePensionIncome"] * inflator
                
            # Other Income
            other_inc_1 = get_d("income", "otherIncomeAmount1") * inflator
            other_inc_2 = get_d("income", "otherIncomeAmount2") * inflator
            income_other = other_inc_1 + other_inc_2
            
            # Total Guaranteed Income
            total_guaranteed_income = income_salary + income_spouse_salary + income_ss + income_spouse_ss + income_pension + income_other
            
            # 3. Required Expenses
            # Base expenses
            base_expenses_monthly = get_d("expenses", "totalMonthlyExpenses")
            if base_expenses_monthly == 0: base_expenses_monthly = 4000.0 # Fallback
            
            annual_expenses = (base_expenses_monthly * 12) * inflator
            if is_retired:
                # Use desired retirement spending if specified and higher/override
                # implementation_plan said use inflation adjusted, but often users set specific retirement target
                desired_spend = inputs["desiredAnnualRetirementSpending"]
                if desired_spend > 0:
                    # Make sure we don't double count if they just filled the expense form.
                    # Logic: If Retired, use Max(InflatedCurrentExpenses, InflatedDesiredSpending)
                    # Or just strictly Desired. Let's use Desired relative to base year.
                    annual_expenses = desired_spend * inflator

            # Define breakdown list for UI (calculated before mortgage logic modified annual_expenses?)
            # Wait, logic above adds mortgage to annual_expenses iteratively?
            
            projected_expenses_list = []
            
            # Mortgage Payment (if exists)
            mortgage_payment = 0.0
            if bal_mortgage > 0:
                mortgage_payment = 28000.0 # Fixed placeholder or from inputs.
                # Assuming mortgage payment is NOT inflation adjusted (fixed rate)
                # Add to total for deficit calculation
                annual_expenses += mortgage_payment
                # Pay down principal roughly
                bal_mortgage = max(0, bal_mortgage - (mortgage_payment * 0.6)) # 60% principal, 40% interest approx for simplicity
                
                projected_expenses_list.append({"category": "Primary Mortgage", "amount": mortgage_payment})

            # Add remaining as Living Expenses
            living_expenses_portion = annual_expenses - mortgage_payment
            projected_expenses_list.insert(0, {"category": "Living Expenses", "amount": living_expenses_portion})

            # 4. RMD Calculations (Required Minimum Distributions)
            rmd_amount = 0.0
            if bal_401k > 0:
                divisor = self.assumptions_service.get_rmd_divisor(age)
                if divisor > 0:
                    rmd_amount = bal_401k / divisor
                    # RMD is forced withdrawal
            
            # 5. Gap Analysis (Income vs Expenses)
            # RMD is taxable income, but it's also cash flow available to spend.
            # Tax on RMD:
            rmd_tax = rmd_amount * TAX_RATE_ORDINARY
            rmd_net = rmd_amount - rmd_tax
            
            # Tax on Guaranteed Income (Working)
            tax_on_income = (income_salary + income_spouse_salary) * TAX_RATE_ORDINARY
            # Tax on Fixed Income (Retirement)
            tax_on_fixed = (income_pension) * TAX_RATE_ORDINARY + (income_ss + income_spouse_ss) * TAX_RATE_SS
            
            total_income_tax_liability = tax_on_income + tax_on_fixed + rmd_tax
            
            net_income_available = total_guaranteed_income + rmd_net - (tax_on_income + tax_on_fixed)
            
            deficit = max(0, annual_expenses - net_income_available)
            surplus = max(0, net_income_available - annual_expenses)
            
            # 6. Withdrawals / Contributions Logic
            withdrawal_taxable = 0.0
            withdrawal_pretax = 0.0
            withdrawal_roth = 0.0
            
            withdrawal_taxes = 0.0
            
            # WITHDRAWAL WATERFALL (Methodology: Tax Efficiency)
            # 1. RMDs (Already taken above as `rmd_net`). If deficit remains:
            # 2. Taxable (Brokerage) -> Cap Gains Rate
            # 3. Tax-Deferred (401k/IRA) -> Ordinary Rate
            # 4. Tax-Free (Roth/HSA) -> 0% Rate
            
            remaining_deficit = deficit
            
            # Step A: Brokerage
            if remaining_deficit > 0 and bal_brokerage > 0:
                # We need `remaining_deficit` NET.
                # Gross Up: Amount = Deficit / (1 - TaxRate)
                needed_gross = remaining_deficit / (1 - TAX_RATE_CAP_GAINS)
                available = bal_brokerage
                
                take = min(needed_gross, available)
                tax_hit = take * TAX_RATE_CAP_GAINS
                net_received = take - tax_hit
                
                withdrawal_taxable += take
                withdrawal_taxes += tax_hit
                bal_brokerage -= take
                remaining_deficit -= net_received
            
            # Step B: Pre-Tax (401k/IRA) - Excluding RMDs already taken
            # Note: RMDs reduce the balance at the end, but here we take ADDITIONAL if needed
            # RMD amount was calculated but not yet deducted from `bal_401k` variable until end? 
            # Let's deduct RMD now to see what's left.
            bal_401k_after_rmd = max(0, bal_401k - rmd_amount)
            
            if remaining_deficit > 0.1 and bal_401k_after_rmd > 0:
                needed_gross = remaining_deficit / (1 - TAX_RATE_ORDINARY)
                available = bal_401k_after_rmd
                
                take = min(needed_gross, available)
                tax_hit = take * TAX_RATE_ORDINARY
                net_received = take - tax_hit
                
                withdrawal_pretax += take
                withdrawal_taxes += tax_hit
                bal_401k_after_rmd -= take # Update temp balance
                remaining_deficit -= net_received
                
            # Step C: Roth / HSA
            # Combined pool for simplicity
            total_tax_free = bal_roth + bal_hsa
            
            if remaining_deficit > 0.1 and total_tax_free > 0:
                take = min(remaining_deficit, total_tax_free)
                # No tax
                withdrawal_roth += take
                
                # Deduct proportionally or Order? Roth then HSA?
                # Let's drain Roth first.
                if bal_roth >= take:
                    bal_roth -= take
                else:
                    leftover = take - bal_roth
                    bal_roth = 0
                    bal_hsa = max(0, bal_hsa - leftover)
                    
                remaining_deficit -= take

            # 7. Apply Growth (End of Year)
            # Apply to remaining balances
            # Update 401k balance including RMD deduction and extra withdrawals
            bal_401k = max(0, bal_401k - rmd_amount - withdrawal_pretax)
            
            # Apply contributions if Surplus (Working years mainly)
            contrib_401k = 0.0
            contrib_brokerage = 0.0
            contrib_savings = 0.0
            
            if surplus > 0:
                if not is_retired:
                    # Generic logic: Save 20% of surplus to Savings, rest to Brokerage
                    # Caps on 401k? Assume user filled 401k via inputs, this is EXTRA surplus?
                    # Inputs usually define "401k Contribution". If defined, we should have deducted it from Income earlier?
                    # The previous logic had specific contribution input logic. Let's restore basic Input Contributions.
                    # Simplified: Surplus goes to Brokerage/Savings.
                    contrib_savings = surplus * 0.2
                    contrib_brokerage = surplus * 0.8
                    bal_savings += contrib_savings
                    bal_brokerage += contrib_brokerage
            
            # Note: User inputs for "Annual Contribution" should ideally be honored. 
            # For this "Quant" refactor, let's assume `surplus` captures the net cashflow available to save.
            
            # Growth
            bal_401k *= (1 + portfolio_growth_rate)
            bal_roth *= (1 + portfolio_growth_rate)
            bal_brokerage *= (1 + portfolio_growth_rate)
            bal_hsa *= (1 + portfolio_growth_rate)
            
            bal_savings *= (1 + bond_growth_rate) # Cash/Bonds lower rate
            
            # 8. Record Data
            total_assets = bal_401k + bal_roth + bal_brokerage + bal_savings + bal_hsa
            total_liabilities = bal_mortgage + bal_other_debt
            net_worth = total_assets - total_liabilities
            
            total_taxes_this_year = total_income_tax_liability + withdrawal_taxes
            cumulative_tax += total_taxes_this_year
            
            # Detailed breakdown for charts
            assets_breakdown = [
                {"name": "401(k) / IRA", "type": "retirement", "balance": bal_401k},
                {"name": "Roth IRA", "type": "retirement", "balance": bal_roth},
                {"name": "Brokerage", "type": "investment", "balance": bal_brokerage},
                {"name": "Savings", "type": "cash", "balance": bal_savings},
                {"name": "HSA", "type": "hsa", "balance": bal_hsa},
            ]
            
            income_sources = []
            if income_salary > 0: income_sources.append({"source": "Salary", "amount": income_salary})
            if income_spouse_salary > 0: income_sources.append({"source": "Spouse Salary", "amount": income_spouse_salary})
            if income_ss > 0: income_sources.append({"source": "Social Security", "amount": income_ss})
            if income_spouse_ss > 0: income_sources.append({"source": "Spouse Social Security", "amount": income_spouse_ss})
            if income_pension > 0: income_sources.append({"source": "Pension", "amount": income_pension})
            if rmd_amount > 0: income_sources.append({"source": "RMD Distributions", "amount": rmd_amount})
            
            # Add Withdrawals to Income Sources (so they appear in breakdown)
            if withdrawal_taxable > 0: income_sources.append({"source": "Investment Withdrawal (Taxable)", "amount": withdrawal_taxable})
            if withdrawal_pretax > 0: income_sources.append({"source": "401k/IRA Withdrawal", "amount": withdrawal_pretax})
            if withdrawal_roth > 0: income_sources.append({"source": "Roth Withdrawal", "amount": withdrawal_roth})
            
            projections.append({
                "year": year,
                "age": age,
                "grossIncome": total_guaranteed_income + rmd_amount + withdrawal_taxable + withdrawal_pretax + withdrawal_roth, 
                "netIncome": net_income_available,
                "totalExpenses": annual_expenses + total_taxes_this_year, # Include taxes in total expenses metric? Or keep separate?
                # Actually, typically Total Expenses in summaries usually implies spending. 
                # But if we show Breakdown, we should probably align `totalExpenses` with the sum of breakdown.
                # `annual_expenses` was just living expenses.
                # Let's keep `totalExpenses` as Just Living Expenses for the top level chart usually, BUT if user wants "Expense Breakdown",
                # The detailed list `expenses` key is what matters for the Table/Card.
                
                "totalAssets": total_assets,
                "totalLiabilities": total_liabilities,
                "netWorth": net_worth,
                "taxesPaid": total_taxes_this_year,
                "cumulativeTax": cumulative_tax,
                "assets": assets_breakdown,
                "liabilities": [{"name": "Mortgage", "type": "mortgage", "balance": bal_mortgage}] if bal_mortgage > 0 else [],
                "income": income_sources,
                "expenses": projected_expenses_list + [{"category": "Taxes", "amount": total_taxes_this_year}]
            })
            
        return projections

    async def create_annual_snapshots(self, plan: RetirementPlan, projections: List[Dict[str, Any]]):
        """
        Persists the calculated projections to the database.

        Creates `AnnualSnapshot` records for each year.
        Uses JSONB columns for assets, liabilities, income, and expenses details.
        """
        for p in projections:
            snapshot = AnnualSnapshot(
                planId=plan.id,
                year=p["year"],
                age=p["age"],
                grossIncome=Decimal(p["grossIncome"]),
                netIncome=Decimal(p["netIncome"]),
                totalExpenses=Decimal(p["totalExpenses"]),
                totalAssets=Decimal(p["totalAssets"]),
                totalLiabilities=Decimal(p["totalLiabilities"]),
                netWorth=Decimal(p["netWorth"]),
                taxesPaid=Decimal(p["taxesPaid"]),
                cumulativeTax=Decimal(p["cumulativeTax"]),
                # JSONB Columns
                assets=p["assets"],
                liabilities=p["liabilities"],
                income=p["income"],
                expenses=p["expenses"]
            )
            self.session.add(snapshot)
            # No need to create child records anymore
        
        await self.session.commit()

    async def create_standard_milestones(self, plan: RetirementPlan):
        # Resolve inputs to get retirement age
        user = await self.get_user_by_id(plan.userId)
        if not user: return
        inputs = self._resolve_inputs(plan, user)
        retirement_age = inputs["retirementAge"]
        
        current_year = datetime.now().year
        milestones = [
            {
                "title": "Retirement Begins",
                "targetYear": current_year + (retirement_age - plan.startAge),
                "targetAge": retirement_age,
                "category": "retirement",
                "description": "Start of retirement phase"
            },
            {
                "title": "Medicare Eligibility",
                "targetYear": current_year + (65 - plan.startAge),
                "targetAge": 65,
                "category": "healthcare",
                "description": "Eligible for Medicare benefits"
            },
            {
                "title": "Social Security Eligibility",
                "targetYear": current_year + (62 - plan.startAge),
                "targetAge": 62,
                "category": "retirement",
                "description": "Eligible for Social Security benefits"
            }
        ]
        
        for m in milestones:
             if m["targetAge"] >= plan.startAge and m["targetAge"] <= plan.endAge:
                 ms = UserMilestone(
                     planId=plan.id,
                     userId=plan.userId,
                     milestoneType="personal",
                     title=m["title"],
                     targetYear=m["targetYear"],
                     targetAge=m["targetAge"],
                     category=m["category"],
                     description=m["description"]
                 )
                 self.session.add(ms)

