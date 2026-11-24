"""D57: growth targets are compared with reported growth in code, and statements that aren't
the company's own commitment (analyst forecasts, market sizes) are dropped at extract."""

from aipb.stages.extract import not_own_statement, split_own, verify
from aipb.verify import gate
from aipb.verify.numbers import NumberRow
from aipb.verify.targets import (
    GROWTH_HOLD,
    growth_checks,
    growth_conflict,
    growth_conflicts,
    growth_target,
)


def change(year: int, value: float, label: str = "revenue") -> NumberRow:
    end = f"{year}-05-31"
    return NumberRow("N6", f"{label} change vs prior year, FY ended {end}", value, "pct_change",
                     "change", "us-gaap:Revenues", year, f"{year - 1}-05-31", end, "a",
                     "2025-06-20")  # fmt: skip


# ---------- growth targets ----------


def test_growth_targets_follow_the_rubric_tolerances():
    double = growth_target("double-digit revenue growth", "revenue growth", "revenue")
    assert double.floor == 9.5 and "double-digit" in double.words  # 10%, the 95% rule
    assert growth_target("triple-digit growth", "revenue growth", "revenue").floor == 95.0
    assert growth_target("15% revenue growth", "revenue growth", "revenue").floor == 15 * 0.95
    assert growth_target("at least 15% growth", "revenue growth", "revenue").floor == 15.0
    assert growth_target("about 15% growth", "revenue growth", "revenue").floor == 15 * 0.9
    assert growth_target("8% to 10% growth", "net sales growth", "revenue").floor == 8.0
    assert growth_target("8-10% growth", "total revenue growth", "revenue").floor == 8.0
    both = growth_target("double-digit revenue growth", "revenue growth and margin expansion",
                         "revenue")  # fmt: skip
    assert both is not None


def test_only_total_revenue_growth_is_compared():
    # A segment, a quarter or another measure isn't the annual total in the number table.
    assert growth_target("double-digit ARR growth", "ARR growth", "revenue") is None
    assert growth_target("double-digit growth", "cloud revenue growth", "revenue") is None
    assert growth_target("50% year-over-year growth", "Q3 2025 revenue growth", "revenue") is None
    assert growth_target("double-digit growth", "ISG net revenue growth", "revenue") is None
    assert growth_target("double-digit revenue growth", "revenue growth", "margin") is None
    assert growth_target("$60 billion", "revenue", "revenue") is None  # not a growth target
    assert growth_target(None, None, "revenue") is None


def test_the_oracle_case_is_held():
    # D56: "double-digit revenue growth this fiscal year", FY2025 growth 8.4%, marked Delivered.
    rows = [change(2024, 6.0), change(2025, 8.38), change(2026, 17.3)]
    checks = growth_checks("double-digit revenue growth", "revenue growth", "revenue", 2025, rows)
    assert len(checks) == 1 and not checks[0].met  # only the deadline year counts
    why = growth_conflict("delivered", checks)
    assert why == GROWTH_HOLD
    # The reason is shown on the public page: no figure, no draft status, no direction.
    assert not any(w in why for w in ("8.4", "%", "Delivered", "delivered", "below", "meets"))
    assert growth_conflicts("delivered", checks) == checks
    assert growth_conflict("on_track", checks)  # the deadline year is reported: not on track
    assert growth_conflict("no_evidence_yet", checks) is None  # partial delivery (rubric 5)
    assert growth_conflict("walked_back", checks) is None


def test_growth_that_meets_the_target_must_be_delivered():
    checks = growth_checks("double-digit revenue growth", "revenue growth", "revenue", 2025,
                           [change(2025, 15.6)])  # fmt: skip
    assert checks[0].met and growth_conflict("delivered", checks) is None
    assert growth_conflict("no_evidence_yet", checks) == GROWTH_HOLD
    assert growth_conflicts("walked_back", checks) == checks


def test_no_deadline_or_no_row_for_the_deadline_year_means_no_check():
    rows = [change(2025, 8.4)]
    target = ("double-digit revenue growth", "revenue growth", "revenue")
    assert growth_checks(*target, None, rows) == []
    assert growth_checks(*target, 2027, rows) == []
    other = [change(2025, 8.4, label="gross profit")]
    assert growth_checks("double-digit revenue growth", "revenue growth", "revenue", 2025,
                         other) == []  # fmt: skip
    assert growth_conflict("delivered", []) is None


def test_held_is_pending_with_the_reason():
    d = gate.held("reported figures: below the target")
    assert not d.publishable and d.label == gate.PENDING and d.reason.startswith("reported")


# ---------- statements that aren't the company's own ----------

PASSAGE = (
    "Generative AI is coming to devices. Industry analysts estimate that 46% of smartphones "
    "sold in 2027 will be generative AI capable, up from 19% in 2024. We expect to ship "
    "Snapdragon AI platforms in more than 20 new devices in 2025. According to IDC, AI PCs "
    "will reach 60% of shipments by 2027."
)


def stated(quote: str, **fields) -> object:
    good, bad = verify(PASSAGE, [{"quote": quote, "ai_link": "AI", "kind": "promise", **fields}])
    assert not bad
    return good[0]


def test_analyst_forecasts_are_not_the_companys_promise():
    v = stated("46% of smartphones sold in 2027 will be generative AI capable")
    # The attribution sits before the quote, in the same sentence.
    assert "attributes to others: 'Industry analysts estimate'" in not_own_statement(PASSAGE, v)
    idc = stated("AI PCs will reach 60% of shipments by 2027")
    assert "'According to IDC'" in not_own_statement(PASSAGE, idc)


def test_the_companys_own_statement_next_to_a_forecast_is_kept():
    v = stated(
        "We expect to ship Snapdragon AI platforms in more than 20 new devices in 2025",
        metric="devices shipping Snapdragon AI platforms",
        target_text="more than 20",
    )
    assert not_own_statement(PASSAGE, v) is None  # the analysts' sentence is a different one
    own, others = split_own(PASSAGE, [v])
    assert own == [v] and others == []


def test_market_sizes_are_not_the_companys_result():
    tam = stated("AI PCs will reach 60% of shipments by 2027", metric="long-term PC TAM",
                 target_text="300 million units")  # fmt: skip
    assert "market size" in not_own_statement(PASSAGE, tam)
    opp = stated(
        "We expect to ship Snapdragon AI platforms in more than 20 new devices in 2025",
        metric="data center AI accelerator market opportunity",
        target_text="$500 billion",
    )
    assert "'market opportunity'" in not_own_statement(PASSAGE, opp)
    share = stated("We expect to ship Snapdragon AI platforms in more than 20 new devices in 2025",
                   metric="market share in AI PCs", target_text="10%")  # fmt: skip
    assert not_own_statement(PASSAGE, share) is None  # the company's own share is its result
    tam_word = stated("We expect to ship Snapdragon AI platforms in more than 20 new devices in "
                      "2025", metric="Tampa data center", target_text="20")  # fmt: skip
    assert not_own_statement(PASSAGE, tam_word) is None  # "TAM" only as a whole word
