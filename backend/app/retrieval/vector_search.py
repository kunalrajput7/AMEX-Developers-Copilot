"""Semantic search: find chunks whose meaning is closest to the question.

Uses pgvector's cosine distance over the HNSW index. Good at questions phrased
differently from the source text ("how do I log in" finding "authentication"),
weak at exact identifiers -- which is what keyword_search.py is for.
"""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Chunk
from app.llm import embedding_client
from app.retrieval.results import RetrievedChunk

logger = logging.getLogger(__name__)

DEFAULT_LIMIT = 50


async def search(
    session: AsyncSession,
    query: str,
    limit: int = DEFAULT_LIMIT,
    chunk_type: str | None = None,
) -> list[RetrievedChunk]:
    """Return the chunks most semantically similar to the query.

    `chunk_type` filters to 'doc', 'code', or 'issue' -- this is what lets the
    agent's three search tools target different parts of the corpus.
    """
    vectors = await embedding_client.embed_texts([query])
    if not vectors:
        return []

    query_vector = vectors[0]

    # Cosine distance: 0 means identical, 2 means opposite.
    distance = Chunk.embedding.cosine_distance(query_vector).label("distance")

    statement = (
        select(Chunk, distance)
        .where(Chunk.embedding.isnot(None))
        .order_by(distance)
        .limit(limit)
    )
    if chunk_type is not None:
        statement = statement.where(Chunk.chunk_type == chunk_type)

    rows = (await session.execute(statement)).all()

    return [
        RetrievedChunk(
            id=chunk.id,
            repo=chunk.repo,
            file_path=chunk.file_path,
            chunk_type=chunk.chunk_type,
            source_url=chunk.source_url,
            content=chunk.content,
            # Report similarity rather than distance, so higher is always better.
            score=1.0 - float(chunk_distance),
        )
        for chunk, chunk_distance in rows
    ]
