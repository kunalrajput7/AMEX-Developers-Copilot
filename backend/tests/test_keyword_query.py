"""Tests for turning a question into a Postgres text-search query.

The failure mode being guarded against is silent: a badly built tsquery returns
zero rows rather than erroring, so retrieval quietly loses half its signal.
"""

from app.retrieval.keyword_search import _to_tsquery_input


def test_question_words_are_or_ed() -> None:
    """A natural-language question must not compile to an AND of every word."""
    result = _to_tsquery_input("how do I authenticate with the Amex API?")

    assert " or " in result
    assert "authenticate" in result


def test_hyphenated_identifier_contributes_its_parts() -> None:
    """A hyphenated token is a phrase query in Postgres, so parts are added too.

    Without this, `X-Amex-Api-Key` requires every segment present and adjacent,
    and a near miss returns nothing instead of partial matches.
    """
    result = _to_tsquery_input("X-Amex-Api-Key")

    assert "X-Amex-Api-Key" in result
    assert "Amex" in result
    assert "Api" in result
    assert "Key" in result


def test_full_identifier_precedes_its_fragments() -> None:
    """The exact form comes first, so it ranks ahead of its parts."""
    result = _to_tsquery_input("SPDX-License-Identifier")
    terms = [term.strip() for term in result.split(" or ")]

    assert terms[0] == "SPDX-License-Identifier"


def test_short_fragments_are_dropped() -> None:
    """One and two character fragments match too much to be useful."""
    result = _to_tsquery_input("a-b-token")

    assert "token" in result
    terms = [term.strip() for term in result.split(" or ")]
    assert "a" not in terms
    assert "b" not in terms


def test_terms_are_deduplicated() -> None:
    """A repeated word appears once, keeping the query readable in logs."""
    result = _to_tsquery_input("token token TOKEN")
    terms = [term.strip().lower() for term in result.split(" or ")]

    assert terms.count("token") == 1


def test_camel_case_identifier_survives_intact() -> None:
    """camelCase carries no hyphens, so it stays a single precise token."""
    assert _to_tsquery_input("storeReceivedOnFailure") == "storeReceivedOnFailure"


def test_query_with_no_identifiers_falls_back_to_the_raw_text() -> None:
    """Punctuation-only input still produces something searchable."""
    assert _to_tsquery_input("?? !!") == "?? !!"
