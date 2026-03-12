import os

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://tds:password@postgres:5432/tds")
DATABASE_URL_ASYNC = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")
DATABASE_URL_SYNC = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")

async_engine = create_async_engine(DATABASE_URL_ASYNC, echo=False, pool_size=20, max_overflow=10)
async_session_factory = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)

sync_engine = create_engine(DATABASE_URL_SYNC, echo=False, pool_size=10, max_overflow=5)
sync_session_factory = sessionmaker(sync_engine, class_=Session, expire_on_commit=False)


async def get_async_session():
    async with async_session_factory() as session:
        yield session


def get_sync_session():
    with sync_session_factory() as session:
        yield session
