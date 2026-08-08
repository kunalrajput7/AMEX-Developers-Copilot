"""Tests for chunking and content hashing -- the parts that decide corpus quality."""

from app.ingestion.chunker import (
    MIN_CHUNK_TOKENS,
    TARGET_TOKENS,
    Chunk,
    chunk_text,
    count_tokens,
)
from app.ingestion.ingest import content_hash


def test_short_text_stays_one_chunk() -> None:
    """Text under the target size is not split."""
    text = "How do I authenticate?\n\nUse the client credentials grant flow."
    assert len(chunk_text(text)) == 1


def test_long_text_is_split_into_multiple_chunks() -> None:
    """Text well over the target size produces several chunks."""
    paragraph = "This sentence exists purely to take up tokens. " * 30
    text = "\n\n".join([paragraph] * 6)

    chunks = chunk_text(text)

    assert len(chunks) > 1
    # Allow overshoot for the overlap carried into each chunk.
    for chunk in chunks:
        assert count_tokens(chunk) <= TARGET_TOKENS * 2


def test_tiny_fragments_are_dropped() -> None:
    """Headings and stray lines alone are not worth storing."""
    assert chunk_text("# Title") == []


def test_short_but_complete_document_is_kept() -> None:
    """A whole document below the fragment threshold survives.

    Guards the distinction between a leftover tail (drop) and a small file
    that is complete in itself (keep).
    """
    text = "How do I authenticate?\n\nUse the client credentials grant flow."

    assert count_tokens(text) < MIN_CHUNK_TOKENS
    assert chunk_text(text) == [text]


def test_oversized_single_block_is_still_split() -> None:
    """A block with no blank lines is split by token count rather than kept whole."""
    text = "word " * 4000

    chunks = chunk_text(text)

    assert len(chunks) > 1


def test_chunks_meet_minimum_size() -> None:
    """Every emitted chunk clears the minimum token threshold."""
    text = "\n\n".join(f"Paragraph {i} with enough words to matter here." for i in range(40))

    for chunk in chunk_text(text):
        assert count_tokens(chunk) >= MIN_CHUNK_TOKENS


def _chunk(repo: str, file_path: str, content: str) -> Chunk:
    """Build a Chunk with the fields the hash depends on."""
    return Chunk(
        source="github",
        repo=repo,
        file_path=file_path,
        chunk_type="doc",
        source_url="https://example.com",
        content=content,
    )


def test_identical_chunks_hash_identically() -> None:
    """The same content from the same place is recognised as unchanged."""
    a = _chunk("org/repo", "README.md", "same text")
    b = _chunk("org/repo", "README.md", "same text")

    assert content_hash(a) == content_hash(b)


def test_same_content_in_different_repos_hashes_differently() -> None:
    """Shared boilerplate stays separately retrievable, each with its own citation."""
    a = _chunk("org/repo-one", "LICENSE.md", "Apache License 2.0")
    b = _chunk("org/repo-two", "LICENSE.md", "Apache License 2.0")

    assert content_hash(a) != content_hash(b)


def test_changed_content_changes_the_hash() -> None:
    """An edited file is treated as new content and re-embedded."""
    before = _chunk("org/repo", "README.md", "old text")
    after = _chunk("org/repo", "README.md", "new text")

    assert content_hash(before) != content_hash(after)
