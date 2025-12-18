from typing import Optional, Any
from uuid import UUID
from datetime import datetime
from sqlmodel import SQLModel, Field, JSON
from sqlalchemy import Column
from uuid6 import uuid7

class Activity(SQLModel, table=True):
    __tablename__ = "activities"
    id: UUID = Field(default_factory=uuid7, primary_key=True)
    userId: UUID = Field(foreign_key="users.id", sa_column_kwargs={"name": "user_id"})
    activityType: str = Field(sa_column_kwargs={"name": "activity_type"})
    title: Optional[str] = None
    description: str
    date: datetime = Field(default_factory=datetime.utcnow)
    activity_metadata: Optional[Any] = Field(default=None, sa_column=Column("metadata", JSON))
