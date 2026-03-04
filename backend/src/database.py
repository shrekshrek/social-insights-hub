from sqlalchemy import MetaData, create_engine
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker, Session

from .config import settings

# Recommended naming convention for PostgreSQL
# See: https://alembic.sqlalchemy.org/en/latest/naming.html
POSTGRES_NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

metadata = MetaData(naming_convention=POSTGRES_NAMING_CONVENTION)


# Create async engine
async_engine = create_async_engine(
    settings.DATABASE_URL.replace("postgresql+psycopg://", "postgresql+asyncpg://"),
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_timeout=settings.DB_POOL_TIMEOUT,
    pool_recycle=settings.DB_POOL_RECYCLE,
    pool_pre_ping=True,  # Check connection health before use
)

# Create async sessionmaker
AsyncSessionLocal = async_sessionmaker(
    async_engine, class_=AsyncSession, expire_on_commit=False
)

# Base class for declarative models, now with naming convention
Base = declarative_base(metadata=metadata)


# ==================== Sync Engine for Celery Tasks ====================
# Celery tasks use read→LLM→write pattern with short-lived DB sessions,
# so a smaller pool is sufficient even at high gevent concurrency.
sync_engine = create_engine(
    settings.DATABASE_URL,  # Use psycopg driver
    pool_size=settings.SYNC_DB_POOL_SIZE,
    max_overflow=settings.SYNC_DB_MAX_OVERFLOW,
    pool_timeout=settings.DB_POOL_TIMEOUT,
    pool_recycle=settings.DB_POOL_RECYCLE,
    pool_pre_ping=True,
)

# Create sync sessionmaker for Celery tasks
SyncSessionLocal = sessionmaker(sync_engine, class_=Session, expire_on_commit=False)


# ==================== Dependencies ====================


# Dependency to get a DB session (async) - for FastAPI
async def get_async_db():
    """
    FastAPI dependency that provides an async SQLAlchemy database session.
    """
    async with AsyncSessionLocal() as session:
        yield session


# Context manager for sync DB session - for Celery tasks
def get_sync_db():
    """
    Context manager that provides a sync SQLAlchemy database session.
    Use this in Celery tasks with gevent pool.

    Example:
        with get_sync_db() as db:
            result = db.query(Model).filter(...).first()
    """
    session = SyncSessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
