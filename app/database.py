from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel
from app.core.config import settings

# Create async engine
# echo=True will log SQL queries for debugging
engine = create_async_engine(
    settings.DATABASE_URL, 
    echo=False, 
    future=True,
    pool_size=20,
    max_overflow=0
)

# Async session factory
async_session_maker = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

async def get_db():
    async with async_session_maker() as session:
        yield session

async def init_db():
    async with engine.begin() as conn:
        # await conn.run_sync(SQLModel.metadata.drop_all)
        await conn.run_sync(SQLModel.metadata.create_all)
