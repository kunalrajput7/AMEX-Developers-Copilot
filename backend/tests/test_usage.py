"""Tests for per-request usage and cost accounting."""

from app.config import settings
from app.observability import usage


def test_no_tracking_outside_a_request_is_not_an_error() -> None:
    """CLI scripts call the model clients with no request around them."""
    usage._current.set(None)

    usage.record_chat(100, 50)
    usage.record_embedding(10)

    assert usage.current() is None


def test_calls_accumulate_across_one_request() -> None:
    """An agent makes several model calls; the request totals all of them."""
    tracked = usage.start()

    usage.record_chat(1000, 200)
    usage.record_chat(1500, 300)
    usage.record_embedding(50)

    assert tracked.chat_calls == 2
    assert tracked.input_tokens == 2500
    assert tracked.output_tokens == 500
    assert tracked.embedding_calls == 1
    assert tracked.embedding_tokens == 50


def test_cost_uses_the_configured_rates() -> None:
    """Cost is computed from config, not hardcoded numbers."""
    tracked = usage.start()
    usage.record_chat(1_000_000, 1_000_000)

    expected = (
        settings.cost_per_million_input_tokens + settings.cost_per_million_output_tokens
    )

    assert tracked.estimated_cost_usd == expected


def test_a_request_that_used_nothing_costs_nothing() -> None:
    """A cached or refused request should not report a phantom cost."""
    assert usage.start().estimated_cost_usd == 0.0


def test_log_fields_are_flat_and_json_safe() -> None:
    """Structured logs need flat scalar fields, not nested objects."""
    tracked = usage.start()
    usage.record_chat(100, 20)

    fields = tracked.as_log_fields()

    assert set(fields) == {
        "chat_calls",
        "input_tokens",
        "output_tokens",
        "embedding_calls",
        "embedding_tokens",
        "estimated_cost_usd",
    }
    assert all(isinstance(value, (int, float)) for value in fields.values())
