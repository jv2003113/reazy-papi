from typing import Optional, List, Any
from uuid import UUID
from decimal import Decimal
from datetime import datetime
from sqlmodel import SQLModel, Field, Relationship, JSON
from sqlalchemy import Column
from uuid6 import uuid7

# Retirement Plan Models

class RetirementPlanBase(SQLModel):
    userId: UUID = Field(foreign_key="users.id", sa_column_kwargs={"name": "user_id"})
    planName: str = Field(sa_column_kwargs={"name": "plan_name"})
    planType: str = Field(default="comprehensive", sa_column_kwargs={"name": "plan_type"})

    # Age & Timeline
    startAge: int = Field(sa_column_kwargs={"name": "start_age"})
    retirementAge: int = Field(sa_column_kwargs={"name": "retirement_age"})
    endAge: int = Field(default=95, sa_column_kwargs={"name": "end_age"})
    spouseStartAge: Optional[int] = Field(sa_column_kwargs={"name": "spouse_start_age"})
    spouseRetirementAge: Optional[int] = Field(sa_column_kwargs={"name": "spouse_retirement_age"})
    spouseEndAge: Optional[int] = Field(sa_column_kwargs={"name": "spouse_end_age"})

    # Social Security
    socialSecurityStartAge: Optional[int] = Field(default=67, sa_column_kwargs={"name": "social_security_start_age"})
    spouseSocialSecurityStartAge: Optional[int] = Field(sa_column_kwargs={"name": "spouse_social_security_start_age"})
    estimatedSocialSecurityBenefit: Decimal = Field(default=0, max_digits=10, decimal_places=2, sa_column_kwargs={"name": "estimated_social_security_benefit"})
    spouseEstimatedSocialSecurityBenefit: Decimal = Field(default=0, max_digits=10, decimal_places=2, sa_column_kwargs={"name": "spouse_estimated_social_security_benefit"})

    # Economic Assumptions
    portfolioGrowthRate: Decimal = Field(default=7.0, max_digits=5, decimal_places=2, sa_column_kwargs={"name": "portfolio_growth_rate"})
    inflationRate: Decimal = Field(default=3.0, max_digits=5, decimal_places=2, sa_column_kwargs={"name": "inflation_rate"})


    # Retirement Income Sources
    pensionIncome: Decimal = Field(default=0, max_digits=10, decimal_places=2, sa_column_kwargs={"name": "pension_income"})
    spousePensionIncome: Decimal = Field(default=0, max_digits=10, decimal_places=2, sa_column_kwargs={"name": "spouse_pension_income"})
    otherRetirementIncome: Decimal = Field(default=0, max_digits=10, decimal_places=2, sa_column_kwargs={"name": "other_retirement_income"})

    # Retirement Spending
    desiredAnnualRetirementSpending: Decimal = Field(default=80000, max_digits=10, decimal_places=2, sa_column_kwargs={"name": "desired_annual_retirement_spending"})
    majorOneTimeExpenses: Decimal = Field(default=0, max_digits=12, decimal_places=2, sa_column_kwargs={"name": "major_one_time_expenses"})
    majorExpensesDescription: Optional[str] = Field(sa_column_kwargs={"name": "major_expenses_description"})

    # Legacy / Metadata
    bondGrowthRate: Decimal = Field(default=4.0, max_digits=5, decimal_places=2, sa_column_kwargs={"name": "bond_growth_rate"})
    initialNetWorth: Decimal = Field(default=0, max_digits=12, decimal_places=2, sa_column_kwargs={"name": "initial_net_worth"})
    totalLifetimeTax: Decimal = Field(default=0, max_digits=12, decimal_places=2, sa_column_kwargs={"name": "total_lifetime_tax"})
    
    isActive: bool = Field(default=True, sa_column_kwargs={"name": "is_active"})

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
    
    incomeBreakdown: Optional[Any] = Field(default=None, sa_column=Column(JSON, name="income_breakdown"))
    expenseBreakdown: Optional[Any] = Field(default=None, sa_column=Column(JSON, name="expense_breakdown"))

