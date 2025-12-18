from typing import Optional, List
from uuid import UUID
from decimal import Decimal
from datetime import datetime
from sqlmodel import SQLModel, Field, Relationship
from uuid6 import uuid7

class InvestmentAccountBase(SQLModel):
    userId: UUID = Field(foreign_key="users.id", sa_column_kwargs={"name": "user_id"})
    accountName: str = Field(sa_column_kwargs={"name": "account_name"})
    accountType: str = Field(sa_column_kwargs={"name": "account_type"}) # 401k, IRA, brokerage, etc.
    balance: Decimal = Field(max_digits=12, decimal_places=2)
    contributionAmount: Optional[Decimal] = Field(default=None, max_digits=10, decimal_places=2, sa_column_kwargs={"name": "contribution_amount"})
    contributionFrequency: Optional[str] = Field(sa_column_kwargs={"name": "contribution_frequency"})
    annualReturn: Optional[Decimal] = Field(default=None, max_digits=5, decimal_places=2, sa_column_kwargs={"name": "annual_return"})
    fees: Optional[Decimal] = Field(default=None, max_digits=5, decimal_places=2)
    isRetirementAccount: bool = Field(default=True, sa_column_kwargs={"name": "is_retirement_account"})
    accountOwner: str = Field(default="primary", sa_column_kwargs={"name": "account_owner"})

class InvestmentAccount(InvestmentAccountBase, table=True):
    __tablename__ = "investment_accounts"
    id: UUID = Field(default_factory=uuid7, primary_key=True)
    createdAt: datetime = Field(default_factory=datetime.utcnow, sa_column_kwargs={"name": "created_at"})
    updatedAt: datetime = Field(default_factory=datetime.utcnow, sa_column_kwargs={"name": "updated_at"})
    
    # Relationships
    allocations: List["AssetAllocation"] = Relationship(back_populates="account", sa_relationship_kwargs={"cascade": "all, delete-orphan"})
    holdings: List["SecurityHolding"] = Relationship(back_populates="account", sa_relationship_kwargs={"cascade": "all, delete-orphan"})

class AssetAllocation(SQLModel, table=True):
    __tablename__ = "asset_allocations"
    id: UUID = Field(default_factory=uuid7, primary_key=True)
    accountId: UUID = Field(foreign_key="investment_accounts.id", sa_column_kwargs={"name": "account_id"})
    assetCategory: str = Field(sa_column_kwargs={"name": "asset_category"})
    percentage: Decimal = Field(max_digits=5, decimal_places=2)
    value: Decimal = Field(max_digits=12, decimal_places=2)
    createdAt: datetime = Field(default_factory=datetime.utcnow, sa_column_kwargs={"name": "created_at"})
    updatedAt: datetime = Field(default_factory=datetime.utcnow, sa_column_kwargs={"name": "updated_at"})
    
    account: InvestmentAccount = Relationship(back_populates="allocations")

class SecurityHolding(SQLModel, table=True):
    __tablename__ = "security_holdings"
    id: UUID = Field(default_factory=uuid7, primary_key=True)
    accountId: UUID = Field(foreign_key="investment_accounts.id", sa_column_kwargs={"name": "account_id"})
    ticker: str
    name: Optional[str] = None
    percentage: str # Stored as string in schema? "percentage: text". Ok.
    assetClass: Optional[str] = Field(sa_column_kwargs={"name": "asset_class"})
    region: Optional[str] = None
    createdAt: datetime = Field(default_factory=datetime.utcnow, sa_column_kwargs={"name": "created_at"})
    updatedAt: datetime = Field(default_factory=datetime.utcnow, sa_column_kwargs={"name": "updated_at"})

    account: InvestmentAccount = Relationship(back_populates="holdings")
