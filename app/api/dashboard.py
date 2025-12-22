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
from app.models.goal import UserGoal
from app.services.recommendation_engine import RecommendationEngine
from app.services.retirement_service import RetirementService

router = APIRouter()

class Recommendation(BaseModel):
    id: str
    title: str
    description: str
    category: str
    impact: str
    status: str
    actionType: str # "GOAL" or "ACTION"
    data: dict | None = None # For goals: {currentAmount, targetAmount, goalType}. For actions: {categoryId, etc}

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
    isStale: bool = False

@router.get("", response_model=DashboardData)
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
    
    # Helpers
    def get_asset(k): return float((current_user.assets or {}).get(k) or 0)
    def get_inc(k): return float((current_user.income or {}).get(k) or 0)
    def get_lia(k): return float((current_user.liabilities or {}).get(k) or 0)
    def get_pers(k): return (current_user.personal_info or {}).get(k)
    
    portfolio_total = (
        get_asset("savingsBalance") + 
        get_asset("checkingBalance") + 
        get_asset("investmentBalance") + 
        get_asset("retirementAccount401k") + 
        get_asset("retirementAccountIRA") + 
        get_asset("retirementAccountRoth")
    )
    
    # Retirement Target & Progress Defaults
    retirement_target_amount = 0
    current_amount = float(portfolio_total) # Liquid assets only
    progress_pct = 0

    if plan:
        # Savings Rate
        monthly_income = (get_inc("currentIncome") +
        get_inc("spouseCurrentIncome") +
        get_inc("otherIncomeAmount1") +
        get_inc("otherIncomeAmount2") 
        ) / 12
        if monthly_income > 0:
            savings_monthly = (
                get_asset("investmentContribution") + 
                get_asset("retirementAccount401kContribution") + 
                get_asset("retirementAccountIRAContribution") + 
                get_asset("retirementAccountRothContribution")
            ) / 12
            savings_rate_amt = savings_monthly
            savings_rate_pct = int((savings_monthly / monthly_income) * 100)
              
        # Retirement Target & Progress
        retirement_target_amount = 0
        current_amount = float(portfolio_total) # Liquid assets only (excludes real estate)
        progress_pct = 0
        
    import app.services.retirement_service as rs_lib # local import to avoid circular? 
    # Actually services shouldn't import API but API imports services. 
    # But dashboard.py is API. So it is safe to import RetirementService.
    
    if plan:
        # Resolve inputs
        inputs = RetirementService._resolve_inputs(plan, current_user)
        
        # Projected Monthly Income (at retirement - when BOTH are retired if couple)
        # Determine the year (relative to now) when the last person retires
        years_to_primary_ret = (inputs.get("retirementAge") or 65) - plan.startAge
        years_to_spouse_ret = 0
        
        # Calculate Spouse Timeline using User Profile
        spouse_age = float((current_user.personal_info or {}).get("spouseCurrentAge") or 0)
        spouse_ret_age = float((current_user.personal_info or {}).get("spouseTargetRetirementAge") or 65)
        
        if spouse_age > 0:
             # If we have a spouse, we approximate their timeline relative to the plan start
             # Plan Start Age is based on User. 
             # We need to know when spouse retires relative to user.
             # Years to spouse retire = Spouse Ret Age - Spouse Current Age.
             years_to_spouse_ret = spouse_ret_age - spouse_age
             
        years_to_full_retirement = max(years_to_primary_ret, years_to_spouse_ret)
        target_lookup_age = plan.startAge + int(years_to_full_retirement)
        
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
             projected_income = float(inputs.get("estimatedSocialSecurityBenefit", 0) or 0) / 12
             
    # Prepare Portfolio Breakdown
    # Cash: Savings + Checking
    cash_val = get_asset("savingsBalance") + get_asset("checkingBalance")
    real_estate_val = get_asset("realEstateValue")
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
    # Simple select of user goal titles
    goals_stmt = (
        select(UserGoal.title)
        .where(UserGoal.userId == current_user.id)
    )
    goals_res = await db.execute(goals_stmt)
    active_goal_titles = goals_res.scalars().all()

    # Fetch User Active Action Titles
    from app.models.action_item import UserActionItem
    actions_stmt = (
        select(UserActionItem.title)
        .where(UserActionItem.user_id == current_user.id)
        # We might want to filter by status='todo' or just existence depending on "if user deletes it comes back" logic.
        # User said: "bring it back if the user deletes the goal".
        # This implies existence check regardless of status, OR if status is DONE it might still be considered "handled".
        # But if they delete the action item, it's gone from DB.
        # So we just check existence in the table.
    )
    actions_res = await db.execute(actions_stmt)
    active_action_titles = actions_res.scalars().all()

    # Generate Recommendations
    recommendations = RecommendationEngine.generate_recommendations(
        current_user, 
        plan, 
        portfolio_allocation, 
        active_goal_titles=active_goal_titles,
        active_action_titles=active_action_titles
    )

    # Use target_lookup_age for the response if plan exists
    display_target_age = target_lookup_age if plan else 65
    
    return {
        "retirementTarget": {
            "targetValue": int(retirement_target_amount),
            "currentValue": int(current_amount),
            "progressPercentage": progress_pct,
            "targetRetirementAge": display_target_age
        },
        "monthlyIncome": {
            "projected": int(projected_income),
            "goal": int(get_inc("currentIncome") * 0.8 / 12),
            "percentOfCurrent": int(projected_income / (get_inc("currentIncome") or 1)/12 * 100),
            "description": "Projected monthly income at retirement (full)",
            "targetYear": (datetime.now().year + (display_target_age - (get_pers("currentAge") or 30))) if plan else 2055
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
        "recentActivities": [],
        "isStale": plan.isStale if plan else False
    }
