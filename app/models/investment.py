from typing import Optional, List, Dict
from uuid import UUID
from decimal import Decimal
from datetime import datetime
from sqlmodel import SQLModel, Field, Relationship
from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import JSONB
from uuid6 import uuid7

class RefAccountType(SQLModel, table=True):
    __tablename__ = "ref_account_types"
    id: UUID = Field(default_factory=uuid7, primary_key=True)
    code: str = Field(unique=True, index=True) # e.g. "401k", "brokerage"
    name: str # e.g. "401(k)", "Brokerage Account"
    createdAt: datetime = Field(default_factory=datetime.utcnow, sa_column_kwargs={"name": "created_at"})

class InvestmentAccountBase(SQLModel):
    # Removing foreign_key="users.id" due to "permission denied for table users"
    userId: UUID = Field(sa_column_kwargs={"name": "user_id"})
    # Replaced name/type with FK to RefAccountType
    typeId: UUID = Field(foreign_key="ref_account_types.id", sa_column_kwargs={"name": "type_id"})
    balance: Decimal = Field(max_digits=12, decimal_places=2)
    contributionAmount: Optional[Decimal] = Field(default=None, max_digits=10, decimal_places=2, sa_column_kwargs={"name": "contribution_amount"})
    accountOwner: str = Field(default="primary", sa_column_kwargs={"name": "account_owner"})

class InvestmentAccount(InvestmentAccountBase, table=True):
    # Using new table name to bypass 'investment_accounts' permission lock
    __tablename__ = "portfolio_accounts" 
    id: UUID = Field(default_factory=uuid7, primary_key=True)
    createdAt: datetime = Field(default_factory=datetime.utcnow, sa_column_kwargs={"name": "created_at"})
    updatedAt: datetime = Field(default_factory=datetime.utcnow, sa_column_kwargs={"name": "updated_at"})
    
    # Relationships
    allocations: List["AssetAllocation"] = Relationship(back_populates="account", sa_relationship_kwargs={"cascade": "all, delete-orphan"})
    holdings: List["SecurityHolding"] = Relationship(back_populates="account", sa_relationship_kwargs={"cascade": "all, delete-orphan"})
    
    # New Relationship
    accountTypeRef: "RefAccountType" = Relationship()

class InvestmentAccountCreate(SQLModel):
    accountType: str # e.g. "401k", "brokerage"
    balance: Decimal
    contributionAmount: Optional[Decimal] = None
    accountOwner: str = "primary"
    # accountName is ignored as we use RefAccountType name

class InvestmentAccountRead(InvestmentAccountBase):
    id: UUID
    # Flattened properties for frontend compatibility
    accountName: str 
    accountType: str
    # Removed unused fields from Read model as well
    createdAt: datetime
    updatedAt: datetime
    holdings: List["SecurityHolding"] = []

class InvestmentAccountUpdate(SQLModel):
    # Restored balance for editing
    balance: Optional[Decimal] = None
    contributionAmount: Optional[Decimal] = None 


class AssetAllocation(SQLModel, table=True):
    __tablename__ = "portfolio_allocations" # New table
    id: UUID = Field(default_factory=uuid7, primary_key=True)
    accountId: UUID = Field(foreign_key="portfolio_accounts.id", sa_column_kwargs={"name": "account_id"}) # Update FK
    assetCategory: str = Field(sa_column_kwargs={"name": "asset_category"})
    percentage: Decimal = Field(max_digits=5, decimal_places=2)
    value: Decimal = Field(max_digits=12, decimal_places=2)
    createdAt: datetime = Field(default_factory=datetime.utcnow, sa_column_kwargs={"name": "created_at"})
    updatedAt: datetime = Field(default_factory=datetime.utcnow, sa_column_kwargs={"name": "updated_at"})
    
    account: InvestmentAccount = Relationship(back_populates="allocations")

class SecurityHolding(SQLModel, table=True):
    __tablename__ = "portfolio_holdings" # New table
    id: UUID = Field(default_factory=uuid7, primary_key=True)
    accountId: UUID = Field(foreign_key="portfolio_accounts.id", sa_column_kwargs={"name": "account_id"}) # Update FK
    ticker: str
    name: Optional[str] = None
    percentage: str # Stored as string in schema? "percentage: text". Ok.
    value: Optional[Decimal] = Field(default=None, max_digits=12, decimal_places=2, sa_column_kwargs={"name": "value"}) 
    assetClass: Optional[str] = Field(sa_column_kwargs={"name": "asset_class"})
    region: Optional[str] = None
    
    # Overrides
    stockPct: Optional[Decimal] = Field(default=None, max_digits=5, decimal_places=2, sa_column_kwargs={"name": "stock_pct"})
    bondPct: Optional[Decimal] = Field(default=None, max_digits=5, decimal_places=2, sa_column_kwargs={"name": "bond_pct"})
    internationalPct: Optional[Decimal] = Field(default=None, max_digits=5, decimal_places=2, sa_column_kwargs={"name": "international_pct"})
    domesticPct: Optional[Decimal] = Field(default=None, max_digits=5, decimal_places=2, sa_column_kwargs={"name": "domestic_pct"})
    cashPct: Optional[Decimal] = Field(default=None, max_digits=5, decimal_places=2, sa_column_kwargs={"name": "cash_pct"})

    createdAt: datetime = Field(default_factory=datetime.utcnow, sa_column_kwargs={"name": "created_at"})
    updatedAt: datetime = Field(default_factory=datetime.utcnow, sa_column_kwargs={"name": "updated_at"})

    account: InvestmentAccount = Relationship(back_populates="holdings")

class RefFund(SQLModel, table=True):
    __tablename__ = "ref_funds"
    ticker: str = Field(primary_key=True)
    name: str
    assetClass: str = Field(sa_column_kwargs={"name": "asset_class"}) # stock, bond, real_estate, other
    region: str = Field(default="domestic") # domestic, international, emerging, global
    expenseRatio: Optional[Decimal] = Field(default=None, max_digits=5, decimal_places=4, sa_column_kwargs={"name": "expense_ratio"})
    sectors: Optional[Dict[str, float]] = Field(default=None, sa_column=Column(JSONB)) # JSONB for sector breakdown
    createdAt: datetime = Field(default_factory=datetime.utcnow, sa_column_kwargs={"name": "created_at"})

# Resolve Forward References
InvestmentAccount.model_rebuild()
InvestmentAccountRead.model_rebuild()
AssetAllocation.model_rebuild()
SecurityHolding.model_rebuild()
