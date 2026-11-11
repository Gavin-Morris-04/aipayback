"""Verification building blocks: calculator, lint, verdict validation, gate, citations."""

import sqlite3

import pytest

from aipb import db
from aipb.llm.client import LLMResult
from aipb.stages import explain as ex
from aipb.verify import gate
from aipb.verify.calc import CalcError, calculate, pct_change
from aipb.verify.context import EvidencePassage, VerifyContext
from aipb.verify.neutral import banned_words
from aipb.verify.numbers import annual_series, deadline_end, fiscal_year_end
from aipb.verify.tier1 import Verdict, validate


def test_calculator():
    assert calculate("(1234.5 - 1100) / 1100 * 100") == pytest.approx(12.227, abs=1e-3)
    assert calculate("$1,500 * 2") == 3000
    for bad in ("__import__('os')", "a + 1", "2 ** 100", "1 / 0", "max(1, 2)"):
        with pytest.raises(CalcError):
            calculate(bad)
    assert pct_change(100, 112) == pytest.approx(12.0)
    assert pct_change(0, 5) is None


def test_neutral_lint_ignores_quotes():
    assert banned_words("The company failed to deliver") == ["failed"]
    assert banned_words('The filing calls it a "failure of innovation" risk.') == []
    assert banned_words("The 2025 10-K reports $162 million of savings.") == []


def ctx(**kw) -> VerifyContext:
    base = dict(
        cluster_id="c1",
        variant="default",
        cik=1,
        ticker="EXMP",
        company="Exemplar",
        promise={"quote": "q"},
        restatements=[],
        promise_passage="",
        first_stated="2025-02-20",
        as_of="2026-10-30",
        fy_end="12-31",
        deadline_end="2025-12-31",
        deadline_passed=True,
        deadline_results_filed=True,
        periodic_after_deadline=1,
        mentions_after_deadline=1,
        evidence=[EvidencePassage("E1", "p1", "10-K", "2026-02-20", "item7", "text", 0.0)],
        numbers=[],
    )
    base.update(kw)
    return VerifyContext(**base)


def raw(**kw) -> dict:
    v = {
        "status": "delivered",
        "walked_back_kind": "none",
        "confidence": 0.9,
        "evidence_ids": ["E1"],
        "number_ids": [],
        "key_finding": "The 10-K reports it.",
    }
    v.update(kw)
    return v


def test_validate_catches_bad_citations_and_impossible_statuses():
    assert validate(raw(), ctx(), "1").valid
    v = validate(raw(evidence_ids=["E9"]), ctx(), "1")
    assert not v.valid and "not provided" in v.problems[0]
    assert not validate(raw(evidence_ids=[]), ctx(), "1").valid  # delivered cites nothing
    assert not validate(raw(status="on_track"), ctx(), "1").valid  # deadline already passed
    assert not validate(raw(key_finding="They failed."), ctx(), "1").valid
    assert validate(raw(status="no_evidence_yet", evidence_ids=[]), ctx(), "1").valid


def test_silent_walkback_is_downgraded_unless_code_conditions_hold():
    v = validate(raw(status="walked_back", walked_back_kind="silent", evidence_ids=[]), ctx(), "1")
    assert v.status == "no_evidence_yet" and v.valid  # only 1 later 10-K/10-Q, and a mention
    quiet = ctx(periodic_after_deadline=2, mentions_after_deadline=0)
    v = validate(raw(status="walked_back", walked_back_kind="silent", evidence_ids=[]), quiet, "1")
    assert v.status == "walked_back" and v.valid
    v = validate(
        raw(status="walked_back", walked_back_kind="explicit", evidence_ids=[]), ctx(), "1"
    )
    assert not v.valid  # an explicit walk-back must cite the passage


def V(status="delivered", conf=0.9, valid=True, kind="none", tier="1"):
    return Verdict(tier, status, kind, conf, ["E1"], [], "x", valid, [] if valid else ["bad"])


