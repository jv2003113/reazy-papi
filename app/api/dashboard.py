from typing import List, Any
from uuid import UUID
from datetime import datetime
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from pydantic import BaseModel

from app.api import deps
from app.database import get_db
from app.models.user import User
from app.models.retirement import RetirementPlan, AnnualSnapshot
from app.models.goal import UserGoal, RefGoal
from app.services.recommendation_engine import RecommendationEngine

router = APIRouter()

class Recommendation(BaseModel):
    id: str
    title: str
    description: str
    category: str
    impact: str
    status: str
    suggestedRefGoalTitle: str | None = None

class Resource(BaseModel):
    id: str
    title: str
    type: str
    url: str
    description: str

class DashboardData(BaseModel):
    retirementTarget: dict
    monthlyIncome: dict
    savingsRate: dict
    portfolioAllocation: dict
    recommendations: List[Recommendation]
    resources: List[Resource]
    recentActivities: List[dict]

@router.get("/", response_model=DashboardData)
async def get_dashboard(
    current_user: User = Depends(deps.get_current_user),
    db: AsyncSession = Depends(get_db)
) -> Any:
    # Get Primary Plan
    result = await db.execute(select(RetirementPlan).where(RetirementPlan.userId == current_user.id, RetirementPlan.planType == 'P'))
    plan = result.scalars().first()
    
    # Defaults
    readiness_score = 0
    projected_income = 0
    savings_rate_pct = 0
    savings_rate_amt = 0
    
    portfolio_total = (
        (current_user.savingsBalance or 0) + 
        (current_user.checkingBalance or 0) + 
        (current_user.investmentBalance or 0) + 
        (current_user.retirementAccount401k or 0) + 
        (current_user.retirementAccountIRA or 0) + 
        (current_user.retirementAccountRoth or 0) 
    )
    
    if plan:
        # Savings Rate
        monthly_income = (float(current_user.currentIncome or 0) +
        float(current_user.spouseCurrentIncome or 0) +
        float(current_user.otherIncomeAmount1 or 0) +
        float(current_user.otherIncomeAmount2 or 0) 
        ) / 12
        if monthly_income > 0:
            savings_monthly = (
                float(current_user.investmentContribution or 0) + 
                float(current_user.retirementAccount401kContribution or 0) + 
                float(current_user.retirementAccountIRAContribution or 0) + 
                float(current_user.retirementAccountRothContribution or 0)
            ) / 12
            savings_rate_amt = savings_monthly
            savings_rate_pct = int((savings_monthly / monthly_income) * 100)
              
        # Retirement Target & Progress
        retirement_target_amount = 0
        current_amount = float(portfolio_total) # Liquid assets only (excludes real estate)
        progress_pct = 0
        
        # Projected Monthly Income (at retirement - when BOTH are retired if couple)
        # Determine the year (relative to now) when the last person retires
        years_to_primary_ret = plan.retirementAge - plan.startAge
        years_to_spouse_ret = 0
        
        if plan.spouseRetirementAge and plan.spouseStartAge:
             years_to_spouse_ret = plan.spouseRetirementAge - plan.spouseStartAge
             
        years_to_full_retirement = max(years_to_primary_ret, years_to_spouse_ret)
        target_lookup_age = plan.startAge + years_to_full_retirement
        
        stmt = select(AnnualSnapshot).where(AnnualSnapshot.planId == plan.id, AnnualSnapshot.age == target_lookup_age)
        snap_res = await db.execute(stmt)
        snap = snap_res.scalars().first()
        
        if snap:
             projected_income = float(snap.grossIncome) / 12
             # Target Amount Calculation:
             # Reverse engineer based on Expenses should be 4% of target.
             # Target = TotalExpenses / 0.04
             retirement_target_amount = float(snap.totalExpenses) / 0.04
             if retirement_target_amount > 0:
                 progress_pct = int((current_amount / retirement_target_amount) * 100)
        else:
             projected_income = float(plan.estimatedSocialSecurityBenefit or 0) / 12
             
    # Prepare Portfolio Breakdown
    # Cash: Savings + Checking
    cash_val = float(current_user.savingsBalance or 0) + float(current_user.checkingBalance or 0)
    real_estate_val = float(current_user.realEstateValue or 0)
    investments_val = float(portfolio_total) - cash_val # Removed real_estate_val subtraction as portfolio_total doesn't include it
    
    # 60/40 Split for investments as placeholder
    stocks_val = investments_val * 0.6
    bonds_val = investments_val * 0.4
    
    def pct(val, tot):
        return int((val / tot * 100)) if tot > 0 else 0
        
    portfolio_allocation = {
        "total": float(portfolio_total) + real_estate_val, # Add real estate here for total allocation view? Or keep consistent? User said "Progress... do not include house equity". Allocation might want it.
        # Line 117-124 showed breakdown. If I change portfolio_total meaning there, it affects frontend.
        # Previous code: portfolio_allocation["total"] = portfolio_total.
        # And categories included realEstate.
        # But portfolio_total sum at line 55 didn't include realEstate.
        # So pct(real_estate_val, portfolio_total) was likely calculating % of LIQUID assets, which is weird if real_estate > liquid.
        # Or real_estate_val was treated as separate?
        # Line 121: "percentage": pct(real_estate_val, float(portfolio_total)).
        # If portfolio_total = 100k liquid, and House = 500k. Pct = 500%.
        # The previous code was likely buggy or assuming definitions I'm correcting.
        # I'll update portfolio_allocation["total"] to be Liquid + RealEstate for the PIE CHART correctness, 
        # but keep "current_amount" for Progress as Liquid Only.
        "categories": {
            "stocks": {"percentage": pct(stocks_val, float(portfolio_total) + real_estate_val), "value": stocks_val},
            "bonds": {"percentage": pct(bonds_val, float(portfolio_total) + real_estate_val), "value": bonds_val},
            "realEstate": {"percentage": pct(real_estate_val, float(portfolio_total) + real_estate_val), "value": real_estate_val},
            "cash": {"percentage": pct(cash_val, float(portfolio_total) + real_estate_val), "value": cash_val}
        }
    }
    
    # Fix total update
    portfolio_allocation["total"] = float(portfolio_total) + real_estate_val



    # Fetch User Active Goals Titles for filtering recommendations
    goals_stmt = (
        select(RefGoal.title)
        .join(UserGoal, UserGoal.refGoalId == RefGoal.id)
        .where(UserGoal.userId == current_user.id)
    )
    goals_res = await db.execute(goals_stmt)
    active_goal_titles = goals_res.scalars().all()

    # Generate Recommendations
    recommendations = RecommendationEngine.generate_recommendations(
        current_user, 
        plan, 
        portfolio_allocation, 
        active_goal_titles=active_goal_titles
    )

    # Use target_lookup_age for the response if plan exists
    display_target_age = target_lookup_age if plan else 65
    
    return {
        "retirementTarget": {
            "targetAmount": int(retirement_target_amount),
            "currentAmount": int(current_amount),
            "progressPercentage": progress_pct,
            "targetRetirementAge": display_target_age
        },
        "monthlyIncome": {
            "projected": int(projected_income),
            "goal": int(float(current_user.currentIncome or 0) * 0.8 / 12),
            "percentOfCurrent": int(projected_income / (float(current_user.currentIncome or 1)/12) * 100),
            "description": "Projected monthly income at retirement (full)",
            "targetYear": (datetime.now().year + (display_target_age - (current_user.currentAge or 30))) if plan else 2055
        },
        "savingsRate": {
            "percentage": savings_rate_pct,
            "monthlyAmount": int(savings_rate_amt)
        },
        "portfolioAllocation": portfolio_allocation,
        "recommendations": recommendations,
        "resources": [
            {
                "id": "res_1",
                "title": "Retirement 101",
                "type": "article",
                "url": "#",
                "description": "Basics of retirement planning"
            }
        ],
        "recentActivities": []
    }
