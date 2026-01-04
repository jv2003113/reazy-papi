from typing import List, Any
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import select, func, col, desc
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from datetime import datetime

from app.api import deps
from app.models.user import User
from app.models.retirement import RetirementPlan, AnnualSnapshot
from app.models.goal import UserGoal
from app.models.form_progress import MultiStepFormProgress
from uuid import UUID

router = APIRouter()

class AdminStats(BaseModel):
    totalUsers: int
    activePlans: int
    totalAssetsTracked: float

class UserSummary(BaseModel):
    id: str
    email: str
    role: str
    createdAt: datetime
    planCount: int
    isActive: bool

class AdminUsersResponse(BaseModel):
    users: List[UserSummary]
    total: int

async def get_current_admin_user(
    current_user: User = Depends(deps.get_current_user),
) -> User:
    if current_user.role != 'admin':
        raise HTTPException(status_code=403, detail="The user doesn't have enough privileges")
    return current_user

@router.get("/stats", response_model=AdminStats)
async def get_admin_stats(
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(deps.get_db),
) -> Any:
    """
    Get system-wide statistics for the admin dashboard.
    """
    # Total Users
    user_count = await db.scalar(select(func.count(User.id))) or 0
    
    # Active Plans (Total plans created)
    plan_count = await db.scalar(select(func.count(RetirementPlan.id))) or 0
    
    # Total Assets Tracked (Sum of all reported assets from Users who have structured asset data)
    # This is complex because assets is JSONB. 
    # For now, we might skip precise calculation or approximate it if SQLModel JSON capabilities are limited.
    # Alternatively, we can count something simpler like "Users with Plans".
    # Let's try to sum primary plan assets if available in snapshots, OR just count data.
    # For MVP, let's just return a placeholder or 0 for complex aggregate.
    # Wait, we can sum 'totalAssets' from the LATEST snapshot of each Primary plan?
    # Or just count 'users with assets configured'.
    
    total_assets = 0 # Placeholder for complex JSONB aggregation
    
    return {
        "totalUsers": user_count,
        "activePlans": plan_count,
        "totalAssetsTracked": total_assets
    }

@router.get("/users", response_model=AdminUsersResponse)
async def get_users_list(
    skip: int = 0,
    limit: int = 20,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(deps.get_db),
) -> Any:
    """
    Get list of users with summary stats.
    """
    # Fetch Users
    stmt = select(User).offset(skip).limit(limit).order_by(desc(User.createdAt))
    result = await db.execute(stmt)
    users = result.scalars().all()
    
    # Get total count for pagination
    total = await db.scalar(select(func.count(User.id))) or 0
    
    user_summaries = []
    
    for user in users:
        # Get Plan Count for this user
        p_stmt = select(func.count(RetirementPlan.id)).where(RetirementPlan.userId == user.id)
        p_count = await db.scalar(p_stmt) or 0
        
        user_summaries.append({
            "id": str(user.id),
            "email": user.email,
            "role": user.role,
            "createdAt": user.createdAt,
            "planCount": p_count,
            "isActive": True # Placeholder, could be based on last login
        })
        
    return {
        "users": user_summaries,
        "total": total
    }

@router.delete("/users/{user_id}", response_model=UserSummary)
async def delete_user(
    user_id: str,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(deps.get_db),
) -> Any:
    """
    Delete a user and all their associated data (Plans, Goals, Progress).
    """
    # Check if user exists
    user_uuid = UUID(user_id)
    stmt = select(User).where(User.id == user_uuid)
    result = await db.execute(stmt)
    user = result.scalars().first()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")
        
    # Cascade Delete Manual (just in case)
    
    # 1. MultiStepFormProgress
    await db.execute(select(MultiStepFormProgress).where(MultiStepFormProgress.userId == user_uuid))
    # Actually execute delete
    from sqlalchemy import delete
    await db.execute(delete(MultiStepFormProgress).where(MultiStepFormProgress.userId == user_uuid))
    
    # 2. Retirement Plans (Snapshots cascade from Plan)
    # Must manually delete snapshots first as bulk delete bypasses ORM cascade and DB might lack ON DELETE CASCADE
    plan_ids_result = await db.execute(select(RetirementPlan.id).where(RetirementPlan.userId == user_uuid))
    plan_ids = plan_ids_result.scalars().all()
    
    if plan_ids:
        await db.execute(delete(AnnualSnapshot).where(AnnualSnapshot.planId.in_(plan_ids)))

    await db.execute(delete(RetirementPlan).where(RetirementPlan.userId == user_uuid))
    
    # 3. User Goals
    await db.execute(delete(UserGoal).where(UserGoal.userId == user_uuid))
    
    # 4. The User
    await db.delete(user)
    
    await db.commit()
    
    return {
        "id": str(user.id),
        "email": user.email,
        "role": user.role,
        "createdAt": user.createdAt,
        "planCount": 0,
        "isActive": False
    }
