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

# For backwards compatibility, but it might still be None/not created yet if accessed directly.
# However, modifying the global variable directly is tricky.
# Instead, we will keep 'engine' but make it a proxy or property, OR we explicitly update usage.
# But 'engine' is exported. Let's redirect usage.

# ACTUALLY, simpler:
# Just don't call _create_engine() at top level.
# And usages like 'async with engine.begin()' need to call 'get_engine().begin()'

# But wait, external modules import 'engine'. changing that would break them.
# I will make 'engine' a proxy object or just keep the variable name but use a LazyProxy if I could.
# Without a proxy class, I have to update callers. 
# Let's check imports. `from .engine import engine` is common.

# Alternative: Wrap it in a class or use a LazyObject. 
# Simplest for now: 
# 1. Rename _create_engine to create_engine
# 2. engine = None
# 3. accessors use get_engine()

# But invalidating the 'engine' import in other files is risky if I don't check all usages.
# I'll search for 'from .* import .*engine'.

# Let's try to update the code in THIS file to use get_engine(), 
# and maybe other files need to be updated. 
# Actually, I can use a simple LazyEngine proxy class here to avoid changing other files.

class LazyEngine:
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
