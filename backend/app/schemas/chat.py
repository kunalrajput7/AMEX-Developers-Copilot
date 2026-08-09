"""Request and response shapes for the chat endpoint."""

from typing import Literal

from pydantic import BaseModel, Field

# Turns of history the agent is shown. Enough for a follow-up to make sense,
# small enough that a long session does not quietly inflate every prompt.
MAX_HISTORY_TURNS = 6


class Turn(BaseModel):
    """One earlier message in the conversation."""

    role: Literal["user", "assistant"]
    content: str = Field(max_length=8000)


class ChatRequest(BaseModel):
    """A developer's question, with whatever came before it."""

    question: str = Field(min_length=3, max_length=2000)

    # Sent by the client on every request; the server keeps no session state.
    # That is what stops one user's conversation reaching another, and it means
    # any surface can hold a conversation without the backend tracking who is
    # who. Oldest turns are dropped in `recent_history` below.
    history: list[Turn] = Field(default_factory=list, max_length=50)

    # Restrict retrieval to one part of the corpus. Mostly useful for
    # debugging and for demonstrating what each retriever contributes.
    chunk_type: str | None = Field(
        default=None, pattern="^(doc|code|issue)$", description="doc | code | issue"
    )

    def recent_history(self) -> list[Turn]:
        """Return the last few turns, oldest first.

        Trimmed rather than rejected: a long conversation should keep working,
        it just stops carrying its whole past into every prompt.
        """
        return self.history[-MAX_HISTORY_TURNS:]


class Citation(BaseModel):
    """One source backing part of an answer."""

    source_url: str
    repo: str
    file_path: str
    chunk_type: str
    snippet: str


class ChatResponse(BaseModel):
    """An answer plus the sources it was drawn from."""

    answer: str
    citations: list[Citation]

    # False when the agent could not trace every claim back to a source. The
    # answer is still returned -- callers decide whether to show a warning --
    # because hiding it would be less honest than flagging it.
    is_grounded: bool = True

    # The searches the agent chose to run. Exposed because "what did it look
    # for" is the first question anyone asks when an answer looks wrong.
    searches: list[str] = []

    retrieval_count: int = 0
