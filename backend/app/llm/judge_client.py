"""The model that grades answers during evaluation.

Deliberately a *different family* from the model that writes them. A model
grading its own output is a defendant judging its own trial: it scores itself
generously, and — worse — it is blind in the same places. If the answering
model misreads a source, the same model as judge tends to misread it
identically and call the answer faithful.

Two models from one vendor share training lineage and therefore share failure
modes, so a stronger sibling only fixes half the problem. A different family is
what makes the judgement independent.

Falls back to the answering model when no judge is configured, so evaluation
still runs — the scores are just softer, and `describe()` says so.
"""

import logging

from openai import AsyncAzureOpenAI

from app.config import settings
from app.llm import chat_client
from app.observability import usage

logger = logging.getLogger(__name__)

# Judging is a scoring task, not a creative one: same input, same verdict,
# every run. Without that the eval harness cannot tell a real regression from
# the judge simply having a different opinion today.
TEMPERATURE = 0.0
MAX_TOKENS = 1024

_client: AsyncAzureOpenAI | None = None


def is_cross_family() -> bool:
    """Return True if the judge is a different model family from the agent."""
    return bool(settings.azure_openai_judge_deployment.strip())


def describe() -> str:
    """Return a one-line description of the judge, for the scorecard header."""
    if is_cross_family():
        return f"{settings.azure_openai_judge_deployment} (independent of the agent)"

    return (
        f"{settings.anthropic_chat_deployment} "
        "(SAME model as the agent -- scores are optimistic)"
    )


def get_client() -> AsyncAzureOpenAI:
    """Return the shared judge client, creating it on first use.

    A separate client from the embedding one even though both point at the same
    Azure resource: they serve different roles and are configured independently,
    and keeping them apart means each module reads on its own.
    """
    global _client

    if _client is None:
        _client = AsyncAzureOpenAI(
            azure_endpoint=settings.azure_openai_endpoint,
            api_key=settings.azure_openai_api_key,
            api_version=settings.azure_openai_api_version,
        )

    return _client


async def complete(prompt: str) -> str:
    """Send a prompt to the independent model and return its reply.

    Used for grading answers and for authoring the synthetic question set --
    both are jobs the answering model should not do for itself.
    """
    if not is_cross_family():
        # No independent model configured; fall back so evaluation still runs.
        return await chat_client.chat_text([{"role": "user", "content": prompt}])

    response = await get_client().chat.completions.create(
        model=settings.azure_openai_judge_deployment,
        messages=[{"role": "user", "content": prompt}],
        temperature=TEMPERATURE,
        max_tokens=MAX_TOKENS,
    )

    if response.usage is not None:
        usage.record_chat(
            response.usage.prompt_tokens, response.usage.completion_tokens
        )

    return response.choices[0].message.content or ""


async def judge(prompt: str) -> str:
    """Send a grading prompt to the judge and return its verdict."""
    return await complete(prompt)
