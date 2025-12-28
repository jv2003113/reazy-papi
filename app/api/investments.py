from typing import List, Any
from uuid import UUID
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api import deps
from app.models import User, InvestmentAccount, SecurityHolding, RefFund, InvestmentAccountRead

router = APIRouter()

# --- FUNDS ---

@router.get("/funds", response_model=List[RefFund])
async def get_funds(
    db: AsyncSession = Depends(deps.get_db),
    ticker: str = None
):
    query = select(RefFund)
    if ticker:
        query = query.where(RefFund.ticker.ilike(f"%{ticker}%"))
    
    result = await db.execute(query)
    funds = result.scalars().all()
    
    # Auto-seed if empty
    if not funds and not ticker:
        funds = await seed_funds(db)
        
    return funds

# Helper to seed funds
async def seed_funds(db: AsyncSession):
    seed_data = [
        {"ticker": "VTI", "name": "Vanguard Total Stock Market ETF", "assetClass": "stock", "region": "domestic", "expenseRatio": 0.03},
        {"ticker": "VOO", "name": "Vanguard S&P 500 ETF", "assetClass": "stock", "region": "domestic", "expenseRatio": 0.03},
        {"ticker": "QQQ", "name": "Invesco QQQ Trust", "assetClass": "stock", "region": "domestic", "expenseRatio": 0.20},
        {"ticker": "VXUS", "name": "Vanguard Total International Stock ETF", "assetClass": "stock", "region": "international", "expenseRatio": 0.07},
        {"ticker": "VEA", "name": "Vanguard Developed Markets ETF", "assetClass": "stock", "region": "international", "expenseRatio": 0.05},
        {"ticker": "VWO", "name": "Vanguard Emerging Markets ETF", "assetClass": "stock", "region": "emerging", "expenseRatio": 0.08},
        {"ticker": "BND", "name": "Vanguard Total Bond Market ETF", "assetClass": "bond", "region": "domestic", "expenseRatio": 0.03},
        {"ticker": "BNDX", "name": "Vanguard Total International Bond ETF", "assetClass": "bond", "region": "international", "expenseRatio": 0.07},
        {"ticker": "AGG", "name": "iShares Core U.S. Aggregate Bond ETF", "assetClass": "bond", "region": "domestic", "expenseRatio": 0.03},
        {"ticker": "TLT", "name": "iShares 20+ Year Treasury Bond ETF", "assetClass": "bond", "region": "domestic", "expenseRatio": 0.15},
        {"ticker": "SHY", "name": "iShares 1-3 Year Treasury Bond ETF", "assetClass": "bond", "region": "domestic", "expenseRatio": 0.15},
        {"ticker": "VNQ", "name": "Vanguard Real Estate ETF", "assetClass": "real_estate", "region": "domestic", "expenseRatio": 0.12},
        {"ticker": "GLD", "name": "SPDR Gold Shares", "assetClass": "other", "region": "global", "expenseRatio": 0.40},
        {"ticker": "IVV", "name": "iShares Core S&P 500 ETF", "assetClass": "stock", "region": "domestic", "expenseRatio": 0.03},
        {"ticker": "IEFA", "name": "iShares Core MSCI EAFE ETF", "assetClass": "stock", "region": "international", "expenseRatio": 0.07},
        {"ticker": "VUG", "name": "Vanguard Growth ETF", "assetClass": "stock", "region": "domestic", "expenseRatio": 0.04},
        {"ticker": "VTV", "name": "Vanguard Value ETF", "assetClass": "stock", "region": "domestic", "expenseRatio": 0.04},
        {"ticker": "BIV", "name": "Vanguard Intermediate-Term Bond ETF", "assetClass": "bond", "region": "domestic", "expenseRatio": 0.04},
        {"ticker": "VCIT", "name": "Vanguard Intermediate-Term Corporate Bond ETF", "assetClass": "bond", "region": "domestic", "expenseRatio": 0.04},
        {"ticker": "MUB", "name": "iShares National Muni Bond ETF", "assetClass": "bond", "region": "domestic", "expenseRatio": 0.05},
    ]
    
    created = []
    for data in seed_data:
        fund = RefFund(**data)
        db.add(fund)
        created.append(fund)
    
    await db.commit()
    return created

