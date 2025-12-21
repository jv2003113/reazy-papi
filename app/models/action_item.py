from datetime import datetime
from typing import Optional
from sqlmodel import SQLModel, Field
import uuid

class UserActionItemBase(SQLModel):
    title: str
    description: Optional[str] = None
    category: str = "general" # e.g. 'financial', 'legal', 'tax'
    status: str = "todo" # 'todo', 'done'
    target_date: Optional[datetime] = None

class UserActionItem(UserActionItemBase, table=True):
    __tablename__ = "user_action_items"
    
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="users.id")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

class UserActionItemCreate(UserActionItemBase):
    pass

class UserActionItemUpdate(SQLModel):
    title: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    status: Optional[str] = None
    target_date: Optional[datetime] = None

class UserActionItemRead(UserActionItemBase):
    id: uuid.UUID
    user_id: uuid.UUID
    created_at: datetime
    updated_at: datetime
