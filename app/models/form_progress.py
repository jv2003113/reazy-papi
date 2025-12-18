from typing import Optional, List, Dict, Any
from uuid import UUID
from datetime import datetime
from sqlmodel import SQLModel, Field, Relationship
from sqlalchemy import JSON, Column
from uuid6 import uuid7
from app.models.user import User

class MultiStepFormProgressBase(SQLModel):
    currentStep: int = Field(default=1, sa_column_kwargs={"name": "current_step"})
    completedSteps: List[int] = Field(default=[], sa_column=Column(JSON, name="completed_steps"))
    formData: Dict[str, Any] = Field(default={}, sa_column=Column(JSON, name="form_data"))
    isCompleted: bool = Field(default=False, sa_column_kwargs={"name": "is_completed"})

class MultiStepFormProgress(MultiStepFormProgressBase, table=True):
    __tablename__ = "multi_step_form_progress"
    
    id: UUID = Field(default_factory=uuid7, primary_key=True)
    userId: UUID = Field(foreign_key="users.id", sa_column_kwargs={"name": "user_id"})
    lastUpdated: datetime = Field(default_factory=datetime.utcnow, sa_column_kwargs={"name": "last_updated"})

class MultiStepFormProgressCreate(MultiStepFormProgressBase):
    pass

class MultiStepFormProgressUpdate(MultiStepFormProgressBase):
    pass

class MultiStepFormProgressRead(MultiStepFormProgressBase):
    id: UUID
    userId: UUID
    lastUpdated: datetime
