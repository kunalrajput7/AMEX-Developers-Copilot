"""The three searches the agent is allowed to run.

Each one is hybrid search restricted to one part of the corpus. Splitting them
up lets the agent aim: a "how do I configure X" question wants docs, a "why
does this throw" question often wants closed issues.

These are the agent's ONLY capabilities. They read the knowledge base and
nothing else -- no writes, no shell, no network. An agent that cannot reach
anything dangerous does not need to be trusted not to.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.retrieval import hybrid
from app.retrieval.results import RetrievedChunk

# Results returned per search. Small on purpose: the agent can search again if
# it needs more, and a smaller set keeps the grading step honest.
RESULTS_PER_SEARCH = 6

# tool name -> (chunk_type it searches, description shown to the model)
TOOLS: dict[str, tuple[str, str]] = {
    "search_docs": (
        "doc",
        "READMEs and documentation. Start here for anything a library "
        "documents about itself: setup, configuration, options, error types "
        "it defines, what it supports, and 'how do I' questions. If the "
        "answer would plausibly appear in a README, this is the tool.",
    ),
    "search_code": (
        "code",
        "Source code. Best when you need the implementation itself -- a "
        "function's exact signature, internal behaviour, or a concrete usage "
        "example. Weaker for questions a README already answers, because a "
        "matching filename is not the same as a matching answer.",
    ),
    "search_issues": (
        "issue",
        "Closed GitHub issues. Best for a specific failure someone else hit: "
        "a stack trace, a version conflict, surprising behaviour. Not for "
        "questions about which errors a library defines -- that is documented.",
    ),
}


def tool_descriptions() -> str:
    """Return the tool list as text, for the decide prompt."""
    return "\n".join(f"- {name}: {description}" for name, (_, description) in TOOLS.items())


def is_valid_tool(name: str) -> bool:
    """Return True if the name is one of the three allowed searches.

    The model picks tool names, so this is the check that stops a hallucinated
    name from reaching the database layer.
    """
    return name in TOOLS


async def run_tool(
    session: AsyncSession, tool_name: str, query: str
) -> list[RetrievedChunk]:
    """Run one search and return its results.

    Raises on an unknown tool rather than silently returning nothing, so a bad
    tool name shows up as an error instead of an unexplained empty answer.
    """
    if not is_valid_tool(tool_name):
        raise ValueError(
            f"Unknown tool {tool_name!r}. Allowed: {', '.join(TOOLS)}"
        )

    chunk_type, _ = TOOLS[tool_name]
    return await hybrid.search(
        session, query, top_n=RESULTS_PER_SEARCH, chunk_type=chunk_type
    )
