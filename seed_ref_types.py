import asyncio
from uuid import UUID
from app.database import async_session_maker, init_db
from app.models.investment import RefAccountType, InvestmentAccount
from sqlalchemy.future import select

async def seed_ref_types():
    async with async_session_maker() as db:
        print("Resetting Portfolio Schema...")
        from sqlalchemy import text
        try:
             # DROP existing tables to force schema refresh (since we removed columns)
             # We own 'portfolio_accounts' now, so we can drop it.
             await db.execute(text("DROP TABLE IF EXISTS portfolio_holdings CASCADE"))
             await db.execute(text("DROP TABLE IF EXISTS portfolio_allocations CASCADE"))
             await db.execute(text("DROP TABLE IF EXISTS portfolio_accounts CASCADE"))
             await db.commit()
             print("Dropped portfolio tables.")
        except Exception as e:
             print(f"Error dropping tables: {e}")
    
    # Re-init DB to recreate tables with NEW schema
    await init_db()
    
    async with async_session_maker() as db:
        print("Checking RefAccountTypes...")
        
        # Define Standard Types
        types = [
            {"code": "401k", "name": "401(k)"},
            {"code": "Roth IRA", "name": "Roth IRA"}, # Note: user.assets keys used 'Roth IRA' mixed case sometimes, stick to standard
            {"code": "IRA", "name": "Traditional IRA"},
            {"code": "brokerage", "name": "Brokerage Account"},
            {"code": "hsa", "name": "Health Savings Account"},
            {"code": "real_estate", "name": "Real Estate"},
            {"code": "other", "name": "Other Asset"},
        ]
        
        # Create Types
        type_map = {}
        for t in types:
            query = select(RefAccountType).where(RefAccountType.code == t["code"])
            result = await db.execute(query)
            existing = result.scalars().first()
            
            if not existing:
                print(f"Creating {t['name']}")
                new_type = RefAccountType(code=t["code"], name=t["name"])
                db.add(new_type)
                await db.commit()
                await db.refresh(new_type)
                type_map[t["code"]] = new_type.id
                type_map[t["code"].lower()] = new_type.id # handle case safety
            else:
                type_map[t["code"]] = existing.id
                type_map[t["code"].lower()] = existing.id
        
        print("RefAccountTypes seeded.")
        
        # WARNING: We are about to DROP existing accounts because schema changed drastically
        # and we don't have migrations to migrate data to new structure safely in this script
        # WITHOUT failing on missing columns if we try to read old rows.
        # Actually, since we updated the model, reading `InvestmentAccount` usually fails if cols missing.
        # So we might need to truncate via raw SQL.
        
        print("Cleaning up incompatible Tables (skipped as we rely on new tables)...")
        # Since we use new table names, init_db() called at start has already created them
        # We don't need to migrate the old 'investment_accounts' table.
        # It will be ignored.
        
        print("Schema migration via new tables complete.")
            
        await db.commit()

if __name__ == "__main__":
    asyncio.run(seed_ref_types())
