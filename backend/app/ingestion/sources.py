"""The common record every ingestion source produces.

Adding a new content source later (Confluence, a docs site) means writing a
loader that yields `SourceDocument`s. Nothing downstream -- chunking, hashing,
embedding, storage -- needs to change.
"""

from dataclasses import dataclass

# Values allowed in the chunks.chunk_type column. The agent's three search
# tools filter on these.
CHUNK_TYPE_DOC = "doc"
CHUNK_TYPE_CODE = "code"
CHUNK_TYPE_ISSUE = "issue"


@dataclass(frozen=True)
class SourceDocument:
    """One retrievable unit of text, before it is split into chunks."""

    source: str  # adapter that produced it, e.g. 'github'
    repo: str  # 'americanexpress/fetchye'
    file_path: str  # 'README.md', or 'issues/123' for an issue
    chunk_type: str  # one of the CHUNK_TYPE_* constants above
    text: str
    source_url: str  # clickable link, stored on every chunk for citations
