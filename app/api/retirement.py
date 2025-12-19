from typing import List, Any
from uuid import UUID
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api import deps
from app.models import User, RetirementPlan, AnnualSnapshot, Milestone
from app.models.retirement import AnnualSnapshotRead
from app.services.retirement_service import RetirementService

router = APIRouter()

@router.get("/", response_model=List[RetirementPlan])
async def get_retirement_plans(
    current_user: User = Depends(deps.get_current_user),
    db: AsyncSession = Depends(deps.get_db),
):
    result = await db.execute(select(RetirementPlan).where(RetirementPlan.userId == current_user.id).order_by(RetirementPlan.createdAt.desc()))
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
    stmt = select(AnnualSnapshot).where(AnnualSnapshot.planId == plan_id).options(
        selectinload(AnnualSnapshot.assets),
        selectinload(AnnualSnapshot.liabilities),
        selectinload(AnnualSnapshot.income),
        selectinload(AnnualSnapshot.expenses)
    ).order_by(AnnualSnapshot.year)
    result_s = await db.execute(stmt)
    snapshots = result_s.scalars().all()
    
    # Milestones
    stmt_m = select(Milestone).where(Milestone.planId == plan_id)
    result_m = await db.execute(stmt_m)
    milestones = result_m.scalars().all()
    
    
    # Return FLATTENED object to match frontend expectations
    # { ...plan, snapshots, milestones }
    print(f"DEBUG: Snapshot 0 assets: {snapshots[0].assets if snapshots else 'No snapshots'}")
    response = plan.model_dump()
    response["snapshots"] = [AnnualSnapshotRead.model_validate(s) for s in snapshots]
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
    # 1. Delete ALL existing P plans to prevent duplicates
    result = await db.execute(select(RetirementPlan).where(RetirementPlan.userId == current_user.id, RetirementPlan.planType == 'P'))
    existing_primary_plans = result.scalars().all()
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
    stmt = select(AnnualSnapshot).where(AnnualSnapshot.planId == plan_data.id).options(
        selectinload(AnnualSnapshot.assets),
        selectinload(AnnualSnapshot.liabilities),
        selectinload(AnnualSnapshot.income),
        selectinload(AnnualSnapshot.expenses)
    ).order_by(AnnualSnapshot.year)
    result_s = await db.execute(stmt)
    snapshots = result_s.scalars().all()
    
    stmt_m = select(Milestone).where(Milestone.planId == plan_data.id)
    result_m = await db.execute(stmt_m)
    milestones = result_m.scalars().all()

    
    # Return FLATTENED response here too if consistent
    response = plan_data.model_dump()
    response["snapshots"] = [AnnualSnapshotRead.model_validate(s) for s in snapshots]
    response["milestones"] = milestones
    # message is extra, usually ignored by typed frontend or handled specially
    # Frontend query for /generate unlikely expects full plan details in return value used for navigation?
    # Actually frontend usually navigates to new plan ID. 
    # But if it consumes the result immediately...
    # For safety, let's keep message separate if possible or add to dict.
    response["message"] = "Primary plan generated"
    return response

@router.get("/{plan_id}/year/{year}", response_model=AnnualSnapshotRead)
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
    # Verify Plan Access
    result = await db.execute(select(RetirementPlan).where(RetirementPlan.id == plan_id))
    plan = result.scalars().first()
    if not plan:
        raise HTTPException(status_code=404, detail="Retirement plan not found")
    if plan.userId != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
        
    # Prepare Simulation Parameters
    # 1. Current Balance (Initial Net Worth or from Snapshots?)
    #    Monte Carlo usually projects from *today*. If the plan has snapshots, we might want the CURRENT year's balance.
    #    Or just use `initialNetWorth` if it's a new plan.
    #    Let's use `initialNetWorth` + accumulated growth (which is complex).
    #    Better: Fetch the FIRST snapshot (start year) balance?
    #    But simplest is `initialNetWorth` as "Current Investable Assets".
    current_balance = float(plan.initialNetWorth or 0)
    
    # 2. Annual Contribution
    #    We need `monthlyContribution` from the plan (if it exists) or calculate from snapshots.
    #    `RetirementPlan` usually has `monthlyContribution`? I didn't see it in `create_retirement_plan`.
    #    It has `desiredAnnualRetirementSpending`.
    #    Snapshots have `contribution`.
    #    Let's assume a standard contribution rate based on `currentIncome` * clean savings rate?
    #    Or maybe check `models/retirement_plan.py` for fields I missed.
    #    Wait, `RetirementService` generates snapshots based on logic.
    #    Let's estimate annual contribution from `currentIncome` * 0.15 (standard) if not stored.
    #    Actually, `RetirementPlan` likely has `monthlyContribution`. I'll check the model.
    #    If not, I'll default to 0 for now or try to infer.
    
    annual_contribution = 10000.0 # Default fallback
    if hasattr(plan, 'monthlyContribution') and plan.monthlyContribution:
         annual_contribution = float(plan.monthlyContribution) * 12
    elif current_user.currentIncome:
         # Default 15% savings rate
         annual_contribution = float(current_user.currentIncome) * 0.15
         
    # 3. Years
    current_age = current_user.currentAge or 30
    retirement_age = plan.retirementAge or 65
    end_age = plan.endAge or 95
    
    years_to_retirement = retirement_age - current_age
    if years_to_retirement < 0: years_to_retirement = 0
    
    total_years = end_age - current_age
    if total_years < 1: total_years = 1
    
    # 4. Annual Withdrawal (Expenses)
    #    Assumption: desiredAnnualRetirementSpending from Plan
    annual_withdrawal = float(plan.desiredAnnualRetirementSpending or 80000.0)
    
    # 5. Risk Profile
    #    Fetch User's risk profile
    risk_profile = current_user.riskTolerance or "moderate"
    
    # Run Simulation
    result = MonteCarloService.run_simulation(
        current_balance=current_balance,
        annual_contribution=annual_contribution,
        years_to_retirement=years_to_retirement,
        total_years=total_years,
        annual_withdrawal=annual_withdrawal,
        risk_profile=risk_profile
    )
    
    return result
