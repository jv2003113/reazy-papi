
import asyncio
from sqlalchemy import text
from app.database import engine

async def add_columns():
    async with engine.begin() as conn:
        print("Adding columns to portfolio_holdings...")
        try:
            await conn.execute(text("ALTER TABLE portfolio_holdings ADD COLUMN stock_pct NUMERIC(5,2);"))
        except Exception as e:
            print(f"stock_pct might exist: {e}")
            
        try:
            await conn.execute(text("ALTER TABLE portfolio_holdings ADD COLUMN bond_pct NUMERIC(5,2);"))
        except Exception as e:
            print(f"bond_pct might exist: {e}")
            
        try:
            await conn.execute(text("ALTER TABLE portfolio_holdings ADD COLUMN international_pct NUMERIC(5,2);"))
        except Exception as e:
            print(f"international_pct might exist: {e}")
            
        try:
            await conn.execute(text("ALTER TABLE portfolio_holdings ADD COLUMN domestic_pct NUMERIC(5,2);"))
        except Exception as e:
            print(f"domestic_pct might exist: {e}")

    print("Done.")

if __name__ == "__main__":
    asyncio.run(add_columns())
