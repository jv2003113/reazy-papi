from typing import Optional, List, Any, Dict
from uuid import UUID
from decimal import Decimal
from sqlmodel import SQLModel, Field, Relationship
from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import JSONB
from uuid6 import uuid7
from datetime import datetime

class UserBase(SQLModel):
    email: str = Field(unique=True, index=True)
    password_hash: Optional[str] = Field(default=None, sa_column_kwargs={"name": "password_hash"}) # Keep legacy/auth fields if any? User model has 'password'.
    
    # JSONB Buckets
    personal_info: Dict[str, Any] = Field(default={}, sa_column=Column(JSONB))
    income: Dict[str, Any] = Field(default={}, sa_column=Column(JSONB))
    expenses: Dict[str, Any] = Field(default={}, sa_column=Column(JSONB))
    assets: Dict[str, Any] = Field(default={}, sa_column=Column(JSONB))
    liabilities: Dict[str, Any] = Field(default={}, sa_column=Column(JSONB))
    risk: Dict[str, Any] = Field(default={}, sa_column=Column(JSONB))

    # Removed flat columns:
    # firstName, lastName, currentAge, targetRetirementAge, currentLocation, maritalStatus, dependents, desiredLifestyle, currency
    # hasSpouse, spouseFirstName, spouseLastName, spouseCurrentAge, spouseTargetRetirementAge, spouseCurrentIncome
    # currentIncome ... all the way down to investmentRebalancingPreference

class UserUpdate(SQLModel):
    # Flexible update model accepting partial JSON updates or specific keys if we want to support legacy API temporarily?
    # No, assuming refactor implies updating the API consumers too.
    email: Optional[str] = None
    
    personal_info: Optional[Dict[str, Any]] = None
    income: Optional[Dict[str, Any]] = None
    expenses: Optional[Dict[str, Any]] = None
    assets: Optional[Dict[str, Any]] = None
    liabilities: Optional[Dict[str, Any]] = None
    risk: Optional[Dict[str, Any]] = None

class User(UserBase, table=True):
    __tablename__ = "users"
    id: UUID = Field(default_factory=uuid7, primary_key=True)
    password: Optional[str] = None # Virtual field for input, not column. Actual column is password_hash in Base.
    
    # Role-Based Access Control
    role: str = Field(default="user", sa_column_kwargs={"name": "role"})
    
    # OAuth Fields
    googleId: Optional[str] = Field(default=None, sa_column_kwargs={"name": "google_id", "unique": True})
    profilePicture: Optional[str] = Field(default=None, sa_column_kwargs={"name": "profile_picture"})
    
    createdAt: datetime = Field(default_factory=datetime.utcnow, sa_column_kwargs={"name": "created_at"})
