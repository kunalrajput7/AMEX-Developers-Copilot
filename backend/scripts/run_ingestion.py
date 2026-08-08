"""CLI: build the knowledge base from the configured Amex repositories.

Examples:
    python scripts/run_ingestion.py --dry-run          # no embedding, no writes
    python scripts/run_ingestion.py --limit 50         # cheap first real run
    python scripts/run_ingestion.py                    # full ingestion
    python scripts/run_ingestion.py --repo fetchye     # one repo only
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

# Allow running this script directly from the backend/ directory.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.database import apply_schema, engine  # noqa: E402
from app.ingestion.ingest import RepoResult, ingest_all  # noqa: E402
from app.ingestion.repos import REPOS  # noqa: E402


def parse_args() -> argparse.Namespace:
    """Define and parse the command-line options."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Load and chunk, but do not embed or write. Costs nothing.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Cap chunks per repository. Use for a cheap first run.",
    )
    parser.add_argument(
        "--repo",
        action="append",
        default=None,
        help="Ingest only this repo (repeatable). Defaults to all configured.",
    )
    parser.add_argument(
        "--no-issues",
        action="store_true",
        help="Skip fetching closed issues from the GitHub API.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show per-repo progress logging.",
    )
    return parser.parse_args()


def print_report(results: list[RepoResult], dry_run: bool) -> None:
    """Print a per-repo table and totals."""
    header = f"{'repo':<42}{'docs':>7}{'chunks':>8}{'added':>8}{'skipped':>9}{'deleted':>9}"
    print("\n" + header)
    print("-" * len(header))

    totals = {"documents": 0, "chunks_seen": 0, "added": 0, "skipped": 0, "deleted": 0}

    for result in results:
        if result.error:
            print(f"{result.repo:<42}  ERROR: {result.error[:60]}")
            continue

        print(
            f"{result.repo:<42}{result.documents:>7}{result.chunks_seen:>8}"
            f"{result.chunks_added:>8}{result.chunks_skipped:>9}{result.chunks_deleted:>9}"
        )
        totals["documents"] += result.documents
        totals["chunks_seen"] += result.chunks_seen
        totals["added"] += result.chunks_added
        totals["skipped"] += result.chunks_skipped
        totals["deleted"] += result.chunks_deleted

    print("-" * len(header))
    print(
        f"{'TOTAL':<42}{totals['documents']:>7}{totals['chunks_seen']:>8}"
        f"{totals['added']:>8}{totals['skipped']:>9}{totals['deleted']:>9}"
    )

    # Aggregate skip reasons across repos -- this is how you spot a filter
    # that is silently throwing away content you wanted.
    all_skips: dict[str, int] = {}
    for result in results:
        for reason, count in result.files_skipped.items():
            all_skips[reason] = all_skips.get(reason, 0) + count

    if all_skips:
        print("\nFiles skipped by filter:")
        for reason, count in sorted(all_skips.items(), key=lambda kv: -kv[1]):
            print(f"  {count:>6}  {reason}")

    if dry_run:
        print("\nDRY RUN -- nothing was embedded or written to the database.")


async def main() -> int:
    """Run ingestion and print a summary. Returns a process exit code."""
    args = parse_args()

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )

    repos = REPOS
    if args.repo:
        wanted = set(args.repo)
        repos = [repo for repo in REPOS if repo.name in wanted]
        unknown = wanted - {repo.name for repo in REPOS}
        if unknown:
            print(f"Unknown repo(s): {', '.join(sorted(unknown))}")
            print(f"Configured: {', '.join(repo.name for repo in REPOS)}")
            return 1

    if not args.dry_run:
        await apply_schema()

    results = await ingest_all(
        repos=repos,
        include_issues=not args.no_issues,
        limit=args.limit,
        dry_run=args.dry_run,
    )

    print_report(results, dry_run=args.dry_run)
    await engine.dispose()

    return 1 if any(result.error for result in results) else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
