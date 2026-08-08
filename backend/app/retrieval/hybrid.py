"""Hybrid search: run both retrievers and merge them with Reciprocal Rank Fusion.

Vector and keyword scores are not comparable -- cosine similarity and ts_rank
live on different scales -- so they cannot simply be added. RRF sidesteps this
by throwing away the scores and using only each result's *rank* in its own list:

    score(chunk) = sum over lists of  1 / (k + rank)

A chunk ranked well by either retriever scores well; one ranked well by both
scores best. `k` damps the influence of top ranks so a single retriever cannot
dominate the fusion; 60 is the value from the original RRF paper.
"""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.retrieval import keyword_search, vector_search
from app.retrieval.results import RetrievedChunk

logger = logging.getLogger(__name__)

# Candidates pulled from each retriever before fusion. Generous, because a
# chunk ranked 40th by one retriever and 2nd by the other is exactly the kind
# of result fusion exists to surface.
CANDIDATES_PER_RETRIEVER = 50

# Results handed back to the caller after fusion.
DEFAULT_TOP_N = 8

RRF_K = 60


def reciprocal_rank_fusion(
    ranked_lists: list[list[RetrievedChunk]],
    top_n: int,
    k: int = RRF_K,
) -> list[RetrievedChunk]:
    """Merge several ranked lists into one, using RRF scores."""
    fused_scores: dict[int, float] = {}
    chunks_by_id: dict[int, RetrievedChunk] = {}

    for ranked in ranked_lists:
        for rank, chunk in enumerate(ranked, start=1):
            fused_scores[chunk.id] = fused_scores.get(chunk.id, 0.0) + 1.0 / (k + rank)
            chunks_by_id[chunk.id] = chunk

    best = sorted(fused_scores.items(), key=lambda item: item[1], reverse=True)

    return [
        RetrievedChunk(
            id=chunks_by_id[chunk_id].id,
            repo=chunks_by_id[chunk_id].repo,
            file_path=chunks_by_id[chunk_id].file_path,
            chunk_type=chunks_by_id[chunk_id].chunk_type,
            source_url=chunks_by_id[chunk_id].source_url,
            content=chunks_by_id[chunk_id].content,
            score=score,
        )
        for chunk_id, score in best[:top_n]
    ]


async def search(
    session: AsyncSession,
    query: str,
    top_n: int = DEFAULT_TOP_N,
    chunk_type: str | None = None,
) -> list[RetrievedChunk]:
    """Retrieve with both methods and return the fused top results."""
    semantic = await vector_search.search(
        session, query, limit=CANDIDATES_PER_RETRIEVER, chunk_type=chunk_type
    )
    lexical = await keyword_search.search(
        session, query, limit=CANDIDATES_PER_RETRIEVER, chunk_type=chunk_type
    )

    logger.info(
        "hybrid search %r -> %d semantic, %d lexical candidates",
        query[:60],
        len(semantic),
        len(lexical),
    )

    return reciprocal_rank_fusion([semantic, lexical], top_n=top_n)
