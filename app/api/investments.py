from typing import List, Any
from uuid import UUID
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api import deps
from app.models import User, InvestmentAccount, SecurityHolding, RefFund, InvestmentAccountRead, InvestmentAccountUpdate, InvestmentAccountCreate

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

from datetime import datetime
from decimal import Decimal
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from app.api import deps
from app.models.user import User
from app.models.investment import (
    InvestmentAccount,
    InvestmentAccountRead,
    InvestmentAccountUpdate,
    SecurityHolding,
    RefFund,
    RefAccountType
)
from uuid import uuid4



@router.get("/users/{user_id}/investment-accounts", response_model=List[InvestmentAccountRead])
async def get_user_investment_accounts(
    user_id: UUID,
    current_user: User = Depends(deps.get_current_user),
    db: AsyncSession = Depends(deps.get_db),
):
    if current_user.id != user_id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # Fetch existing DB accounts with holdings and type reference
    query = select(InvestmentAccount)\
        .where(InvestmentAccount.userId == user_id)\
        .options(selectinload(InvestmentAccount.holdings), selectinload(InvestmentAccount.accountTypeRef))
    
    result = await db.execute(query)
    db_accounts = result.scalars().all()
    
    # Map to Response Model (Flattening Type)
    response_accounts = []
    
    # Populate Metadata (Name, Class, Region) dynamically from RefFund
    # Also fetch all funds map once
    funds = []
    if db_accounts:
        funds_res = await db.execute(select(RefFund))
        funds = funds_res.scalars().all()
    fund_map = {f.ticker.upper(): f for f in funds}


    for account in db_accounts:
        # Resolve Name/Type from Reference
        acct_name = account.accountTypeRef.name if account.accountTypeRef else "Unknown Account"
        acct_type_code = account.accountTypeRef.code if account.accountTypeRef else "unknown"

        if account.holdings:
            for holding in account.holdings:
                if holding.ticker:
                    f = fund_map.get(holding.ticker.upper())
                    if f:
                        holding.name = f.name
                        holding.assetClass = f.assetClass
                        holding.region = f.region
        
        # Create Read Model
        read_model = InvestmentAccountRead(
            id=account.id,
            userId=account.userId,
            typeId=account.typeId,
            accountName=acct_name, # Mapped from Ref
            accountType=acct_type_code, # Mapped from Ref
            balance=account.balance,
            contributionAmount=account.contributionAmount,
            accountOwner=account.accountOwner,
            createdAt=account.createdAt,
            updatedAt=account.updatedAt,
            holdings=account.holdings
        )
        response_accounts.append(read_model)

    return response_accounts

@router.post("/investment-accounts", response_model=InvestmentAccountRead)
async def create_investment_account(
    account_in: "InvestmentAccountCreate", # Use string ref or import
    current_user: User = Depends(deps.get_current_user),
    db: AsyncSession = Depends(deps.get_db),
):

    
    # 1. Resolve Account Type Code -> ID
    # Normalize input
    code = account_in.accountType.lower() if account_in.accountType else "other"
    
    # Try exact match first, then lower
    res = await db.execute(select(RefAccountType).where(RefAccountType.code == account_in.accountType))
    ref_type = res.scalars().first()
    
    if not ref_type:
         # Try case insensitive
         res = await db.execute(select(RefAccountType).where(RefAccountType.code == code))
         ref_type = res.scalars().first()
         
    if not ref_type:
        # Fallback to 'brokerage' (commonly available) or 'other'
        res = await db.execute(select(RefAccountType).where(RefAccountType.code == "brokerage"))
        ref_type = res.scalars().first()
        
    if not ref_type:
         res = await db.execute(select(RefAccountType).where(RefAccountType.code == "other"))
         ref_type = res.scalars().first()
         
    if not ref_type:
        raise HTTPException(status_code=400, detail=f"Invalid account type: {account_in.accountType} and 'other' fallback missing.")

    # 2. Create Instance
    account = InvestmentAccount(
        userId=current_user.id,
        typeId=ref_type.id,
        balance=account_in.balance,
        contributionAmount=account_in.contributionAmount,
        accountOwner=account_in.accountOwner
    )

    db.add(account)
    await db.commit()
    await db.refresh(account)
    
    # Re-fetch with holdings/ref for Read Model
    query = select(InvestmentAccount).where(InvestmentAccount.id == account.id)\
        .options(selectinload(InvestmentAccount.holdings), selectinload(InvestmentAccount.accountTypeRef))
    result = await db.execute(query)
    saved_account = result.scalars().first()
    
    # Construct Read Model (Manual map required due to flattened Ref properties)
    acct_name = saved_account.accountTypeRef.name if saved_account.accountTypeRef else "Unknown"
    acct_type_code = saved_account.accountTypeRef.code if saved_account.accountTypeRef else "unknown"
    
    return InvestmentAccountRead(
        id=saved_account.id,
        userId=saved_account.userId,
        typeId=saved_account.typeId,
        accountName=acct_name,
        accountType=acct_type_code,
        balance=saved_account.balance,
        contributionAmount=saved_account.contributionAmount,
        accountOwner=saved_account.accountOwner,
        createdAt=saved_account.createdAt,
        updatedAt=saved_account.updatedAt,
        holdings=saved_account.holdings
    )

