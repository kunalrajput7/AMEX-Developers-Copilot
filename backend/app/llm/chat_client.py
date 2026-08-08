"""Chat model client: Claude Sonnet on Azure AI Foundry.

Foundry serves Anthropic models on its own `/anthropic` surface, which speaks
the Anthropic protocol rather than the OpenAI one, so this uses the Anthropic
SDK. Embeddings come from a different client -- see embedding_client.py.

Every chat call in the project goes through here, which keeps the vendor
dependency in one file and makes it easy to mock in tests.
"""

import asyncio
import logging
from dataclasses import dataclass

from anthropic import AsyncAnthropicFoundry, RateLimitError

from app.config import settings
from app.observability import usage

logger = logging.getLogger(__name__)

# Foundry enforces a per-minute token budget. Under load -- an evaluation run,
# or several users at once -- that ceiling is reached routinely, so it is
# ordinary operation to wait for, not an error to surface.
MAX_RATE_LIMIT_RETRIES = 5
INITIAL_BACKOFF_SECONDS = 20.0

_client: AsyncAnthropicFoundry | None = None


@dataclass(frozen=True)
class ChatReply:
    """A model response plus the token counts needed for cost reporting."""

    text: str
    input_tokens: int
    output_tokens: int


def get_client() -> AsyncAnthropicFoundry:
    """Return the shared Anthropic client, creating it on first use."""
    global _client

    if _client is None:
        settings.require_model_config()
        _client = AsyncAnthropicFoundry(
            api_key=settings.anthropic_foundry_api_key,
            base_url=settings.anthropic_foundry_base_url,
        )

    return _client


async def _create_with_backoff(client: AsyncAnthropicFoundry, request: dict):
    """Send a request, waiting out per-minute rate limits rather than failing.

    The limit is measured over a rolling minute, so the backoff starts near
    that window rather than at the usual second or two -- retrying sooner just
    burns another attempt against a budget that has not refilled.
    """
    backoff = INITIAL_BACKOFF_SECONDS

    for attempt in range(1, MAX_RATE_LIMIT_RETRIES + 1):
        try:
            return await client.messages.create(**request)
        except RateLimitError:
            if attempt == MAX_RATE_LIMIT_RETRIES:
                raise
            logger.warning(
                "Rate limited (attempt %d/%d). Waiting %.0fs.",
                attempt,
                MAX_RATE_LIMIT_RETRIES,
                backoff,
            )
            await asyncio.sleep(backoff)
            backoff *= 1.5

    raise RuntimeError("unreachable")  # every path above returns or raises


async def chat(
    messages: list[dict[str, str]],
    system: str | None = None,
    temperature: float = 0.0,
    max_tokens: int | None = None,
    model: str | None = None,
) -> ChatReply:
    """Send a chat request and return the reply text with token usage.

    `system` is a separate parameter rather than a message role, which is how
    the Anthropic API expects it. Temperature defaults to 0 so that agent
    decisions and evaluation runs are reproducible -- without that, the eval
    harness cannot tell a real regression from sampling noise.
    """
    client = get_client()

    request: dict = {
        "model": model or settings.anthropic_chat_deployment,
        "messages": messages,
        "max_tokens": max_tokens or settings.chat_max_tokens,
        "temperature": temperature,
    }
    if system is not None:
        request["system"] = system

    response = await _create_with_backoff(client, request)

    # Responses can contain several blocks; join the text ones.
    text = "".join(
        block.text for block in response.content if getattr(block, "type", "") == "text"
    )

    usage.record_chat(response.usage.input_tokens, response.usage.output_tokens)

    return ChatReply(
        text=text,
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
    )


async def chat_text(
    messages: list[dict[str, str]],
    system: str | None = None,
    temperature: float = 0.0,
    model: str | None = None,
) -> str:
    """Convenience wrapper returning just the reply text."""
    reply = await chat(messages, system=system, temperature=temperature, model=model)
    return reply.text
