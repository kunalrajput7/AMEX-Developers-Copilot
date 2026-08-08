"""Shared test setup.

Most tests are pure and need nothing. A few genuinely need Postgres — the ones
guarding the stale sweep, and the smoke test, which boots the app and therefore
applies the schema. Those skip when no database is reachable so `pytest` still
works on a laptop with Docker down.

The probe below is a bare TCP connect rather than a driver connection: the
application's connect path retries ten times with backoff, which is right when
a container is still starting and wrong when a test just wants a yes or no.
"""

import socket

from sqlalchemy.engine import make_url

from app.config import settings

# Long enough for a local container, short enough that a full suite run with no
# database costs well under a second rather than a minute and a half.
PROBE_TIMEOUT_SECONDS = 0.5


def database_is_reachable() -> bool:
    """Return True if something is listening on the configured database port."""
    url = make_url(settings.database_url)
    host = url.host or "localhost"
    port = url.port or 5432

    try:
        with socket.create_connection((host, port), timeout=PROBE_TIMEOUT_SECONDS):
            return True
    except OSError:
        return False


# Evaluated once at collection time, so the probe runs a single time per run.
DATABASE_AVAILABLE = database_is_reachable()

SKIP_REASON = (
    f"Postgres not reachable at {make_url(settings.database_url).host}"
    f":{make_url(settings.database_url).port or 5432} -- run `docker compose up -d`"
)
