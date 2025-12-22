from typing import List, Any
from uuid import UUID
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from pydantic import BaseModel

from app.api import deps
from app.models import User, RetirementPlan, AnnualSnapshot, UserMilestone
from app.models.retirement import AnnualSnapshotRead
from app.services.retirement_service import RetirementService
from app.models.goal import UserGoal
from app.models.action_item import UserActionItem
from app.services.recommendation_engine import RecommendationEngine

router = APIRouter()

@router.get("", response_model=List[RetirementPlan])
async def get_retirement_plans(
    current_user: User = Depends(deps.get_current_user),
    db: AsyncSession = Depends(deps.get_db),
):
    """
    List all retirement plans for the authenticated user.
    """
    result = await db.execute(select(RetirementPlan).where(RetirementPlan.userId == current_user.id).order_by(RetirementPlan.createdAt.desc()))
    return result.scalars().all()

@router.post("", response_model=RetirementPlan)
async def create_retirement_plan(
    plan_data: RetirementPlan,
    current_user: User = Depends(deps.get_current_user),
    db: AsyncSession = Depends(deps.get_db),
):
    # Check limit
    existing = await db.execute(select(RetirementPlan).where(RetirementPlan.userId == current_user.id))
    if len(existing.scalars().all()) >= 4:
        raise HTTPException(status_code=400, detail="Maximum of 4 plans allowed per user")

    plan_data.userId = current_user.id
    db.add(plan_data)
    await db.commit()
    await db.refresh(plan_data)
    
    # Generate Logic
    service = RetirementService(db)
    await service.generate_retirement_plan(plan_data)
    
    return plan_data

@router.get("/{plan_id}", response_model=RetirementPlan)
async def get_retirement_plan(
    plan_id: UUID,
    current_user: User = Depends(deps.get_current_user),
    db: AsyncSession = Depends(deps.get_db),
):
    result = await db.execute(select(RetirementPlan).where(RetirementPlan.id == plan_id))
    plan = result.scalars().first()
    if not plan:
        raise HTTPException(status_code=404, detail="Retirement plan not found")
    if plan.userId != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    return plan

@router.patch("/{plan_id}", response_model=RetirementPlan)
async def update_retirement_plan(
    plan_id: UUID,
    plan_update: dict,
    current_user: User = Depends(deps.get_current_user),
    db: AsyncSession = Depends(deps.get_db),
):
    result = await db.execute(select(RetirementPlan).where(RetirementPlan.id == plan_id))
    plan = result.scalars().first()
    if not plan:
        raise HTTPException(status_code=404, detail="Retirement plan not found")
    if plan.userId != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
        
    # Update fields
    for key, value in plan_update.items():
        if hasattr(plan, key):
            setattr(plan, key, value)
            
    db.add(plan)
    await db.commit()
    await db.refresh(plan)
    
    # Regenerate if critical fields changed
    critical_fields = [
        'currentAge', 'retirementAge', 'lifeExpectancy', 'currentIncome', 'startAge', 'endAge', 
        'inflationRate', 'portfolioGrowthRate', 'initialNetWorth'
    ]
    if any(k in plan_update for k in critical_fields):
        service = RetirementService(db)
        await service.generate_retirement_plan(plan)
        
    return plan

@router.delete("/{plan_id}", status_code=204)
async def delete_retirement_plan(
    plan_id: UUID,
    current_user: User = Depends(deps.get_current_user),
    db: AsyncSession = Depends(deps.get_db),
):
    result = await db.execute(select(RetirementPlan).where(RetirementPlan.id == plan_id))
    plan = result.scalars().first()
    if not plan:
        raise HTTPException(status_code=404, detail="Retirement plan not found")
    if plan.userId != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
        
    await db.delete(plan)
    await db.commit()
    return None

