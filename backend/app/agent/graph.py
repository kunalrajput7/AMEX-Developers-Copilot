"""How the five steps connect.

The loop, in words:

    decide what to search for
      -> run the search
      -> grade what came back
      -> good enough? write the answer. otherwise decide again.
    write the answer
      -> check every claim is cited
      -> grounded? done. otherwise search again and rewrite.

Every path out of `decide` and `check_citations` is bounded, so the agent
always terminates: it runs out of search budget, or out of rewrites, or both.
"""

import logging
from collections.abc import AsyncIterator
from functools import partial

from langgraph.graph import END, START, StateGraph
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent import nodes
from app.agent.citations import keep_cited_sources
from app.agent.state import AgentState, new_state
from app.retrieval.results import RetrievedChunk

logger = logging.getLogger(__name__)


def after_decide(state: AgentState) -> str:
    """Search again, or stop and answer."""
    if state.get("done_searching") or nodes.budget_exhausted(state):
        return "generate"
    return "retrieve"


def after_grade(state: AgentState) -> str:
    """Answer if the sources are good enough or the budget is spent."""
    if state.get("done_searching") or nodes.budget_exhausted(state):
        return "generate"
    return "decide"


def after_check(state: AgentState) -> str:
    """Finish, or go looking for better sources and rewrite.

    Rewriting needs new material to work with, so an ungrounded answer sends
    the agent back to `decide` rather than straight to `generate` -- otherwise
    it would rewrite from the same sources and reach the same conclusion.
    """
    if state.get("is_grounded"):
        return END
    if state.get("rewrite_count", 0) > nodes.MAX_REWRITES:
        logger.info("giving up on grounding after %d rewrites", state["rewrite_count"])
        return END
    if nodes.budget_exhausted(state):
        return END
    return "decide"


def build_graph(session: AsyncSession):
    """Wire the nodes into a runnable graph.

    The database session is bound here so the node functions stay plain
    functions of state, which keeps them easy to read and to test.
    """
    graph = StateGraph(AgentState)

    graph.add_node("decide", nodes.decide)
    graph.add_node("retrieve", partial(nodes.retrieve, session=session))
    graph.add_node("grade", nodes.grade)
    graph.add_node("generate", nodes.generate)
    graph.add_node("check_citations", nodes.check_citations)

    graph.add_edge(START, "decide")
    graph.add_conditional_edges("decide", after_decide, ["retrieve", "generate"])
    graph.add_edge("retrieve", "grade")
    graph.add_conditional_edges("grade", after_grade, ["decide", "generate"])
    graph.add_edge("generate", "check_citations")
    graph.add_conditional_edges("check_citations", after_check, ["decide", END])

    return graph.compile()


async def answer_question(
    session: AsyncSession, question: str, history: str = ""
) -> tuple[str, list[RetrievedChunk], AgentState]:
    """Run the agent over one question, optionally in the context of earlier ones.

    Returns the answer, the sources it used, and the final state -- the state
    is what the caller logs to show how the agent got there.
    """
    graph = build_graph(session)

    # Each question starts from a fresh state. Any conversation history comes in
    # from the caller rather than a server-side store, so nothing carries over
    # between requests or between users on its own.
    final: AgentState = await graph.ainvoke(new_state(question, history))

    # The agent reads more than it uses. Show only what the answer cites, so a
    # listed source always means "this backs the answer".
    answer, sources = keep_cited_sources(
        final.get("answer", ""), final.get("chunks", [])
    )

    logger.info(
        "agent finished: %d searches, %d sources read, %d cited, grounded=%s",
        final.get("tool_calls_used", 0),
        len(final.get("chunks", [])),
        len(sources),
        final.get("is_grounded"),
    )

    return answer, sources, final


async def stream_question(
    session: AsyncSession, question: str, history: str = ""
) -> AsyncIterator[tuple[str, AgentState]]:
    """Run the agent, yielding (step name, state so far) as each step finishes.

    An agent takes many seconds and several model calls, so the useful thing to
    stream is its progress -- "searching code", "checking citations" -- rather
    than tokens. The caller turns these into events for the UI.
    """
    graph = build_graph(session)
    state = new_state(question, history)

    async for step in graph.astream(state, stream_mode="updates"):
        for step_name, update in step.items():
            state.update(update)
            yield step_name, state
