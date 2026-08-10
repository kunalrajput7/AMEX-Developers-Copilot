"""Tests for the evaluation summary the UI reads.

The panel exists so a reader can check the project's claims about itself, which
only works if the numbers come from a recorded run. These tests pin the two
ways that could quietly stop being true: the gate agreeing with the thresholds
file, and a missing run reading as "not run" rather than as a passing one.
"""

import json

import pytest
from fastapi import HTTPException

from app.api import routes_eval


def test_metrics_are_compared_against_the_thresholds_file() -> None:
    """A score under its floor is reported as failing, and drags the gate down."""
    thresholds = routes_eval.load_thresholds()
    assert thresholds, "thresholds.yaml should define gold-tier floors"

    metric = next(iter(thresholds))
    floor = thresholds[metric]

    run = {"averages": {metric: floor - 0.01}, "cases": []}
    summary = _summarise(run)

    assert summary["metrics"][0]["passing"] is False
    assert summary["gate_passing"] is False


def test_a_score_on_the_floor_passes() -> None:
    """The gate fails below the floor, not at it -- run_eval.py uses the same rule."""
    thresholds = routes_eval.load_thresholds()
    metric = next(iter(thresholds))

    summary = _summarise({"averages": {metric: thresholds[metric]}, "cases": []})

    assert summary["metrics"][0]["passing"] is True
    assert summary["gate_passing"] is True


def test_failing_cases_are_listed_and_excluded_from_the_pass_count() -> None:
    run = {
        "averages": {},
        "cases": [
            {"question": "one", "failure": None},
            {"question": "two", "failure": "retrieval_miss"},
        ],
    }

    summary = _summarise(run)

    assert summary["total"] == 2
    assert summary["passed"] == 1
    assert summary["failures"] == [
        {"question": "two", "failure": "retrieval_miss"}
    ]


def test_no_recorded_run_is_a_404_not_an_empty_pass(monkeypatch) -> None:
    """A fresh clone has no results. Reporting that as 0/0 passing would lie."""
    monkeypatch.setattr(routes_eval, "latest_results_file", lambda: None)

    with pytest.raises(HTTPException) as raised:
        routes_eval.latest_evaluation()

    assert raised.value.status_code == 404


def test_the_recorded_run_on_disk_is_readable(tmp_path) -> None:
    """Guards against a results file the endpoint cannot parse."""
    path = routes_eval.latest_results_file()
    if path is None:
        pytest.skip("no evaluation has been run in this checkout")

    summary = routes_eval.latest_evaluation()

    assert summary["total"] > 0
    assert summary["passed"] <= summary["total"]
    assert len(summary["metrics"]) > 0


def _summarise(run: dict) -> dict:
    """Run the endpoint against a made-up result file."""
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "eval-20260101-000000.json"
        path.write_text(json.dumps(run), encoding="utf-8")

        original = routes_eval.latest_results_file
        routes_eval.latest_results_file = lambda: path
        try:
            return routes_eval.latest_evaluation()
        finally:
            routes_eval.latest_results_file = original
