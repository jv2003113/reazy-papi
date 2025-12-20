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
from app.models.goal import RefGoal, UserGoal, GoalType
from app.services.goal_calculator import GoalCalculator

router = APIRouter()

class RefGoalRead(BaseModel):
    id: UUID
    title: str
    description: Optional[str]
    category: str
    icon: str
    defaultTargetOffset: Optional[int]

class UserGoalCreate(BaseModel):
    refGoalId: Optional[UUID] = None
    customTitle: Optional[str] = None
    customDescription: Optional[str] = None
    customIcon: Optional[str] = None
    targetDate: Optional[datetime] = None
    status: str = "in_progress"
    targetAmount: Optional[float] = None  # Added targetAmount

class UserGoalUpdate(BaseModel):
    status: Optional[str] = None
    progress: Optional[int] = None
    targetDate: Optional[datetime] = None

class UserGoalRead(BaseModel):
    id: UUID
    title: str
    description: Optional[str]
    icon: str
    category: Optional[str]
    status: str
    progress: int
    targetDate: Optional[datetime]
    refGoalId: Optional[UUID]
    targetAmount: Optional[float]
    currentAmount: Optional[float]

# --- Endpoints ---

@router.get("/ref-goals", response_model=List[RefGoalRead])
async def get_ref_goals(
    db: AsyncSession = Depends(get_db)
) -> Any:
    """
    Fetch the list of standard 'Reference Goals' available to all users.
    
    Examples: 'Emergency Fund', 'Max 401(k)', 'Pay Off Debt'.
    If the table is empty, this endpoint seeds it with default values.
    """
    stmt = select(RefGoal).where(RefGoal.isActive == True)
    result = await db.execute(stmt)
    goals = result.scalars().all()
    
    # Auto-seed if empty (Simple approach for development)
    if not goals:
        defaults = [
            RefGoal(title="Emergency Fund", description="Save 3-6 months of expenses", category="risk", icon="ShieldCheck", defaultTargetOffset=1, type=GoalType.EMERGENCY_FUND),
            RefGoal(title="Max 401(k)", description="Contribute the maximum annual amount to your 401(k)", category="retirement", icon="Briefcase", defaultTargetOffset=1, type=GoalType.RETIREMENT_401K),
            RefGoal(title="Pay Off Debt", description="Eliminate high-interest consumer debt", category="financial", icon="CreditCard", defaultTargetOffset=3, type=GoalType.DEBT_PAYOFF),
            RefGoal(title="Pay off Mortgage", description="Pay off remaining mortgage balance", category="lifestyle", icon="Home", defaultTargetOffset=5, type=GoalType.MORTGAGE_PAYOFF),
            RefGoal(title="Health Savings", description="Fund your HSA for medical expenses", category="health", icon="HeartPulse", defaultTargetOffset=1, type=GoalType.HEALTH_SAVINGS),
            RefGoal(title="Additional Income", description="Establish sources of additional income", category="investing", icon="TrendingUp", defaultTargetOffset=10, type=GoalType.ADDITIONAL_INCOME),
        ]
        for g in defaults:
            db.add(g)
        await db.commit()
        
        # Re-fetch
        result = await db.execute(stmt)
        goals = result.scalars().all()
        
    return goals

@router.get("/user-goals", response_model=List[UserGoalRead])
async def get_user_goals(
    current_user: User = Depends(deps.get_current_user),
    db: AsyncSession = Depends(get_db)
) -> Any:
    """
    Fetch all goals belonging to the current user.
    
    Key Logic:
    - This endpoint returns DYNAMIC data. 
    - It calls `GoalCalculator.calculate_current_progress` for each goal to ensure 
      the `currentAmount` reflects the user's latest financial data (e.g. real-time savings balance).
    """
    # Fetch user goals with RefGoal relationship eagerly if possible, or join
    # SQLModel relationships are async, easier to join manually or assume strict fetching.
    # We'll use a join for efficiency or just fetch. 
    # Let's simple select.
    stmt = select(UserGoal, RefGoal).outerjoin(RefGoal).where(UserGoal.userId == current_user.id)
    result = await db.execute(stmt)
    rows = result.all()
    
    output = []
    for user_goal, ref_goal in rows:
        # Dynamic Recalculation (Display Only)
        if ref_goal:
             # Use ref_goal.type if available, else fallback to parsing title for backward compatibility or simple default
             goal_type = ref_goal.type if ref_goal.type else GoalType.CUSTOM
             new_current = GoalCalculator.calculate_current_progress(current_user, user_goal.targetAmount or 0, goal_type)
             user_goal.currentAmount = new_current
             if (user_goal.targetAmount or 0) > 0:
                  progress_val = int((new_current / user_goal.targetAmount) * 100)
                  user_goal.progress = max(0, min(100, progress_val))

        # Determine display fields (prefer user custom, fallback to ref)
        title = user_goal.customTitle or (ref_goal.title if ref_goal else "Custom Goal")
        desc = user_goal.customDescription or (ref_goal.description if ref_goal else "")
        icon = user_goal.customIcon or (ref_goal.icon if ref_goal else "Target")
        cat = ref_goal.category if ref_goal else "personal"
        
        output.append(UserGoalRead(
            id=user_goal.id,
            title=title,
            description=desc,
            icon=icon,
            category=cat,
            status=user_goal.status,
            progress=user_goal.progress,
            targetDate=user_goal.targetDate,
            refGoalId=user_goal.refGoalId,
            targetAmount=user_goal.targetAmount,
            currentAmount=user_goal.currentAmount
        ))
        
    return output

