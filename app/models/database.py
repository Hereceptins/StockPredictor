"""
SQLAlchemy 数据库配置 —— 支持 SQLite (开发) / PostgreSQL (生产)
"""

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

# 解析数据库URL（SQLite需要特殊处理async）
db_url = settings.database_url
if db_url.startswith("sqlite"):
    # aiosqlite
    engine = create_async_engine(db_url, echo=settings.debug)
else:
    engine = create_async_engine(db_url, echo=settings.debug, pool_size=10, max_overflow=20)

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def init_db():
    """创建所有表"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db() -> AsyncSession:
    """FastAPI依赖注入：获取数据库会话"""
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()
