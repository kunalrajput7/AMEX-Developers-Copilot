"""Async database engine, session factory, and schema bootstrap.

Every database connection in the project comes from here.
"""

import asyncio
import logging
from collections.abc import AsyncIterator
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import settings

logger = logging.getLogger(__name__)

SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"

# Postgres in Docker can take a few seconds to accept connections after the
# container starts, so startup retries rather than failing on the first attempt.
CONNECT_RETRIES = 10
CONNECT_RETRY_DELAY_SECONDS = 1.5

engine: AsyncEngine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_pre_ping=True,
)

SessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_session() -> AsyncIterator[AsyncSession]:
    """Yield a database session, closing it when the caller is done."""
    async with SessionLocal() as session:
        yield session


async def _run_sql_script(sql: str) -> None:
    """Execute a multi-statement SQL script in one transaction.

    Runs through the raw asyncpg connection because asyncpg's prepared-statement
    path (what SQLAlchemy uses by default) rejects scripts containing more than
    one statement. Splitting the script on ';' ourselves is not safe -- comments
    and string literals can contain semicolons.
    """
    async with engine.begin() as connection:
        raw_connection = await connection.get_raw_connection()
        await raw_connection.driver_connection.execute(sql)


async def apply_schema() -> None:
    """Create the pgvector extension, tables, and indexes if they do not exist.

    Retries while Postgres is still starting up. Raises if the database stays
    unreachable, or immediately if the schema itself is invalid.
    """
    sql = SCHEMA_PATH.read_text(encoding="utf-8")

    for attempt in range(1, CONNECT_RETRIES + 1):
        try:
            await _run_sql_script(sql)
            return
        except (ConnectionError, OSError) as exc:
            # Postgres is not accepting connections yet -- worth retrying.
            if attempt == CONNECT_RETRIES:
                raise RuntimeError(
                    f"Could not reach Postgres at {settings.database_url} after "
                    f"{CONNECT_RETRIES} attempts. Is it running? Try: docker compose up -d"
                ) from exc
            logger.info(
                "Waiting for Postgres (attempt %d/%d)...", attempt, CONNECT_RETRIES
            )
            await asyncio.sleep(CONNECT_RETRY_DELAY_SECONDS)


async def ping() -> bool:
    """Return True if the database answers a trivial query."""
    async with engine.connect() as connection:
        result = await connection.execute(text("SELECT 1"))
        return result.scalar() == 1


async def schema_is_ready() -> bool:
    """Return True if the chunks table exists, meaning the schema was applied."""
    async with engine.connect() as connection:
        result = await connection.execute(text("SELECT to_regclass('public.chunks')"))
        return result.scalar() is not None