# --- INVESTMENT ACCOUNTS ---

@router.get("/users/{user_id}/investment-accounts", response_model=List[InvestmentAccountRead])
async def get_user_investment_accounts(
    user_id: UUID,
    current_user: User = Depends(deps.get_current_user),
    db: AsyncSession = Depends(deps.get_db),
):
    if current_user.id != user_id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # 1. Fetch existing DB accounts with holdings
    query = select(InvestmentAccount).where(InvestmentAccount.userId == user_id).options(selectinload(InvestmentAccount.holdings))
    result = await db.execute(query)
    db_accounts = result.scalars().all()
    
    # 2. SYNC LOGIC: Check User JSON assets and ensure accounts exist
    # Mapping User JSON keys to Account Types
    # JSON Key -> (Account Name, Account Type, IsRetirement, Owner)
    asset_map = {
        # Primary User
        "retirementAccount401k": ("401(k)", "401k", True, "primary"),
        "retirementAccountIRA": ("Traditional IRA", "IRA", True, "primary"),
        "retirementAccountRoth": ("Roth IRA", "Roth IRA", True, "primary"),
        "investmentBalance": ("Brokerage Account", "Brokerage", False, "primary"),
        "hsaBalance": ("Health Savings Account", "HSA", True, "primary"),
        # Spouse
        "spouseRetirementAccount401k": ("Spouse 401(k)", "401k", True, "spouse"),
        "spouseRetirementAccountIRA": ("Spouse Traditional IRA", "IRA", True, "spouse"),
        "spouseRetirementAccountRoth": ("Spouse Roth IRA", "Roth IRA", True, "spouse"),
        "spouseInvestmentBalance": ("Spouse Brokerage Account", "Brokerage", False, "spouse"),
        "spouseHsaBalance": ("Spouse Health Savings Account", "HSA", True, "spouse"),
    }
    
    start_assets = current_user.assets or {}
    changes_made = False
    
    for json_key, (name, acct_type, is_ret, owner) in asset_map.items():
        val = start_assets.get(json_key)
        if val and float(val) > 0:
            # Check if exists (match Type AND Owner)
            # using accountName as discriminator if types are same?
            # Better to use accountOwner field if available.
            # We assume db_accounts have accountOwner populated.
            exists = next((a for a in db_accounts if a.accountType == acct_type and a.accountOwner == owner), None)
            
            if exists:
                if float(exists.balance) != float(val):
                    exists.balance = Decimal(str(val))
                    db.add(exists)
                    changes_made = True
            else:
                new_acct = InvestmentAccount(
                    userId=user_id,
                    accountName=name,
                    accountType=acct_type,
                    balance=Decimal(str(val)),
                    isRetirementAccount=is_ret,
                    accountOwner=owner
                )
                db.add(new_acct)
                changes_made = True
                new_acct.holdings = [] 
                db_accounts = list(db_accounts) + [new_acct]

    if changes_made:
        await db.commit()
        # Re-fetch is safest to get IDs and defaults
        result = await db.execute(query)
        db_accounts = result.scalars().all()
        
    # 3. Populate Metadata (Name, Class, Region) dynamically from RefFund
    if db_accounts:
        # Fetch all funds for lookup
        funds_res = await db.execute(select(RefFund))
        funds = funds_res.scalars().all()
        fund_map = {f.ticker.upper(): f for f in funds}
        
        for account in db_accounts:
            if account.holdings:
                for holding in account.holdings:
                    # Look up fund info
                    if holding.ticker:
                        f = fund_map.get(holding.ticker.upper())
                        if f:
                            holding.name = f.name
                            holding.assetClass = f.assetClass
                            holding.region = f.region

    return db_accounts

