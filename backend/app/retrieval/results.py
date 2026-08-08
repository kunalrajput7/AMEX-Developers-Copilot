"""The common shape every retriever returns.

Vector search, keyword search, and the fused hybrid search all produce these,
so they can be compared, merged, and rendered as citations interchangeably.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class RetrievedChunk:
    """One chunk returned by a retriever, with the score that ranked it."""

    id: int
    repo: str
    file_path: str
    chunk_type: str
    source_url: str
    content: str
    score: float

    def snippet(self, max_chars: int = 300) -> str:
        """Return a short preview of the content, for citations and logs."""
        text = " ".join(self.content.split())
        if len(text) <= max_chars:
            return text
        return text[:max_chars].rstrip() + "..."


def format_for_prompt(chunks: list[RetrievedChunk]) -> str:
    """Render chunks as a numbered source list for a prompt.

    The numbering is what the model cites as [1], [2], so it must match the
    order of the chunks list the caller keeps.
    """
    return "\n\n".join(
        f"[{index}] {chunk.repo}/{chunk.file_path} ({chunk.chunk_type})\n"
        f"URL: {chunk.source_url}\n"
        f"---\n{chunk.content}"
        for index, chunk in enumerate(chunks, start=1)
    )
