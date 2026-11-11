"""Eval math: matching, P/R/F1, intervals, field parsing, the split."""

import pytest

from aipb.evals import metrics as M
from aipb.evals.split import freeze_split, make_split

TEXT = (
    "We expect the program to deliver $150 million in annual run-rate cost savings by the "
    "end of 2025, and we plan to reduce support headcount by about 10 percent."
)


def test_match_by_quote_overlap():
    gold = [
        {"quote": "We expect the program to deliver $150 million in annual run-rate cost savings",
         "claim_type": "cost_savings"},
        {"quote": "we plan to reduce support headcount by about 10 percent",
         "claim_type": "workforce"},
    ]  # fmt: skip
    pred = [
        # Longer span, same promise: IoU well above 0.5.
        {"quote": "We expect the program to deliver $150 million in annual run-rate cost "
                  "savings by the end of 2025", "claim_type": "cost_savings"},
        {"quote": "support headcount", "claim_type": "workforce"},  # too short: IoU < 0.5
    ]  # fmt: skip
    matches, missed, extra = M.match_passage(TEXT, gold, pred)
    assert len(matches) == 1 and matches[0].gold is gold[0]
    assert missed == [gold[1]] and extra == [pred[1]]


def test_capitalization_differences_still_match():
    gold = [{"quote": "We plan to reduce support headcount by about 10 percent"}]
    pred = [{"quote": "we plan to reduce support headcount by about 10 percent"}]
    matches, _, _ = M.match_passage(TEXT, gold, pred)
    assert len(matches) == 1


def test_prf_edge_cases():
    assert M.prf(8, 2, 2) == pytest.approx({"precision": 0.8, "recall": 0.8, "f1": 0.8})
    assert M.prf(0, 0, 0) == {"precision": None, "recall": None, "f1": None}
    assert M.prf(0, 3, 2)["f1"] == 0.0


def test_bootstrap_interval_contains_point_and_is_reproducible():
    units = [(1, 0, 0)] * 8 + [(0, 1, 1)] * 2
    stat = lambda s: M.prf(*(sum(x[i] for x in s) for i in range(3)))["f1"]  # noqa: E731
    lo, hi = M.bootstrap(units, stat)
    assert lo <= stat(units) <= hi
    assert M.bootstrap(units, stat) == (lo, hi)  # seeded


def test_wilson_interval():
    lo, hi = M.wilson(0, 22)
    assert lo == 0.0 and 0.1 < hi < 0.2  # "0 of 22" still leaves real uncertainty
    assert M.wilson(0, 0) is None


@pytest.mark.parametrize(
    "text, value",
    [("$150 million", 150e6), ("about 10 percent", 10), ("$1.5 billion", 1.5e9),
     ("2,000 roles", 2000), (None, None), ("double", None)],
)  # fmt: skip
def test_number_of(text, value):
    assert M.number_of(text) == value


def test_field_agreement():
    m = M.Match(
        {"claim_type": "cost_savings", "target": "$150 million", "deadline": "end of 2025"},
        {"claim_type": "cost_savings", "target_value": 150e6, "deadline_year": 2025},
        1.0,
    )
    wrong = M.Match(
        {"claim_type": "margin", "target": "1 point", "deadline": "fiscal 2026"},
        {"claim_type": "cost_savings", "target_text": "2 points", "deadline_year": 2025},
        1.0,
    )
    out = M.field_agreement([m, wrong])
    assert out["claim_type"]["accuracy"] == 0.5
    assert out["target"]["accuracy"] == 0.5
    assert out["deadline_year"]["accuracy"] == 0.5


def test_split_is_grouped_seeded_and_frozen(tmp_path):
    companies = {f"T{i}": f"S{i % 4}" for i in range(10)}
    split = make_split(companies)
    assert len(split["dev"]) == 6 and len(split["test"]) == 4
    assert not set(split["dev"]) & set(split["test"])
    assert make_split(companies) == split
    path = tmp_path / "splits.json"
    first = freeze_split(path, companies)
    companies["T10"] = "S0"  # a later change does not move the frozen split
    assert freeze_split(path, companies)["dev"] == first["dev"]
    assert freeze_split(path, companies, force=True)["replaced_previous"] is True
