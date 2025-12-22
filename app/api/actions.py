import uuid
from typing import Any
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from app.api import deps
from app.database import get_db
from app.models.user import User
from app.models.action_item import UserActionItem, UserActionItemCreate, UserActionItemUpdate, UserActionItemRead

router = APIRouter()

@router.get("", response_model=List[UserActionItemRead])
async def get_user_actions(
    current_user: User = Depends(deps.get_current_user),
    session: AsyncSession = Depends(get_db),
    status: str | None = None
) -> Any:
    """
    Get current user's action items.
    Optional 'status' query param to filter by 'todo' or 'done'.
    """
    query = select(UserActionItem).where(UserActionItem.user_id == current_user.id)
    if status:
        query = query.where(UserActionItem.status == status)
    
    # Sort by created_at desc
    query = query.order_by(UserActionItem.created_at.desc())
    
    result = await session.execute(query)
    return result.scalars().all()

@router.post("", response_model=UserActionItemRead)
async def create_user_action(
    action_in: UserActionItemCreate,
    current_user: User = Depends(deps.get_current_user),
    session: AsyncSession = Depends(get_db)
) -> Any:
    """
    Create a new action item.
    """
    action_data = action_in.model_dump()
    action = UserActionItem(**action_data, user_id=current_user.id)
    session.add(action)



    await session.commit()
    await session.refresh(action)
    return action

@router.patch("/{action_id}", response_model=UserActionItemRead)
async def update_user_action(
    action_id: uuid.UUID,
    action_in: UserActionItemUpdate,
    current_user: User = Depends(deps.get_current_user),
    session: AsyncSession = Depends(get_db)
) -> Any:
    """
    Update an action item.
    """
    result = await session.execute(
        select(UserActionItem).where(
            UserActionItem.id == action_id,
            UserActionItem.user_id == current_user.id
        )
    )
    action = result.scalar_one_or_none()
    
    if not action:
        raise HTTPException(status_code=404, detail="Action item not found")
        
    update_data = action_in.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(action, key, value)
        
    session.add(action)
    


    await session.commit()
    await session.refresh(action)
    return action

@router.delete("/{action_id}", response_model=dict)
async def delete_user_action(
    action_id: uuid.UUID,
    current_user: User = Depends(deps.get_current_user),
    session: AsyncSession = Depends(get_db)
) -> Any:
    """
    Delete an action item.
    """
    result = await session.execute(
        select(UserActionItem).where(
            UserActionItem.id == action_id,
            UserActionItem.user_id == current_user.id
        )
    )
    action = result.scalar_one_or_none()
    
    if not action:
        raise HTTPException(status_code=404, detail="Action item not found")
        
    await session.delete(action)
    


    await session.commit()
    return {"message": "Action item deleted successfully"}
