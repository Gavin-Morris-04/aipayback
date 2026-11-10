"""Keyword prefilter and conservative dedup."""

from pathlib import Path

import pytest

from aipb.stages.prefilter import Deduper, Lexicon, numbers_in

REPO = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def lex() -> Lexicon:
    return Lexicon.load(REPO / "config" / "keywords.yaml")


def test_ai_terms(lex):
    assert lex.scan("We expanded our AI platform.")[0] == ["ai"]
    assert lex.scan("Our artiﬁcial intelligence tools")[0] == ["artificial intelligence"]
    assert lex.scan("Agentforce and watsonx and Copilot")[0] == ["agentforce", "copilot", "watsonx"]
    assert lex.scan("We use large language models (LLMs).")[0] == ["large language models", "llms"]


def test_ai_is_case_sensitive(lex):
    # "ai" inside words or in lower case is not a hit; "Ai" is not either.
    assert lex.scan("He said the Ai Weiwei exhibit was maintained.")[0] == []
    assert lex.scan("Einstein was a physicist")[0] == ["einstein"]  # known noise; classifier drops


def test_forward_cues(lex):
    _, fwd = lex.scan("We expect savings of $1 billion by 2026 and will reduce costs.")
    assert {"expect", "will", "by 2026"} <= set(fwd)
    assert lex.scan("Revenue was $5 billion in 2024.")[1] == []


def test_numbers_in():
    assert numbers_in("$3,500 million by 2025, 10.5%") == ("10.5", "2025", "3500")


def test_exact_and_near_duplicates_with_same_numbers_are_merged():
    d = Deduper()
    base = (
        "We expect our AI program to deliver $150 million in annual run-rate cost savings "
        "by the end of 2025 through automation of customer support, software development "
        "and finance operations across all of our regions and business units worldwide."
    )
    assert d.check("p1", base) is None
    assert d.check("p2", base) == "p1"  # exact
    near = base.replace("worldwide.", "worldwide, as described above.")
    assert d.check("p3", near) == "p1"  # near-identical, same numbers


def test_changed_number_is_never_a_duplicate():
    """The safety property: a raised or lowered target must stay visible."""
    d = Deduper()
    old = "We expect AI to deliver $3.5 billion in savings by the end of 2025 " + "x " * 60
    new = old.replace("$3.5 billion", "$4.5 billion")
    later = old.replace("2025", "2026")
    assert d.check("p1", old) is None
    assert d.check("p2", new) is None
    assert d.check("p3", later) is None


def test_exact_only_mode():
    d = Deduper(threshold=2.0)
    assert d.check("a", "Some text here.") is None
    assert d.check("b", "Some  text here.") == "a"  # whitespace-insensitive
    assert d.check("c", "Some text here!") is None
