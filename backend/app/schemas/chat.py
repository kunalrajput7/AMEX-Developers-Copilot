"""Request and response shapes for the chat endpoint."""

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """A developer's question."""

    question: str = Field(min_length=3, max_length=2000)

    # Restrict retrieval to one part of the corpus. Mostly useful for
    # debugging and for demonstrating what each retriever contributes.
    chunk_type: str | None = Field(
        default=None, pattern="^(doc|code|issue)$", description="doc | code | issue"
    )


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