@pytest.mark.parametrize(
    "t1, t2, kw, label, publishable",
    [
        (V(), None, {}, "Delivered", True),
        (V(conf=0.5), None, {}, gate.PENDING, False),
        (V(conf=0.5), V(conf=0.9, tier="2"), {}, "Delivered", True),
        (V(valid=False), V(status="on_track", tier="2"), {}, "On track", True),
        (V(status="on_track"), V(status="delivered", tier="2"), {}, gate.PENDING, False),
        (
            V(status="no_evidence_yet", conf=0.4),
            V(status="on_track", tier="2"),
            {},
            "On track",
            True,
        ),
        (V(status="on_track"), V(status="delivered", conf=0.3, tier="2"), {}, "On track", True),
        (V(status="walked_back", kind="explicit"), None, {}, gate.PENDING, False),
        (
            V(status="walked_back", kind="explicit"),
            V(status="on_track", tier="2"),
            {},
            gate.PENDING,
            False,
        ),
        (
            V(status="walked_back", kind="explicit"),
            V(status="walked_back", kind="explicit", tier="2"),
            {},
            "Walked back",
            True,
        ),
        (
            V(status="walked_back", kind="silent"),
            V(status="walked_back", kind="silent", tier="2"),
            {},
            "Walked back (silent)",
            True,
        ),
        (V(), None, {"explanation_ok": False}, gate.PENDING, False),
        (V(), None, {"open_error_report": True}, gate.PENDING, False),
        (None, None, {}, gate.PENDING, False),
    ],
)
def test_gate(t1, t2, kw, label, publishable):
    args = {"explanation_ok": True, "open_error_report": False, **kw}
    d = gate.decide(t1, t2, **args)
    assert (d.label, d.publishable) == (label, publishable)


def test_needs_tier2():
    assert gate.needs_tier2(V(conf=0.5)) and gate.needs_tier2(V(status="walked_back"))
    assert gate.needs_tier2(None) and not gate.needs_tier2(V())


def _result(blocks):
    return LLMResult({"content": blocks, "stop_reason": "end_turn"}, False, "c", 0)


def test_explanation_citations_are_checked_against_the_documents():
    docs = ex.documents(
        "We expect X.",
        "10-K filed 2025-02-20",
        "We expect X. More text.",
        [EvidencePassage("E1", "p", "10-Q", "2025-07-30", "s", "We did X.", 0)],
        [],
    )
    good = [
        {
            "type": "text",
            "text": "It promised X.",
            "citations": [
                {
                    "type": "char_location",
                    "cited_text": "We expect X.",
                    "document_index": 0,
                    "start_char_index": 0,
                    "end_char_index": 12,
                }
            ],
        },
        {
            "type": "text",
            "text": " A 10-Q reports it.",
            "citations": [
                {
                    "type": "char_location",
                    "cited_text": "We did X.",
                    "document_index": 1,
                    "start_char_index": 0,
                    "end_char_index": 9,
                }
            ],
        },
    ]
    e = ex.check(_result(good), docs, "on_track")
    assert e.ok and len(e.citations) == 2
    forged = [dict(good[0]), good[1]]
    forged[0] = {**good[0], "citations": [{**good[0]["citations"][0], "cited_text": "We beat X"}]}
    assert not ex.check(_result(forged), docs, "on_track").citations_valid
    assert not ex.check(_result(good[1:]), docs, "on_track").ok  # promise not cited
    assert not ex.check(_result(good[:1]), docs, "delivered").ok  # no evidence cited
    assert ex.check(_result(good[:1]), docs, "no_evidence_yet").ok
    worded = [*good, {"type": "text", "text": " Management failed."}]
    assert not ex.check(_result(worded), docs, "on_track").lint_ok


@pytest.fixture
def facts_db(tmp_path):
    conn = db.connect(tmp_path / "x.sqlite")
    rows = [
        (
            1,
            "us-gaap",
            "Revenues",
            "USD",
            "2023-01-01",
            "2023-12-31",
            100.0,
            2023,
            "FY",
            "10-K",
            "2024-02-01",
            "a1",
            "",
        ),
        (
            1,
            "us-gaap",
            "Revenues",
            "USD",
            "2023-01-01",
            "2023-12-31",
            101.0,
            2024,
            "FY",
            "10-K",
            "2025-02-01",
            "a2",
            "",
        ),  # restated in the next 10-K
        (
            1,
            "us-gaap",
            "Revenues",
            "USD",
            "2024-01-01",
            "2024-12-31",
            120.0,
            2024,
            "FY",
            "10-K",
            "2025-02-01",
            "a2",
            "",
        ),
        (
            1,
            "us-gaap",
            "Revenues",
            "USD",
            "2024-07-01",
            "2024-09-30",
            30.0,
            2024,
            "Q3",
            "10-Q",
            "2024-10-30",
            "a3",
            "",
        ),
    ]
    conn.executemany("INSERT INTO xbrl_facts VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    conn.commit()
    yield conn
    conn.close()


def test_annual_series_prefers_restated_values(facts_db: sqlite3.Connection):
    tag, annual = annual_series(facts_db, 1, ["OperatingExpenses", "Revenues"])
    assert tag == "Revenues"
    assert {k: v["value"] for k, v in annual.items()} == {"2023-12-31": 101.0, "2024-12-31": 120.0}
    assert fiscal_year_end(facts_db, 1) == "12-31"
    assert deadline_end(2025, "06-30") == "2025-06-30" and deadline_end(None, "12-31") is None
