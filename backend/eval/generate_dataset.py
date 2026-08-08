"""Build the synthetic evaluation set from the corpus.

    python eval/generate_dataset.py --count 40

Picks chunks at random, asks a model what question each one answers, and writes
the result as a dataset row. Because the question is generated *from* a known
chunk, that chunk's URL is the ground-truth source -- which is what makes the
retrieval metrics exact even on generated data.

The questions are authored by the independent model, not the one that will be
answering them: a model writing its own exam gravitates toward questions it
already handles well.

The reference *answers* are still only as good as the model that wrote them, so
the synthetic tier is for volume and trend. The hand-written gold tier is what
gates the build.
"""

import argparse
import asyncio
import json
import random
import sys
from pathlib import Path

from sqlalchemy import func, select

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.database import SessionLocal, engine  # noqa: E402
from app.db.models import Chunk  # noqa: E402
from app.llm import judge_client  # noqa: E402

OUTPUT = Path(__file__).resolve().parent / "datasets" / "synthetic.jsonl"

# Short chunks rarely contain a full answer, so they make poor questions.
MIN_CHUNK_CHARS = 400

PROMPT = """\
Here is an extract from the {repo} repository, file {file_path}:

---
{content}
---

Write one realistic question a developer would ask that this extract answers,
along with the answer taken only from this extract.

The question must stand alone: someone reading it without the extract should
understand what is being asked. Do not write "in this extract" or "according
to the code above". Mention the project or tool by name where it helps.

If the extract is boilerplate -- a licence, a code of conduct, a changelog --
reply with {{"skip": true}} instead.

Reply with JSON only:
{{"question": "...", "answer": "..."}}
"""


def parse_args() -> argparse.Namespace:
    """Define and parse the command-line options."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=40, help="Rows to generate.")
    parser.add_argument("--seed", type=int, default=7, help="Sampling seed.")
    return parser.parse_args()


async def pick_chunks(count: int, seed: int) -> list[Chunk]:
    """Sample chunks spread across repositories and content types."""
    random.seed(seed)

    async with SessionLocal() as session:
        # Oversample, then thin out, so one large repo cannot dominate the set.
        statement = (
            select(Chunk)
            .where(func.length(Chunk.content) >= MIN_CHUNK_CHARS)
            .order_by(func.random())
            .limit(count * 3)
        )
        candidates = list((await session.execute(statement)).scalars().all())

    per_repo: dict[str, int] = {}
    chosen: list[Chunk] = []
    cap = max(2, count // 4)

    for chunk in candidates:
        if per_repo.get(chunk.repo, 0) >= cap:
            continue
        per_repo[chunk.repo] = per_repo.get(chunk.repo, 0) + 1
        chosen.append(chunk)
        if len(chosen) >= count:
            break

    return chosen


async def make_row(chunk: Chunk) -> dict | None:
    """Turn one chunk into a dataset row, or None if it is not worth using."""
    # Written by the independent model, not the one that will be answering.
    # A model that authors its own exam tends to ask the questions it already
    # answers well, which quietly flatters the scores.
    reply = await judge_client.complete(
        PROMPT.format(
            repo=chunk.repo,
            file_path=chunk.file_path,
            content=chunk.content[:4000],
        )
    )

    start, end = reply.find("{"), reply.rfind("}")
    if start == -1 or end == -1:
        return None

    try:
        parsed = json.loads(reply[start : end + 1])
    except json.JSONDecodeError:
        return None

    if parsed.get("skip") or not parsed.get("question") or not parsed.get("answer"):
        return None

    return {
        "question": parsed["question"],
        "reference_answer": parsed["answer"],
        "expected_source_url": chunk.source_url,
        "tier": "synthetic",
    }


async def main() -> int:
    """Generate the dataset and write it to disk."""
    args = parse_args()

    chunks = await pick_chunks(args.count, args.seed)
    print(f"Generating questions from {len(chunks)} chunks...")

    semaphore = asyncio.Semaphore(4)

    async def guarded(chunk: Chunk) -> dict | None:
        """Generate one row, limiting how many run at once."""
        async with semaphore:
            return await make_row(chunk)

    rows = [row for row in await asyncio.gather(*(guarded(c) for c in chunks)) if row]

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8"
    )

    skipped = len(chunks) - len(rows)
    print(f"Wrote {len(rows)} rows to {OUTPUT.name} ({skipped} chunks skipped)")

    await engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
