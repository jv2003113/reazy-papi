from typing import List, Optional, Any
from uuid import UUID
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from pydantic import BaseModel

from app.api import deps
from app.database import get_db
from app.models.user import User
from app.models.goal import UserGoal
from app.services.goal_calculator import GoalCalculator

router = APIRouter()

# --- Pydantic Schemas ---

class UserGoalCreate(BaseModel):
    title: str
    description: Optional[str] = None
    category: str = "personal"
    icon: str = "Target"
    
    status: str = "in_progress"
    targetValue: Optional[float] = None  
    currentValue: Optional[float] = None # Allow manual setting
    valueType: str = "money"
    
    # Metadata for auto-calculation (optional)
    goalTypeHint: Optional[str] = None # e.g. "EMERGENCY_FUND"

class UserGoalUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    icon: Optional[str] = None
    status: Optional[str] = None
    progress: Optional[int] = None
    targetValue: Optional[float] = None
    currentValue: Optional[float] = None
    valueType: Optional[str] = None

class UserGoalRead(BaseModel):
    id: UUID
    title: str
    description: Optional[str]
    category: str
    icon: str
    status: str
    progress: int
    targetValue: Optional[float]
    currentValue: Optional[float]
    valueType: str
    createdAt: datetime
    updatedAt: datetime

# --- Endpoints ---

@router.get("/user-goals", response_model=List[UserGoalRead])
async def get_user_goals(
    current_user: User = Depends(deps.get_current_user),
    db: AsyncSession = Depends(get_db)
) -> Any:
    """
    Fetch all goals belonging to the current user.
    """
    stmt = select(UserGoal).where(UserGoal.userId == current_user.id)
    result = await db.execute(stmt)
    user_goals = result.scalars().all()
    
    # Dynamic Recalculation logic (Optional/Advanced)
    # Since we dropped the explicit 'type' link, we rely on stored values 
    # OR we could try to infer type from Title if we wanted to keep auto-updating logic.
    # For now, we return the stored values as the User intends to own them.
    
    return [
        UserGoalRead(
            id=g.id,
            title=g.title,
            description=g.description,
            category=g.category,
            icon=g.icon,
            status=g.status,
            progress=g.progress,
            targetValue=g.targetValue,
            currentValue=g.currentValue,
            valueType=g.valueType,
            createdAt=g.createdAt,
            updatedAt=g.updatedAt
        ) for g in user_goals
    ]

@router.post("/user-goals", response_model=UserGoalRead)
async def create_user_goal(
    goal_in: UserGoalCreate,
    current_user: User = Depends(deps.get_current_user),
    db: AsyncSession = Depends(get_db)
) -> Any:
    """
    Create a new goal for the user.
    Supports auto-calculation if `goalTypeHint` is provided.
    """
    
    # Initial Calculation Logic
    # If the frontend passes a hint, we can use the Calculator to preset values
    initial_current = goal_in.currentValue or 0.0
    initial_target = goal_in.targetValue or 0.0
    
    if goal_in.goalTypeHint:
        # Use simple string matching in calculator if we adapt it, 
        # OR just use logic here if Calculator isn't updated yet.
        # Let's try to trust the Calculator if it supports strings.
        try:
             calc = GoalCalculator.calculate_initial_values(current_user, goal_in.goalTypeHint)
             if not initial_current and calc.get("currentValue", 0) > 0:
                 initial_current = calc["currentValue"]
             if not initial_target and calc.get("targetValue", 0) > 0:
                 initial_target = calc["targetValue"]
        except:
            pass # Ignore calculation errors on hints
            
    # Calculate initial progress
    initial_progress = 0
    if initial_target > 0:
        initial_progress = int((initial_current / initial_target) * 100)
        initial_progress = min(100, max(0, initial_progress))
    
    user_goal = UserGoal(
        userId=current_user.id,
        title=goal_in.title,
        description=goal_in.description,
        category=goal_in.category,
        icon=goal_in.icon,
        status=goal_in.status,
        progress=initial_progress,
        currentValue=initial_current,
        targetValue=initial_target,
        valueType=goal_in.valueType
    )
    db.add(user_goal)
    
    # Mark plan as stale
    from app.models.retirement import RetirementPlan
    from sqlmodel import select
    query = select(RetirementPlan).where(RetirementPlan.userId == current_user.id, RetirementPlan.isActive == True)
    result = await db.execute(query)
    plan = result.scalars().first()
    if plan:
        plan.isStale = True
        db.add(plan)
        
    await db.commit()
    await db.refresh(user_goal)
    
    return UserGoalRead(
        id=user_goal.id,
        title=user_goal.title,
        description=user_goal.description,
        category=user_goal.category,
        icon=user_goal.icon,
        status=user_goal.status,
        progress=user_goal.progress,
        targetValue=user_goal.targetValue,
        currentValue=user_goal.currentValue,
        valueType=user_goal.valueType,
        createdAt=user_goal.createdAt,
        updatedAt=user_goal.updatedAt
    )

@router.patch("/user-goals/{goal_id}", response_model=UserGoalRead)
async def update_user_goal(
    goal_id: UUID,
    goal_in: UserGoalUpdate,
    current_user: User = Depends(deps.get_current_user),
    db: AsyncSession = Depends(get_db)
) -> Any:
    user_goal = await db.get(UserGoal, goal_id)
    if not user_goal:
        raise HTTPException(status_code=404, detail="Goal not found")
    if user_goal.userId != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
        
    goal_data = goal_in.dict(exclude_unset=True)
    for key, value in goal_data.items():
        setattr(user_goal, key, value)
        
    # Recalculate progress if values changed
    if goal_in.currentValue is not None or goal_in.targetValue is not None:
         t = user_goal.targetValue or 0
         c = user_goal.currentValue or 0
         if t > 0:
             user_goal.progress = min(100, max(0, int((c / t) * 100)))
             
    db.add(user_goal)
    
    # Mark plan as stale
    from app.models.retirement import RetirementPlan
    from sqlmodel import select
    query = select(RetirementPlan).where(RetirementPlan.userId == current_user.id, RetirementPlan.isActive == True)
    result = await db.execute(query)
    plan = result.scalars().first()
    if plan:
        plan.isStale = True
        db.add(plan)

    await db.commit()
    await db.refresh(user_goal)
    
    return UserGoalRead(
        id=user_goal.id,
        title=user_goal.title,
        description=user_goal.description,
        category=user_goal.category,
        icon=user_goal.icon,
        status=user_goal.status,
        progress=user_goal.progress,
        targetValue=user_goal.targetValue,
        currentValue=user_goal.currentValue,
        valueType=user_goal.valueType,
        createdAt=user_goal.createdAt,
        updatedAt=user_goal.updatedAt
    )

@router.delete("/user-goals/{goal_id}")
async def delete_user_goal(
    goal_id: UUID,
    current_user: User = Depends(deps.get_current_user),
    db: AsyncSession = Depends(get_db)
) -> Any:
    user_goal = await db.get(UserGoal, goal_id)
    if not user_goal:
        raise HTTPException(status_code=404, detail="Goal not found")
    if user_goal.userId != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
        
    await db.delete(user_goal)
    # Mark plan as stale
    from app.models.retirement import RetirementPlan
    from sqlmodel import select
    query = select(RetirementPlan).where(RetirementPlan.userId == current_user.id, RetirementPlan.isActive == True)
    result = await db.execute(query)
    plan = result.scalars().first()
    if plan:
        plan.isStale = True
        db.add(plan)
        
    await db.commit()
    return {"ok": True}
