"""One structured log line per request, carrying latency, tokens, and cost.

JSON rather than prose because these lines are meant to be queried -- "which
questions cost the most", "what is p95 latency", "did token use jump after that
deploy" are all one filter away, and none of them are answerable from a
human-readable log.
"""

import json
import logging
import sys
import time
from collections.abc import Awaitable, Callable

from fastapi import Request, Response

from app.observability import usage

logger = logging.getLogger("request")

# Endpoints logged at debug rather than info. Health checks are polled
# constantly and would drown out the requests worth reading.
QUIET_PATHS = {"/health", "/health/db"}


class JsonFormatter(logging.Formatter):
    """Render a log record as a single JSON object."""

    def format(self, record: logging.LogRecord) -> str:
        """Return the record as one JSON line."""
        payload = {
            "time": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Fields attached via logger.info(..., extra={...}) land on the record
        # as plain attributes; copy the ones we put there.
        for key, value in getattr(record, "fields", {}).items():
            payload[key] = value

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload)


def configure(json_logs: bool = True) -> None:
    """Install the log handler for the process.

    Plain text is easier to read while developing; JSON is what you want
    anywhere the logs are collected.
    """
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        JsonFormatter()
        if json_logs
        else logging.Formatter("%(asctime)s %(levelname)s %(name)s - %(message)s")
    )

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(logging.INFO)


async def log_requests(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Time a request, record what it spent, and log one line about it."""
    request_usage = usage.start()
    started = time.perf_counter()

    try:
        response = await call_next(request)
        status = response.status_code
    except Exception:
        # Still log the line -- a request that fails is the one you most want
        # the latency and token numbers for.
        logger.exception(
            "request failed",
            extra={
                "fields": {
                    "method": request.method,
                    "path": request.url.path,
                    "status": 500,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                    **request_usage.as_log_fields(),
                }
            },
        )
        raise

    duration_ms = round((time.perf_counter() - started) * 1000, 1)
    level = logging.DEBUG if request.url.path in QUIET_PATHS else logging.INFO

    logger.log(
        level,
        "request",
        extra={
            "fields": {
                "method": request.method,
                "path": request.url.path,
                "status": status,
                "duration_ms": duration_ms,
                **request_usage.as_log_fields(),
            }
        },
    )

    # Handy when watching a single request in the browser's network tab.
    response.headers["X-Response-Time-Ms"] = str(duration_ms)

    return response
