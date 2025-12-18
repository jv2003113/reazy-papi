from typing import List, Any
from uuid import UUID
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.models import User, RetirementPlan, AnnualSnapshot, Milestone
from app.services.retirement_service import RetirementService

router = APIRouter()

@router.get("/", response_model=List[RetirementPlan])
async def get_retirement_plans(
    current_user: User = Depends(deps.get_current_user),
    db: AsyncSession = Depends(deps.get_db),
):
    result = await db.execute(select(RetirementPlan).where(RetirementPlan.userId == current_user.id))
    return result.scalars().all()

@router.post("/", response_model=RetirementPlan)
async def create_retirement_plan(
    plan_data: RetirementPlan, # Accepts full model or base? Input usually doesn't have ID.
    # But SQLModel table=True models have ID optional.
    # Ideally should use a Create schema. For now reuse model.
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
    plan_update: dict, # Using dict to allow partial updates broadly or define a specific Pydantic model
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

from pydantic import BaseModel

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
    stmt = select(AnnualSnapshot).where(AnnualSnapshot.planId == plan_id).order_by(AnnualSnapshot.year)
    result_s = await db.execute(stmt)
    snapshots = result_s.scalars().all()
    
    # Milestones
    stmt_m = select(Milestone).where(Milestone.planId == plan_id)
    result_m = await db.execute(stmt_m)
    milestones = result_m.scalars().all()
    
    
    # Return FLATTENED object to match frontend expectations
    # { ...plan, snapshots, milestones }
    response = plan.model_dump()
    response["snapshots"] = snapshots
    response["milestones"] = milestones
    return response

@router.post("/generate")
async def generate_primary_plan(
    request: dict, # Expects { formData: ... }
    current_user: User = Depends(deps.get_current_user),
    db: AsyncSession = Depends(deps.get_db),
):
    # Logic to create/replace primary plan
    # 1. Delete existing P plan
    result = await db.execute(select(RetirementPlan).where(RetirementPlan.userId == current_user.id, RetirementPlan.planType == 'P'))
    existing_primary = result.scalars().first()
    if existing_primary:
        await db.delete(existing_primary)
        await db.commit()
        
    # 2. Create new plan
    form_data = request.get("formData", {})
    
    def safe_int(val):
        if val == "" or val is None:
            return 0
        try:
            return int(float(val)) # Handle "100.00" or "100"
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
    initial_assets = (
        safe_int(form_data.get("savingsBalance")) +
        safe_int(form_data.get("checkingBalance")) +
        safe_int(form_data.get("investmentBalance")) +
        safe_int(form_data.get("retirementAccount401k")) +
        safe_int(form_data.get("retirementAccountIRA")) +
        safe_int(form_data.get("retirementAccountRoth"))
    )
    
    plan_data = RetirementPlan(
        userId=current_user.id,
        planName="Primary Retirement Plan",
        planType="P",
        startAge=int(current_user.currentAge or 30),
        retirementAge=int(current_user.targetRetirementAge or 65),
        endAge=95,
        desiredAnnualRetirementSpending=form_data.get("expectedAnnualExpenses", 80000),
        initialNetWorth=initial_assets,
        portfolioGrowthRate=safe_decimal(form_data.get("portfolioGrowthRate"), 7.0),
        inflationRate=safe_decimal(form_data.get("inflationRate"), 3.0),
        # Ensure other fields are defaults
    )
    
    db.add(plan_data)
    await db.commit()
    await db.refresh(plan_data)
    
    service = RetirementService(db)
    await service.generate_retirement_plan(plan_data)
    
    # Reload snapshots and milestones for full response
    stmt = select(AnnualSnapshot).where(AnnualSnapshot.planId == plan_data.id).order_by(AnnualSnapshot.year)
    result_s = await db.execute(stmt)
    snapshots = result_s.scalars().all()
    
    stmt_m = select(Milestone).where(Milestone.planId == plan_data.id)
    result_m = await db.execute(stmt_m)
    milestones = result_m.scalars().all()

    
    # Return FLATTENED response here too if consistent
    response = plan_data.model_dump()
    response["snapshots"] = snapshots
    response["milestones"] = milestones
    # message is extra, usually ignored by typed frontend or handled specially
    # Frontend query for /generate unlikely expects full plan details in return value used for navigation?
    # Actually frontend usually navigates to new plan ID. 
    # But if it consumes the result immediately...
    # For safety, let's keep message separate if possible or add to dict.
    response["message"] = "Primary plan generated"
    return response

@router.get("/{plan_id}/year/{year}")
async def get_retirement_plan_snapshot(
    plan_id: UUID,
    year: int,
    current_user: User = Depends(deps.get_current_user),
    db: AsyncSession = Depends(deps.get_db),
):
    # Verify Plan Access
    result = await db.execute(select(RetirementPlan).where(RetirementPlan.id == plan_id))
    plan = result.scalars().first()
    if not plan:
        raise HTTPException(status_code=404, detail="Retirement plan not found")
    if plan.userId != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
        
    # Fetch Snapshot
    stmt = select(AnnualSnapshot).where(AnnualSnapshot.planId == plan_id, AnnualSnapshot.year == year)
    result_s = await db.execute(stmt)
    snapshot = result_s.scalars().first()
    
    if not snapshot:
        raise HTTPException(status_code=404, detail=f"Snapshot for year {year} not found")
        
    return snapshot
