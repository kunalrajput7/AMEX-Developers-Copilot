"""Embedding client: text-embedding-3-large on Azure AI Foundry.

Unlike the chat model, embeddings are served on the resource's Azure OpenAI
surface, so this uses the OpenAI SDK.

The model is natively 3072-dimensional, but pgvector's HNSW index supports at
most 2000 dimensions. The v3 embedding models accept a `dimensions` parameter,
so every request asks for 1536 -- keeping the index usable without giving up
the larger model's quality.
"""

import logging

from openai import AsyncAzureOpenAI

from app.config import settings
from app.observability import usage

logger = logging.getLogger(__name__)

_client: AsyncAzureOpenAI | None = None


def get_client() -> AsyncAzureOpenAI:
    """Return the shared Azure OpenAI client, creating it on first use."""
    global _client

    if _client is None:
        settings.require_model_config()
        _client = AsyncAzureOpenAI(
            azure_endpoint=settings.azure_openai_endpoint,
            api_key=settings.azure_openai_api_key,
            api_version=settings.azure_openai_api_version,
        )

    return _client


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a batch of texts and return one vector per input, in order."""
    if not texts:
        return []

    client = get_client()
    response = await client.embeddings.create(
        model=settings.azure_openai_embedding_deployment,
        input=texts,
        dimensions=settings.embedding_dimensions,
    )

    usage.record_embedding(response.usage.total_tokens)

    # The API may return results out of order; `index` is authoritative.
    ordered = sorted(response.data, key=lambda item: item.index)
    vectors = [item.embedding for item in ordered]

    for vector in vectors:
        if len(vector) != settings.embedding_dimensions:
            raise RuntimeError(
                f"Embedding model returned {len(vector)} dimensions but the "
                f"database column expects {settings.embedding_dimensions}. "
                f"Check AZURE_OPENAI_EMBEDDING_DEPLOYMENT and the "
                f"embedding_dimensions setting agree with schema.sql."
            )

    return vectors
