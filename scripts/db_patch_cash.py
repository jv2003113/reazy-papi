
import asyncio
from sqlalchemy import text
from app.database import engine

async def add_cash_column():
    async with engine.begin() as conn:
        print("Adding cash_pct column to portfolio_holdings...")
        try:
            await conn.execute(text("ALTER TABLE portfolio_holdings ADD COLUMN cash_pct NUMERIC(5,2);"))
            print("Successfully added cash_pct.")
        except Exception as e:
            print(f"cash_pct might exist or error: {e}")

    print("Done.")

if __name__ == "__main__":
    asyncio.run(add_cash_column())