from app.services.goal_calculator import GoalCalculator

# ...

@router.post("/user-goals", response_model=UserGoalRead)
async def create_user_goal(
    goal_in: UserGoalCreate,
    current_user: User = Depends(deps.get_current_user),
    db: AsyncSession = Depends(get_db)
) -> Any:
    """
    Create a new goal for the user.
    
    If `refGoalId` is provided (Standard Goal), it uses `GoalCalculator` to:
    - Determine a smart default `targetAmount` (e.g. 6 months expenses or IRS limit).
    - Determine the initial `currentAmount`.
    """
    # 1. Calculate Initial Values if RefGoal is present
    initial_current = 0.0
    initial_target = 0.0
    initial_progress = 0
    
    if goal_in.refGoalId:
        ref_goal = await db.get(RefGoal, goal_in.refGoalId)
        if ref_goal:
            calc = GoalCalculator.calculate_initial_values(current_user, ref_goal.type)
            initial_current = calc["currentAmount"]
            # Prefer user-supplied target over calculated default
            initial_target = goal_in.targetAmount if goal_in.targetAmount is not None else calc["targetAmount"]
            if initial_target > 0:
                initial_progress = int((initial_current / initial_target) * 100)
                if initial_progress > 100:
                    initial_progress = 100

    user_goal = UserGoal(
        userId=current_user.id,
        refGoalId=goal_in.refGoalId,
        customTitle=goal_in.customTitle,
        customDescription=goal_in.customDescription,
        customIcon=goal_in.customIcon,
        status=goal_in.status,
        targetDate=goal_in.targetDate,
        progress=initial_progress,
        currentAmount=initial_current,
        targetAmount=initial_target
    )
    db.add(user_goal)
    await db.commit()
    await db.refresh(user_goal)
    
    # Fetch ref goal if needed for response
    ref_goal = None
    if user_goal.refGoalId:
        ref_goal = await db.get(RefGoal, user_goal.refGoalId)
        
    title = user_goal.customTitle or (ref_goal.title if ref_goal else "Custom Goal")
    desc = user_goal.customDescription or (ref_goal.description if ref_goal else "")
    icon = user_goal.customIcon or (ref_goal.icon if ref_goal else "Target")
    cat = ref_goal.category if ref_goal else "personal"
    
    return UserGoalRead(
        id=user_goal.id,
        title=title,
        description=desc,
        icon=icon,
        category=cat,
        status=user_goal.status,
        progress=user_goal.progress,
        targetDate=user_goal.targetDate,
        refGoalId=user_goal.refGoalId,
        currentAmount=user_goal.currentAmount,
        targetAmount=user_goal.targetAmount
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
        
    if goal_in.status is not None:
        user_goal.status = goal_in.status
    if goal_in.progress is not None:
        user_goal.progress = goal_in.progress
    if goal_in.targetDate is not None:
        user_goal.targetDate = goal_in.targetDate
        
    db.add(user_goal)
    await db.commit()
    await db.refresh(user_goal)
    
    ref_goal = None
    if user_goal.refGoalId:
        ref_goal = await db.get(RefGoal, user_goal.refGoalId)
        
    title = user_goal.customTitle or (ref_goal.title if ref_goal else "Custom Goal")
    desc = user_goal.customDescription or (ref_goal.description if ref_goal else "")
    icon = user_goal.customIcon or (ref_goal.icon if ref_goal else "Target")
    cat = ref_goal.category if ref_goal else "personal"
    
    return UserGoalRead(
        id=user_goal.id,
        title=title,
        description=desc,
        icon=icon,
        category=cat,
        status=user_goal.status,
        progress=user_goal.progress,
        targetDate=user_goal.targetDate,
        refGoalId=user_goal.refGoalId,
        currentAmount=user_goal.currentAmount,
        targetAmount=user_goal.targetAmount
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
    await db.commit()
    return {"ok": True}
