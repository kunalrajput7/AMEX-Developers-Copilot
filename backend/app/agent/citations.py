"""Keep only the sources the answer actually used.

The agent gathers more chunks than it ends up needing -- that is the point of
searching more than once. But showing all of them as citations is misleading:
a reader assumes a listed source backs the answer.

So after the answer is written we keep only the sources it cites, and renumber
the markers so [1] in the text still means the first source in the list.
"""

import re

from app.retrieval.results import RetrievedChunk

# Matches [1], [12] -- the inline markers the answer prompt asks for.
_CITATION_MARKER = re.compile(r"\[(\d+)\]")


def cited_indexes(answer: str) -> list[int]:
    """Return the source numbers referenced in an answer, in first-use order."""
    seen: list[int] = []
    for match in _CITATION_MARKER.finditer(answer):
        number = int(match.group(1))
        if number not in seen:
            seen.append(number)
    return seen


def keep_cited_sources(
    answer: str, chunks: list[RetrievedChunk]
) -> tuple[str, list[RetrievedChunk]]:
    """Drop uncited sources and renumber the answer's markers to match.

    Returns the rewritten answer and the sources it cites. An answer with no
    citations -- typically one saying the sources do not cover the question --
    keeps its text and returns no sources, rather than listing everything the
    agent happened to read.
    """
    used = [index for index in cited_indexes(answer) if 1 <= index <= len(chunks)]

    if not used:
        return answer, []

    # Old source number -> new position in the filtered list.
    renumbered = {old: new for new, old in enumerate(used, start=1)}

    def replace(match: re.Match) -> str:
        """Rewrite one marker, leaving out-of-range ones untouched."""
        old = int(match.group(1))
        return f"[{renumbered[old]}]" if old in renumbered else match.group(0)

    return _CITATION_MARKER.sub(replace, answer), [chunks[old - 1] for old in used]
