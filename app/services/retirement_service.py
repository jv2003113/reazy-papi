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
            "spousePensionIncome": float(overrides.get("spousePensionIncome", 0)),
            
            # Asset Contributions
            "retirementAccount401kContribution": float(val("retirementAccount401kContribution", "assets", "retirementAccount401kContribution", 0)),
            "retirementAccountIRAContribution": float(val("retirementAccountIRAContribution", "assets", "retirementAccountIRAContribution", 0)),
            "retirementAccountRothContribution": float(val("retirementAccountRothContribution", "assets", "retirementAccountRothContribution", 0)),
            "hsaContribution": float(val("hsaContribution", "assets", "hsaContribution", 0)),
            "investmentContribution": float(val("investmentContribution", "assets", "investmentContribution", 0)),

            # Spouse Asset Contributions
            "spouseRetirementAccount401kContribution": float(val("spouseRetirementAccount401kContribution", "assets", "spouseRetirementAccount401kContribution", 0)),
            "spouseRetirementAccountIRAContribution": float(val("spouseRetirementAccountIRAContribution", "assets", "spouseRetirementAccountIRAContribution", 0)),
            "spouseRetirementAccountRothContribution": float(val("spouseRetirementAccountRothContribution", "assets", "spouseRetirementAccountRothContribution", 0)),
            "spouseHsaContribution": float(val("spouseHsaContribution", "assets", "spouseHsaContribution", 0))
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
        
        # Determine Filing Status
        # Simple heuristic: If spouse fields heavily used, assume MFJ.
        # User doesn't have explicit filing status field yet? 
        # We can check "spouseStartAge" which implies spouse exists.
        filing_status = "single"
        if inputs.get("spouseStartAge") is not None:
             filing_status = "married_jointly"
        
        # 2. Initialize Current Balances (Year 0 State)
        def get_d(category, key, default=0):
            d = getattr(user, category, {}) or {}
            val = d.get(key)
            try:
                return float(val) if val is not None else float(default)
            except (ValueError, TypeError):
                return float(default)

        # Asset Buckets (Split)
        # User
        user_bal_401k = get_d("assets", "retirementAccount401k") + get_d("assets", "retirementAccountIRA")
        user_bal_roth = get_d("assets", "retirementAccountRoth")
        user_bal_hsa = get_d("assets", "hsaBalance")
        
        # Spouse
        spouse_bal_401k = get_d("assets", "spouseRetirementAccount401k") + get_d("assets", "spouseRetirementAccountIRA")
        spouse_bal_roth = get_d("assets", "spouseRetirementAccountRoth")
        spouse_bal_hsa = get_d("assets", "spouseHsaBalance")

        # Joint / Other
        bal_brokerage = get_d("assets", "investmentBalance")
        bal_savings = get_d("assets", "savingsBalance") + get_d("assets", "checkingBalance")
        
        # Combined for withdrawals logic (initially) and reporting
        bal_401k = user_bal_401k + spouse_bal_401k
        bal_roth = user_bal_roth + spouse_bal_roth
        bal_hsa = user_bal_hsa + spouse_bal_hsa
        
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
                
                # Income Breakdown (Current)
                income_sources = []
                if curr_salary > 0: income_sources.append({"source": "Salary", "amount": curr_salary})
                if curr_spouse_salary > 0: income_sources.append({"source": "Spouse Salary", "amount": curr_spouse_salary})
                
                # Liabilities Breakdown
                liabilities_breakdown = []
                if bal_mortgage > 0: liabilities_breakdown.append({"name": "Mortgage", "type": "mortgage", "balance": bal_mortgage})
                if bal_other_debt > 0: liabilities_breakdown.append({"name": "Other Debts", "type": "debt", "balance": bal_other_debt})
                
                # Expenses Breakdown (Current)
                # We use the current monthly expenses * 12
                base_monthly = get_d("expenses", "totalMonthlyExpenses")
                current_annual_expenses = base_monthly * 12
                
                expenses_breakdown = []
                # If we have breakdown in user profile, we could try to use it, but flat total is safer for now.
                # Let's add a "Living Expenses" item.
                if bal_mortgage > 0:
                     # Estimate mortgage part if possible, otherwise bundle.
                     # Simply adding total as "Living Expenses" for Year 0 to match total.
                     pass
                
                expenses_breakdown.append({"category": "Current Living Expenses", "amount": current_annual_expenses})

                projections.append({
                    "year": year,
                    "age": age,
                    "grossIncome": gross_income,
                    "netIncome": gross_income * 0.8, # Placeholder tax rate
                    "totalExpenses": current_annual_expenses,
                    "totalAssets": total_assets,
                    "totalLiabilities": total_liabilities,
                    "netWorth": net_worth,
                    "taxesPaid": 0, # Not calculating tax for Year 0 (past/current), just reporting
                    "cumulativeTax": 0,
                    "assets": snapshots_assets,
                    "liabilities": liabilities_breakdown,
                    "income": income_sources,
                    "expenses": expenses_breakdown
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
            
            # Spouse SS
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
            base_expenses_monthly = get_d("expenses", "totalMonthlyExpenses")
            if base_expenses_monthly == 0: base_expenses_monthly = 4000.0 # Fallback
            
            annual_expenses = (base_expenses_monthly * 12) * inflator
            if is_retired:
                desired_spend = inputs["desiredAnnualRetirementSpending"]
                if desired_spend > 0:
                    annual_expenses = desired_spend * inflator

            projected_expenses_list = []
            
            # Mortgage Payment (if exists)
            mortgage_payment = 0.0
            if bal_mortgage > 0:
                mortgage_payment = 28000.0 # Fixed
                annual_expenses += mortgage_payment
                bal_mortgage = max(0, bal_mortgage - (mortgage_payment * 0.6))
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
            
            # 5. ESTIMATED Tax Calculation (For Cash Flow Gap Analysis)
            # We don't know exact total income until we know withdrawals, but withdrawals depend on deficit (taxable).
            # Iterative approach is best, but for MVP we estimate using "Guaranteed + RMD".
            
            # Categorize Income Streams
            # Ordinary Income
            # Note: SS taxability is complex. Generally up to 85% is taxable.
            taxable_ss = (income_ss + income_spouse_ss) * 0.85
            ordinary_income_base = income_salary + income_spouse_salary + income_pension + income_other + rmd_amount + taxable_ss
            
            # Initial Tax Calculation (Pre-Withdrawals)
            est_fed_tax = self.assumptions_service.calculate_federal_income_tax(ordinary_income_base, filing_status)
            # State tax? (Not implemented in assumptions yet, assume 0 or included)
            
            # Net Income Available
            # Note: "Income Tax" is an expense we must pay.
            # Cash Flow In = Guaranteed Income + RMD
            # Cash Flow Out = Expenses + Taxes
            
            total_inflow = total_guaranteed_income + rmd_amount
            # Note: total_guaranteed_income includes FULL SS. 
            # Tax calc used partial SS.
            
            # We need to cover Annual Expenses + Estimated Taxes.
            required_outflow = annual_expenses + est_fed_tax
            
            deficit = max(0, required_outflow - total_inflow)
            surplus = max(0, total_inflow - required_outflow)
            
            # 6. Withdrawals / Contributions Logic
            withdrawal_taxable = 0.0 # From Brokerage (Cap Gains + Basis)
            withdrawal_pretax = 0.0 # From 401k (Ordinary)
            withdrawal_roth = 0.0 # From Roth (Tax Free)
            
            withdrawal_taxes_added = 0.0
            
            remaining_deficit = deficit
            
            # Determine Marginal Rate for Gross Up
            marginal_rate = self.assumptions_service.get_marginal_rate(ordinary_income_base, filing_status)
            if marginal_rate == 0: marginal_rate = 0.10 # Floor to avoid div by zero issues if income is 0
            
            # Step A: Brokerage (Cap Gains)
            # Assumption: 100% is Cap Gains (for tax accuracy Rec #1). 
            # Rate: 0%, 15%, 20%
            if remaining_deficit > 0 and bal_brokerage > 0:
                # Cap Gains Rate Estimate? 
                # It stacks on top of Ordinary.
                # Simplification: Assume 15% unless high income.
                est_cap_rate = 0.15 
                if ordinary_income_base > 450000: est_cap_rate = 0.20
                if ordinary_income_base < 40000: est_cap_rate = 0.0 # Rough check
                
                needed_gross = remaining_deficit / (1 - est_cap_rate)
                available = bal_brokerage
                
                take = min(needed_gross, available)
                
                # Calculate actual tax impact
                # This adds to "Cap Gains" bucket
                tax_on_withdrawal = self.assumptions_service.calculate_capital_gains_tax(ordinary_income_base, take, filing_status)
                
                withdrawal_taxable += take
                withdrawal_taxes_added += tax_on_withdrawal
                
                net_received = take - tax_on_withdrawal
                bal_brokerage -= take
                remaining_deficit -= net_received
            
            # Step B: Pre-Tax (401k/IRA)
            bal_401k_after_rmd = max(0, bal_401k - rmd_amount)
            
            if remaining_deficit > 0.1 and bal_401k_after_rmd > 0:
                # Ordinary Income
                needed_gross = remaining_deficit / (1 - marginal_rate)
                available = bal_401k_after_rmd
                
                take = min(needed_gross, available)
                
                # Tax Impact
                # Re-calc tax with added ordinary
                base_tax = est_fed_tax
                new_tax = self.assumptions_service.calculate_federal_income_tax(ordinary_income_base + take, filing_status)
                tax_on_withdrawal = new_tax - base_tax
                
                withdrawal_pretax += take
                withdrawal_taxes_added += tax_on_withdrawal
                
                net_received = take - tax_on_withdrawal
                bal_401k_after_rmd -= take
                remaining_deficit -= net_received
                
                # Update Ordinary Base for subsequent steps (though usually none tax-impacting after this)
                ordinary_income_base += take
                
            # Step C: Roth / HSA
            total_tax_free = bal_roth + bal_hsa
            
            if remaining_deficit > 0.1 and total_tax_free > 0:
                take = min(remaining_deficit, total_tax_free)
                withdrawal_roth += take
                
                if bal_roth >= take:
                    bal_roth -= take
                else:
                    leftover = take - bal_roth
                    bal_roth = 0
                    bal_hsa = max(0, bal_hsa - leftover)
                    
                remaining_deficit -= take

            # 7. Finalize Year
            
            # Recalculate Final Tax Liability with exact totals
            final_ordinary_income = income_salary + income_spouse_salary + income_pension + income_other + rmd_amount + taxable_ss + withdrawal_pretax
            final_cap_gains = withdrawal_taxable # Assuming 100% gain
            
            final_fed_tax = self.assumptions_service.calculate_federal_income_tax(final_ordinary_income, filing_status)
            final_cap_tax = self.assumptions_service.calculate_capital_gains_tax(final_ordinary_income, final_cap_gains, filing_status)
            
            total_tax_paid = final_fed_tax + final_cap_tax
            cumulative_tax += total_tax_paid
            
            # Apply Contributions (If Working)
            
            # Sync Sub-Balances (Proportional Reduction if Withdrawals occurred)
            # 401k
            prev_total_401k = user_bal_401k + spouse_bal_401k
            # Balance available before growth but AFTER withdrawals
            bal_401k_post_wd = max(0, bal_401k - rmd_amount - withdrawal_pretax)
            
            if prev_total_401k > 0:
                remaining_ratio = bal_401k_post_wd / prev_total_401k
                if remaining_ratio < 0: remaining_ratio = 0
                user_bal_401k *= remaining_ratio
                spouse_bal_401k *= remaining_ratio
            else:
                 # If previous total was 0, but maybe we have new contributions coming? 
                 # Or if balance became 0, sub-balances are 0.
                 user_bal_401k = 0
                 spouse_bal_401k = 0

            # Roth
            # Determine how much was withdrawn from Roth
            # Start of loop bal_roth was sum.
            bal_roth_post_wd = bal_roth # bal_roth was decremented in Step C
            prev_total_roth = user_bal_roth + spouse_bal_roth
            if prev_total_roth > 0:
                remaining_ratio = bal_roth_post_wd / prev_total_roth
                user_bal_roth *= remaining_ratio
                spouse_bal_roth *= remaining_ratio
            else:
                user_bal_roth = 0
                spouse_bal_roth = 0
                
            # HSA
            bal_hsa_post_wd = bal_hsa
            prev_total_hsa = user_bal_hsa + spouse_bal_hsa
            if prev_total_hsa > 0:
                remaining_ratio = bal_hsa_post_wd / prev_total_hsa
                user_bal_hsa *= remaining_ratio
                spouse_bal_hsa *= remaining_ratio
            else:
                user_bal_hsa = 0
                spouse_bal_hsa = 0

            # Apply New Contributions
            # User Contributions
            if not is_retired:
                 user_contrib_401k = inputs["retirementAccount401kContribution"] + inputs["retirementAccountIRAContribution"]
                 user_contrib_roth = inputs["retirementAccountRothContribution"]
                 user_contrib_hsa = inputs["hsaContribution"]
                 
                 user_bal_401k += user_contrib_401k
                 user_bal_roth += user_contrib_roth
                 user_bal_hsa += user_contrib_hsa
                 
                 bal_brokerage += inputs["investmentContribution"]

            # Spouse Contributions
            spouse_is_retired = False
            if inputs.get("spouseRetirementAge") and inputs.get("spouseStartAge"):
                 spouse_age_now = inputs["spouseStartAge"] + years_from_start
                 if spouse_age_now >= inputs["spouseRetirementAge"]:
                     spouse_is_retired = True
            
            if not spouse_is_retired and inputs.get("spouseStartAge"): 
                 spouse_contrib_401k = inputs["spouseRetirementAccount401kContribution"] + inputs["spouseRetirementAccountIRAContribution"]
                 spouse_contrib_roth = inputs["spouseRetirementAccountRothContribution"]
                 spouse_contrib_hsa = inputs["spouseHsaContribution"]
                 
                 spouse_bal_401k += spouse_contrib_401k
                 spouse_bal_roth += spouse_contrib_roth
                 spouse_bal_hsa += spouse_contrib_hsa
            
            
            # Apply Growth
            # 401k balance update (use the sub-balances which now have contributions)
            user_bal_401k *= (1 + portfolio_growth_rate)
            spouse_bal_401k *= (1 + portfolio_growth_rate)
            
            user_bal_roth *= (1 + portfolio_growth_rate)
            spouse_bal_roth *= (1 + portfolio_growth_rate)
            
            user_bal_hsa *= (1 + portfolio_growth_rate)
            spouse_bal_hsa *= (1 + portfolio_growth_rate)

            bal_brokerage *= (1 + portfolio_growth_rate)
            bal_savings *= (1 + bond_growth_rate)
            
            # Recombine for next loop iteration
            bal_401k = user_bal_401k + spouse_bal_401k
            bal_roth = user_bal_roth + spouse_bal_roth
            bal_hsa = user_bal_hsa + spouse_bal_hsa
            
            # 8. Record Data
            total_assets = bal_401k + bal_roth + bal_brokerage + bal_savings + bal_hsa
            total_liabilities = bal_mortgage + bal_other_debt
            net_worth = total_assets - total_liabilities
            
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
            
            if withdrawal_taxable > 0: income_sources.append({"source": "Investment Withdrawal (Taxable)", "amount": withdrawal_taxable})
            if withdrawal_pretax > 0: income_sources.append({"source": "401k/IRA Withdrawal", "amount": withdrawal_pretax})
            if withdrawal_roth > 0: income_sources.append({"source": "Roth Withdrawal", "amount": withdrawal_roth})
            
            projections.append({
                "year": year,
                "age": age,
                "grossIncome": total_guaranteed_income + rmd_amount + withdrawal_taxable + withdrawal_pretax + withdrawal_roth, 
                "netIncome": (total_guaranteed_income + rmd_amount + withdrawal_taxable + withdrawal_pretax + withdrawal_roth) - total_tax_paid,
                "totalExpenses": annual_expenses + total_tax_paid, 
                "totalAssets": total_assets,
                "totalLiabilities": total_liabilities,
                "netWorth": net_worth,
                "taxesPaid": total_tax_paid,
                "cumulativeTax": cumulative_tax,
                "assets": assets_breakdown,
                "liabilities": [{"name": "Mortgage", "type": "mortgage", "balance": bal_mortgage}] if bal_mortgage > 0 else [],
                "income": income_sources,
                "expenses": projected_expenses_list + [{"category": "Taxes", "amount": total_tax_paid}]
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

