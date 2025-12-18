from typing import Optional, List, Any
from uuid import UUID
from decimal import Decimal
from sqlmodel import SQLModel, Field, Relationship
from sqlalchemy import JSON, Column
from uuid6 import uuid7
from datetime import datetime

class UserBase(SQLModel):
    firstName: Optional[str] = Field(sa_column_kwargs={"name": "first_name"})
    lastName: Optional[str] = Field(sa_column_kwargs={"name": "last_name"})
    email: str = Field(unique=True, index=True)
    currentAge: Optional[int] = Field(sa_column_kwargs={"name": "current_age"})
    targetRetirementAge: Optional[int] = Field(sa_column_kwargs={"name": "target_retirement_age"})
    currentLocation: Optional[str] = Field(sa_column_kwargs={"name": "current_location"})
    maritalStatus: Optional[str] = Field(sa_column_kwargs={"name": "marital_status"})
    dependents: Optional[int] = Field(default=0)
    currentIncome: Optional[Decimal] = Field(default=0, max_digits=12, decimal_places=2, sa_column_kwargs={"name": "current_income"})
    desiredLifestyle: Optional[str] = Field(sa_column_kwargs={"name": "desired_lifestyle"})
    currency: str = Field(default="$")
    
    # Spouse
    hasSpouse: bool = Field(default=False, sa_column_kwargs={"name": "has_spouse"})
    spouseFirstName: Optional[str] = Field(sa_column_kwargs={"name": "spouse_first_name"})
    spouseLastName: Optional[str] = Field(sa_column_kwargs={"name": "spouse_last_name"})
    spouseCurrentAge: Optional[int] = Field(sa_column_kwargs={"name": "spouse_current_age"})
    spouseTargetRetirementAge: Optional[int] = Field(sa_column_kwargs={"name": "spouse_target_retirement_age"})
    spouseCurrentIncome: Optional[Decimal] = Field(default=0, max_digits=12, decimal_places=2, sa_column_kwargs={"name": "spouse_current_income"})
    
    # Additional Income
    otherIncomeSource1: Optional[str] = Field(sa_column_kwargs={"name": "other_income_source_1"})
    otherIncomeAmount1: Optional[Decimal] = Field(default=0, max_digits=12, decimal_places=2, sa_column_kwargs={"name": "other_income_amount_1"})
    otherIncomeSource2: Optional[str] = Field(sa_column_kwargs={"name": "other_income_source_2"})
    otherIncomeAmount2: Optional[Decimal] = Field(default=0, max_digits=12, decimal_places=2, sa_column_kwargs={"name": "other_income_amount_2"})
    expectedIncomeGrowth: Optional[Decimal] = Field(default=3.0, max_digits=5, decimal_places=2, sa_column_kwargs={"name": "expected_income_growth"})
    spouseExpectedIncomeGrowth: Optional[Decimal] = Field(default=3.0, max_digits=5, decimal_places=2, sa_column_kwargs={"name": "spouse_expected_income_growth"})
    
    # Expenses (JSON)
    expenses: List[dict] = Field(default=[], sa_column=Column(JSON))
    totalMonthlyExpenses: Optional[Decimal] = Field(default=0, max_digits=12, decimal_places=2, sa_column_kwargs={"name": "total_monthly_expenses"})
    
    # Assets
    savingsBalance: Optional[Decimal] = Field(default=0, max_digits=15, decimal_places=2, sa_column_kwargs={"name": "savings_balance"})
    checkingBalance: Optional[Decimal] = Field(default=0, max_digits=15, decimal_places=2, sa_column_kwargs={"name": "checking_balance"})
    investmentBalance: Optional[Decimal] = Field(default=0, max_digits=15, decimal_places=2, sa_column_kwargs={"name": "investment_balance"})
    investmentContribution: Optional[Decimal] = Field(default=0, max_digits=12, decimal_places=2, sa_column_kwargs={"name": "investment_contribution"})
    retirementAccount401k: Optional[Decimal] = Field(default=0, max_digits=15, decimal_places=2, sa_column_kwargs={"name": "retirement_account_401k"})
    retirementAccount401kContribution: Optional[Decimal] = Field(default=0, max_digits=12, decimal_places=2, sa_column_kwargs={"name": "retirement_account_401k_contribution"})
    retirementAccountIRA: Optional[Decimal] = Field(default=0, max_digits=15, decimal_places=2, sa_column_kwargs={"name": "retirement_account_ira"})
    retirementAccountIRAContribution: Optional[Decimal] = Field(default=0, max_digits=12, decimal_places=2, sa_column_kwargs={"name": "retirement_account_ira_contribution"})
    retirementAccountRoth: Optional[Decimal] = Field(default=0, max_digits=15, decimal_places=2, sa_column_kwargs={"name": "retirement_account_roth"})
    retirementAccountRothContribution: Optional[Decimal] = Field(default=0, max_digits=12, decimal_places=2, sa_column_kwargs={"name": "retirement_account_roth_contribution"})
    realEstateValue: Optional[Decimal] = Field(default=0, max_digits=15, decimal_places=2, sa_column_kwargs={"name": "real_estate_value"})
    otherAssetsValue: Optional[Decimal] = Field(default=0, max_digits=15, decimal_places=2, sa_column_kwargs={"name": "other_assets_value"})
    
    # Liabilities
    mortgageBalance: Optional[Decimal] = Field(default=0, max_digits=15, decimal_places=2, sa_column_kwargs={"name": "mortgage_balance"})
    mortgagePayment: Optional[Decimal] = Field(default=0, max_digits=12, decimal_places=2, sa_column_kwargs={"name": "mortgage_payment"})
    mortgageRate: Optional[Decimal] = Field(default=0, max_digits=5, decimal_places=2, sa_column_kwargs={"name": "mortgage_rate"})
    mortgageYearsLeft: Optional[int] = Field(sa_column_kwargs={"name": "mortgage_years_left"})
    creditCardDebt: Optional[Decimal] = Field(default=0, max_digits=15, decimal_places=2, sa_column_kwargs={"name": "credit_card_debt"})
    studentLoanDebt: Optional[Decimal] = Field(default=0, max_digits=15, decimal_places=2, sa_column_kwargs={"name": "student_loan_debt"})
    otherDebt: Optional[Decimal] = Field(default=0, max_digits=15, decimal_places=2, sa_column_kwargs={"name": "other_debt"})
    totalMonthlyDebtPayments: Optional[Decimal] = Field(default=0, max_digits=12, decimal_places=2, sa_column_kwargs={"name": "total_monthly_debt_payments"})
    
    # Risk Assessment
    investmentExperience: Optional[str] = Field(sa_column_kwargs={"name": "investment_experience"})
    riskTolerance: Optional[str] = Field(sa_column_kwargs={"name": "risk_tolerance"})
    investmentTimeline: Optional[str] = Field(sa_column_kwargs={"name": "investment_timeline"})
    preferredInvestmentTypes: List[str] = Field(default=[], sa_column=Column(JSON, name="preferred_investment_types"))
    marketVolatilityComfort: Optional[str] = Field(sa_column_kwargs={"name": "market_volatility_comfort"})
    investmentRebalancingPreference: Optional[str] = Field(sa_column_kwargs={"name": "investment_rebalancing_preference"})

