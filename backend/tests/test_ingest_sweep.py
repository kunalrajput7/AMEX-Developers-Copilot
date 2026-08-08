"""Tests for the stale-chunk sweep -- the one destructive path in ingestion.

Worth its own file, and worth needing a database: this code deletes rows, and
it has already shipped one bug that silently destroyed valid content. A wrong
sweep produces no error and no crash -- just a knowledge base that is quietly
missing things. Only a real database can prove the WHERE clause is right.

Skips when Postgres is not reachable so `pytest` still works with Docker down.
CI runs it for real -- see .github/workflows/eval.yml.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import settings
from app.db.database import SCHEMA_PATH
from app.db.models import Chunk
from app.ingestion.ingest import _delete_stale, should_sweep
from tests.conftest import DATABASE_AVAILABLE, SKIP_REASON

# A repo name no real ingestion will ever produce, so these rows can be
# cleaned up by name without touching the real corpus.
TEST_REPO = "test-fixture/sweep"


@pytest.fixture
async def session():
    """Yield a database session, skipping the test if Postgres is unreachable.

    Builds its own engine with NullPool rather than reusing the application's.
    asyncpg binds a connection to the event loop that opened it, and pytest
    gives each test a fresh loop -- a pooled connection therefore fails on
    reuse in the next test. NullPool opens and closes per use, so nothing
    crosses loops.

    The skip is deliberately narrow: only an unreachable database skips. Any
    other error is a real failure and must surface, because a test that skips
    itself when something is wrong is worse than no test at all.
    """
    if not DATABASE_AVAILABLE:
        pytest.skip(SKIP_REASON)

    test_engine = create_async_engine(settings.database_url, poolclass=NullPool)

    # The tests job starts an empty Postgres, so create the schema if needed.
    async with test_engine.begin() as connection:
        raw = await connection.get_raw_connection()
        await raw.driver_connection.execute(SCHEMA_PATH.read_text(encoding="utf-8"))

    maker = async_sessionmaker(bind=test_engine, expire_on_commit=False)

    async with maker() as db:
        await db.execute(delete(Chunk).where(Chunk.repo == TEST_REPO))
        await db.commit()

        yield db

        await db.execute(delete(Chunk).where(Chunk.repo == TEST_REPO))
        await db.commit()

    await test_engine.dispose()


async def _insert(db, chunk_type: str, marker: str, ingested_at: datetime) -> None:
    """Insert one fixture chunk with a known type and timestamp."""
    db.add(
        Chunk(
            source="test",
            repo=TEST_REPO,
            file_path=f"{marker}.md",
            chunk_type=chunk_type,
            source_url=f"https://example.com/{marker}",
            content=f"content for {marker}",
            content_hash=f"hash-{marker}",
            embedding=None,
            ingested_at=ingested_at,
        )
    )
    await db.commit()


async def _remaining(db) -> set[str]:
    """Return the chunk types still present for the fixture repo."""
    result = await db.execute(select(Chunk.chunk_type).where(Chunk.repo == TEST_REPO))
    return set(result.scalars().all())


# --- the rule that decides whether sweeping is allowed at all --------------


def test_a_full_run_may_sweep() -> None:
    """With no limit, the run saw everything and can judge what is stale."""
    assert should_sweep(None) is True


def test_a_limited_run_may_not_sweep() -> None:
    """--limit means most of the repo was never looked at.

    Sweeping here would delete nearly everything, which is the opposite of
    what someone reaching for a cheap partial run wants.
    """
    assert should_sweep(20) is False
    assert should_sweep(1) is False
    assert should_sweep(0) is False


# --- the sweep itself ------------------------------------------------------


async def test_stale_chunks_of_a_loaded_type_are_deleted(session) -> None:
    """Content the run no longer produced is removed, so nothing stale is cited."""
    run_started = datetime.now(timezone.utc)
    await _insert(session, "doc", "old", run_started - timedelta(hours=1))

    deleted = await _delete_stale(session, TEST_REPO, run_started, {"doc"})
    await session.commit()

    assert deleted == 1
    assert await _remaining(session) == set()


async def test_chunks_seen_in_this_run_survive(session) -> None:
    """Anything touched by the current run is current, not stale."""
    run_started = datetime.now(timezone.utc)
    await _insert(session, "doc", "fresh", run_started)

    deleted = await _delete_stale(session, TEST_REPO, run_started, {"doc"})
    await session.commit()

    assert deleted == 0
    assert await _remaining(session) == {"doc"}


async def test_types_this_run_did_not_load_are_left_alone(session) -> None:
    """The regression test for the data-loss bug.

    A `--no-issues` run never loads issue chunks. Without scoping the delete to
    the types actually loaded, the sweep reads their absence as "deleted
    upstream" and destroys them -- which is exactly what happened once.
    """
    run_started = datetime.now(timezone.utc)
    stale = run_started - timedelta(hours=1)

    await _insert(session, "doc", "stale-doc", stale)
    await _insert(session, "code", "stale-code", stale)
    await _insert(session, "issue", "untouched-issue", stale)

    # A run that loaded docs and code, but not issues.
    deleted = await _delete_stale(session, TEST_REPO, run_started, {"doc", "code"})
    await session.commit()

    assert deleted == 2
    assert await _remaining(session) == {"issue"}


async def test_no_loaded_types_deletes_nothing(session) -> None:
    """A run that loaded nothing has no grounds to delete anything."""
    run_started = datetime.now(timezone.utc)
    await _insert(session, "doc", "safe", run_started - timedelta(hours=1))

    deleted = await _delete_stale(session, TEST_REPO, run_started, set())
    await session.commit()

    assert deleted == 0
    assert await _remaining(session) == {"doc"}


async def test_other_repos_are_never_touched(session) -> None:
    """The sweep is scoped to one repo; a sibling repo must be unaffected."""
    run_started = datetime.now(timezone.utc)
    await _insert(session, "doc", "mine", run_started - timedelta(hours=1))

    deleted = await _delete_stale(session, "some-other/repo", run_started, {"doc"})
    await session.commit()

    assert deleted == 0
    assert await _remaining(session) == {"doc"}
