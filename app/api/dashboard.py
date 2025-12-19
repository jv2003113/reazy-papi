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

router = APIRouter()

class Recommendation(BaseModel):
    id: str
    title: str
    description: str
    category: str
    impact: str
    status: str

class Resource(BaseModel):
    id: str
    title: str
    type: str
    url: str
    description: str

class DashboardData(BaseModel):
    retirementReadiness: dict
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
              
        # Readiness
        readiness_score = 75 
        
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
        else:
             projected_income = float(plan.estimatedSocialSecurityBenefit or 0) / 12
             
    # Prepare Portfolio Breakdown
    # Cash: Savings + Checking
    cash_val = float(current_user.savingsBalance or 0) + float(current_user.checkingBalance or 0)
    real_estate_val = float(current_user.realEstateValue or 0)
    investments_val = float(portfolio_total) - cash_val - real_estate_val
    
    # 60/40 Split for investments as placeholder
    stocks_val = investments_val * 0.6
    bonds_val = investments_val * 0.4
    
    def pct(val, tot):
        return int((val / tot * 100)) if tot > 0 else 0
        
    portfolio_allocation = {
        "total": float(portfolio_total),
        "categories": {
            "stocks": {"percentage": pct(stocks_val, float(portfolio_total)), "value": stocks_val},
            "bonds": {"percentage": pct(bonds_val, float(portfolio_total)), "value": bonds_val},
            "realEstate": {"percentage": pct(real_estate_val, float(portfolio_total)), "value": real_estate_val},
            "cash": {"percentage": pct(cash_val, float(portfolio_total)), "value": cash_val}
        }
    }
    
    # Use target_lookup_age for the response if plan exists
    display_target_age = target_lookup_age if plan else 65
    
    return {
        "retirementReadiness": {
            "score": readiness_score,
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
        "recommendations": [
            {
                "id": "rec_1", 
                "title": "Increase 401(k) Contribution", 
                "description": "You are currently below the annual max.",
                "category": "saving",
                "impact": "high",
                "status": "active"
            }
        ],
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
