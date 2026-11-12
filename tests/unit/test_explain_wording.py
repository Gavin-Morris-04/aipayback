"""Explanations: range comparisons are computed in code, and the wording is checked (D46)."""

from aipb.llm.client import LLMResult
from aipb.stages import explain as ex
from aipb.verify.context import EvidencePassage
from aipb.verify.neutral import first_person, process_words
from aipb.verify.numbers import NumberRow
from aipb.verify.targets import comparisons, usd_range


def row(label: str, value: float, year: int, unit: str = "USD", kind: str = "fact") -> NumberRow:
    end = f"{year}-12-31"
    return NumberRow("N1", f"{label} for the fiscal year ended {end}", value, unit, kind, "t",
                     year, f"{year}-01-01", end, "a", "2026-01-29")  # fmt: skip


def test_dollar_ranges_are_parsed():
    assert usd_range("$30-37 billion") == (30e9, 37e9)
    assert usd_range("approximately $70 billion to $72 billion") == (70e9, 72e9)
    assert usd_range("$35–40 billion") == (35e9, 40e9)
    assert usd_range("between $100 million and $150 million") == (100e6, 150e6)
    assert usd_range("about $5 billion") is None and usd_range(None) is None


def test_capex_rows_for_the_deadline_year_are_placed_against_the_range():
    rows = [
        row("capex", 37.26e9, 2024),
        row("capex", 69.69e9, 2025),
        row("capex", 87.1, 2025, unit="pct_change", kind="change"),
        row("capital expenditures as the company defines them (computed by code)", 72.22e9, 2025),
        row("finance lease principal", 2.52e9, 2025),
    ]
    out = comparisons("approximately $70 billion to $72 billion", "capex_investment", 2025, rows)
    assert len(out) == 2
    assert "($69.69 billion) is below the range; it does not reach the low end." in out[0]
    assert "($72.22 billion) is above the range; it reaches the low end." in out[1]
    assert "promised range of $70 billion to $72 billion" in out[0]
    within = comparisons("$66 billion to $72 billion", "capex_investment", 2025, rows)
    assert "is within the range; it reaches the low end" in within[0]
    assert comparisons("$30-37 billion", "revenue", 2024, rows) == []  # capex promises only


def test_the_company_voice_and_our_process_stay_out_of_explanations():
    assert first_person("We anticipate capex of $40 billion.") == ["we"]
    assert first_person('Meta said "we anticipate capex" and our 10-K agrees.') == ["our"]
    assert first_person("The U.S. market grew; Meta said “we expect growth”.") == []
    found = process_words("The key finding is not verified in the documents provided.")
    assert found == ["key finding", "not verified", "the documents"]


def _cited(text: str, idx: int, cited: str) -> dict:
    return {
        "type": "text",
        "text": text,
        "citations": [
            {
                "type": "char_location",
                "cited_text": cited,
                "document_index": idx,
                "start_char_index": 0,
                "end_char_index": len(cited),
            }
        ],
    }


def test_an_explanation_in_the_company_voice_is_held_back():
    docs = ex.documents(
        "We expect X.",
        "10-K filed 2025-02-20",
        "We expect X. More text.",
        [EvidencePassage("E1", "p", "10-Q", "2025-07-30", "s", "We did X.", 0)],
        [],
    )
    later = _cited(" It did.", 1, "We did X.")
    third = [_cited('Acme said "we expect X."', 0, "We expect X."), later]
    assert ex.check(LLMResult({"content": third}, False, "c", 0), docs, "delivered").ok
    first = [_cited("We expect X.", 0, "We expect X."), later]
    e = ex.check(LLMResult({"content": first}, False, "c", 0), docs, "delivered")
    assert e.citations_valid and not e.lint_ok and not e.ok
    assert any("company's voice" in p for p in e.problems)


def test_a_word_for_word_citation_is_shown_as_a_quote():
    docs = ex.documents(
        "We expect X.",
        "10-K filed 2025-02-20",
        "We expect to ship X in the second quarter. More text.",
        [EvidencePassage("E1", "p", "10-Q", "2025-07-30", "s", "We shipped X.", 0)],
        [],
    )
    copied = "We expect to ship X in the second quarter."
    blocks = [
        {"type": "text", "text": "Acme said in its 10-K that "},
        _cited(copied, 0, copied),
        _cited(" The 10-Q reports shipments.", 1, "We shipped X."),
    ]
    e = ex.check(LLMResult({"content": blocks}, False, "c", 0), docs, "delivered")
    assert e.text.startswith("Acme said in its 10-K that “We expect to ship X")
    assert e.ok  # quoted, so "We" is the company's voice, shown as a quote
    assert e.citations[0]["after_char"] == len("Acme said in its 10-K that ") + len(copied) + 2
