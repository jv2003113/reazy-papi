from typing import List, Any
from app.api import deps
from fastapi import APIRouter, Depends
from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.user import User
from app.models.milestone import RefMilestone

router = APIRouter()

@router.get("/standard", response_model=List[RefMilestone])
async def get_standard_milestones(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user)
) -> Any:
    statement = select(RefMilestone).where(RefMilestone.isActive == True).order_by(RefMilestone.sortOrder)
    results = await db.execute(statement)
    return results.scalars().all()
