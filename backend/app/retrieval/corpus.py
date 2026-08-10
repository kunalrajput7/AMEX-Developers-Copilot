"""What is actually in the knowledge base.

Used when the assistant talks about itself. Asked "who are you", a model will
happily name American Express projects it remembers from training -- One App,
Holocron -- whether or not they were ever indexed. That invites a question the
agent can only refuse, and it is the same invented-detail problem the citation
check exists to catch, arriving on the one path that skips retrieval.

Reading the repo list from the database keeps the claim true by construction.
"""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def list_repos(session: AsyncSession) -> list[str]:
    """Return the indexed repositories, most thoroughly indexed first."""
    result = await session.execute(
        text(
            "SELECT repo FROM chunks GROUP BY repo ORDER BY COUNT(*) DESC"
        )
    )
    return [row[0] for row in result]
