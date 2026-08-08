"""CLI: verify both Azure AI Foundry deployments before spending money.

Run this whenever credentials change:
    python scripts/check_models.py

Makes one tiny chat call and one tiny embedding call, then reports what it
found. Cheaper than discovering a wrong deployment name 1,000 chunks in.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings  # noqa: E402
from app.llm import chat_client, embedding_client, judge_client  # noqa: E402


def mask(secret: str) -> str:
    """Return a key fingerprint safe to print in a terminal or a screenshot."""
    if len(secret) < 12:
        return "(too short to be valid)"
    return f"{secret[:4]}...{secret[-4:]} ({len(secret)} chars)"


async def main() -> int:
    """Check config, chat, and embeddings. Returns a process exit code."""
    print("Azure AI Foundry preflight")
    print("-" * 62)

    try:
        settings.require_model_config()
    except RuntimeError as exc:
        print(f"FAIL: {exc}")
        return 1

    print("Chat -- writes the answers (Anthropic surface)")
    print(f"  base URL:    {settings.anthropic_foundry_base_url}")
    print(f"  deployment:  {settings.anthropic_chat_deployment}")
    print(f"  api key:     {mask(settings.anthropic_foundry_api_key)}")

    print("\nEmbeddings -- builds the knowledge base (Azure OpenAI surface)")
    print(f"  endpoint:    {settings.azure_openai_endpoint}")
    print(f"  deployment:  {settings.azure_openai_embedding_deployment}")
    print(f"  api version: {settings.azure_openai_api_version}")
    print(f"  dimensions:  {settings.embedding_dimensions} (requested)")

    print("\nJudge -- grades answers during evaluation")
    print(f"  deployment:  {judge_client.describe()}")

    print("\nTesting chat...")
    try:
        reply = await chat_client.chat(
            [{"role": "user", "content": "Reply with the single word: ready"}]
        )
        print(f"  OK - replied {reply.text.strip()[:40]!r}")
        print(f"       tokens in={reply.input_tokens} out={reply.output_tokens}")
    except Exception as exc:
        print(f"  FAIL - {type(exc).__name__}: {str(exc)[:300]}")
        return 1

    print("\nTesting embeddings...")
    try:
        vectors = await embedding_client.embed_texts(["preflight check"])
        print(f"  OK - returned {len(vectors[0])} dimensions")
    except Exception as exc:
        print(f"  FAIL - {type(exc).__name__}: {str(exc)[:300]}")
        return 1

    print("\nTesting judge...")
    try:
        verdict = await judge_client.judge("Reply with the single word: ready")
        print(f"  OK - replied {verdict.strip()[:40]!r}")
        if not judge_client.is_cross_family():
            print("  WARNING: no independent judge configured.")
            print("  Evaluation will run, but the answering model grades itself")
            print("  and its scores will read higher than they should.")
            print("  Set AZURE_OPENAI_JUDGE_DEPLOYMENT to fix.")
    except Exception as exc:
        print(f"  FAIL - {type(exc).__name__}: {str(exc)[:300]}")
        return 1

    print("\nAll checks passed. Safe to run scripts/run_ingestion.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
