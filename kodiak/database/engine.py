import inspect
from collections.abc import AsyncGenerator
from loguru import logger

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import text, event
from sqlalchemy.pool import NullPool
from sqlmodel import SQLModel

from kodiak.core.config import settings


class SchemaMigrationRequired(Exception):
    """Raised when the database schema doesn't match the expected model."""
    pass


def _create_engine():
    """Create the async database engine with appropriate settings for the database type."""
    connect_args = {}
    engine_kwargs: dict = {
        "echo": settings.debug,
        "future": True,
    }

    if settings.is_sqlite:
        connect_args = {"check_same_thread": False}
        # Each AsyncSession gets its own connection so concurrent sessions
        # never share a connection object and cannot corrupt each other's
        # transaction state machine.
        engine_kwargs["poolclass"] = NullPool
        logger.info(f"Using SQLite database at: {settings.sqlite_path or '~/.kodiak/kodiak.db'}")
    else:
        logger.info(f"Using PostgreSQL database at: {settings.postgres_server}:{settings.postgres_port}/{settings.postgres_db}")

    engine_kwargs["connect_args"] = connect_args
    eng = create_async_engine(settings.async_database_url, **engine_kwargs)

    if settings.is_sqlite:
        # WAL mode: allows concurrent readers alongside a single writer so
        # multiple agents do not starve each other on SELECT while one is
        # committing.  busy_timeout: instead of immediately raising
        # "database is locked", SQLite waits up to N ms for the lock to be
        # released — prevents the OperationalError that propagates through
        # SQLAlchemy and triggers rollback() during _prepare_impl().
        @event.listens_for(eng.sync_engine, "connect")
        def _set_sqlite_pragmas(dbapi_conn, _connection_record):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.close()

    return eng



_engine = None


def get_engine():
    """Lazily create and return the database engine."""
    global _engine
    if _engine is None:
        _engine = _create_engine()
    return _engine


class _EngineProxy:
    """Compatibility proxy that always delegates to the canonical engine."""

    def __getattr__(self, name):
        return getattr(get_engine(), name)


engine = _EngineProxy()


async def init_db():
    """
    Initialize the database by creating all tables.
    This function ensures all SQLModel tables are created properly.
    """
    try:
        logger.info("Initializing database...")
        
        async with get_engine().begin() as conn:
            # Import all models to ensure they're registered with SQLModel metadata
            from kodiak.database import models  # noqa
            
            if settings.is_sqlite:
                await _validate_sqlite_schema(conn)
            
            # Create all tables
            await conn.run_sync(SQLModel.metadata.create_all)
            
        logger.info("Database initialization completed successfully")
        
        # Verify database connectivity
        await verify_database_connectivity()
        
    except SQLAlchemyError as e:
        logger.error(f"Database initialization failed: {e}")
        raise
    except SchemaMigrationRequired as e:
        logger.error(str(e))
        raise
    except Exception as e:
        logger.error(f"Unexpected error during database initialization: {e}")
        raise


async def _validate_sqlite_schema(conn) -> None:
    """Validate that the SQLite schema.
    
    Fails fast matches the expected WorkUnit shape with explicit guidance if the schema is legacy (has targets_json/targets_hash)
    or missing required columns. Old databases should be reset, not migrated.
    """
    try:
        result = conn.execute(text("PRAGMA table_info(workunit)"))
        if inspect.isawaitable(result):
            result = await result
        columns = {row[1] for row in result.fetchall()}
    except SQLAlchemyError:
        return

    # Fresh databases may not have created tables yet during bootstrap.
    if not columns:
        return
    
    legacy_columns = {"targets_json", "targets_hash"}
    if legacy_columns.intersection(columns):
        raise SchemaMigrationRequired(
            "Legacy WorkUnit schema detected (has targets_json/targets_hash columns). "
            "The multi-agent kernel requires a fresh schema. "
            "Run: kodiak migrate --reset"
        )
    
    required_columns = {"target", "target_kind", "tool_family", "scope_key"}
    missing = required_columns - columns
    if missing:
        raise SchemaMigrationRequired(
            f"WorkUnit schema is incomplete. Missing columns: {', '.join(missing)}. "
            "The database may be corrupted or from an incompatible version. "
            "Run: kodiak migrate --reset"
        )


async def reset_database() -> None:
    """Destructively reset the database by dropping all tables and recreating.
    
    This is the only supported path for migrating to the multi-agent kernel schema.
    """
    global _engine
    
    logger.warning("🔄 Starting database reset...")
    
    if not settings.is_sqlite:
        raise SchemaMigrationRequired(
            "Database reset is only supported for SQLite. "
            "For PostgreSQL, manually run: DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
        )
    
    try:
        async with get_engine().begin() as conn:
            from kodiak.database import models as _models  # noqa: F401
            await conn.run_sync(SQLModel.metadata.drop_all)
            await conn.run_sync(SQLModel.metadata.create_all)
        
        logger.info("✅ Database reset complete")
        
    except SQLAlchemyError as e:
        logger.error(f"Database reset failed: {e}")
        raise SchemaMigrationRequired(f"Database reset failed: {e}")



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
    # autoflush=False: prevents SELECT queries from triggering an implicit
    # flush mid-transaction, which can cause "Session.add() during flush"
    # SAWarnings and downstream state-machine errors when concurrent agents
    # share the event loop.  All write paths explicitly call commit().
    async with AsyncSession(get_engine(), expire_on_commit=False, autoflush=False) as session:
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
