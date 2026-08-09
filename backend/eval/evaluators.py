"""How an answer is scored.

Two kinds of metric, deliberately kept apart because they deserve different
levels of trust:

  Retrieval metrics are computed by comparing URLs. No model reads them, so
  the arithmetic is exact and free.

  Generation metrics need a model to judge them, because "is this claim
  supported" has no arithmetic answer.

  Neither kind is reproducible run to run, and it is worth being clear about
  why. The retrieval metrics measure *which chunks the agent gathered*, and the
  agent picks its own search queries -- those vary between runs even at
  temperature 0, because model inference is not bit-deterministic. Exact
  arithmetic over a non-deterministic input is still non-deterministic.
  Measured spread across two identical runs was 0.04 to 0.08 on every metric,
  with three of twenty-five questions changing verdict. Treat every number here
  as a trend, and see thresholds.yaml for how the floors account for it.

The judge is a different model family from the one being graded, so its
verdicts are independent rather than self-congratulatory. See llm/judge_client.
"""

import json
import logging
import re
from dataclasses import dataclass, field

from app.llm import judge_client

logger = logging.getLogger(__name__)

_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)


REFUSAL_JUDGE_PROMPT = """\
A documentation assistant was asked a question its source corpus does not cover.
The only correct behaviour is to say it cannot answer from the sources.

Question:
{question}

Why it is unanswerable:
{reference_answer}

The assistant's answer:
{answer}

Score 1.0 if it clearly declined, said the sources do not cover this, or asked
for something outside its scope. Score 0.0 if it answered anyway -- including a
confident answer that happens to be true in general, since it could not have
known that from these sources. Partial credit for a hedged answer that still
asserts specifics.

Reply with JSON only:
{{"refusal_correctness": 0.0, "notes": "one short sentence"}}
"""


JUDGE_PROMPT = """\
You are grading an answer produced by a documentation assistant.

Question:
{question}

Reference answer (what a correct answer should contain):
{reference_answer}

Sources the assistant was given:
{context}

The assistant's answer:
{answer}

Score three things from 0.0 to 1.0:

- faithfulness: is every claim in the answer supported by the sources? An
  answer that correctly states the sources do not cover the question scores
  1.0. An answer containing any invented detail scores below 0.5.
- answer_relevance: does it actually address what was asked?
- answer_correctness: does it agree with the reference answer?

Reply with JSON only:
{{"faithfulness": 0.0, "answer_relevance": 0.0, "answer_correctness": 0.0, "notes": "one short sentence"}}
"""


@dataclass
class EvalCase:
    """One row of the evaluation dataset."""

    question: str
    reference_answer: str
    expected_source_url: str
    tier: str  # 'gold' (hand-written, trusted) or 'synthetic' (generated)

    # True for questions the corpus genuinely cannot answer. The correct
    # behaviour is to say so, and these are the only cases that test it --
    # every other question has an answer, so refusing is never the right move.
    # Without them the harness measures accuracy and never measures honesty.
    expects_refusal: bool = False

    # Other sources that answer the question just as well. Some questions are
    # legitimately answered from several files -- a README and the code it
    # describes, say -- and insisting on one of them marks a correct answer
    # wrong for citing the better source.
    alternate_source_urls: list[str] = field(default_factory=list)

    @property
    def acceptable_urls(self) -> list[str]:
        """Every source that counts as finding the answer."""
        return [self.expected_source_url, *self.alternate_source_urls]


@dataclass
class EvalResult:
    """What the agent produced for one case, and how it scored."""

    case: EvalCase
    answer: str
    retrieved_urls: list[str]
    cited_urls: list[str]
    is_grounded: bool
    searches: list[str]
    metrics: dict[str, float] = field(default_factory=dict)
    failure: str | None = None
    judge_notes: str = ""


def normalise_url(url: str) -> str:
    """Strip anchors and trailing slashes so URL comparison is not brittle."""
    return url.split("#")[0].rstrip("/").strip().lower()


# --- Retrieval metrics: exact, no model involved -------------------------


def context_recall(result: EvalResult) -> float:
    """1.0 if an acceptable source was retrieved at all, else 0.0.

    The single most important metric here. If the right document never comes
    back, no amount of prompt tuning will produce a correct answer.

    Not stable run to run: it depends on which searches the agent chose, and
    those vary. A single-run drop is a coin flip; a sustained drop is real.
    """
    acceptable = {normalise_url(url) for url in result.case.acceptable_urls}
    retrieved = {normalise_url(url) for url in result.retrieved_urls}
    return 1.0 if acceptable & retrieved else 0.0


def citation_recall(result: EvalResult) -> float:
    """1.0 if an acceptable source was actually cited, not merely retrieved.

    Stricter than context_recall: retrieving the right document and then
    ignoring it is a real failure that recall alone would hide.
    """
    acceptable = {normalise_url(url) for url in result.case.acceptable_urls}
    cited = {normalise_url(url) for url in result.cited_urls}
    return 1.0 if acceptable & cited else 0.0


