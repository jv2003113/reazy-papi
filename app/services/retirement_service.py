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
    AnnualSnapshotAsset, 
    AnnualSnapshotLiability, 
    AnnualSnapshotIncome, 
    AnnualSnapshotExpense,
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

    def calculate_financial_projections(self, plan: RetirementPlan, user: User) -> List[Dict[str, Any]]:
        """
        Core simulation engine. Calculates financial state for every year from startAge to endAge.

        Logic:
        - Iterates through each year/age.
        - Determines if user is in 'Working' or 'Retired' phase based on `plan.retirementAge`.
        - Calculates Income:
            - Working: Salary (inflated).
            - Retired: Social Security + Pension (inflated).
            - Other: Additional income sources.
        - Calculates Expenses:
            - Inflates base expenses year-over-year.
        - Calculates Contributions (Working Phase):
            - 401k/IRA limits applied.
            - Spillover goes to Brokerage/Savings.
            - HSA contributions added.
        - Calculates Withdrawals (Retired Phase):
            - Covers expense deficits from various accounts (401k, Brokerage, etc.).
        - Applies Investment Growth:
            - Compound growth on assets (Portfolio Rate for stocks, Bond Rate for cash).
        - Tracks Net Worth, Assets, Liabilities.

        Args:
            plan (RetirementPlan): Plan assumptions (growth rates, retirement age).
            user (User): Current financial starting point (balances, salaries).

        Returns:
            List[Dict]: A list of dictionary objects representing the financial state for each year.
        """
        projections = []
        current_year = datetime.now().year
        
        inflation_rate = float(plan.inflationRate) / 100
        portfolio_growth_rate = float(plan.portfolioGrowthRate) / 100
        bond_growth_rate = float(plan.bondGrowthRate) / 100
        
        # Initial Balances
        total_401k = float(user.retirementAccount401k or 0) + float(user.retirementAccountIRA or 0)
        total_roth_ira = float(user.retirementAccountRoth or 0)
        total_brokerage = float(user.investmentBalance or 0)
        total_brokerage = float(user.investmentBalance or 0)
        total_savings = float(user.savingsBalance or 0) + float(user.checkingBalance or 0)
        total_hsa = float(user.hsaBalance or 0) + float(user.spouseHsaBalance or 0)
        
        mortgage_balance = float(user.mortgageBalance or 0)
        mortgage_payment_annual = float(user.mortgagePayment or 0) * 12 # User stores monthly? Schema says mortgagePayment is decimal. Usually monthly.
        # Logic in TS said: let mortgagePayment = Number(user.mortgagePayment) || 0; // Monthly
        
        # Debts
        credit_card_debt = float(user.creditCardDebt or 0)
        student_loan_debt = float(user.studentLoanDebt or 0)
        other_debt = float(user.otherDebt or 0)
        
        cumulative_tax = 0.0
        
        # Loop
        for age in range(plan.startAge, plan.endAge + 1):
            year = current_year + (age - plan.startAge)
            years_from_start = age - plan.startAge
            
            is_retired = age >= plan.retirementAge
            is_working_age = not is_retired
            
            # Income
            current_income = 0.0
            spouse_current_income = 0.0
            social_security_income = 0.0
            pension_income = 0.0
            
            if is_working_age:
                user_salary = float(user.currentIncome or 0)
                spouse_salary = float(user.spouseCurrentIncome or 0)
                
                current_income = user_salary * ((1 + inflation_rate) ** years_from_start)
                spouse_current_income = spouse_salary * ((1 + inflation_rate) ** years_from_start)
                
            else:
                # Retirement
                if age >= (plan.socialSecurityStartAge or 67):
                    social_security_income = float(plan.estimatedSocialSecurityBenefit or 0) * ((1 + inflation_rate) ** years_from_start)
                
                pension_income = float(plan.pensionIncome or 0) * ((1 + inflation_rate) ** years_from_start)

            # Other Income
            other_income1 = float(user.otherIncomeAmount1 or 0) * ((1 + inflation_rate) ** years_from_start) if user.otherIncomeAmount1 else 0
            other_income2 = float(user.otherIncomeAmount2 or 0) * ((1 + inflation_rate) ** years_from_start) if user.otherIncomeAmount2 else 0
            
            gross_income = current_income + spouse_current_income + other_income1 + other_income2
            # Note: SS and Pension added to gross later for tax calc? 
            # TS logic: 
            # if isWorkingAge: gross = current + spouse. 
            # else: pension. SS. 
            # Then adds otherIncome to gross. 
            
            if not is_working_age:
                gross_income += social_security_income + pension_income
                
            # Net Income Estimation
            if is_working_age:
                net_income = gross_income * 0.75
            else:
                net_income = gross_income * 0.85

            # Expenses
            base_annual_expenses = 0.0
            detailed_expenses = []
            
            if user.expenses:
                # Handle expenses list
                # In Python user.expenses is List[dict] already due to SQLModel JSON
                for exp in user.expenses:
                     amt = float(exp.get("amount", 0)) * 12
                     base_annual_expenses += amt
                     detailed_expenses.append({
                         "category": exp.get("category", "Uncategorized"), 
                         "amount": amt,
                         "description": exp.get("description", "")
                     })
            
            if base_annual_expenses == 0:
                # Fallback
                 base_annual_expenses = float(user.totalMonthlyExpenses or 0) * 12
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
            contribution_brokerage = 0.0
            contribution_savings = 0.0
            contribution_hsa = 0.0
            
            withdrawal_401k = 0.0
            withdrawal_roth_ira = 0.0
            withdrawal_brokerage = 0.0
            withdrawal_brokerage = 0.0
            withdrawal_savings = 0.0
            withdrawal_hsa = 0.0
            
            if is_working_age:
                # Contributions
                contribution_401k = min(23000, gross_income * 0.15)
                catch_up = 7500 if age >= 50 else 6500
                contribution_roth_ira = catch_up # Logic in TS was catch_up? Check. Yes: age >= 50 ? 7500 : 6500
                
                remaining_income = net_income - total_expenses - contribution_401k - contribution_roth_ira
                contribution_brokerage = max(0, remaining_income * 0.7)
                contribution_savings = max(0, remaining_income * 0.3)
                
                # HSA Contribution (User + Spouse)
                hsa_contrib_user = float(user.hsaContribution or 0)
                hsa_contrib_spouse = float(user.spouseHsaContribution or 0)
                contribution_hsa = hsa_contrib_user + hsa_contrib_spouse
            else:
                # Withdrawals
                fixed_income = social_security_income + pension_income
                deficit = max(total_expenses - fixed_income, 0)
                
                if deficit > 0:
                    withdrawal_401k = deficit * 0.4
                    withdrawal_roth_ira = deficit * 0.2
                    withdrawal_brokerage = deficit * 0.4
                    # Only withdraw from HSA for "Health Expenses" if we had them separated, 
                    # for now assume it acts like a tax-advantaged account we tap last or specifically?
                    # Let's keep it simple: grow it, but don't auto-tap it for general deficit yet unless needed?
                    # Or treat it like Roth?
                    # Let's just grow it for net worth purposes as per request "shown in breakdown".
                
                # Recalculate gross mainly for tax purposes if needed, but TS logic reused grossIncome variable
                # "grossIncome = fixedIncome + withdrawal401k..." 
                # This overrides previous grossIncome calculation which didn't include withdrawals?
                gross_income = fixed_income + withdrawal_401k + withdrawal_roth_ira + withdrawal_brokerage
                net_income = gross_income * 0.85

            # Apply Growth
            total_401k = (total_401k + contribution_401k - withdrawal_401k) * (1 + portfolio_growth_rate)
            total_roth_ira = (total_roth_ira + contribution_roth_ira - withdrawal_roth_ira) * (1 + portfolio_growth_rate)
            total_brokerage = (total_brokerage + contribution_brokerage - withdrawal_brokerage) * (1 + portfolio_growth_rate)
            total_savings = (total_savings + contribution_savings) * (1 + bond_growth_rate)
            total_hsa = (total_hsa + contribution_hsa - withdrawal_hsa) * (1 + portfolio_growth_rate) # Assuming invested HSA
            
            # Mortgage
            current_mortgage_payment = 0.0
            if age < 60 and mortgage_balance > 0:
                 current_mortgage_payment = 28000.0 # TS hardcoded 28000? "mortgagePayment = 28000; // Roughly $2,333/month" 
                 # Wait, TS logic has a hardcoded value overriding user value?? 
                 # "if (age < 60) { mortgagePayment = 28000; ... }"
                 # I should probably respect the user's mortgage payment if available, but for PARITY I will copy logic.
                 # Actually, TS logic: "let mortgagePayment = Number(user.mortgagePayment) || 0;" was initialized at top.
                 # BUT inside loop: "if (age < 60) { mortgagePayment = 28000; ... }" 
                 # This looks like dev testing code left in TS?
                 # Parity requires I do what TS does, but this seems wrong.
                 # I'll stick to 28000 parity for now but maybe flag it.
                 # Actually, let's use the user's payment if > 0, else 28000 default?
                 # No, TS code unconditionally sets it to 28000.
                 current_mortgage_payment = 28000.0
                 mortgage_balance = max(0, mortgage_balance * 1.05 - current_mortgage_payment)
            
            # Taxes
            taxes_paid = gross_income * 0.25 if is_working_age else gross_income * 0.15
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
              # Store Asset Breakdown for this year
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
            if pension_income > 0: proj["income"].append({"source": "Pension", "amount": pension_income})
            
            projections.append(proj)
            
        return projections

    async def create_annual_snapshots(self, plan: RetirementPlan, projections: List[Dict[str, Any]]):
        """
        Persists the calculated projections to the database.

        Creates `AnnualSnapshot` records for each year, and associated child records:
        - `AnnualSnapshotAsset`
        - `AnnualSnapshotLiability`
        - `AnnualSnapshotIncome`
        - `AnnualSnapshotExpense`

        This allows the frontend to query detailed breakdowns for any specific year.
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
                cumulativeTax=Decimal(p["cumulativeTax"])
            )
            self.session.add(snapshot)
            await self.session.flush() # flush to get ID
            
            # Assets
            for a in p["assets"]:
                asset = AnnualSnapshotAsset(
                    snapshotId=snapshot.id,
                    name=a["name"],
                    type=a["type"],
                    balance=Decimal(a["balance"]),
                    growth=Decimal(a["growth"]),
                    contribution=Decimal(a["contribution"]),
                    withdrawal=Decimal(a["withdrawal"])
                )
                self.session.add(asset)
            
            # Liabilities
            for l in p["liabilities"]:
                lib = AnnualSnapshotLiability(
                    snapshotId=snapshot.id,
                    name=l["name"],
                    type=l["type"],
                    balance=Decimal(l["balance"]),
                    payment=Decimal(l["payment"])
                )
                self.session.add(lib)
                
            # Income
            for i in p["income"]:
                inc = AnnualSnapshotIncome(
                    snapshotId=snapshot.id,
                    source=i["source"],
                    amount=Decimal(i["amount"])
                )
                self.session.add(inc)

            # Expenses
            for e in p["expenses"]:
                exp = AnnualSnapshotExpense(
                    snapshotId=snapshot.id,
                    category=e["category"],
                    amount=Decimal(e["amount"])
                )
                self.session.add(exp)

    async def create_standard_milestones(self, plan: RetirementPlan):
        current_year = datetime.now().year
        milestones = [
            {
                "title": "Retirement Begins",
                "targetYear": current_year + (plan.retirementAge - plan.startAge),
                "targetAge": plan.retirementAge,
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

