from typing import Optional, List
from uuid import UUID
from decimal import Decimal
from datetime import datetime
from sqlmodel import SQLModel, Field, Relationship
from uuid6 import uuid7

class RothConversionPlanBase(SQLModel):
    userId: UUID = Field(foreign_key="users.id", sa_column_kwargs={"name": "user_id"})
    planName: str = Field(sa_column_kwargs={"name": "plan_name"})
    currentAge: int = Field(sa_column_kwargs={"name": "current_age"})
    retirementAge: int = Field(sa_column_kwargs={"name": "retirement_age"})
    traditionalIraBalance: Decimal = Field(max_digits=12, decimal_places=2, sa_column_kwargs={"name": "traditional_ira_balance"})
    currentTaxRate: Decimal = Field(max_digits=5, decimal_places=2, sa_column_kwargs={"name": "current_tax_rate"})
    expectedRetirementTaxRate: Decimal = Field(max_digits=5, decimal_places=2, sa_column_kwargs={"name": "expected_retirement_tax_rate"})
    annualIncome: Decimal = Field(max_digits=10, decimal_places=2, sa_column_kwargs={"name": "annual_income"})
    conversionAmount: Decimal = Field(max_digits=12, decimal_places=2, sa_column_kwargs={"name": "conversion_amount"})
    yearsToConvert: int = Field(sa_column_kwargs={"name": "years_to_convert"})
    expectedReturn: Decimal = Field(max_digits=5, decimal_places=2, sa_column_kwargs={"name": "expected_return"})
    isActive: bool = Field(default=True, sa_column_kwargs={"name": "is_active"})
    notes: Optional[str] = None

class RothConversionPlan(RothConversionPlanBase, table=True):
    __tablename__ = "roth_conversion_plans"
    id: UUID = Field(default_factory=uuid7, primary_key=True)
    createdAt: datetime = Field(default_factory=datetime.utcnow, sa_column_kwargs={"name": "created_at"})
    updatedAt: datetime = Field(default_factory=datetime.utcnow, sa_column_kwargs={"name": "updated_at"})

    scenarios: List["RothConversionScenario"] = Relationship(back_populates="plan", sa_relationship_kwargs={"cascade": "all, delete-orphan"})


class RothConversionScenario(SQLModel, table=True):
    __tablename__ = "roth_conversion_scenarios"
    id: UUID = Field(default_factory=uuid7, primary_key=True)
    planId: UUID = Field(foreign_key="roth_conversion_plans.id", sa_column_kwargs={"name": "plan_id"})
    year: int
    age: int
    conversionAmount: Decimal = Field(max_digits=12, decimal_places=2, sa_column_kwargs={"name": "conversion_amount"})
    taxCost: Decimal = Field(max_digits=12, decimal_places=2, sa_column_kwargs={"name": "tax_cost"})
    traditionalBalance: Decimal = Field(max_digits=12, decimal_places=2, sa_column_kwargs={"name": "traditional_balance"})
    rothBalance: Decimal = Field(max_digits=12, decimal_places=2, sa_column_kwargs={"name": "roth_balance"})
    totalTaxPaid: Decimal = Field(max_digits=12, decimal_places=2, sa_column_kwargs={"name": "total_tax_paid"})
    netWorth: Decimal = Field(max_digits=12, decimal_places=2, sa_column_kwargs={"name": "net_worth"})
    createdAt: datetime = Field(default_factory=datetime.utcnow, sa_column_kwargs={"name": "created_at"})

    plan: RothConversionPlan = Relationship(back_populates="scenarios")
