"""CLI: ask the agent a question.

Same agent the web app uses, different surface:

    python scripts/ask.py "How do I authenticate with the Amex API?"
    python scripts/ask.py "why does my snapshot test fail on CI" --trace
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.agent.graph import answer_question  # noqa: E402
from app.db.database import SessionLocal, engine  # noqa: E402


def parse_args() -> argparse.Namespace:
    """Define and parse the command-line options."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("question", help="What to ask.")
    parser.add_argument(
        "--trace",
        action="store_true",
        help="Show the agent's steps as it works.",
    )
    return parser.parse_args()


async def main() -> int:
    """Ask the agent and print the answer with its sources."""
    args = parse_args()

    logging.basicConfig(
        level=logging.INFO if args.trace else logging.WARNING,
        format="  %(name)s | %(message)s",
    )

    async with SessionLocal() as session:
        answer, chunks, state = await answer_question(session, args.question)

    print("\n" + "=" * 78)
    print(answer)
    print("=" * 78)

    if chunks:
        print("\nSources:")
        for index, chunk in enumerate(chunks, start=1):
            print(f"  [{index}] {chunk.repo}/{chunk.file_path}")
            print(f"      {chunk.source_url}")

    print(
        f"\nSearches run: {state.get('tool_calls_used', 0)}"
        f" | Sources: {len(chunks)}"
        f" | Grounded: {state.get('is_grounded')}"
    )
    for entry in state.get("searches", []):
        print(f"  - {entry}")

    await engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
