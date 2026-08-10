"""Tests for routing a message to the search loop or to a direct reply.

The classification itself needs a model, so it is not tested here. What is
tested is the part that must never go wrong regardless of what the model says:
an unrecognised or malformed answer has to fall back to searching. Skipping
retrieval wrongly means answering a technical question from nothing.
"""

from app.agent.graph import after_triage
from app.agent.nodes import DIRECT_ROUTES, SEARCH_ROUTE
from app.agent.state import new_state


def test_a_new_state_searches_by_default() -> None:
    """Nothing has classified the message yet, so the safe route is retrieval."""
    assert new_state("How do I authenticate?")["route"] == SEARCH_ROUTE


def test_search_route_enters_the_retrieval_loop() -> None:
    assert after_triage({"route": SEARCH_ROUTE}) == "decide"


def test_conversational_routes_skip_retrieval() -> None:
    """Greetings and questions about the assistant have nothing to look up."""
    for route in DIRECT_ROUTES:
        assert after_triage({"route": route}) == "respond"


def test_an_unknown_route_searches_rather_than_replying_blind() -> None:
    """A hallucinated or missing route must not bypass the knowledge base.

    This is the failure that matters: replying directly to a real question
    produces a confident answer with no sources behind it, which is exactly
    what the rest of the agent exists to prevent.
    """
    for route in ["", "chitchat", "SMALLTALK", None]:
        assert after_triage({"route": route}) == "decide"

    assert after_triage({}) == "decide"
