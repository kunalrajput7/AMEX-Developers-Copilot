"""Orchestrates ingestion: load -> chunk -> hash -> skip known -> embed -> store.

The hash-and-skip step is what makes re-running cheap: unchanged chunks are
never re-embedded. The freshness sweep is what keeps the corpus honest: chunks
whose source file changed or disappeared are deleted, so the agent can never
cite content that no longer exists.
"""

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import delete, insert, select, update

from app.db.database import SessionLocal
from app.db.models import Chunk as ChunkRow
from app.ingestion import chunker, embedder, github_loader
from app.ingestion.chunker import Chunk
from app.ingestion.repos import REPOS, RepoSpec

logger = logging.getLogger(__name__)


@dataclass
class RepoResult:
    """What happened for one repository during an ingestion run."""

    repo: str
    documents: int = 0
    chunks_seen: int = 0
    chunks_added: int = 0
    chunks_skipped: int = 0
    chunks_deleted: int = 0
    files_skipped: dict[str, int] = field(default_factory=dict)
    error: str | None = None


def content_hash(chunk: Chunk) -> str:
    """Return a stable hash identifying this chunk's content and origin.

    Origin is part of the hash on purpose. Two repos can legitimately contain
    the same licence text or boilerplate, and both should be retrievable with
    their own citation rather than one silently shadowing the other.
    """
    payload = f"{chunk.repo}\x00{chunk.file_path}\x00{chunk.content}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


async def _existing_hashes(session, repo: str) -> set[str]:
    """Return the content hashes already stored for a repository."""
    result = await session.execute(
        select(ChunkRow.content_hash).where(ChunkRow.repo == repo)
    )
    return set(result.scalars().all())


async def _touch(session, hashes: list[str], run_started: datetime) -> None:
    """Mark unchanged chunks as seen in this run so the sweep spares them."""
    if not hashes:
        return

    # Chunked to keep parameter lists a sane size for very large repos.
    for start in range(0, len(hashes), 1000):
        await session.execute(
            update(ChunkRow)
            .where(ChunkRow.content_hash.in_(hashes[start : start + 1000]))
            .values(ingested_at=run_started)
        )


def should_sweep(limit: int | None) -> bool:
    """Return True if this run is entitled to delete stale chunks.

    A limited run only looked at part of the repo, so it cannot tell what is
    stale -- everything it skipped would look deleted. This is a named function
    rather than an inline check because getting it wrong destroys data silently,
    and a rule with a name is a rule with a test.
    """
    return limit is None


async def _delete_stale(
    session, repo: str, run_started: datetime, chunk_types: set[str]
) -> int:
    """Delete chunks this run did not see, within the types it actually loaded.

    Scoping by chunk_type matters: a run with --no-issues never loads issue
    chunks, and without this filter the sweep would read their absence as
    "deleted upstream" and destroy them. Same for any future partial source.
    """
    if not chunk_types:
        return 0

    result = await session.execute(
        delete(ChunkRow)
        .where(ChunkRow.repo == repo)
        .where(ChunkRow.chunk_type.in_(chunk_types))
        .where(ChunkRow.ingested_at < run_started)
    )
    return result.rowcount or 0


async def ingest_repo(
    repo: RepoSpec,
    include_issues: bool = True,
    limit: int | None = None,
    dry_run: bool = False,
) -> RepoResult:
    """Ingest one repository. With dry_run, nothing is embedded or written."""
    result = RepoResult(repo=repo.full_name)
    run_started = datetime.now(timezone.utc)

    documents, files_skipped = github_loader.load_repo(repo, include_issues=include_issues)
    result.documents = len(documents)
    result.files_skipped = files_skipped

    # Recorded before any limit is applied, so the freshness sweep knows which
    # kinds of content this run is entitled to have an opinion about.
    loaded_chunk_types = {document.chunk_type for document in documents}

    chunks = chunker.chunk_documents(documents)
    if limit is not None:
        chunks = chunks[:limit]
    result.chunks_seen = len(chunks)

    if dry_run:
        return result

    async with SessionLocal() as session:
        known = await _existing_hashes(session, repo.full_name)

        new_chunks: list[Chunk] = []
        new_hashes: set[str] = set()
        unchanged: list[str] = []

        for chunk in chunks:
            digest = content_hash(chunk)
            if digest in known:
                unchanged.append(digest)
            elif digest not in new_hashes:
                # Guard against duplicate chunks within a single run, which
                # would violate the UNIQUE constraint on content_hash.
                new_hashes.add(digest)
                new_chunks.append(chunk)

        result.chunks_skipped = len(unchanged)

        await _touch(session, unchanged, run_started)

        if new_chunks:
            logger.info(
                "%s: embedding %d new chunks (%d unchanged)",
                repo.full_name,
                len(new_chunks),
                len(unchanged),
            )
            vectors = await embedder.embed_all([chunk.content for chunk in new_chunks])

            rows = [
                {
                    "source": chunk.source,
                    "repo": chunk.repo,
                    "file_path": chunk.file_path,
                    "chunk_type": chunk.chunk_type,
                    "source_url": chunk.source_url,
                    "content": chunk.content,
                    "content_hash": content_hash(chunk),
                    "embedding": vector,
                    "ingested_at": run_started,
                }
                for chunk, vector in zip(new_chunks, vectors)
            ]
            await session.execute(insert(ChunkRow), rows)
            result.chunks_added = len(rows)

        if should_sweep(limit):
            result.chunks_deleted = await _delete_stale(
                session, repo.full_name, run_started, loaded_chunk_types
            )
        else:
            logger.info(
                "%s: skipping stale cleanup because --limit was used",
                repo.full_name,
            )

        await session.commit()

    return result


async def ingest_all(
    repos: list[RepoSpec] | None = None,
    include_issues: bool = True,
    limit: int | None = None,
    dry_run: bool = False,
) -> list[RepoResult]:
    """Ingest every configured repository, continuing past individual failures."""
    results: list[RepoResult] = []

    for repo in repos or REPOS:
        try:
            results.append(
                await ingest_repo(
                    repo,
                    include_issues=include_issues,
                    limit=limit,
                    dry_run=dry_run,
                )
            )
        except Exception as exc:
            # One unreachable repo should not abandon the whole corpus.
            logger.error("Failed to ingest %s: %s", repo.full_name, exc)
            results.append(RepoResult(repo=repo.full_name, error=str(exc)))

    return results
