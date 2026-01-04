from typing import List, Any, Optional
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
        
    # Field Mapping for Primary Plan -> User Profile
    # Maps plan_key -> (jsonb_column, json_key)
    # If not in this map, it might be a native plan field.
    user_field_map = {
        "retirementAge": ("personal_info", "targetRetirementAge"),
        "inflationRate": ("personal_info", "inflationRateAssumption"), # personal_info seems appropriate for assumptions
        "portfolioGrowthRate": ("risk", "investmentReturnAssumption"),
        "bondGrowthRate": ("risk", "bondGrowthRateAssumption"),
        "desiredAnnualRetirementSpending": ("expenses", "desiredRetirementSpending"),
        "socialSecurityStartAge": ("income", "socialSecurityStartAge"),
        "estimatedSocialSecurityBenefit": ("income", "socialSecurityAmount"),
        "pensionIncome": ("income", "pensionIncome"),
        "majorOneTimeExpenses": ("expenses", "majorOneTimeExpenses"),
        "majorExpensesDescription": ("expenses", "majorExpensesDescription")
    }

    if plan.planType == 'P':
        # Update User Profile for Primary Plan
        user_updated = False
        
        # We need to manually mark JSON fields as modified if we mutate them in place, 
        # or we re-assign the whole dict. Re-assigning is safer.
        # Let's clone current dicts to be safe
        u_personal = dict(current_user.personal_info or {})
        u_risk = dict(current_user.risk or {})
        u_income = dict(current_user.income or {})
        u_expenses = dict(current_user.expenses or {})
        
        # Helper to get the right dict ref
        def get_dict_ref(col):
            if col == "personal_info": return u_personal
            if col == "risk": return u_risk
            if col == "income": return u_income
            if col == "expenses": return u_expenses
            return None

        for key, value in plan_update.items():
            if key in user_field_map:
                col_name, json_key = user_field_map[key]
                d = get_dict_ref(col_name)
                if d is not None:
                    d[json_key] = value
                    user_updated = True
            elif hasattr(plan, key):
                # Allow updating native plan fields like planName, startAge, endAge
                setattr(plan, key, value)
        
        if user_updated:
            current_user.personal_info = u_personal
            current_user.risk = u_risk
            current_user.income = u_income
            current_user.expenses = u_expenses
            db.add(current_user)
            
    else:
        # Update Overrides for Variant Plan
        overrides = dict(plan.planOverrides) if plan.planOverrides else {}
        for key, value in plan_update.items():
            if key in user_field_map or key in ["startAge", "endAge"]:
                # Store input fields in overrides
                overrides[key] = value
            elif hasattr(plan, key):
                setattr(plan, key, value)
        
        plan.planOverrides = overrides

    db.add(plan)
    await db.commit()
    await db.refresh(plan)
    
    # Regenerate Plan
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
    stmt = select(AnnualSnapshot).where(AnnualSnapshot.planId == plan_id).order_by(AnnualSnapshot.year)
    result_s = await db.execute(stmt)
    snapshots = result_s.scalars().all()
    
    # Milestones
    stmt_m = select(UserMilestone).where(UserMilestone.planId == plan_id)
    result_m = await db.execute(stmt_m)
    milestones = result_m.scalars().all()
    
    response = plan.model_dump()
    # Merge overrides into response for UI convenience?
    # UI likely expects "retirementAge" at top level.
    # Service resolver logic handles logic, but UI needs display.
    # We should patch the response to include effective values.
    
    # This is tricky because model_dump() is from SQLModel.
    # I'll let the UI read 'planOverrides' if present, but for Primary it might be empty.
    # Better: Patch the response with resolved values.
    # Patch response with resolved values for UI
    service = RetirementService(db)
    resolved = service._resolve_inputs(plan, current_user)
    
    # UI expects rates as percentages (e.g. "3.0" not 0.03) and values as strings
    ui_resolved = dict(resolved)
    if "inflationRate" in ui_resolved:
        ui_resolved["inflationRate"] = str(round(float(ui_resolved["inflationRate"]) * 100, 2))
    if "portfolioGrowthRate" in ui_resolved:
        ui_resolved["portfolioGrowthRate"] = str(round(float(ui_resolved["portfolioGrowthRate"]) * 100, 2))
    if "bondGrowthRate" in ui_resolved:
        ui_resolved["bondGrowthRate"] = str(round(float(ui_resolved["bondGrowthRate"]) * 100, 2))
        
    response.update(ui_resolved)
    
    response["snapshots"] = [AnnualSnapshotRead.model_validate(s.model_dump()) for s in snapshots]
    response["milestones"] = milestones
    return response