@router.get("/{plan_id}/full")
async def get_full_retirement_plan(
    plan_id: UUID,
    current_user: User = Depends(deps.get_current_user),
    db: AsyncSession = Depends(deps.get_db),
):
    # Fetch Plan
    result = await db.execute(select(RetirementPlan).where(RetirementPlan.id == plan_id))
    plan = result.scalars().first()
    if not plan:
        raise HTTPException(status_code=404, detail="Retirement plan not found")
    if plan.userId != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
        
    # Snapshots
    stmt = select(AnnualSnapshot).where(AnnualSnapshot.planId == plan_id).options(
        selectinload(AnnualSnapshot.assets),
        selectinload(AnnualSnapshot.liabilities),
        selectinload(AnnualSnapshot.income),
        selectinload(AnnualSnapshot.expenses)
    ).order_by(AnnualSnapshot.year)
    result_s = await db.execute(stmt)
    snapshots = result_s.scalars().all()
    
    # Milestones
    stmt_m = select(UserMilestone).where(UserMilestone.planId == plan_id)
    result_m = await db.execute(stmt_m)
    milestones = result_m.scalars().all()
    
    response = plan.model_dump()
    response["snapshots"] = [AnnualSnapshotRead.model_validate(s) for s in snapshots]
    response["milestones"] = milestones
    return response

@router.post("/generate")
async def generate_primary_plan(
    request: dict,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(deps.get_current_user),
    db: AsyncSession = Depends(deps.get_db),
):
    # 1. Capture defaults from existing P plan
    result = await db.execute(select(RetirementPlan).where(RetirementPlan.userId == current_user.id, RetirementPlan.planType == 'P'))
    existing_primary_plans = result.scalars().all()
    
    defaults = {
        "desiredAnnualRetirementSpending": 80000.0,
        "portfolioGrowthRate": 7.0,
        "inflationRate": 3.0
    }
    
    if existing_primary_plans:
        last_plan = existing_primary_plans[0]
        defaults["desiredAnnualRetirementSpending"] = float(last_plan.desiredAnnualRetirementSpending or 80000.0)
        defaults["portfolioGrowthRate"] = float(last_plan.portfolioGrowthRate or 7.0)
        defaults["inflationRate"] = float(last_plan.inflationRate or 3.0)

    for p in existing_primary_plans:
        await db.delete(p)
    if existing_primary_plans:
        await db.commit()
        
    # 2. Create new plan
    form_data = request.get("formData", {})
    
    def safe_int(val):
        if val == "" or val is None:
            return 0
        try:
            return int(float(val))
        except (ValueError, TypeError):
            return 0

    def safe_decimal(val, default):
        if val == "" or val is None:
            return Decimal(str(default))
        try:
            return Decimal(str(val))
        except (ValueError, TypeError, Exception):
            return Decimal(str(default))

    # Calculate initial net worth
    def get_val(key, default_attr):
        val = form_data.get(key)
        if val is not None and val != "":
             return val
        return getattr(current_user, default_attr)

    initial_assets = (
        safe_int(get_val("savingsBalance", "savingsBalance")) +
        safe_int(get_val("checkingBalance", "checkingBalance")) +
        safe_int(get_val("investmentBalance", "investmentBalance")) +
        safe_int(get_val("retirementAccount401k", "retirementAccount401k")) +
        safe_int(get_val("retirementAccountIRA", "retirementAccountIRA")) +
        safe_int(get_val("retirementAccountRoth", "retirementAccountRoth"))
    )
    
    plan_data = RetirementPlan(
        userId=current_user.id,
        planName="Primary Retirement Plan",
        planType="P",
        startAge=int(current_user.currentAge or 30),
        retirementAge=int(current_user.targetRetirementAge or 65),
        endAge=95,
        desiredAnnualRetirementSpending=form_data.get("expectedAnnualExpenses", defaults["desiredAnnualRetirementSpending"]),
        initialNetWorth=initial_assets,
        portfolioGrowthRate=safe_decimal(form_data.get("portfolioGrowthRate"), defaults["portfolioGrowthRate"]),
        inflationRate=safe_decimal(form_data.get("inflationRate"), defaults["inflationRate"]),
        isStale=False
    )
    
    db.add(plan_data)
    
    # 3. Trigger Generation
    service = RetirementService(db)
    await service.generate_retirement_plan(plan_data)
    
    # 4. Background AI Refresh
    try:
        g_res = await db.execute(select(UserGoal.title).where(UserGoal.userId == current_user.id, UserGoal.status == "in_progress"))
        active_goal_titles = g_res.scalars().all()
        
        a_res = await db.execute(select(UserActionItem.title).where(UserActionItem.user_id == current_user.id, UserActionItem.status == "todo"))
        active_action_titles = a_res.scalars().all()
        
        background_tasks.add_task(
            RecommendationEngine.trigger_ai_refresh,
            current_user,
            plan_data,
            active_goal_titles,
            active_action_titles
        )
    except Exception as e:
        print(f"Failed to queue AI refresh: {e}")

    await db.commit()
    await db.refresh(plan_data)
    
    # Reload snapshots and milestones for full response
    stmt = select(AnnualSnapshot).where(AnnualSnapshot.planId == plan_data.id).options(
        selectinload(AnnualSnapshot.assets),
        selectinload(AnnualSnapshot.liabilities),
        selectinload(AnnualSnapshot.income),
        selectinload(AnnualSnapshot.expenses)
    ).order_by(AnnualSnapshot.year)
    result_s = await db.execute(stmt)
    snapshots = result_s.scalars().all()
    
    stmt_m = select(UserMilestone).where(UserMilestone.planId == plan_data.id)
    result_m = await db.execute(stmt_m)
    milestones = result_m.scalars().all()

    response = plan_data.model_dump()
    response["snapshots"] = [AnnualSnapshotRead.model_validate(s) for s in snapshots]
    response["milestones"] = milestones
    response["message"] = "Primary plan generated"
    return response