class AnnualSnapshot(AnnualSnapshotBase, table=True):
    __tablename__ = "annual_snapshots"
    id: UUID = Field(default_factory=uuid7, primary_key=True)
    createdAt: datetime = Field(default_factory=datetime.utcnow, sa_column_kwargs={"name": "created_at"})
    
    # Relationships
    plan: RetirementPlan = Relationship(back_populates="snapshots")
    assets: List["AnnualSnapshotAsset"] = Relationship(back_populates="snapshot", sa_relationship_kwargs={"cascade": "all, delete-orphan"})
    liabilities: List["AnnualSnapshotLiability"] = Relationship(back_populates="snapshot", sa_relationship_kwargs={"cascade": "all, delete-orphan"})
    income: List["AnnualSnapshotIncome"] = Relationship(back_populates="snapshot", sa_relationship_kwargs={"cascade": "all, delete-orphan"})
    expenses: List["AnnualSnapshotExpense"] = Relationship(back_populates="snapshot", sa_relationship_kwargs={"cascade": "all, delete-orphan"})

# Snapshot Children

class AnnualSnapshotAsset(SQLModel, table=True):
    __tablename__ = "annual_snapshots_assets"
    id: UUID = Field(default_factory=uuid7, primary_key=True)
    snapshotId: UUID = Field(foreign_key="annual_snapshots.id", sa_column_kwargs={"name": "snapshot_id"})
    name: str
    type: str # 401k, savings, brokerage, etc.
    balance: Decimal = Field(default=0, max_digits=12, decimal_places=2)
    growth: Decimal = Field(default=0, max_digits=10, decimal_places=2)
    contribution: Decimal = Field(default=0, max_digits=10, decimal_places=2)
    withdrawal: Decimal = Field(default=0, max_digits=10, decimal_places=2)
    
    snapshot: AnnualSnapshot = Relationship(back_populates="assets")

class AnnualSnapshotLiability(SQLModel, table=True):
    __tablename__ = "annual_snapshots_liabilities"
    id: UUID = Field(default_factory=uuid7, primary_key=True)
    snapshotId: UUID = Field(foreign_key="annual_snapshots.id", sa_column_kwargs={"name": "snapshot_id"})
    name: str
    type: str
    balance: Decimal = Field(default=0, max_digits=12, decimal_places=2)
    payment: Decimal = Field(default=0, max_digits=10, decimal_places=2)

    snapshot: AnnualSnapshot = Relationship(back_populates="liabilities")

class AnnualSnapshotIncome(SQLModel, table=True):
    __tablename__ = "annual_snapshots_income"
    id: UUID = Field(default_factory=uuid7, primary_key=True)
    snapshotId: UUID = Field(foreign_key="annual_snapshots.id", sa_column_kwargs={"name": "snapshot_id"})
    source: str
    amount: Decimal = Field(default=0, max_digits=12, decimal_places=2)

    snapshot: AnnualSnapshot = Relationship(back_populates="income")

class AnnualSnapshotExpense(SQLModel, table=True):
    __tablename__ = "annual_snapshots_expenses"
    id: UUID = Field(default_factory=uuid7, primary_key=True)
    snapshotId: UUID = Field(foreign_key="annual_snapshots.id", sa_column_kwargs={"name": "snapshot_id"})
    category: str
    amount: Decimal = Field(default=0, max_digits=12, decimal_places=2)

    snapshot: AnnualSnapshot = Relationship(back_populates="expenses")


# Read Models for API Responses

class AnnualSnapshotRead(AnnualSnapshotBase):
    id: UUID
    createdAt: datetime
    assets: List[AnnualSnapshotAsset] = []
    liabilities: List[AnnualSnapshotLiability] = []
    income: List[AnnualSnapshotIncome] = []
    expenses: List[AnnualSnapshotExpense] = []

