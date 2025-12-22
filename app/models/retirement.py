from typing import Optional, List, Any, Dict
from uuid import UUID
from decimal import Decimal
from datetime import datetime
from sqlmodel import SQLModel, Field, Relationship, JSON
from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import JSONB
from uuid6 import uuid7

# Retirement Plan Models

class RetirementPlanBase(SQLModel):
    userId: UUID = Field(foreign_key="users.id", sa_column_kwargs={"name": "user_id"})
    planName: str = Field(sa_column_kwargs={"name": "plan_name"})
    planType: str = Field(default="comprehensive", sa_column_kwargs={"name": "plan_type"})

    # Age & Timeline
    startAge: int = Field(sa_column_kwargs={"name": "start_age"})
    # retirementAge removed (use overrides)
    endAge: int = Field(default=95, sa_column_kwargs={"name": "end_age"})
    # spouse ages removed (use overrides)

    # Plan Overrides (JSONB)
    # Stores scenario-specific inputs like { "retirementAge": 60, "inflationRate": 4.5 }
    # Primary Plan will have this as None/Null.
    planOverrides: Optional[Dict] = Field(default=None, sa_column=Column(JSONB, name="plan_overrides"))

    # Metadata
    totalLifetimeTax: Decimal = Field(default=0, max_digits=12, decimal_places=2, sa_column_kwargs={"name": "total_lifetime_tax"})
    
    isActive: bool = Field(default=True, sa_column_kwargs={"name": "is_active"})
    isStale: bool = Field(default=False, sa_column_kwargs={"name": "is_stale"})

class RetirementPlan(RetirementPlanBase, table=True):
    __tablename__ = "retirement_plans"
    id: UUID = Field(default_factory=uuid7, primary_key=True)
    createdAt: datetime = Field(default_factory=datetime.utcnow, sa_column_kwargs={"name": "created_at"})
    updatedAt: datetime = Field(default_factory=datetime.utcnow, sa_column_kwargs={"name": "updated_at"})

    # Relationships
    snapshots: List["AnnualSnapshot"] = Relationship(back_populates="plan", sa_relationship_kwargs={"cascade": "all, delete-orphan"})


# Annual Snapshot Models

class AnnualSnapshotBase(SQLModel):
    planId: UUID = Field(foreign_key="retirement_plans.id", sa_column_kwargs={"name": "plan_id"})
    year: int
    age: int
    grossIncome: Decimal = Field(default=0, max_digits=12, decimal_places=2, sa_column_kwargs={"name": "gross_income"})
    netIncome: Decimal = Field(default=0, max_digits=12, decimal_places=2, sa_column_kwargs={"name": "net_income"})
    totalExpenses: Decimal = Field(default=0, max_digits=12, decimal_places=2, sa_column_kwargs={"name": "total_expenses"})
    totalAssets: Decimal = Field(default=0, max_digits=12, decimal_places=2, sa_column_kwargs={"name": "total_assets"})
    totalLiabilities: Decimal = Field(default=0, max_digits=12, decimal_places=2, sa_column_kwargs={"name": "total_liabilities"})
    netWorth: Decimal = Field(default=0, max_digits=12, decimal_places=2, sa_column_kwargs={"name": "net_worth"})
    taxesPaid: Decimal = Field(default=0, max_digits=12, decimal_places=2, sa_column_kwargs={"name": "taxes_paid"})
    cumulativeTax: Decimal = Field(default=0, max_digits=12, decimal_places=2, sa_column_kwargs={"name": "cumulative_tax"})
    
    incomeBreakdown: Optional[Any] = Field(default=None, sa_column=Column(JSONB, name="income_breakdown"))
    expenseBreakdown: Optional[Any] = Field(default=None, sa_column=Column(JSONB, name="expense_breakdown"))
    
    # JSONB Columns for Details
    assets: List[Dict] = Field(default=[], sa_column=Column(JSONB))
    liabilities: List[Dict] = Field(default=[], sa_column=Column(JSONB))
    income: List[Dict] = Field(default=[], sa_column=Column(JSONB))
    expenses: List[Dict] = Field(default=[], sa_column=Column(JSONB))

class AnnualSnapshot(AnnualSnapshotBase, table=True):
    __tablename__ = "annual_snapshots"
    id: UUID = Field(default_factory=uuid7, primary_key=True)
    createdAt: datetime = Field(default_factory=datetime.utcnow, sa_column_kwargs={"name": "created_at"})
    
    # Relationships
    plan: RetirementPlan = Relationship(back_populates="snapshots")
    # relationships to child tables removed

# Snapshot Children Tables Removed


# Read Models for API Responses

class AnnualSnapshotRead(AnnualSnapshotBase):
    id: UUID
    createdAt: datetime
    assets: List[Dict] = []
    liabilities: List[Dict] = []
    income: List[Dict] = []
    expenses: List[Dict] = []

