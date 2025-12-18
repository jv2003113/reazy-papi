from typing import Any, Optional
from uuid import UUID
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.api import deps
from app.database import get_db
from app.models.user import User, UserBase, UserUpdate
from app.models.form_progress import MultiStepFormProgress

router = APIRouter()

@router.get("/{user_id}", response_model=User)
async def get_user(
    user_id: UUID,
    current_user: User = Depends(deps.get_current_user),
    db: AsyncSession = Depends(get_db)
) -> Any:
    # Allow user to access only their own data
    if current_user.id != user_id:
        raise HTTPException(status_code=403, detail="Not authorized")
    return current_user

@router.patch("/{user_id}", response_model=User)
async def update_user(
    user_id: UUID,
    user_in: UserUpdate,
    current_user: User = Depends(deps.get_current_user),
    db: AsyncSession = Depends(get_db)
) -> Any:
    if current_user.id != user_id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    user_data = user_in.model_dump(exclude_unset=True)
    for key, value in user_data.items():
        setattr(current_user, key, value)
    
    db.add(current_user)
    await db.commit()
    await db.refresh(current_user)
    return current_user

# Multi-Step Form Progress

@router.get("/{user_id}/multi-step-form-progress", response_model=Optional[MultiStepFormProgress])
async def get_multi_step_form_progress(
    user_id: UUID,
    current_user: User = Depends(deps.get_current_user),
    db: AsyncSession = Depends(get_db)
) -> Any:
    if current_user.id != user_id:
        raise HTTPException(status_code=403, detail="Not authorized")
        
    query = select(MultiStepFormProgress).where(MultiStepFormProgress.userId == user_id)
    result = await db.execute(query)
    return result.scalars().first()

@router.post("/{user_id}/multi-step-form-progress", response_model=MultiStepFormProgress)
async def save_multi_step_form_progress(
    user_id: UUID,
    progress_in: MultiStepFormProgress, # Using model as schemas for simplicity now
    current_user: User = Depends(deps.get_current_user),
    db: AsyncSession = Depends(get_db)
) -> Any:
    if current_user.id != user_id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # Check if exists
    query = select(MultiStepFormProgress).where(MultiStepFormProgress.userId == user_id)
    result = await db.execute(query)
    existing = result.scalars().first()
    
    if existing:
        progress_data = progress_in.model_dump(exclude_unset=True)
        # Exclude ID and userId to prevent overwrite if passed
        progress_data.pop("id", None)
        progress_data.pop("userId", None)
        
        for key, value in progress_data.items():
            setattr(existing, key, value)
        
        # Always update lastUpdated
        from datetime import datetime
        existing.lastUpdated = datetime.utcnow()
        
        db.add(existing)
        await db.commit()
        await db.refresh(existing)
        return existing
    else:
        # Create new
        progress_in.userId = user_id
        db.add(progress_in)
        await db.commit()
        await db.refresh(progress_in)
        return progress_in

    # Same logic as POST for now (idempotent upsert logic usually handled by POST in this app context)
    return await save_multi_step_form_progress(user_id, progress_in, current_user, db)

# Dashboard

from pydantic import BaseModel
from typing import List
from app.models.retirement import RetirementPlan, AnnualSnapshot

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

class Activity(BaseModel): # Simple version
    id: str
    userId: UUID
    type: str
    description: str
    createdAt: Any

class DashboardData(BaseModel):
    retirementReadiness: dict
    monthlyIncome: dict
    savingsRate: dict
    portfolioAllocation: dict
    recommendations: List[Recommendation]
    resources: List[Resource]
    recentActivities: List[dict] # Use dict to avoid strict Activity validation

@router.get("/{user_id}/dashboard", response_model=DashboardData)
async def get_user_dashboard(
    user_id: UUID,
    current_user: User = Depends(deps.get_current_user),
    db: AsyncSession = Depends(get_db)
) -> Any:
    if current_user.id != user_id:
        raise HTTPException(status_code=403, detail="Not authorized")
        
    # Get Primary Plan
    result = await db.execute(select(RetirementPlan).where(RetirementPlan.userId == user_id, RetirementPlan.planType == 'P'))
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
        (current_user.retirementAccountRoth or 0) +
        (current_user.realEstateValue or 0)
    )
    
    if plan:
        # Get latest snapshot or near retirement?
        # Usually readiness is based on End of Plan success or current trajectory.
        # For simple metrics, we'll just placeholder logic or use user inputs.
        
        # Savings Rate
        monthly_income = float(current_user.currentIncome or 0) / 12
        if monthly_income > 0:
            savings_monthly = (
                float(current_user.investmentContribution or 0) + 
                float(current_user.retirementAccount401kContribution or 0) + 
                float(current_user.retirementAccountIRAContribution or 0) + 
                float(current_user.retirementAccountRothContribution or 0)
            )
            # Add savings?
            savings_rate_amt = savings_monthly
            savings_rate_pct = int((savings_monthly / monthly_income) * 100)
            
        # Readiness
        # Placeholder: If plan exists, assume 75% ready
        readiness_score = 75 
        
        # Projected Monthly Income (at retirement)
        # Using plan.pensionIncome + plan.estimatedSocialSecurityBenefit ?
        # Or from snapshot at retirement age?
        # Let's fetch snapshot at retirement age
        stmt = select(AnnualSnapshot).where(AnnualSnapshot.planId == plan.id, AnnualSnapshot.age == plan.retirementAge)
        snap_res = await db.execute(stmt)
        snap = snap_res.scalars().first()
        if snap:
             # Gross income at retirement
             projected_income = float(snap.grossIncome) / 12
        else:
             # Fallback
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
    
    return {
        "retirementReadiness": {
            "score": readiness_score,
            "targetRetirementAge": plan.retirementAge if plan else 65
        },
        "monthlyIncome": {
            "projected": int(projected_income),
            "goal": int(float(current_user.currentIncome or 0) * 0.8 / 12), # 80% replacement rule
            "percentOfCurrent": int(projected_income / (float(current_user.currentIncome or 1)/12) * 100),
            "description": "Projected monthly income at retirement",
            "targetYear": (datetime.now().year + (plan.retirementAge - (current_user.currentAge or 30))) if plan else 2055
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