@router.patch("/investment-accounts/{account_id}", response_model=InvestmentAccountRead)
async def update_investment_account(
    account_id: UUID,
    account_update: InvestmentAccountUpdate,
    current_user: User = Depends(deps.get_current_user),
    db: AsyncSession = Depends(deps.get_db),
):
    # Fetch account with holdings to verify ownership and update balance logic
    query = select(InvestmentAccount).where(InvestmentAccount.id == account_id).options(selectinload(InvestmentAccount.holdings), selectinload(InvestmentAccount.accountTypeRef))
    result = await db.execute(query)
    account = result.scalars().first()
    
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
        
    if account.userId != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
        
    update_data = account_update.dict(exclude_unset=True)
    
    # Handle Balance Update (Restored Logic)
    if 'balance' in update_data:
        new_balance = update_data['balance']
        
        # Calculate sum of NON-unallocated holdings
        current_holdings_sum = sum(h.value or Decimal(0) for h in account.holdings if h.ticker != "UNALLOCATED")
        
        if new_balance < current_holdings_sum:
            raise HTTPException(status_code=400, detail=f"Balance cannot be less than the sum of your holdings (${current_holdings_sum})")
            
        # Calculate Unallocated Amount
        unallocated_amount = new_balance - current_holdings_sum
        
        # Find existing Unallocated holding
        unalloc_holding = next((h for h in account.holdings if h.ticker == "UNALLOCATED"), None)
        
        if unallocated_amount > 0:
            if unalloc_holding:
                unalloc_holding.value = unallocated_amount
                db.add(unalloc_holding)
            else:
                # Create Unallocated
                new_unalloc = SecurityHolding(
                    accountId=account.id,
                    ticker="UNALLOCATED",
                    name="Unallocated Cash",
                    value=unallocated_amount,
                    percentage="0", # Recalc later
                    assetClass="cash"
                )
                db.add(new_unalloc)
                # Append to holdings list for memory consistency in this request
                account.holdings.append(new_unalloc)
        else:
            # If 0 unallocated, remove if exists
            if unalloc_holding:
                await db.delete(unalloc_holding)
                account.holdings = [h for h in account.holdings if h.ticker != "UNALLOCATED"]
        
        # Update percentages for ALL holdings based on new total
        if new_balance > 0:
            for h in account.holdings:
                 # If we just updated unalloc, use its new value reference if possible, or object state
                 val = h.value
                 if h.ticker == "UNALLOCATED" and unallocated_amount > 0:
                     val = unallocated_amount
                 
                 if val:
                    h.percentage = f"{(val / new_balance * 100):.2f}"
                    db.add(h)
                    
        # Apply balance to account object
        account.balance = new_balance

    # Update other fields
    if 'contributionAmount' in update_data:
         account.contributionAmount = update_data['contributionAmount']

    account.updatedAt = datetime.utcnow()
    db.add(account)
    await db.commit()
    await db.refresh(account)
    
    # Construct Read Model for response
    acct_name = account.accountTypeRef.name if account.accountTypeRef else "Unknown Account"
    acct_type_code = account.accountTypeRef.code if account.accountTypeRef else "unknown"
    
    return InvestmentAccountRead(
        id=account.id,
        userId=account.userId,
        typeId=account.typeId,
        accountName=acct_name,
        accountType=acct_type_code,
        balance=account.balance,
        contributionAmount=account.contributionAmount,
        accountOwner=account.accountOwner,
        createdAt=account.createdAt,
        updatedAt=account.updatedAt,
        holdings=account.holdings
    )

