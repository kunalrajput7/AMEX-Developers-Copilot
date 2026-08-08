"""Track what one request cost, in tokens and dollars.

A request fans out into many model calls -- the agent alone makes four or more,
and ingestion embeds in batches. Counting them per call tells you nothing
useful; counting them per request tells you what a user question actually
costs. A context variable does that accounting without threading a counter
through every function signature.
"""

from contextvars import ContextVar
from dataclasses import dataclass

from app.config import settings


@dataclass
class RequestUsage:
    """Everything one request spent."""

    chat_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0

    embedding_calls: int = 0
    embedding_tokens: int = 0

    @property
    def estimated_cost_usd(self) -> float:
        """Return the estimated cost of this request.

        An estimate, not a bill: it uses list prices from config and ignores
        prompt caching. Useful for spotting a question that costs 10x the
        others, not for reconciling an invoice.
        """
        million = 1_000_000
        return (
            self.input_tokens / million * settings.cost_per_million_input_tokens
            + self.output_tokens / million * settings.cost_per_million_output_tokens
            + self.embedding_tokens / million * settings.cost_per_million_embedding_tokens
        )

    def as_log_fields(self) -> dict[str, float | int]:
        """Return the counters as flat fields for a structured log line."""
        return {
            "chat_calls": self.chat_calls,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "embedding_calls": self.embedding_calls,
            "embedding_tokens": self.embedding_tokens,
            "estimated_cost_usd": round(self.estimated_cost_usd, 6),
        }


# None outside a tracked request -- CLI scripts and tests call the model clients
# without any request around them, and that must not be an error.
_current: ContextVar[RequestUsage | None] = ContextVar("request_usage", default=None)


def start() -> RequestUsage:
    """Begin tracking a new request and return its counter."""
    usage = RequestUsage()
    _current.set(usage)
    return usage


def current() -> RequestUsage | None:
    """Return the counter for the request in flight, if there is one."""
    return _current.get()


def record_chat(input_tokens: int, output_tokens: int) -> None:
    """Add one chat call to the current request's total."""
    usage = _current.get()
    if usage is None:
        return

    usage.chat_calls += 1
    usage.input_tokens += input_tokens
    usage.output_tokens += output_tokens


def record_embedding(tokens: int) -> None:
    """Add one embedding call to the current request's total."""
    usage = _current.get()
    if usage is None:
        return

    usage.embedding_calls += 1
    usage.embedding_tokens += tokens
