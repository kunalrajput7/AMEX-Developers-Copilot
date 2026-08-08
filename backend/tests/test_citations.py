"""Tests for trimming an answer's sources down to the ones it cites."""

from app.agent.citations import cited_indexes, keep_cited_sources
from app.retrieval.results import RetrievedChunk


def _chunk(chunk_id: int) -> RetrievedChunk:
    """Build a chunk that is identifiable by its id."""
    return RetrievedChunk(
        id=chunk_id,
        repo="org/repo",
        file_path=f"file{chunk_id}.md",
        chunk_type="doc",
        source_url=f"https://example.com/{chunk_id}",
        content=f"content {chunk_id}",
        score=1.0,
    )


def test_cited_indexes_are_returned_in_first_use_order() -> None:
    """Markers are collected once each, in the order the reader meets them."""
    assert cited_indexes("See [3] and [1], then [3] again.") == [3, 1]


def test_uncited_sources_are_dropped() -> None:
    """Sources the answer never referenced do not appear as citations."""
    chunks = [_chunk(i) for i in range(1, 6)]

    _, kept = keep_cited_sources("Only [2] and [4] matter.", chunks)

    assert [chunk.id for chunk in kept] == [2, 4]


def test_markers_are_renumbered_to_match_the_kept_list() -> None:
    """[2] and [4] become [1] and [2], so the text matches what is shown."""
    chunks = [_chunk(i) for i in range(1, 6)]

    answer, kept = keep_cited_sources("Only [2] and [4] matter.", chunks)

    assert answer == "Only [1] and [2] matter."
    assert len(kept) == 2


def test_answer_without_citations_returns_no_sources() -> None:
    """A refusal should not list every source the agent happened to read."""
    chunks = [_chunk(i) for i in range(1, 4)]

    answer, kept = keep_cited_sources("The sources do not cover this.", chunks)

    assert answer == "The sources do not cover this."
    assert kept == []


def test_out_of_range_markers_are_left_alone() -> None:
    """A hallucinated [99] is not renumbered into something misleading."""
    chunks = [_chunk(1), _chunk(2)]

    answer, kept = keep_cited_sources("Real [1], invented [99].", chunks)

    assert "[99]" in answer
    assert [chunk.id for chunk in kept] == [1]
