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
            
            "spouseSocialSecurityStartAge": int(overrides.get("spouseSocialSecurityStartAge", 67)),
            "spouseEstimatedSocialSecurityBenefit": float(overrides.get("spouseEstimatedSocialSecurityBenefit", 0)),
            "spousePensionIncome": float(overrides.get("spousePensionIncome", 0))
        }

    def calculate_financial_projections(self, plan: RetirementPlan, user: User) -> List[Dict[str, Any]]:
        """
        Core simulation engine. Calculates financial state for every year.
        Uses resolved inputs from User + Overrides.
        """
        projections = []
        current_year = datetime.now().year
        
        # Resolve effective inputs
        inputs = RetirementService._resolve_inputs(plan, user)
        
        inflation_rate = inputs["inflationRate"]
        portfolio_growth_rate = inputs["portfolioGrowthRate"]
        bond_growth_rate = inputs["bondGrowthRate"]
        
        retirement_age = inputs["retirementAge"]
        start_age = inputs["startAge"]
        end_age = inputs["endAge"]

        # Helper for safer retrieval
        def get_d(category, key, default=0):
            d = getattr(user, category, {}) or {}
            return float(d.get(key) or 0)
        
        # Initial Balances
        total_401k = get_d("assets", "retirementAccount401k") + get_d("assets", "retirementAccountIRA")
        total_roth_ira = get_d("assets", "retirementAccountRoth")
        total_brokerage = get_d("assets", "investmentBalance")
        total_savings = get_d("assets", "savingsBalance") + get_d("assets", "checkingBalance")
        total_hsa = get_d("assets", "hsaBalance") + get_d("assets", "spouseHsaBalance")
        
        mortgage_balance = get_d("liabilities", "mortgageBalance")
        
        # Debts
        credit_card_debt = get_d("liabilities", "creditCardDebt")
        student_loan_debt = get_d("liabilities", "studentLoanDebt")
        other_debt = get_d("liabilities", "otherDebt")
        
        cumulative_tax = 0.0
        
        # Loop
        for age in range(start_age, end_age + 1):
            year = current_year + (age - start_age)
            years_from_start = age - start_age
            
            is_retired = age >= retirement_age
            is_working_age = not is_retired
            
            # Income
            current_income = 0.0
            spouse_current_income = 0.0
            social_security_income = 0.0
            pension_income_val = 0.0
            
            if is_working_age:
                user_salary = get_d("income", "currentIncome")
                spouse_salary = get_d("income", "spouseCurrentIncome")
                
                current_income = user_salary * ((1 + inflation_rate) ** years_from_start)
                spouse_current_income = spouse_salary * ((1 + inflation_rate) ** years_from_start)
                
            else:
                # Retirement
                if age >= inputs["socialSecurityStartAge"]:
                    social_security_income = inputs["estimatedSocialSecurityBenefit"] * ((1 + inflation_rate) ** years_from_start)
                
                pension_income_val = inputs["pensionIncome"] * ((1 + inflation_rate) ** years_from_start)

            # Other Income
            u_inc = getattr(user, "income", {}) or {}
            other_income_amt1 = float(u_inc.get("otherIncomeAmount1") or 0)
            other_income_amt2 = float(u_inc.get("otherIncomeAmount2") or 0)

            other_income1 = other_income_amt1 * ((1 + inflation_rate) ** years_from_start) if other_income_amt1 else 0
            other_income2 = other_income_amt2 * ((1 + inflation_rate) ** years_from_start) if other_income_amt2 else 0
            
            gross_income = current_income + spouse_current_income + other_income1 + other_income2
            
            if not is_working_age:
                gross_income += social_security_income + pension_income_val
                
            # Net Income Estimation
            if is_working_age:
                net_income = gross_income * 0.75
            else:
                net_income = gross_income * 0.85

            # Expenses
            base_annual_expenses = 0.0
            detailed_expenses = []
            
            u_exp = getattr(user, "expenses", {}) or {}
            exp_breakdown = u_exp.get("breakdown", [])
            total_monthly_exp_val = float(u_exp.get("totalMonthlyExpenses") or 0)

            if exp_breakdown:
                for exp in exp_breakdown:
                    try:
                        amt = float(exp.get("amount", 0) or 0) * 12
                    except (ValueError, TypeError):
                        amt = 0.0
                    
                    base_annual_expenses += amt
                    detailed_expenses.append({
                        "category": exp.get("category", "Uncategorized"), 
                        "amount": amt,
                        "description": exp.get("description", "")
                    })
            
            if base_annual_expenses == 0:
                 base_annual_expenses = total_monthly_exp_val * 12
                 if base_annual_expenses == 0:
                     base_annual_expenses = 45000.0
                 detailed_expenses.append({"category": "Living Expenses", "amount": base_annual_expenses})
            
            projected_expenses_list = []
            total_expenses = 0.0
            for item in detailed_expenses:
                inflated_amt = item["amount"] * ((1 + inflation_rate) ** years_from_start)
                projected_expenses_list.append({
                    "category": f"{item['category']} - {item.get('description', '')}" if item.get('description') else item['category'],
                    "amount": inflated_amt
                })
                total_expenses += inflated_amt
            
            # Contributions / Withdrawals
            contribution_401k = 0.0
            contribution_roth_ira = 0.0
            contribution_brokerage = 0.0
            contribution_savings = 0.0
            contribution_hsa = 0.0
            
            withdrawal_401k = 0.0
            withdrawal_roth_ira = 0.0
            withdrawal_brokerage = 0.0
            withdrawal_savings = 0.0
            withdrawal_hsa = 0.0
            
            if is_working_age:
                # Contributions
                contribution_401k = min(23000, gross_income * 0.15)
                catch_up = 7500 if age >= 50 else 6500
                contribution_roth_ira = catch_up
                
                remaining_income = net_income - total_expenses - contribution_401k - contribution_roth_ira
                contribution_brokerage = max(0, remaining_income * 0.7)
                contribution_savings = max(0, remaining_income * 0.3)
                
                hsa_contrib_user = get_d("assets", "hsaContribution")
                hsa_contrib_spouse = get_d("assets", "spouseHsaContribution")
                contribution_hsa = hsa_contrib_user + hsa_contrib_spouse
            else:
                # Withdrawals
                fixed_income = social_security_income + pension_income_val
                deficit = max(total_expenses - fixed_income, 0)
                
                if deficit > 0:
                    withdrawal_401k = deficit * 0.4
                    withdrawal_roth_ira = deficit * 0.2
                    withdrawal_brokerage = deficit * 0.4
                
                gross_income = fixed_income + withdrawal_401k + withdrawal_roth_ira + withdrawal_brokerage
                net_income = gross_income * 0.85

            # Apply Growth
            total_401k = (total_401k + contribution_401k - withdrawal_401k) * (1 + portfolio_growth_rate)
            total_roth_ira = (total_roth_ira + contribution_roth_ira - withdrawal_roth_ira) * (1 + portfolio_growth_rate)
            total_brokerage = (total_brokerage + contribution_brokerage - withdrawal_brokerage) * (1 + portfolio_growth_rate)
            total_savings = (total_savings + contribution_savings) * (1 + bond_growth_rate)
            total_hsa = (total_hsa + contribution_hsa - withdrawal_hsa) * (1 + portfolio_growth_rate)
            
            # Mortgage
            current_mortgage_payment = 0.0
            if age < 60 and mortgage_balance > 0:
                 current_mortgage_payment = 28000.0
                 mortgage_balance = max(0, mortgage_balance * 1.05 - current_mortgage_payment)
            
            # Taxes
            taxes_paid = gross_income * 0.25 if is_working_age else gross_income * 0.15
            cumulative_tax += taxes_paid
            
            total_assets = total_401k + total_roth_ira + total_brokerage + total_savings + total_hsa
            total_liabilities = mortgage_balance + credit_card_debt + student_loan_debt + other_debt
            net_worth = total_assets - total_liabilities
            
            # Construct Projection Object
            proj = {
                "year": year,
                "age": age,
                "grossIncome": gross_income,
                "netIncome": net_income,
                "totalExpenses": total_expenses,
                "totalAssets": total_assets,
                "totalLiabilities": total_liabilities,
                "netWorth": net_worth,
                "taxesPaid": taxes_paid,
                "cumulativeTax": cumulative_tax,
                "assets": [
                    {"name": "401(k) / IRA", "type": "retirement", "balance": total_401k, "growth": total_401k * portfolio_growth_rate, "contribution": contribution_401k, "withdrawal": withdrawal_401k},
                    {"name": "Roth IRA", "type": "retirement", "balance": total_roth_ira, "growth": total_roth_ira * portfolio_growth_rate, "contribution": contribution_roth_ira, "withdrawal": withdrawal_roth_ira},
                    {"name": "Brokerage", "type": "investment", "balance": total_brokerage, "growth": total_brokerage * portfolio_growth_rate, "contribution": contribution_brokerage, "withdrawal": withdrawal_brokerage},
                    {"name": "Savings", "type": "cash", "balance": total_savings, "growth": total_savings * bond_growth_rate, "contribution": contribution_savings, "withdrawal": withdrawal_savings},
                    {"name": "HSA", "type": "hsa", "balance": total_hsa, "growth": total_hsa * portfolio_growth_rate, "contribution": contribution_hsa, "withdrawal": withdrawal_hsa},
                ],
                "liabilities": [],
                "income": [],
                "expenses": projected_expenses_list + [{"category": "Taxes", "amount": taxes_paid}]
            }
            
            if mortgage_balance > 0:
                proj["liabilities"].append({"name": "Primary Mortgage", "type": "mortgage", "balance": mortgage_balance, "payment": current_mortgage_payment})
            
            # Populate income list
            if current_income > 0: proj["income"].append({"source": "Salary", "amount": current_income})
            if spouse_current_income > 0: proj["income"].append({"source": "Spouse Salary", "amount": spouse_current_income})
            if social_security_income > 0: proj["income"].append({"source": "Social Security", "amount": social_security_income})
            if pension_income_val > 0: proj["income"].append({"source": "Pension", "amount": pension_income_val})
            
            projections.append(proj)
            
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

