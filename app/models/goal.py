from typing import Optional, List
from uuid import UUID
from datetime import datetime
from sqlmodel import SQLModel, Field, Relationship
from uuid6 import uuid7

# Goals Models

class UserGoal(SQLModel, table=True):
    __tablename__ = "user_goals"
    id: UUID = Field(default_factory=uuid7, primary_key=True)
    userId: UUID = Field(foreign_key="users.id", sa_column_kwargs={"name": "user_id"})
    
    # Core Fields (Dynamic)
    title: str
    description: Optional[str] = None
    category: str = Field(default="personal") # "financial", "retirement", "health", etc.
    icon: str = Field(default="Target") # Lucide icon name
    
    # Progress & Status
    status: str = Field(default="in_progress") # "in_progress", "completed", "abandoned"
    progress: int = Field(default=0) # 0-100
    targetAmount: Optional[float] = Field(default=0, sa_column_kwargs={"name": "target_amount"})
    currentAmount: Optional[float] = Field(default=0, sa_column_kwargs={"name": "current_amount"})
    
    # Timestamps
    createdAt: datetime = Field(default_factory=datetime.utcnow, sa_column_kwargs={"name": "created_at"})
    updatedAt: datetime = Field(default_factory=datetime.utcnow, sa_column_kwargs={"name": "updated_at"})

