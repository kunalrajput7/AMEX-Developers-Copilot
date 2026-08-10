"""Serving the most recent evaluation run to the UI.

A demo that claims to be accurate should be able to show its working. This
reads the newest file in eval/results -- the same artefact CI reads -- rather
than any number typed into the frontend, so the panel cannot drift away from
what was actually measured.

Read-only, and it deliberately does not offer a "run evaluation" button: a full
run takes about twenty minutes and costs real money at the model provider.
"""

import json
import logging
from pathlib import Path

import yaml
from fastapi import APIRouter, HTTPException

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/eval", tags=["eval"])

EVAL_DIR = Path(__file__).resolve().parent.parent.parent / "eval"
RESULTS_DIR = EVAL_DIR / "results"
THRESHOLDS_FILE = EVAL_DIR / "thresholds.yaml"

# What each metric means, in one line, for the UI. Kept here rather than in the
# frontend so the explanation ships with the code that produces the number.
METRIC_HELP = {
    "context_recall": "Did the search find the right source at all?",
    "citation_recall": "Did the answer actually cite that source?",
    "reciprocal_rank": "How near the top of the results was it?",
    "faithfulness": "Is every claim supported by the sources?",
    "answer_relevance": "Does the answer address the question asked?",
    "answer_correctness": "Does it match the reference answer?",
    "refusal_correctness": "Were unanswerable questions declined, not guessed at?",
}

# Metrics computed by comparing URLs rather than by asking a model.
EXACT_METRICS = {"context_recall", "citation_recall", "reciprocal_rank"}


def latest_results_file() -> Path | None:
    """Return the newest local run, else the committed baseline, else None.

    Local runs are timestamped and git-ignored, so a machine that has run the
    evaluation shows its own numbers. A fresh clone has none of those and falls
    back to baseline.json, which is committed -- otherwise the panel would be
    empty for everyone who has not spent twenty minutes and real model calls
    reproducing a result that was already recorded.
    """
    if not RESULTS_DIR.is_dir():
        return None

    runs = sorted(RESULTS_DIR.glob("eval-*.json"))
    if runs:
        return runs[-1]

    baseline = RESULTS_DIR / "baseline.json"
    return baseline if baseline.is_file() else None


def load_thresholds() -> dict[str, float]:
    """Return the gold-tier floors that gate the build."""
    if not THRESHOLDS_FILE.is_file():
        return {}
    parsed = yaml.safe_load(THRESHOLDS_FILE.read_text(encoding="utf-8")) or {}
    return parsed.get("gold") or {}


@router.get("/latest")
def latest_evaluation() -> dict:
    """Summarise the most recent evaluation run."""
    path = latest_results_file()
    if path is None:
        raise HTTPException(
            status_code=404,
            detail="No evaluation has been run yet. Run: python eval/run_eval.py",
        )

    try:
        run = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.exception("Could not read evaluation results from %s", path)
        raise HTTPException(
            status_code=500, detail=f"Evaluation results are unreadable: {exc}"
        ) from exc

    averages = run.get("averages") or {}
    thresholds = load_thresholds()
    cases = run.get("cases") or []

    metrics = [
        {
            "name": name,
            "score": score,
            "threshold": thresholds.get(name),
            "passing": thresholds.get(name) is None or score >= thresholds[name],
            "help": METRIC_HELP.get(name, ""),
            "judged": name not in EXACT_METRICS,
        }
        for name, score in averages.items()
    ]

    failures = [
        {
            "question": case.get("question", ""),
            "failure": case["failure"],
        }
        for case in cases
        if case.get("failure")
    ]

    return {
        "run_at": run.get("run_at", ""),
        "judge": run.get("judge", ""),
        "total": len(cases),
        "passed": len(cases) - len(failures),
        "failures": failures,
        "metrics": metrics,
        # A single breach fails the build, so the gate is reported separately
        # from the pass count -- they answer different questions.
        "gate_passing": all(metric["passing"] for metric in metrics),
    }
