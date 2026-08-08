"""CLI: query the knowledge base directly, without the LLM.

Useful for seeing what retrieval actually returns, and for comparing the two
retrievers against each other:

    python scripts/search.py "how do I authenticate"
    python scripts/search.py "X-Amex-Api-Key" --method all
    python scripts/search.py "resize snapshots" --type issue
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.database import SessionLocal, engine  # noqa: E402
from app.retrieval import hybrid, keyword_search, vector_search  # noqa: E402
from app.retrieval.results import RetrievedChunk  # noqa: E402


def parse_args() -> argparse.Namespace:
    """Define and parse the command-line options."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query", help="What to search for.")
    parser.add_argument(
        "--method",
        choices=["hybrid", "vector", "keyword", "all"],
        default="hybrid",
        help="Which retriever to use. 'all' runs each and compares them.",
    )
    parser.add_argument(
        "--type",
        dest="chunk_type",
        choices=["doc", "code", "issue"],
        default=None,
        help="Restrict to one part of the corpus.",
    )
    parser.add_argument("--top", type=int, default=5, help="Results to show.")
    return parser.parse_args()


def print_results(title: str, chunks: list[RetrievedChunk], top: int) -> None:
    """Print a ranked result list."""
    print(f"\n{title}")
    print("-" * 78)

    if not chunks:
        print("  (no results)")
        return

    for rank, chunk in enumerate(chunks[:top], start=1):
        print(f"{rank}. [{chunk.score:.4f}] {chunk.repo}/{chunk.file_path}")
        print(f"   {chunk.chunk_type} | {chunk.source_url}")
        print(f"   {chunk.snippet(160)}")


async def main() -> int:
    """Run the requested search and print results."""
    args = parse_args()

    async with SessionLocal() as session:
        if args.method in ("vector", "all"):
            results = await vector_search.search(
                session, args.query, limit=args.top, chunk_type=args.chunk_type
            )
            print_results("VECTOR (semantic similarity)", results, args.top)

        if args.method in ("keyword", "all"):
            results = await keyword_search.search(
                session, args.query, limit=args.top, chunk_type=args.chunk_type
            )
            print_results("KEYWORD (full-text match)", results, args.top)

        if args.method in ("hybrid", "all"):
            results = await hybrid.search(
                session, args.query, top_n=args.top, chunk_type=args.chunk_type
            )
            print_results("HYBRID (RRF fusion)", results, args.top)

    await engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