@router.post("/investment-accounts", response_model=InvestmentAccountRead)
async def create_investment_account(
    account: InvestmentAccount,
    current_user: User = Depends(deps.get_current_user),
    db: AsyncSession = Depends(deps.get_db),
):
    account.userId = current_user.id
    db.add(account)
    await db.commit()
    await db.refresh(account)
    return account

@router.delete("/investment-accounts/{account_id}", status_code=204)
async def delete_investment_account(
    account_id: UUID,
    current_user: User = Depends(deps.get_current_user),
    db: AsyncSession = Depends(deps.get_db),
):
    query = select(InvestmentAccount).where(InvestmentAccount.id == account_id)
    result = await db.execute(query)
    account = result.scalars().first()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    if account.userId != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    await db.delete(account)
    await db.commit()
    await db.commit()
    return None

# --- AI EXTRACTION ---

@router.post("/extract-from-document")
async def extract_portfolio_from_document(
    file: UploadFile = File(...),
    current_user: User = Depends(deps.get_current_user),
):
    """
    Upload a portfolio statement (PDF/Image) and extract data using AI.
    """
    from app.services.ai_service import AIService
    
    content = await file.read()
    result = AIService.extract_portfolio_from_file(
        file_content=content,
        mime_type=file.content_type,
        user_id=str(current_user.id)
    )
    
    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])
        
    return result

# --- HOLDINGS ---

@router.post("/security-holdings", response_model=SecurityHolding)
async def create_security_holding(
    holding: SecurityHolding,
    current_user: User = Depends(deps.get_current_user),
    db: AsyncSession = Depends(deps.get_db),
):
    # Verify account ownership
    query = select(InvestmentAccount).where(InvestmentAccount.id == holding.accountId)
    result = await db.execute(query)
    account = result.scalars().first()
    
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    if account.userId != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")

    db.add(holding)
    await db.commit()
    await db.refresh(holding)
    
    # Populate Metadata from RefFund for Response (Not creating DB dependency for now)
    if holding.ticker:
        f_res = await db.execute(select(RefFund).where(RefFund.ticker == holding.ticker))
        fund = f_res.scalars().first()
        if fund:
            holding.name = fund.name
            holding.assetClass = fund.assetClass
            holding.region = fund.region
            
    return holding

@router.patch("/security-holdings/{holding_id}", response_model=SecurityHolding)
async def update_security_holding(
    holding_id: UUID,
    holding_update: dict,
    current_user: User = Depends(deps.get_current_user),
    db: AsyncSession = Depends(deps.get_db),
):
    query = select(SecurityHolding).where(SecurityHolding.id == holding_id)
    result = await db.execute(query)
    holding = result.scalars().first()
    if not holding:
        raise HTTPException(status_code=404, detail="Holding not found")
        
    # Verify account ownership
    acct_query = select(InvestmentAccount).where(InvestmentAccount.id == holding.accountId)
    res_a = await db.execute(acct_query)
    account = res_a.scalars().first()
    if not account or account.userId != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
        
    for key, value in holding_update.items():
        if hasattr(holding, key):
            setattr(holding, key, value)
            
    db.add(holding)
    await db.commit()
    await db.refresh(holding)
    return holding

@router.delete("/security-holdings/{holding_id}", status_code=204)
async def delete_security_holding(
    holding_id: UUID,
    current_user: User = Depends(deps.get_current_user),
    db: AsyncSession = Depends(deps.get_db),
):
    query = select(SecurityHolding).where(SecurityHolding.id == holding_id)
    result = await db.execute(query)
    holding = result.scalars().first()
    if not holding:
        raise HTTPException(status_code=404, detail="Holding not found")
        
    # Verify ownership
    acct_query = select(InvestmentAccount).where(InvestmentAccount.id == holding.accountId)
    res_a = await db.execute(acct_query)
    account = res_a.scalars().first()
    if not account or account.userId != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
        
    await db.delete(holding)
    await db.commit()
    return None
