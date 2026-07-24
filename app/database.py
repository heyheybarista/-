from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from app.config import get_settings

settings = get_settings()
# SQLite with aiosqlite, WAL mode
DATABASE_URL = f"sqlite+aiosqlite:///{settings.database_path}"

engine = create_async_engine(DATABASE_URL, echo=False, connect_args={"check_same_thread": False})

AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def init_db():
    import app.models  # noqa: ensure all models loaded
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    # enable WAL
    async with engine.connect() as conn:
        await conn.exec_driver_sql("PRAGMA journal_mode=WAL")
        await conn.exec_driver_sql("PRAGMA foreign_keys=ON")


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
