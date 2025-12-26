from typing import Optional
from uuid import UUID
from datetime import datetime
from sqlmodel import SQLModel, Field, Relationship
from uuid6 import uuid7

# Milestone Models

class MilestoneBase(SQLModel):
    # For personal milestones, userId is required. For standard milestones (which is separate table), it's not.
    # But wait, the schema had separate tables `milestones` and `standard_milestones`.
    # Let's keep them separate here too.
    title: str
    description: Optional[str] = None
    targetYear: Optional[int] = Field(sa_column_kwargs={"name": "target_year"})
    targetAge: Optional[int] = Field(sa_column_kwargs={"name": "target_age"})
    category: Optional[str] = None # retirement, healthcare, financial, family, etc.
    icon: Optional[str] = None
    
class UserMilestone(MilestoneBase, table=True):
    __tablename__ = "user_milestones"
    id: UUID = Field(default_factory=uuid7, primary_key=True)
    planId: Optional[UUID] = Field(foreign_key="retirement_plans.id", sa_column_kwargs={"name": "plan_id"})
    userId: Optional[UUID] = Field(foreign_key="users.id", sa_column_kwargs={"name": "user_id"})
    
    milestoneType: str = Field(sa_column_kwargs={"name": "milestone_type"}) # personal, standard
    isCompleted: bool = Field(default=False, sa_column_kwargs={"name": "is_completed"})
    color: str = Field(default="#3b82f6")
    
    createdAt: datetime = Field(default_factory=datetime.utcnow, sa_column_kwargs={"name": "created_at"})


class RefMilestone(SQLModel, table=True):
    __tablename__ = "ref_milestones"
    id: UUID = Field(default_factory=uuid7, primary_key=True)
    title: str
    description: str
    targetAge: float = Field(sa_column_kwargs={"name": "target_age"})
    category: str
    icon: str
    isActive: bool = Field(default=True, sa_column_kwargs={"name": "is_active"})
    sortOrder: int = Field(default=0, sa_column_kwargs={"name": "sort_order"})
    
    createdAt: datetime = Field(default_factory=datetime.utcnow, sa_column_kwargs={"name": "created_at"})
    updatedAt: datetime = Field(default_factory=datetime.utcnow, sa_column_kwargs={"name": "updated_at"})
