"""Lexical search: find chunks containing the question's actual words.

Uses Postgres full-text search over the generated `tsv` column and its GIN
index. This is what catches exact identifiers -- header names like
`X-Amex-Api-Key`, error codes, endpoint paths, function names -- where
embeddings are unreliable because such tokens carry little semantic signal.
"""

import logging
import re

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Chunk
from app.retrieval.results import RetrievedChunk

logger = logging.getLogger(__name__)

DEFAULT_LIMIT = 50

# Identifiers worth searching for as-is: X-Amex-Api-Key, getToken, HTTP_401.
_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_\-]{2,}")

# Parts of a hyphenated identifier shorter than this are too generic to help.
_MIN_PART_LENGTH = 3


def _to_tsquery_input(query: str) -> str:
    """Reduce a natural-language question to searchable terms, OR-ed together.

    Two things are going on here, both of which cause silent zero-result
    searches if skipped:

    1. plainto_tsquery ANDs every word, so a full question like "how do I
       authenticate with the Amex API?" matches almost nothing. OR-ing the
       identifier-ish tokens keeps recall usable.

    2. Postgres parses a hyphenated token as a *phrase* query -- searching
       `X-Amex-Api-Key` compiles to `x-amex-api-key <-> x <-> amex <-> api
       <-> key`, which needs every part present and adjacent. So hyphenated
       identifiers also contribute their individual parts. The full form still
       ranks higher where it appears, but a near miss degrades to partial
       matches instead of nothing at all.
    """
    terms: list[str] = []

    for token in _IDENTIFIER.findall(query):
        terms.append(token)
        if "-" in token:
            terms.extend(
                part for part in token.split("-") if len(part) >= _MIN_PART_LENGTH
            )

    # Preserve order while removing duplicates, so the query stays readable
    # in logs and the whole identifier comes before its fragments.
    seen: set[str] = set()
    unique = [term for term in terms if not (term.lower() in seen or seen.add(term.lower()))]

    return " or ".join(unique) if unique else query


async def search(
    session: AsyncSession,
    query: str,
    limit: int = DEFAULT_LIMIT,
    chunk_type: str | None = None,
) -> list[RetrievedChunk]:
    """Return the chunks whose text best matches the query's terms."""
    ts_query = func.websearch_to_tsquery("english", _to_tsquery_input(query))
    rank = func.ts_rank(Chunk.tsv, ts_query).label("rank")

    statement = (
        select(Chunk, rank)
        .where(Chunk.tsv.op("@@")(ts_query))
        .order_by(rank.desc())
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
            score=float(chunk_rank),
        )
        for chunk, chunk_rank in rows
    ]
