"""The chat endpoints.

Two ways to ask the same agent the same question:

  POST /chat         wait for the finished answer as JSON. Used by the CLI and
                     the evaluation harness, where a single result is wanted.
  POST /chat/stream  server-sent events reporting each step as it happens, then
                     the answer. Used by the web app, so the user can see what
                     the agent is doing during the several seconds it takes.
"""

import json
import logging
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.citations import keep_cited_sources
from app.agent.graph import answer_question, stream_question
from app.agent.state import AgentState
from app.db.database import get_session
from app.retrieval.results import RetrievedChunk
from app.schemas.chat import ChatRequest, ChatResponse, Citation

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])

# What each agent step is called in the UI.
STEP_LABELS = {
    "decide": "Deciding what to look for",
    "retrieve": "Searching the knowledge base",
    "grade": "Checking whether the sources are enough",
    "generate": "Writing the answer",
    "check_citations": "Verifying every claim is cited",
}


def to_citations(chunks: list[RetrievedChunk]) -> list[Citation]:
    """Convert retrieved chunks into the response's citation shape."""
    return [
        Citation(
            source_url=chunk.source_url,
            repo=chunk.repo,
            file_path=chunk.file_path,
            chunk_type=chunk.chunk_type,
            snippet=chunk.snippet(),
        )
        for chunk in chunks
    ]


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    session: AsyncSession = Depends(get_session),
) -> ChatResponse:
    """Answer a developer question from the knowledge base, with citations."""
    answer, chunks, state = await answer_question(session, request.question)

    return ChatResponse(
        answer=answer,
        citations=to_citations(chunks),
        retrieval_count=len(chunks),
        searches=state.get("searches", []),
        is_grounded=bool(state.get("is_grounded")),
    )


def sse(event: dict) -> str:
    """Format one dict as a server-sent event."""
    return f"data: {json.dumps(event)}\n\n"


async def event_stream(
    session: AsyncSession, question: str
) -> AsyncIterator[str]:
    """Yield SSE events describing the agent's progress, then its answer."""
    state: AgentState = {}

    try:
        async for step_name, state in stream_question(session, question):
            label = STEP_LABELS.get(step_name, step_name)

            # The searches list is the most informative progress detail, so
            # show the query the agent actually just ran.
            detail = ""
            if step_name == "retrieve" and state.get("searches"):
                detail = state["searches"][-1]

            yield sse({"type": "step", "step": step_name, "label": label, "detail": detail})

        answer, chunks = keep_cited_sources(
            state.get("answer", ""), state.get("chunks", [])
        )

        yield sse(
            {
                "type": "answer",
                "answer": answer,
                "citations": [citation.model_dump() for citation in to_citations(chunks)],
                "is_grounded": bool(state.get("is_grounded")),
                "searches": state.get("searches", []),
            }
        )

    except Exception as exc:
        # A dropped stream with no explanation is the worst failure mode for a
        # UI, so errors are sent as an event rather than closing the connection.
        logger.exception("Agent failed while streaming")
        yield sse({"type": "error", "message": str(exc)})


@router.post("/chat/stream")
async def chat_stream(
    request: ChatRequest,
    session: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    """Answer a question, reporting each step of the agent as it happens."""
    return StreamingResponse(
        event_stream(session, request.question),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