def reciprocal_rank(result: EvalResult) -> float:
    """1/rank of the best acceptable source, or 0 if none were retrieved.

    Shows ranking quality rather than presence, so a change that pushes the
    right source from position 1 to position 8 is visible even though
    context_recall stays at 1.0.
    """
    acceptable = {normalise_url(url) for url in result.case.acceptable_urls}
    for rank, url in enumerate(result.retrieved_urls, start=1):
        if normalise_url(url) in acceptable:
            return 1.0 / rank
    return 0.0


# --- Generation metrics: judged by a model -------------------------------


def _parse_scores(reply: str, result: EvalResult) -> dict:
    """Pull the judge's JSON verdict out of its reply, or {} if unparseable.

    Returning empty rather than raising means one malformed verdict costs that
    case's judged metrics, not the whole run -- and `averages` skips missing
    metrics, so the remaining cases still produce a usable scorecard.
    """
    match = _JSON_BLOCK.search(reply)
    if not match:
        logger.warning("Judge returned no JSON for %r", result.case.question[:60])
        return {}

    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        logger.warning("Judge returned malformed JSON for %r", result.case.question[:60])
        return {}


async def judge_answer(result: EvalResult, context: str) -> dict[str, float]:
    """Ask the judge model to score faithfulness, relevance, and correctness.

    All three in one call rather than three, which keeps eval runs affordable.
    """
    prompt = JUDGE_PROMPT.format(
        question=result.case.question,
        reference_answer=result.case.reference_answer,
        context=context or "(no sources retrieved)",
        answer=result.answer or "(no answer produced)",
    )

    scores = _parse_scores(await judge_client.judge(prompt), result)
    if not scores:
        return {}

    result.judge_notes = str(scores.get("notes", ""))

    return {
        name: float(scores.get(name, 0.0))
        for name in ("faithfulness", "answer_relevance", "answer_correctness")
    }


# --- Failure analysis -----------------------------------------------------

# An average tells you quality moved. A failure breakdown tells you where to
# look, which is the difference between a number and a debugging tool.
FAILURE_RETRIEVAL_MISS = "retrieval_miss"
FAILURE_RETRIEVED_BUT_UNCITED = "retrieved_but_uncited"
FAILURE_UNGROUNDED = "ungrounded"
FAILURE_WRONG_ANSWER = "wrong_answer"

# The worst outcome the system can produce: a confident answer to something the
# corpus never covered. Tracked separately because it is a different kind of
# wrong -- not an imperfect answer, but an invented one.
FAILURE_ANSWERED_INSTEAD_OF_REFUSING = "answered_instead_of_refusing"


def classify_failure(result: EvalResult) -> str | None:
    """Name the first thing that went wrong, or None if the case passed.

    Ordered from earliest stage to latest: a retrieval miss explains every
    later failure, so reporting it as "wrong answer" would be misleading.

    Note what does *not* appear here: the agent's own `is_grounded` flag. The
    agent sets that false when it runs out of rewrites, which is not the same
    as producing a bad answer -- observed cases score 1.0 on every judged
    metric while still self-flagging. An independent judge is the whole reason
    for having an evaluation harness, so it decides; `is_grounded` is reported
    separately as operational detail.
    """
    metrics = result.metrics

    # Unanswerable questions are judged on one thing only: did it decline?
    # Retrieval metrics are meaningless here -- there is no correct source to
    # find, and search always returns *something*.
    if result.case.expects_refusal:
        if metrics.get("refusal_correctness", 1.0) < 0.5:
            return FAILURE_ANSWERED_INSTEAD_OF_REFUSING
        return None

    if metrics.get("context_recall", 0.0) < 1.0:
        return FAILURE_RETRIEVAL_MISS

    if metrics.get("citation_recall", 0.0) < 1.0:
        return FAILURE_RETRIEVED_BUT_UNCITED

    if metrics.get("faithfulness", 1.0) < 0.5:
        return FAILURE_UNGROUNDED

    if metrics.get("answer_correctness", 1.0) < 0.5:
        return FAILURE_WRONG_ANSWER

    return None


async def judge_refusal(result: EvalResult) -> dict[str, float]:
    """Score whether an unanswerable question was correctly declined."""
    prompt = REFUSAL_JUDGE_PROMPT.format(
        question=result.case.question,
        reference_answer=result.case.reference_answer,
        answer=result.answer or "(no answer produced)",
    )

    scores = _parse_scores(await judge_client.judge(prompt), result)
    if not scores:
        return {}

    result.judge_notes = str(scores.get("notes", ""))
    return {"refusal_correctness": float(scores.get("refusal_correctness", 0.0))}


async def score(result: EvalResult, context: str) -> EvalResult:
    """Fill in every metric for one result, then classify any failure.

    Answerable and unanswerable questions get different metrics, because they
    are asking different things of the system. Averaging in run_eval.py skips
    metrics a case does not carry, so the two kinds coexist in one dataset.
    """
    if result.case.expects_refusal:
        result.metrics.update(await judge_refusal(result))
    else:
        result.metrics["context_recall"] = context_recall(result)
        result.metrics["citation_recall"] = citation_recall(result)
        result.metrics["reciprocal_rank"] = reciprocal_rank(result)
        result.metrics.update(await judge_answer(result, context))

    result.failure = classify_failure(result)
    return result
