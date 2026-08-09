"""Tests for conversation history handling.

History is what makes a follow-up like "what about the .NET one?" resolvable.
It is also the easiest thing to let grow without bound, so the trimming rules
matter as much as the formatting.
"""

from app.api.routes_chat import MAX_TURN_CHARS, format_history
from app.schemas.chat import MAX_HISTORY_TURNS, ChatRequest, Turn


def _turns(count: int) -> list[dict]:
    """Build alternating user/assistant turns, numbered so order is visible."""
    return [
        {"role": "user" if i % 2 == 0 else "assistant", "content": f"message {i}"}
        for i in range(count)
    ]


def test_a_first_question_has_no_history() -> None:
    """The common case: nothing before it, so nothing to render."""
    request = ChatRequest(question="How do I authenticate?")

    assert request.recent_history() == []
    assert format_history(request.recent_history()) == ""


def test_history_is_trimmed_to_the_most_recent_turns() -> None:
    """A long conversation keeps working; it just stops carrying its whole past."""
    request = ChatRequest(question="and now?", history=_turns(20))

    recent = request.recent_history()

    assert len(recent) == MAX_HISTORY_TURNS
    # Kept the newest, dropped the oldest.
    assert recent[-1].content == "message 19"
    assert all(turn.content != "message 0" for turn in recent)


def test_short_history_is_kept_whole() -> None:
    """Below the cap, nothing is dropped."""
    request = ChatRequest(question="and now?", history=_turns(2))

    assert len(request.recent_history()) == 2


def test_formatting_labels_the_speakers() -> None:
    """The model reads plain text, so roles become readable labels."""
    rendered = format_history(
        [
            Turn(role="user", content="How do I authenticate?"),
            Turn(role="assistant", content="Use HmacAuthBuilder."),
        ]
    )

    assert rendered == "Developer: How do I authenticate?\nAssistant: Use HmacAuthBuilder."


def test_long_turns_are_truncated() -> None:
    """An answer can run long; only its gist is needed to resolve a follow-up.

    Without this, a few verbose turns would crowd the retrieved sources out of
    the prompt -- the opposite of what history is for.
    """
    rendered = format_history([Turn(role="assistant", content="x" * 5000)])

    assert len(rendered) < MAX_TURN_CHARS + 100
    assert rendered.endswith("...")


def test_formatting_collapses_whitespace() -> None:
    """Markdown answers carry newlines that would break the one-line-per-turn shape."""
    rendered = format_history(
        [Turn(role="assistant", content="line one\n\n  line two\ttabbed")]
    )

    assert rendered == "Assistant: line one line two tabbed"
    assert "\n" not in rendered
