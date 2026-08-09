"""The five steps the agent can take.

Each function takes the current state and returns only the keys it changed.
They are plain async functions -- graph.py is what connects them into a loop.
"""

import json
import logging
import re

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent import prompts, tools
from app.agent.state import AgentState, merge_chunks
from app.config import settings
from app.llm import chat_client
from app.retrieval.results import format_for_prompt

logger = logging.getLogger(__name__)

# How many times an ungrounded answer may be thrown away and rewritten.
MAX_REWRITES = 1

_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)


def history_block(state: AgentState) -> str:
    """Render earlier turns for a prompt, or an empty string on a first question."""
    history = state.get("history", "")
    return prompts.HISTORY_BLOCK.format(history=history) if history else ""


def parse_json_reply(text: str) -> dict:
    """Pull a JSON object out of a model reply.

    Models often wrap JSON in prose or a markdown fence, so we take the outermost
    braces rather than assuming the whole reply is JSON. Returns an empty dict if
    nothing parses -- callers treat that as "no decision" and fall back safely.
    """
    match = _JSON_BLOCK.search(text)
    if not match:
        logger.warning("No JSON found in model reply: %r", text[:200])
        return {}

    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        logger.warning("Malformed JSON in model reply: %r", match.group(0)[:200])
        return {}


async def decide(state: AgentState) -> dict:
    """Choose the next search to run, or declare the gathered sources enough."""
    searches = state.get("searches", [])
    grade_reason = state.get("grade_reason", "")

    prompt = prompts.DECIDE.format(
        question=state["question"],
        history_block=history_block(state),
        tools=tools.tool_descriptions(),
        searches="\n".join(f"- {entry}" for entry in searches) or "(none yet)",
        chunk_count=len(state.get("chunks", [])),
        grade_note=f"\nThe last results were weak because: {grade_reason}"
        if grade_reason
        else "",
    )

    reply = await chat_client.chat_text([{"role": "user", "content": prompt}])
    decision = parse_json_reply(reply)

    if decision.get("done"):
        logger.info("decide -> done (%s)", decision.get("reasoning", ""))
        return {"done_searching": True}

    tool_name = decision.get("tool", "")
    query = decision.get("query", "")

    # A hallucinated tool name or empty query means the model gave us nothing
    # usable. Stop searching rather than guessing on its behalf.
    if not tools.is_valid_tool(tool_name) or not query:
        logger.warning("decide -> unusable choice %r/%r, stopping search", tool_name, query)
        return {"done_searching": True}

    logger.info("decide -> %s(%r) because %s", tool_name, query, decision.get("reasoning", ""))
    return {"next_tool": tool_name, "next_query": query, "done_searching": False}


async def retrieve(state: AgentState, session: AsyncSession) -> dict:
    """Run the chosen search and add anything new to the gathered chunks."""
    tool_name = state["next_tool"]
    query = state["next_query"]

    found = await tools.run_tool(session, tool_name, query)
    merged = merge_chunks(state.get("chunks", []), found)

    added = len(merged) - len(state.get("chunks", []))
    logger.info("retrieve -> %s found %d, %d new", tool_name, len(found), added)

    return {
        "chunks": merged,
        "searches": state.get("searches", []) + [f"{tool_name}: {query}"],
        "tool_calls_used": state.get("tool_calls_used", 0) + 1,
    }


async def grade(state: AgentState) -> dict:
    """Judge whether the gathered sources can actually answer the question."""
    chunks = state.get("chunks", [])
    if not chunks:
        return {"grade_reason": "no sources found yet"}

    # The searches so far are part of the judgement: one search returning
    # loosely-related files is a weaker position than three that converged.
    searches = state.get("searches", [])
    prompt = prompts.GRADE.format(
        question=state["question"],
        searches="\n".join(f"- {entry}" for entry in searches) or "(none)",
        context=format_for_prompt(chunks),
    )

    reply = await chat_client.chat_text([{"role": "user", "content": prompt}])
    verdict = parse_json_reply(reply)

    sufficient = bool(verdict.get("sufficient"))
    reason = verdict.get("reason", "")

    logger.info("grade -> sufficient=%s (%s)", sufficient, reason)

    if sufficient:
        return {"done_searching": True, "grade_reason": ""}

    return {"done_searching": False, "grade_reason": reason}


async def generate(state: AgentState) -> dict:
    """Write the answer from the gathered sources."""
    chunks = state.get("chunks", [])

    if not chunks:
        return {
            "answer": (
                "I could not find anything relevant in the indexed American "
                "Express repositories for that question."
            ),
            "is_grounded": True,
        }

    # On a rewrite, tell the model exactly which claims were rejected. Without
    # this it rewrites from the same sources and repeats the same mistake.
    unsupported = state.get("unsupported_claims", [])
    revision_note = (
        prompts.REVISION_NOTE.format(
            claims="\n".join(f"- {claim}" for claim in unsupported)
        )
        if unsupported
        else ""
    )

    reply = await chat_client.chat(
        [
            {
                "role": "user",
                "content": prompts.ANSWER_USER.format(
                    context=format_for_prompt(chunks),
                    history_block=history_block(state),
                    question=state["question"],
                    revision_note=revision_note,
                ),
            }
        ],
        system=prompts.ANSWER_SYSTEM,
    )

    logger.info("generate -> %d chars, %d output tokens", len(reply.text), reply.output_tokens)
    return {"answer": reply.text}


async def check_citations(state: AgentState) -> dict:
    """Verify every claim in the answer traces back to a source."""
    chunks = state.get("chunks", [])
    if not chunks:
        return {"is_grounded": True}

    prompt = prompts.CHECK_CITATIONS.format(
        context=format_for_prompt(chunks),
        answer=state.get("answer", ""),
    )

    reply = await chat_client.chat_text([{"role": "user", "content": prompt}])
    verdict = parse_json_reply(reply)

    # Default to grounded when the check itself fails to parse. The alternative
    # -- discarding a good answer because the checker misbehaved -- is worse.
    grounded = bool(verdict.get("grounded", True))
    unsupported = verdict.get("unsupported_claims", [])

    if not grounded:
        logger.info("check_citations -> ungrounded: %s", unsupported)
        return {
            "is_grounded": False,
            "rewrite_count": state.get("rewrite_count", 0) + 1,
            "grade_reason": f"unsupported claims: {'; '.join(unsupported)[:200]}",
            "unsupported_claims": unsupported,
        }

    logger.info("check_citations -> grounded")
    return {"is_grounded": True, "unsupported_claims": []}


def budget_exhausted(state: AgentState) -> bool:
    """Return True once the agent has used all its allowed searches."""
    return state.get("tool_calls_used", 0) >= settings.max_tool_calls
