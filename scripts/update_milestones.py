import asyncio
import sys
import os

# Add parent directory to path so we can import app
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from app.database import engine
from app.models.milestone import RefMilestone

NEW_MILESTONES = [
    {
        "targetAge": 50.0,
        "title": "Catch-up Contributions",
        "description": "Eligible for additional 401(k) and IRA contributions",
        "category": "financial",
        "icon": "info"
    },
    {
        "targetAge": 55.0,
        "title": "The Rule of 55",
        "description": "If you leave your job in or after the year you turn 55, you can take penalty-free (but taxed) withdrawals from your current employer's 401(k) or 403(b).",
        "category": "retirement",
        "icon": "info"
    },
    {
        "targetAge": 55.0,
        "title": "HSA Catch-up",
        "description": "Eligible for an additional $1,000 'catch-up' contribution to a Health Savings Account (HSA).",
        "category": "health",
        "icon": "info"
    },
    {
        "targetAge": 59.5,
        "title": "Penalty-Free Withdrawals",
        "description": "The 10% early withdrawal penalty expires for all traditional IRAs and 401(k)s, regardless of employment status.",
        "category": "financial",
        "icon": "info"
    },
    {
        "targetAge": 60.0,
        "title": "Social Security Survivors",
        "description": "Widows/widowers can begin claiming survivor benefits (at a reduced rate).",
        "category": "income",
        "icon": "info"
    },
    {
        "targetAge": 62.0,
        "title": "Early Social Security",
        "description": "Eligible for reduced Social Security benefits (75% of full benefit)",
        "category": "income",
        "icon": "info"
    },
    {
        "targetAge": 65.0,
        "title": "Medicare Eligibility",
        "description": "Eligible for Medicare health insurance",
        "category": "health",
        "icon": "info"
    },
    {
        "targetAge": 65.0,
        "title": "HSA Penalty Sunset",
        "description": "After 65, you can withdraw HSA funds for non-medical expenses without the 20% penalty (though you pay income tax, similar to a Traditional IRA).",
        "category": "health",
        "icon": "info"
    },
    {
        "targetAge": 67.0,
        "title": "Full Retirement Age",
        "description": "Eligible for full Social Security benefits",
        "category": "income",
        "icon": "info"
    },
    {
        "targetAge": 70.0,
        "title": "Max Social Security",
        "description": "Benefits stop increasing. There is no financial benefit to waiting past age 70 to claim.",
        "category": "income",
        "icon": "info"
    },
    {
        "targetAge": 70.5,
        "title": "QCD Eligibility",
        "description": "You can make Qualified Charitable Distributions (QCDs) directly from an IRA to a charity. This counts toward RMDs later and is tax-free.",
        "category": "tax",
        "icon": "info"
    },
    {
        "targetAge": 73.0,
        "title": "Required Minimum Distributions",
        "description": "Must begin taking RMDs from retirement accounts",
        "category": "tax",
        "icon": "info"
    },
    {
        "targetAge": 75.0,
        "title": "Updated RMD Age",
        "description": "Under the SECURE Act 2.0, if you were born in 1960 or later, your RMD age shifts from 73 to 75.",
        "category": "tax",
        "icon": "info"
    }
]

async def update_milestones():
    # 1. Update Schema
    try:
        async with engine.begin() as conn:
            print("1. Altering table to support floats (attempting)...")
            await conn.execute(text("ALTER TABLE ref_milestones ALTER COLUMN target_age TYPE float USING target_age::float"))
    except Exception as e:
        print(f"Skipping ALTER TABLE (might lack permission or already done): {e}")

    # 2. Clear Table
    async with engine.begin() as conn:
        print("2. Clearing table (using DELETE)...")
        await conn.execute(text("DELETE FROM ref_milestones"))
    
    # 3. Insert Data
    from sqlmodel import Session
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.ext.asyncio import AsyncSession
    
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    print("3. Inserting new milestones...")
    try:
        async with async_session() as session:
            for m_data in NEW_MILESTONES:
                milestone = RefMilestone(
                    targetAge=m_data["targetAge"],
                    title=m_data["title"],
                    description=m_data["description"],
                    category=m_data["category"],
                    icon=m_data["icon"],
                    isActive=True,
                    sortOrder=int(m_data["targetAge"]) 
                )
                session.add(milestone)
            
            await session.commit()
            print("Success! Milestones updated.")
    except Exception as e:
        print(f"Insertion failed: {e}")
        # Identify if it's due to float constraint
        if "input syntax for integer" in str(e) or "integer" in str(e):
             print("CRITICAL: Database schema requires 'targetAge' to be INTEGER. Schema update failed.")

if __name__ == "__main__":
    asyncio.run(update_milestones())
