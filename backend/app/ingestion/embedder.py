"""Turn chunk texts into vectors, in batches, with retries.

Batching matters: one request per chunk would be both slow and expensive in
request overhead. Retries matter because Azure rate-limits under load.
"""

import asyncio
import logging
from collections.abc import Callable

from app.llm import embedding_client

logger = logging.getLogger(__name__)

# Azure accepts large batches, but smaller ones fail less often and give
# more granular progress reporting.
BATCH_SIZE = 64

MAX_RETRIES = 4
INITIAL_BACKOFF_SECONDS = 2.0


async def _embed_batch_with_retry(texts: list[str]) -> list[list[float]]:
    """Embed one batch, backing off exponentially on transient failures."""
    backoff = INITIAL_BACKOFF_SECONDS

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return await embedding_client.embed_texts(texts)
        except Exception as exc:
            if attempt == MAX_RETRIES:
                raise
            logger.warning(
                "Embedding batch failed (attempt %d/%d): %s. Retrying in %.0fs.",
                attempt,
                MAX_RETRIES,
                exc,
                backoff,
            )
            await asyncio.sleep(backoff)
            backoff *= 2

    return []  # unreachable, but keeps the type checker happy


async def embed_all(
    texts: list[str],
    on_progress: Callable[[int, int], None] | None = None,
) -> list[list[float]]:
    """Embed every text, in batches, returning vectors in the original order."""
    vectors: list[list[float]] = []

    for start in range(0, len(texts), BATCH_SIZE):
        batch = texts[start : start + BATCH_SIZE]
        vectors.extend(await _embed_batch_with_retry(batch))

        if on_progress is not None:
            on_progress(len(vectors), len(texts))

    return vectors
