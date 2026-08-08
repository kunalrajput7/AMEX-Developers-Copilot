"""Typed application settings, loaded once from the environment / .env file.

This is the only place in the project that reads environment variables.
Every other module imports `settings` from here.
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/config.py -> backend/
BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """All configuration for the backend, validated at import time."""

    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Chat model: Claude on Azure AI Foundry -----------------------------
    # Served through Foundry's Anthropic surface, which speaks the Anthropic
    # protocol rather than the OpenAI one -- hence a separate client.
    # Defaults are empty so the app can boot before credentials are added;
    # `require_model_config()` turns a missing value into a clear error at the
    # moment it is actually needed.
    anthropic_foundry_base_url: str = ""
    anthropic_foundry_api_key: str = ""
    anthropic_chat_deployment: str = ""

    # Legacy: a second Claude deployment for judging. Kept for compatibility,
    # but a same-family judge only removes self-grading, not the shared blind
    # spots -- prefer AZURE_OPENAI_JUDGE_DEPLOYMENT below.
    anthropic_judge_deployment: str = ""

    # Upper bound on a single answer. Answers are short and grounded, so this
    # is generous rather than tight.
    chat_max_tokens: int = 2000

    # --- Embedding model: text-embedding-3-large on the same resource -------
    # This one *is* the Azure OpenAI surface, so it uses the OpenAI client.
    azure_openai_endpoint: str = ""
    azure_openai_api_key: str = ""
    azure_openai_api_version: str = "2024-10-21"
    azure_openai_embedding_deployment: str = ""

    # The evaluation judge -- an OpenAI model on the same resource, chosen to
    # be a different family from the Claude model that writes the answers.
    # Independent judgement is the whole point; a sibling model shares the
    # answering model's blind spots. Blank falls back to the answering model,
    # which still runs but produces optimistic scores.
    azure_openai_judge_deployment: str = ""

    # text-embedding-3-large is natively 3072 dimensions, but pgvector's HNSW
    # index only supports up to 2000. The v3 embedding models accept a
    # `dimensions` parameter, so we ask for 1536 -- which keeps the index
    # usable and still outperforms text-embedding-3-small at the same size.
    # Must match VECTOR(n) in schema.sql.
    embedding_dimensions: int = 1536

    # --- Database -----------------------------------------------------------
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/copilot"

    # --- GitHub (optional, raises ingestion rate limits) --------------------
    github_token: str = ""

    # --- Agent budget -------------------------------------------------------
    max_tool_calls: int = 5

    # --- Cost estimation (US dollars per million tokens) --------------------
    # Used only to log an estimated cost per request. List prices, so the
    # figure ignores prompt caching and any negotiated discount -- it is for
    # spotting a question that costs ten times the others, not for billing.
    #
    # Claude Sonnet 4.6 on Foundry bills at standard Anthropic API rates.
    cost_per_million_input_tokens: float = 3.00
    cost_per_million_output_tokens: float = 15.00

    # Verify this against your own Azure pricing page -- embedding rates vary
    # by region and change more often than the chat ones.
    cost_per_million_embedding_tokens: float = 0.13

    @property
    def judge_deployment(self) -> str:
        """Return the name of whichever model grades answers.

        Preference order: the cross-family OpenAI judge, then a second Claude
        deployment, then the answering model itself as a last resort.
        """
        return (
            self.azure_openai_judge_deployment
            or self.anthropic_judge_deployment
            or self.anthropic_chat_deployment
        )

    def require_model_config(self) -> None:
        """Raise a readable error if the Foundry settings are not filled in yet."""
        missing = [
            name
            for name, value in (
                ("ANTHROPIC_FOUNDRY_BASE_URL", self.anthropic_foundry_base_url),
                ("ANTHROPIC_FOUNDRY_API_KEY", self.anthropic_foundry_api_key),
                ("ANTHROPIC_CHAT_DEPLOYMENT", self.anthropic_chat_deployment),
                ("AZURE_OPENAI_ENDPOINT", self.azure_openai_endpoint),
                ("AZURE_OPENAI_API_KEY", self.azure_openai_api_key),
                (
                    "AZURE_OPENAI_EMBEDDING_DEPLOYMENT",
                    self.azure_openai_embedding_deployment,
                ),
            )
            if not value.strip()
        ]
        if missing:
            raise RuntimeError(
                "Missing Azure AI Foundry settings: "
                + ", ".join(missing)
                + f". Copy {BACKEND_DIR / '.env.example'} to "
                + f"{BACKEND_DIR / '.env'} and fill them in."
            )


@lru_cache
def get_settings() -> Settings:
    """Return the settings singleton, building it on first use."""
    return Settings()


settings = get_settings()