@router.post("/generate")
async def generate_primary_plan(
    request: dict,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(deps.get_current_user),
    db: AsyncSession = Depends(deps.get_db),
):
    # 1. Capture defaults from existing P plan (Legacy support? Or User Profile?)
    # Since we moved to User Profile, we should look there, but if we are "resetting" we might just wipe.
    pass 
    # Logic simplifiction: Just wipe existing P plans and create new one.
    
    result = await db.execute(select(RetirementPlan).where(RetirementPlan.userId == current_user.id, RetirementPlan.planType == 'P'))
    existing_primary_plans = result.scalars().all()

    for p in existing_primary_plans:
        await db.delete(p)
    if existing_primary_plans:
        await db.commit()
    
    # 2. Update User Profile from FormData (if provided)
    form_data = request.get("formData", {})
    
    def safe_decimal(val, default):
        if val == "" or val is None: return Decimal(str(default))
        try: return Decimal(str(val))
        except: return Decimal(str(default))

    # Update User attributes if present in form_data
    # This ensures the Primary Plan (which uses User) gets these values
    # We must update the JSONB columns, not flat fields
    u_personal = dict(current_user.personal_info or {})
    u_risk = dict(current_user.risk or {})
    u_expenses = dict(current_user.expenses or {})

    user_updated = False
    if "expectedAnnualExpenses" in form_data:
        u_expenses["desiredRetirementSpending"] = safe_decimal(form_data["expectedAnnualExpenses"], 80000)
        user_updated = True
    if "portfolioGrowthRate" in form_data:
        u_risk["investmentReturnAssumption"] = safe_decimal(form_data["portfolioGrowthRate"], 7.0)
        user_updated = True
    if "inflationRate" in form_data:
        u_personal["inflationRateAssumption"] = safe_decimal(form_data["inflationRate"], 3.0)
        user_updated = True
    if "targetRetirementAge" in form_data:
         u_personal["targetRetirementAge"] = int(form_data["targetRetirementAge"])
         user_updated = True

    if user_updated:
        current_user.personal_info = u_personal
        current_user.risk = u_risk
        current_user.expenses = u_expenses
        db.add(current_user)
    
    current_age = (current_user.personal_info or {}).get("currentAge") or 30

    plan_data = RetirementPlan(
        userId=current_user.id,
        planName="Primary Retirement Plan",
        planType="P",
        startAge=int(current_age),
        # retirementAge removed
        endAge=95,
        # input columns removed
        isStale=False
    )
    
    db.add(plan_data)
    await db.commit()
    await db.refresh(plan_data)
    
    # 3. Trigger Generation
    service = RetirementService(db)
    await service.generate_retirement_plan(plan_data)
    
    # 4. Background AI Refresh
    # ... (Keep existing AI logic) ...
    try:
        g_res = await db.execute(select(UserGoal.title).where(UserGoal.userId == current_user.id, UserGoal.status == "in_progress"))
        active_goal_titles = g_res.scalars().all()
        a_res = await db.execute(select(UserActionItem.title).where(UserActionItem.user_id == current_user.id, UserActionItem.status == "todo"))
        active_action_titles = a_res.scalars().all()
        background_tasks.add_task(RecommendationEngine.trigger_ai_refresh, current_user, plan_data, active_goal_titles, active_action_titles)
    except Exception as e:
        print(f"Failed to queue AI refresh: {e}")

    await db.commit()
    await db.refresh(plan_data)
    
    # Reload items
    stmt = select(AnnualSnapshot).where(AnnualSnapshot.planId == plan_data.id).order_by(AnnualSnapshot.year)
    result_s = await db.execute(stmt)
    snapshots = result_s.scalars().all()
    
    stmt_m = select(UserMilestone).where(UserMilestone.planId == plan_data.id)
    result_m = await db.execute(stmt_m)
    milestones = result_m.scalars().all()

    response = plan_data.model_dump()
    # Patch response with resolved values for UI
    # Patch response with resolved values for UI
    resolved = service._resolve_inputs(plan_data, current_user)
    
    # UI expects rates as percentages (e.g. "3.0" not 0.03) and values as strings
    ui_resolved = dict(resolved)
    if "inflationRate" in ui_resolved:
        ui_resolved["inflationRate"] = str(round(float(ui_resolved["inflationRate"]) * 100, 2))
    if "portfolioGrowthRate" in ui_resolved:
        ui_resolved["portfolioGrowthRate"] = str(round(float(ui_resolved["portfolioGrowthRate"]) * 100, 2))
    if "bondGrowthRate" in ui_resolved:
        ui_resolved["bondGrowthRate"] = str(round(float(ui_resolved["bondGrowthRate"]) * 100, 2))

    response.update(ui_resolved)
    
    response["snapshots"] = [AnnualSnapshotRead.model_validate(s.model_dump()) for s in snapshots]
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
        
    stmt = select(AnnualSnapshot).where(AnnualSnapshot.planId == plan_id, AnnualSnapshot.year == year)
    result_s = await db.execute(stmt)
    snapshot = result_s.scalars().first()
    
    if not snapshot:
        raise HTTPException(status_code=404, detail=f"Snapshot for year {year} not found")
        
    return AnnualSnapshotRead.model_validate(snapshot.model_dump())

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
        
    # Resolve inputs (User + Overrides)
    service = RetirementService(db)
    inputs = service._resolve_inputs(plan, current_user)

    # Calculate Current Balance (Liquid + Retirement)
    # Helper for safer retrieval
    def get_d(category, key, default=0):
        d = getattr(current_user, category, {}) or {}
        return float(d.get(key) or 0)

    current_balance = (
        get_d("assets", "savingsBalance") + 
        get_d("assets", "checkingBalance") + 
        get_d("assets", "investmentBalance") + 
        get_d("assets", "retirementAccount401k") + 
        get_d("assets", "retirementAccountIRA") + 
        get_d("assets", "retirementAccountRoth")
    )
    
    annual_contribution = 10000.0
    u_income = get_d("income", "currentIncome")
    if u_income > 0:
         annual_contribution = u_income * 0.15
         
    current_age = (current_user.personal_info or {}).get("currentAge") or 30
    retirement_age = inputs["retirementAge"]
    end_age = plan.endAge or 95 # Still on plan
    
    years_to_retirement = retirement_age - current_age
    if years_to_retirement < 0: years_to_retirement = 0
    
    total_years = end_age - current_age
    if total_years < 1: total_years = 1
    
    annual_withdrawal = float(inputs["desiredAnnualRetirementSpending"] or 80000.0)
    
    risk_profile = (current_user.risk or {}).get("riskTolerance") or "moderate"
    
    result = MonteCarloService.run_simulation(
        current_balance=current_balance,
        annual_contribution=annual_contribution,
        years_to_retirement=years_to_retirement,
        total_years=total_years,
        annual_withdrawal=annual_withdrawal,
        risk_profile=risk_profile
    )
    
    return result

