"""Health endpoints used to confirm the API and its database are alive."""

from fastapi import APIRouter

from app.db import database

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    """Return ok if the API process is running."""
    return {"status": "ok"}


@router.get("/health/db")
async def health_db() -> dict[str, str | bool]:
    """Report whether Postgres is reachable and the schema has been applied.

    Both must be true for the knowledge base to work, so both are reported
    rather than collapsing them into a single ok.
    """
    try:
        reachable = await database.ping()
        schema_ready = await database.schema_is_ready()
    except Exception as exc:
        return {"status": "error", "detail": str(exc)}

    return {
        "status": "ok" if (reachable and schema_ready) else "error",
        "connected": reachable,
        "schema_applied": schema_ready,
    }
