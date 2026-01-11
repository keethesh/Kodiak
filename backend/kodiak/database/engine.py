from collections.abc import AsyncGenerator
from loguru import logger

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import text
from sqlmodel import SQLModel

from kodiak.core.config import settings

engine = create_async_engine(
    settings.async_database_url,
    echo=settings.debug,
    future=True,
)


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
        async with AsyncSession(engine) as session:
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
    async with AsyncSession(engine, expire_on_commit=False) as session:
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