@router.post("/{plan_id}/regenerate", response_model=RetirementPlan)
async def regenerate_plan(
    plan_id: UUID,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(deps.get_current_user),
    db: AsyncSession = Depends(deps.get_db),
):
    """
    Regenerate a specific retirement plan (re-run calculations).
    Useful when underlying data (User Profile, Assets) has changed, marking the plan as stale.
    """
    result = await db.execute(select(RetirementPlan).where(RetirementPlan.id == plan_id))
    plan = result.scalars().first()
    if not plan:
        raise HTTPException(status_code=404, detail="Retirement plan not found")
    if plan.userId != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
        
    # Regenerate Calculation
    service = RetirementService(db)
    await service.generate_retirement_plan(plan)
    
    # Mark as clean
    plan.isStale = False
    db.add(plan)
    await db.commit()
    await db.refresh(plan)
    
    # Background AI Refresh
    try:
        g_res = await db.execute(select(UserGoal.title).where(UserGoal.userId == current_user.id, UserGoal.status == "in_progress"))
        active_goal_titles = g_res.scalars().all()
        a_res = await db.execute(select(UserActionItem.title).where(UserActionItem.user_id == current_user.id, UserActionItem.status == "todo"))
        active_action_titles = a_res.scalars().all()
        # Note: RecommendationEngine needs to be imported or available
        background_tasks.add_task(RecommendationEngine.trigger_ai_refresh, current_user, plan, active_goal_titles, active_action_titles)
    except Exception as e:
        print(f"Failed to queue AI refresh: {e}")
        
    return plan
