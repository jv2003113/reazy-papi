from typing import Optional, List
from uuid import UUID
from datetime import datetime
from sqlmodel import SQLModel, Field, Relationship
from uuid6 import uuid7

# Goals Models

class RefGoal(SQLModel, table=True):
    __tablename__ = "ref_goals"
    id: UUID = Field(default_factory=uuid7, primary_key=True)
    title: str
    description: Optional[str] = None
    category: str # "financial", "retirement", "health", etc.
    icon: str # Lucide icon name
    defaultTargetOffset: Optional[int] = Field(default=None, sa_column_kwargs={"name": "default_target_offset"}) # Years from now
    
    isActive: bool = Field(default=True, sa_column_kwargs={"name": "is_active"})
    createdAt: datetime = Field(default_factory=datetime.utcnow, sa_column_kwargs={"name": "created_at"})
    
    # Relationship to user goals not strictly needed for navigation but useful for data integrity if needed
    
    
class UserGoal(SQLModel, table=True):
    __tablename__ = "user_goals"
    id: UUID = Field(default_factory=uuid7, primary_key=True)
    userId: UUID = Field(foreign_key="users.id", sa_column_kwargs={"name": "user_id"})
    refGoalId: Optional[UUID] = Field(foreign_key="ref_goals.id", sa_column_kwargs={"name": "ref_goal_id"})
    
    # Allow custom goals that don't link to a ref goal
    customTitle: Optional[str] = Field(sa_column_kwargs={"name": "custom_title"})
    customDescription: Optional[str] = Field(sa_column_kwargs={"name": "custom_description"})
    customIcon: Optional[str] = Field(sa_column_kwargs={"name": "custom_icon"})
    
    status: str = Field(default="in_progress") # "in_progress", "completed", "abandoned"
    targetDate: Optional[datetime] = Field(sa_column_kwargs={"name": "target_date"})
    progress: int = Field(default=0) # 0-100
    targetAmount: Optional[float] = Field(default=0, sa_column_kwargs={"name": "target_amount"})
    currentAmount: Optional[float] = Field(default=0, sa_column_kwargs={"name": "current_amount"})
    
    createdAt: datetime = Field(default_factory=datetime.utcnow, sa_column_kwargs={"name": "created_at"})
    updatedAt: datetime = Field(default_factory=datetime.utcnow, sa_column_kwargs={"name": "updated_at"})
    
    # Relationships
    refGoal: Optional[RefGoal] = Relationship()
