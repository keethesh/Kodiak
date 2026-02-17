from collections.abc import AsyncGenerator
from loguru import logger

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import text, event
from sqlmodel import SQLModel

from kodiak.core.config import settings


def _create_engine():
    """Create the async database engine with appropriate settings for the database type."""
    connect_args = {}
    
    if settings.is_sqlite:
        # SQLite-specific configuration
        connect_args = {"check_same_thread": False}
        logger.info(f"Using SQLite database at: {settings.sqlite_path or '~/.kodiak/kodiak.db'}")
    else:
        logger.info(f"Using PostgreSQL database at: {settings.postgres_server}:{settings.postgres_port}/{settings.postgres_db}")
    
    return create_async_engine(
        settings.async_database_url,
        echo=settings.debug,
        future=True,
        connect_args=connect_args,
    )



_engine = None

def get_engine():
    """Lazily create and return the database engine."""
    global _engine
    if _engine is None:
        _engine = _create_engine()
    return _engine


class LazyEngine:
    """Lazy engine proxy to avoid eager database connection on import."""
    def __init__(self):
        self._engine = None
        
    def _ensure_engine(self):
        if self._engine is None:
            self._engine = _create_engine()
        return self._engine
        
    def __getattr__(self, name):
        return getattr(self._ensure_engine(), name)
        
    async def begin(self):
        return self._ensure_engine().begin()
        
    async def connect(self):
        return self._ensure_engine().connect()
        
    async def dispose(self):
        if self._engine:
            await self._engine.dispose()
            
    # Add other necessary delegate methods if needed, or rely on __getattr__
    # explicit async methods are needed for 'async with' usually if it returns a context manager
    
engine = LazyEngine()


async def init_db():
    """
    Initialize the database by creating all tables.
    This function ensures all SQLModel tables are created properly.
    """
    try:
        logger.info("Initializing database...")
        
        async with engine.begin() as conn:
            # Import all models to ensure they're registered with SQLModel metadata
            from kodiak.database import models  # noqa
            
            # Create all tables
            await conn.run_sync(SQLModel.metadata.create_all)
            
        logger.info("Database initialization completed successfully")
        
        # Verify database connectivity
        await verify_database_connectivity()
        
    except SQLAlchemyError as e:
        logger.error(f"Database initialization failed: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error during database initialization: {e}")
        raise



async def verify_database_connectivity():
    """
    Verify that the database connection is working properly.
    """
    try:
        # Use get_engine() to ensure we have the actual engine instance
        async with AsyncSession(get_engine()) as session:
            # Simple query to verify connectivity
            result = await session.execute(text("SELECT 1"))
            result.fetchone()
            logger.info("Database connectivity verified")
    except Exception as e:
        logger.error(f"Database connectivity verification failed: {e}")
        raise


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Get a database session with proper error handling.
    """
    # Use get_engine() to ensure we have the actual engine instance
    async with AsyncSession(get_engine(), expire_on_commit=False) as session:
        try:
            yield session
        except SQLAlchemyError as e:
            logger.error(f"Database session error: {e}")
            await session.rollback()
            raise
        except Exception as e:
            logger.error(f"Unexpected session error: {e}")
            await session.rollback()
            raise
        finally:
            await session.close()
