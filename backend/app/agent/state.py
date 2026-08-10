"""What the agent knows while it works on one question.

A single dictionary is passed from step to step. Each step reads what it needs
and returns only the keys it changed -- LangGraph merges those in. Everything
the agent remembers about a question lives here and nowhere else, which is what
keeps one user's conversation from leaking into another's.
"""

from typing import TypedDict

from app.retrieval.results import RetrievedChunk


class AgentState(TypedDict, total=False):
    """The agent's working memory for a single question."""

    # --- Input ---
    question: str

    # Earlier turns, already trimmed, rendered as plain text. Needed because
    # follow-ups are usually unintelligible alone: "what about the .NET one?"
    # only means something next to the question before it. Empty for a first
    # question, and never carried between requests -- the client sends it.
    history: str

    # --- What it has searched so far ---
    # Every search it ran, as "tool: query". Shown to the model so it does not
    # repeat itself, and printed in logs so you can see how it reasoned.
    searches: list[str]

    # Chunks gathered across all searches, deduplicated by chunk id.
    chunks: list[RetrievedChunk]

    # --- Budget ---
    # Incremented on every search. When it reaches settings.max_tool_calls the
    # agent must stop searching and answer with whatever it has. This is the
    # guard against an agent looping forever on a question it cannot answer.
    tool_calls_used: int

    # --- Routing ---
    # "search" runs the full retrieval loop. "smalltalk" and "about" answer
    # directly without touching the knowledge base, because a greeting has
    # nothing to retrieve. Defaults to "search" whenever triage is unsure.
    route: str

    # --- What the last step decided ---
    next_tool: str  # which search to run next
    next_query: str  # what to search for
    done_searching: bool  # the model says it has enough
    grade_reason: str  # why the last results were judged weak

    # --- Output ---
    answer: str
    is_grounded: bool  # every claim traced to a chunk
    rewrite_count: int  # answers discarded for being ungrounded
    unsupported_claims: list[str]  # what the last check rejected, fed to the rewrite


def new_state(question: str, history: str = "") -> AgentState:
    """Return a fresh state for a question, with all counters at zero."""
    return AgentState(
        question=question,
        history=history,
        searches=[],
        chunks=[],
        tool_calls_used=0,
        route="search",
        next_tool="",
        next_query="",
        done_searching=False,
        grade_reason="",
        answer="",
        is_grounded=False,
        rewrite_count=0,
        unsupported_claims=[],
    )


def merge_chunks(
    existing: list[RetrievedChunk], new: list[RetrievedChunk]
) -> list[RetrievedChunk]:
    """Add new chunks to the collection, skipping ones already gathered.

    Without this, a retry that finds the same chunks again would re-send them
    to the model, burning tokens and budget for no new information.
    """
    seen = {chunk.id for chunk in existing}
    return existing + [chunk for chunk in new if chunk.id not in seen]
