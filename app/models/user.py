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
    # Subscription (Lemon Squeezy)
    subscriptionStatus: str = Field(default="none", sa_column_kwargs={"name": "subscription_status"}) # active, past_due, cancelled, none
    subscriptionId: str | None = Field(default=None, sa_column_kwargs={"name": "subscription_id"})
    customerId: str | None = Field(default=None, sa_column_kwargs={"name": "customer_id"})
    variantId: str | None = Field(default=None, sa_column_kwargs={"name": "variant_id"})
    currentPeriodEnd: datetime | None = Field(default=None, sa_column_kwargs={"name": "current_period_end"})

    role: str = Field(default="user", sa_column_kwargs={"name": "role"}) # user, admin
    
    # OAuth Fields
    googleId: Optional[str] = Field(default=None, sa_column_kwargs={"name": "google_id", "unique": True})
    profilePicture: Optional[str] = Field(default=None, sa_column_kwargs={"name": "profile_picture"})
    
    createdAt: datetime = Field(default_factory=datetime.utcnow, sa_column_kwargs={"name": "created_at"})

    @property
    def has_access(self) -> bool:
        # Admins always have access
        if self.role == "admin":
            return True
            
        # Active or Trialing users have access
        if self.subscriptionStatus in ["active", "on_trial"]:
            return True
            
        # Cancelled users have access until the period ends
        if self.subscriptionStatus == "cancelled" and self.currentPeriodEnd:
            # Check if end date is in the future
            # Ensure timezone awareness matches (using utcnow for safety)
            # currentPeriodEnd is stored as datetime
            # If naive, assume UTC.
            now = datetime.utcnow()
            if self.currentPeriodEnd.replace(tzinfo=None) > now:
                return True
                
        return False

class UserRead(UserBase):
    id: UUID
    role: str
    subscriptionStatus: str = "none"
    subscriptionId: Optional[str] = None
    customerId: Optional[str] = None
    variantId: Optional[str] = None
    currentPeriodEnd: Optional[datetime] = None
    googleId: Optional[str] = None
    profilePicture: Optional[str] = None
    createdAt: datetime
    has_access: bool

    model_config = {
        "from_attributes": True
    }