@router.post("/investment-accounts/{account_id}/reset", response_model=InvestmentAccountRead)
async def reset_investment_account(
    account_id: UUID,
    current_user: User = Depends(deps.get_current_user),
    db: AsyncSession = Depends(deps.get_db),
):
    # Fetch account to verify ownership
    query = select(InvestmentAccount).where(InvestmentAccount.id == account_id).options(selectinload(InvestmentAccount.holdings), selectinload(InvestmentAccount.accountTypeRef))
    result = await db.execute(query)
    account = result.scalars().first()
    
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
        
    if account.userId != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
        
    # 1. Delete all holdings
    for holding in account.holdings:
        await db.delete(holding)
    
    # 2. Reset Balance and Contribution
    account.balance = Decimal(0)
    # Resetting contribution as well? User request said "clears holdings and set the balance to $0".
    # reset implies a fresh start, so usually implies removing contributions too to avoid mismatch.
    account.contributionAmount = Decimal(0) 
    account.holdings = [] # Clear relationship in memory
    
    account.updatedAt = datetime.utcnow()
    db.add(account)
    await db.commit()
    await db.refresh(account)
    
    # Return Read Model
    acct_name = account.accountTypeRef.name if account.accountTypeRef else "Unknown"
    acct_type_code = account.accountTypeRef.code if account.accountTypeRef else "unknown"
    
    return InvestmentAccountRead(
        id=account.id,
        userId=account.userId,
        typeId=account.typeId,
        accountName=acct_name,
        accountType=acct_type_code,
        balance=account.balance,
        contributionAmount=account.contributionAmount,
        accountOwner=account.accountOwner,
        createdAt=account.createdAt,
        updatedAt=account.updatedAt,
        holdings=[]
    )

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

    # REFACTOR: Balance = Sum of Holdings
    # Recalculate account balance based on all holdings
    # We need to fetch all holdings for this account to sum them up
    # However, since we just added one, we might need a fresh fetch
    
    # 1. Fetch all holdings for account
    h_query = select(SecurityHolding).where(SecurityHolding.accountId == holding.accountId)
    h_res = await db.execute(h_query)
    all_holdings = h_res.scalars().all()
    
    # 2. Sum values
    new_balance = sum((h.value or Decimal(0)) for h in all_holdings)
    
    # 3. Update account balance
    account.balance = new_balance
    db.add(account)
    await db.commit()
    
    # 4. Update Percentages (Optional, but good for consistency)
    if new_balance > 0:
        for h in all_holdings:
            if h.value:
                h.percentage = f"{(h.value / new_balance * 100):.2f}"
                db.add(h)
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

    # REFACTOR: Balance = Sum of Holdings
    h_query = select(SecurityHolding).where(SecurityHolding.accountId == holding.accountId)
    h_res = await db.execute(h_query)
    all_holdings = h_res.scalars().all()
    
    new_balance = sum((h.value or Decimal(0)) for h in all_holdings)
    
    account.balance = new_balance
    db.add(account)
    await db.commit()
    
    # Update Percentages
    if new_balance > 0:
        for h in all_holdings:
            if h.value:
                h.percentage = f"{(h.value / new_balance * 100):.2f}"
                db.add(h)
        await db.commit()

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

    # REFACTOR: Balance = Sum of Holdings
    h_query = select(SecurityHolding).where(SecurityHolding.accountId == holding.accountId)
    h_res = await db.execute(h_query)
    all_holdings = h_res.scalars().all()
    
    new_balance = sum((h.value or Decimal(0)) for h in all_holdings)
    
    account.balance = new_balance
    db.add(account)
    await db.commit()
    
    # Update Percentages
    if new_balance > 0:
        for h in all_holdings:
             if h.value:
                h.percentage = f"{(h.value / new_balance * 100):.2f}"
                db.add(h)
    
    await db.commit()
    return None
@router.delete("/users/{user_id}/investment-accounts/{account_id}/holdings", status_code=204)
async def delete_account_holdings(
    user_id: UUID,
    account_id: UUID,
    current_user: User = Depends(deps.get_current_user),
    db: AsyncSession = Depends(deps.get_db),
):
    if current_user.id != user_id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # Verify account ownership
    account_query = select(InvestmentAccount).where(InvestmentAccount.id == account_id)
    result = await db.execute(account_query)
    account = result.scalars().first()
    
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
        
    if account.userId != user_id:
        raise HTTPException(status_code=403, detail="Not authorized")

    # Delete all holdings
    # Note: sqlmodel delete is not always direct, using sqlalchemy delete
    from sqlmodel import delete
    query = delete(SecurityHolding).where(SecurityHolding.accountId == account_id)
    await db.execute(query)
    
    # Reset balance to 0
    account.balance = Decimal(0)
    db.add(account)
    
    await db.commit()
    return None

