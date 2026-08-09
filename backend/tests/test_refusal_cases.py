"""Tests for how unanswerable questions are scored.

These carry the harness's only measurement of honesty. Every other question
rewards producing an answer, so without them a system that never refuses would
score perfectly while being unusable — and the classifier that separates the
two kinds is therefore worth pinning down.
"""

from eval.evaluators import (
    FAILURE_ANSWERED_INSTEAD_OF_REFUSING,
    FAILURE_RETRIEVAL_MISS,
    EvalCase,
    EvalResult,
    classify_failure,
)


def _result(expects_refusal: bool, **metrics) -> EvalResult:
    """Build a scored result for the classifier to judge."""
    case = EvalCase(
        question="does the corpus cover this?",
        reference_answer="...",
        expected_source_url="" if expects_refusal else "https://example.com/a",
        tier="gold",
        expects_refusal=expects_refusal,
    )
    result = EvalResult(
        case=case,
        answer="...",
        retrieved_urls=[],
        cited_urls=[],
        is_grounded=True,
        searches=[],
    )
    result.metrics = metrics
    return result


def test_correctly_declining_passes() -> None:
    """Saying "the sources do not cover this" is the right answer here."""
    assert classify_failure(_result(True, refusal_correctness=1.0)) is None


def test_answering_anyway_is_a_failure() -> None:
    """A confident answer to an uncovered question is the worst outcome."""
    result = _result(True, refusal_correctness=0.0)

    assert classify_failure(result) == FAILURE_ANSWERED_INSTEAD_OF_REFUSING


def test_a_hedged_answer_still_fails() -> None:
    """Partial credit below the halfway mark still counts as answering."""
    assert (
        classify_failure(_result(True, refusal_correctness=0.4))
        == FAILURE_ANSWERED_INSTEAD_OF_REFUSING
    )


def test_retrieval_metrics_do_not_fail_a_refusal_case() -> None:
    """There is no correct source to find, so a retrieval miss is meaningless.

    Search always returns *something*, so scoring these on context_recall would
    fail every refusal case for a reason that has nothing to do with behaviour.
    """
    result = _result(True, refusal_correctness=1.0, context_recall=0.0)

    assert classify_failure(result) is None


def test_answerable_questions_are_unaffected() -> None:
    """The ordinary path still reports a retrieval miss first."""
    result = _result(False, context_recall=0.0, citation_recall=0.0)

    assert classify_failure(result) == FAILURE_RETRIEVAL_MISS


def test_a_missing_judge_verdict_does_not_invent_a_failure() -> None:
    """If the judge reply failed to parse, do not report a false positive.

    A malformed verdict is a harness problem, not a model failure, and marking
    it as one would send someone debugging the wrong thing.
    """
    assert classify_failure(_result(True)) is None
