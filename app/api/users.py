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
    
    # Mark plan as stale
    from app.models.retirement import RetirementPlan
    # Target ALL active plans (Primary + Variants) as basic data changed
    query = select(RetirementPlan).where(
        RetirementPlan.userId == user_id, 
        RetirementPlan.isActive == True
    )
    result = await db.execute(query)
    plans = result.scalars().all()
    for plan in plans:
        print(f"Marking plan {plan.id} ({plan.planType}) as stale for user {user_id}")
        plan.isStale = True
        db.add(plan)
    
    if not plans:
        print(f"No active plans found for user {user_id} to mark as stale.")
    
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

@router.patch("/{user_id}/multi-step-form-progress", response_model=MultiStepFormProgress)
async def update_multi_step_form_progress(
    user_id: UUID,
    progress_in: MultiStepFormProgress,
    current_user: User = Depends(deps.get_current_user),
    db: AsyncSession = Depends(get_db)
) -> Any:
    # Same logic as POST for now (idempotent upsert logic usually handled by POST in this app context)
    return await save_multi_step_form_progress(user_id, progress_in, current_user, db)
