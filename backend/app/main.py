"""FastAPI entry point for the Amex Developer Copilot backend.

Run locally with:
    uvicorn app.main:app --reload
"""

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import routes_chat, routes_health
from app.db import database
from app.observability import logging as observability

# Plain text while developing, JSON anywhere logs are collected.
observability.configure(json_logs=os.getenv("JSON_LOGS", "").lower() == "true")

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Apply the database schema on startup and dispose the engine on shutdown.

    A schema failure aborts startup on purpose: an API serving requests against
    a missing or half-applied schema fails later, in confusing ways.
    """
    await database.apply_schema()
    logger.info("Database schema applied.")

    yield

    await database.engine.dispose()


app = FastAPI(
    title="Amex Developer Copilot",
    description="Agentic knowledge assistant over American Express open-source repos.",
    version="0.1.0",
    lifespan=lifespan,
)

# One structured line per request: latency, tokens, estimated cost.
app.middleware("http")(observability.log_requests)

# The React dev server runs on a different port, so it needs CORS access.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(routes_health.router)
app.include_router(routes_chat.router)