class UserUpdate(UserBase):
    email: Optional[str] = None
    currency: Optional[str] = None
    
    # Redefine required-optional fields from UserBase with explicit defaults
    desiredLifestyle: Optional[str] = None
    spouseCurrentAge: Optional[int] = None
    spouseTargetRetirementAge: Optional[int] = None
    mortgageYearsLeft: Optional[int] = None
    investmentExperience: Optional[str] = None
    riskTolerance: Optional[str] = None
    investmentTimeline: Optional[str] = None
    marketVolatilityComfort: Optional[str] = None
    investmentRebalancingPreference: Optional[str] = None
    # Add other fields that might be problematic if they lack defaults in base
    firstName: Optional[str] = None
    lastName: Optional[str] = None
    currentLocation: Optional[str] = None
    maritalStatus: Optional[str] = None
    spouseFirstName: Optional[str] = None
    spouseLastName: Optional[str] = None
    otherIncomeSource1: Optional[str] = None
    otherIncomeSource2: Optional[str] = None
    
    # Critical fields that lacked defaults in base
    currentAge: Optional[int] = None
    targetRetirementAge: Optional[int] = None

class User(UserBase, table=True):
    __tablename__ = "users"
    id: UUID = Field(default_factory=uuid7, primary_key=True)
    password: str
    createdAt: datetime = Field(default_factory=datetime.utcnow, sa_column_kwargs={"name": "created_at"})