@router.get("/{plan_id}/year/{year}", response_model=AnnualSnapshotRead)
async def get_retirement_plan_snapshot(
    plan_id: UUID,
    year: int,
    current_user: User = Depends(deps.get_current_user),
    db: AsyncSession = Depends(deps.get_db),
):
    result = await db.execute(select(RetirementPlan).where(RetirementPlan.id == plan_id))
    plan = result.scalars().first()
    if not plan:
        raise HTTPException(status_code=404, detail="Retirement plan not found")
    if plan.userId != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
        
    stmt = select(AnnualSnapshot).where(AnnualSnapshot.planId == plan_id, AnnualSnapshot.year == year).options(
        selectinload(AnnualSnapshot.assets),
        selectinload(AnnualSnapshot.liabilities),
        selectinload(AnnualSnapshot.income),
        selectinload(AnnualSnapshot.expenses)
    )
    result_s = await db.execute(stmt)
    snapshot = result_s.scalars().first()
    
    if not snapshot:
        raise HTTPException(status_code=404, detail=f"Snapshot for year {year} not found")
        
    return snapshot

from app.services.monte_carlo import MonteCarloService, SimulationResult

@router.get("/{plan_id}/monte-carlo", response_model=SimulationResult)
async def get_monte_carlo_simulation(
    plan_id: UUID,
    current_user: User = Depends(deps.get_current_user),
    db: AsyncSession = Depends(deps.get_db),
):
    result = await db.execute(select(RetirementPlan).where(RetirementPlan.id == plan_id))
    plan = result.scalars().first()
    if not plan:
        raise HTTPException(status_code=404, detail="Retirement plan not found")
    if plan.userId != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
        
    current_balance = float(plan.initialNetWorth or 0)
    
    annual_contribution = 10000.0
    if hasattr(plan, 'monthlyContribution') and plan.monthlyContribution:
         annual_contribution = float(plan.monthlyContribution) * 12
    elif current_user.currentIncome:
         annual_contribution = float(current_user.currentIncome) * 0.15
         
    current_age = current_user.currentAge or 30
    retirement_age = plan.retirementAge or 65
    end_age = plan.endAge or 95
    
    years_to_retirement = retirement_age - current_age
    if years_to_retirement < 0: years_to_retirement = 0
    
    total_years = end_age - current_age
    if total_years < 1: total_years = 1
    
    annual_withdrawal = float(plan.desiredAnnualRetirementSpending or 80000.0)
    
    risk_profile = current_user.riskTolerance or "moderate"
    
    result = MonteCarloService.run_simulation(
        current_balance=current_balance,
        annual_contribution=annual_contribution,
        years_to_retirement=years_to_retirement,
        total_years=total_years,
        annual_withdrawal=annual_withdrawal,
        risk_profile=risk_profile
    )
    
    return result
