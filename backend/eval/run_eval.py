"""Run the agent over the evaluation dataset and print a scorecard.

    python eval/run_eval.py                 # gold tier, the CI gate
    python eval/run_eval.py --tier all      # gold + synthetic
    python eval/run_eval.py --limit 5       # quick check while developing

Exits non-zero when any gold metric falls below its threshold, which is what
turns this from a report into a release gate.
"""

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.agent.graph import answer_question  # noqa: E402
from app.db.database import SessionLocal, engine  # noqa: E402
from app.llm import judge_client  # noqa: E402
from app.retrieval.results import format_for_prompt  # noqa: E402
from eval.evaluators import EvalCase, EvalResult, score  # noqa: E402

EVAL_DIR = Path(__file__).resolve().parent
DATASETS = EVAL_DIR / "datasets"
RESULTS_DIR = EVAL_DIR / "results"
THRESHOLDS = EVAL_DIR / "thresholds.yaml"

METRIC_ORDER = [
    "context_recall",
    "citation_recall",
    "reciprocal_rank",
    "faithfulness",
    "answer_relevance",
    "answer_correctness",
]

# How many questions run at once. Each question costs the agent several model
# calls with large contexts, and Foundry meters input tokens per minute, so
# raising this mostly buys rate-limit waits rather than speed.
DEFAULT_CONCURRENCY = 2


def parse_args() -> argparse.Namespace:
    """Define and parse the command-line options."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--tier",
        choices=["gold", "synthetic", "all"],
        default="gold",
        help="Which dataset to run. Only gold gates the build.",
    )
    parser.add_argument("--limit", type=int, default=None, help="Run only N cases.")
    parser.add_argument(
        "--no-gate",
        action="store_true",
        help="Report scores but always exit 0.",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=DEFAULT_CONCURRENCY,
        help="Questions to run at once. Raise only if your quota allows.",
    )
    return parser.parse_args()


def load_cases(tier: str, limit: int | None) -> list[EvalCase]:
    """Read the requested dataset files into EvalCases."""
    files = []
    if tier in ("gold", "all"):
        files.append(DATASETS / "gold.jsonl")
    if tier in ("synthetic", "all"):
        files.append(DATASETS / "synthetic.jsonl")

    cases: list[EvalCase] = []
    for path in files:
        if not path.exists():
            print(f"  (skipping {path.name} -- not generated yet)")
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                cases.append(EvalCase(**json.loads(line)))

    return cases[:limit] if limit else cases


async def run_case(case: EvalCase, semaphore: asyncio.Semaphore) -> EvalResult:
    """Ask the agent one question and score the answer."""
    async with semaphore:
        async with SessionLocal() as session:
            answer, cited, state = await answer_question(session, case.question)

        retrieved = state.get("chunks", [])
        result = EvalResult(
            case=case,
            answer=answer,
            retrieved_urls=[chunk.source_url for chunk in retrieved],
            cited_urls=[chunk.source_url for chunk in cited],
            is_grounded=bool(state.get("is_grounded")),
            searches=state.get("searches", []),
        )

        print(f"  scored: {case.question[:64]}")
        return await score(result, format_for_prompt(retrieved))


def averages(results: list[EvalResult]) -> dict[str, float]:
    """Return the mean of each metric across results."""
    means: dict[str, float] = {}
    for metric in METRIC_ORDER:
        values = [r.metrics[metric] for r in results if metric in r.metrics]
        if values:
            means[metric] = sum(values) / len(values)
    return means


def print_scorecard(results: list[EvalResult], means: dict[str, float]) -> None:
    """Print the metric table and the failure breakdown."""
    print("\n" + "=" * 62)
    print(f"SCORECARD  ({len(results)} questions)")
    # Named on every scorecard because the judge determines how much the
    # generation metrics are worth. A self-graded run and an independently
    # graded one are not comparable, and the header is what says which is which.
    print(f"judge: {judge_client.describe()}")
    print("=" * 62)

    for metric in METRIC_ORDER:
        if metric in means:
            bar = "#" * round(means[metric] * 30)
            print(f"  {metric:<20} {means[metric]:.3f}  {bar}")

    # An average says quality moved; the breakdown says where to look.
    failures = [r for r in results if r.failure]
    print(f"\n  passed: {len(results) - len(failures)}/{len(results)}")

    # Reported but not counted as failures -- see classify_failure. A rising
    # number here means the agent is spending rewrites it does not need.
    self_flagged = [r for r in results if not r.is_grounded]
    if self_flagged:
        print(f"  agent self-flagged as ungrounded: {len(self_flagged)}")

    if failures:
        counts: dict[str, int] = {}
        for result in failures:
            counts[result.failure] = counts.get(result.failure, 0) + 1

        print("\n  FAILURE BREAKDOWN")
        for name, count in sorted(counts.items(), key=lambda kv: -kv[1]):
            print(f"    {count:>3}  {name}")

        print("\n  FAILING QUESTIONS")
        for result in failures:
            print(f"    [{result.failure}] {result.case.question[:70]}")
            if result.failure == "retrieval_miss":
                print(f"          wanted: {result.case.expected_source_url}")


def check_gate(means: dict[str, float], thresholds: dict[str, float]) -> list[str]:
    """Return a list of threshold breaches, empty if everything passed."""
    return [
        f"{metric}: {means[metric]:.3f} < {minimum:.2f}"
        for metric, minimum in thresholds.items()
        if metric in means and means[metric] < minimum
    ]


def save_results(results: list[EvalResult], means: dict[str, float]) -> Path:
    """Write the full run to a timestamped JSON file for later comparison."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    path = RESULTS_DIR / f"eval-{stamp}.json"

    path.write_text(
        json.dumps(
            {
                "run_at": stamp,
                "judge": judge_client.describe(),
                "averages": means,
                "cases": [
                    {
                        "question": r.case.question,
                        "tier": r.case.tier,
                        "expected_source_url": r.case.expected_source_url,
                        "answer": r.answer,
                        "cited_urls": r.cited_urls,
                        "searches": r.searches,
                        "metrics": r.metrics,
                        "failure": r.failure,
                        "judge_notes": r.judge_notes,
                    }
                    for r in results
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return path


async def main() -> int:
    """Run the evaluation and return a process exit code."""
    args = parse_args()

    cases = load_cases(args.tier, args.limit)
    if not cases:
        print("No evaluation cases found.")
        return 1

    print(f"Running {len(cases)} questions through the agent...\n")

    semaphore = asyncio.Semaphore(args.concurrency)
    results = await asyncio.gather(*(run_case(case, semaphore) for case in cases))

    means = averages(results)
    print_scorecard(results, means)

    path = save_results(results, means)
    print(f"\n  saved: {path.relative_to(EVAL_DIR.parent)}")

    await engine.dispose()

    thresholds = yaml.safe_load(THRESHOLDS.read_text(encoding="utf-8")) or {}
    breaches = check_gate(means, thresholds.get("gold") or {})

    if breaches and not args.no_gate:
        print("\n  GATE FAILED")
        for breach in breaches:
            print(f"    {breach}")
        return 1

    print("\n  GATE PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
