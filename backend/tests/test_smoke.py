"""Smoke tests: the app builds and its health endpoint responds."""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.conftest import DATABASE_AVAILABLE, SKIP_REASON

# Starting the app applies the database schema, and a schema failure aborts
# startup on purpose -- so this test needs Postgres even though the endpoint
# it checks does not.
pytestmark = pytest.mark.skipif(not DATABASE_AVAILABLE, reason=SKIP_REASON)


def test_health_returns_ok() -> None:
    """GET /health returns status ok once the app has started."""
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
