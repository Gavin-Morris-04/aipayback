"""Where a reported figure sits against a promised dollar range, computed in code (D46).

The explainer is a language model, and in the pilot it wrote "$37.26 billion falls within
$30-37 billion" and "$72.22 billion is within the $70-72 billion range only at the top
end". Comparing a number with a range is arithmetic, and arithmetic is done in code. These
sentences go into the explainer's reported-figures document, so it can cite them.

Narrow on purpose: dollar ranges on capex promises, and only rows for the deadline year.
Total-revenue growth targets are compared the same way (D57), further down.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from aipb.verify.numbers import NumberRow

_SCALE = {"million": 1e6, "billion": 1e9, "trillion": 1e12}
_NUM = r"(\d+(?:,\d{3})*(?:\.\d+)?)"
_UNIT = r"(million|billion|trillion)"
_RANGE = re.compile(
    rf"\$\s?{_NUM}\s*{_UNIT}?\s*(?:-|\u2013|\u2014|to|and)\s*\$?\s?{_NUM}\s*{_UNIT}",
    re.IGNORECASE,
)
_CAPEX_ROWS = ("capex for", "capital expenditures as the company defines them")


def usd_range(target_text: str | None) -> tuple[float, float] | None:
    """(low, high) in dollars from "$30-37 billion" or "approximately $70 billion to $72
    billion"; None if the target isn't a dollar range."""
    m = _RANGE.search(target_text or "")
    if not m:
        return None
    lo, lo_unit, hi, hi_unit = m.groups()
    high = float(hi.replace(",", "")) * _SCALE[hi_unit.lower()]
    low = float(lo.replace(",", "")) * _SCALE[(lo_unit or hi_unit).lower()]
    return (low, high) if low <= high else None


def _usd(v: float) -> str:
    for unit, scale in (("trillion", 1e12), ("billion", 1e9), ("million", 1e6)):
        if abs(v) >= scale:
            return f"${f'{v / scale:,.2f}'.rstrip('0').rstrip('.')} {unit}"
    return f"${v:,.0f}"


def comparisons(
    target_text: str | None,
    claim_type: str | None,
    deadline_year: int | None,
    numbers: list[NumberRow],
) -> list[str]:
    """One sentence per capex row for the deadline year: below, within or above the range."""
    rng = usd_range(target_text)
    if rng is None or claim_type != "capex_investment":
        return []
    low, high = rng
    out = []
    for n in numbers:
        if n.unit != "USD" or n.kind == "change" or not n.label.startswith(_CAPEX_ROWS):
            continue
        if deadline_year and n.fiscal_year != deadline_year:
            continue
        where = "below" if n.value < low else ("above" if n.value > high else "within")
        reach = "it reaches the low end" if n.value >= low else "it does not reach the low end"
        out.append(
            f"Compared by code with the promised range of {_usd(low)} to {_usd(high)}, the "
            f"{n.label} ({n.display()}) is {where} the range; {reach}."
        )
    return out


# ---------- growth targets (D57) ----------
# In the S&P 100 run an Oracle promise of "double-digit revenue growth this fiscal year" was
# marked Delivered next to 8.4% growth, and both checks agreed (D56). Whether a growth rate
# meets a target is arithmetic, so code compares them and the gate holds any status the
# figure contradicts. Narrow on purpose: total revenue (or sales) growth in percent, the
# deadline year's reported change only, and the rubric's tolerances (section 5).

# "revenue growth", "total net sales growth", "revenue growth and margin expansion" (a second
# metric after "and"). Not "cloud revenue", "ISG net revenue growth" or "Q3 2025 revenue
# growth": a segment or a quarter isn't the annual total the number table holds.
_TOTAL_REVENUE = re.compile(
    r"(?:total |annual |consolidated |year-over-year |overall )*(?:net )?(?:revenues?|sales)"
    r"(?: growth(?: rate)?)?(?: and .+)?",
    re.IGNORECASE,
)
_GROWTH = re.compile(r"\bgrow|\bgrowth\b|\bincrease", re.IGNORECASE)
_DIGITS = re.compile(r"\b(double|triple)[- ]digits?\b", re.IGNORECASE)
_PCT = rf"{_NUM}\s*(?:%|percent\b)"
_PCT_RANGE = re.compile(rf"{_NUM}\s*%?\s*(?:-|\u2013|\u2014|to)\s*{_PCT}", re.IGNORECASE)
_PCT_ONE = re.compile(_PCT, re.IGNORECASE)
_FLOOR_WORDS = re.compile(r"\b(?:at least|more than|over|exceed\w*|above)\b", re.IGNORECASE)
_ABOUT_WORDS = re.compile(r"\b(?:about|approximately|around|roughly|nearly)\b", re.IGNORECASE)


@dataclass(frozen=True)
class GrowthTarget:
    floor: float  # the lowest growth, in percent, that meets the target under the rubric
    words: str  # how the target reads, for the sentence


def growth_target(
    target_text: str | None, metric: str | None, claim_type: str | None
) -> GrowthTarget | None:
    """The rubric's floor for a total-revenue growth target, or None if it isn't one.

    - "double-digit" is a target of 10%; "triple-digit" of 100%. Section 5's 95% rule applies.
    - "X% to Y%": the low end, no extra tolerance.
    - "at least / more than / exceed X%": 100% of X. "About X%": 90% of X. Otherwise 95% of X.
    """
    if claim_type != "revenue" or not _TOTAL_REVENUE.fullmatch((metric or "").strip()):
        return None
    t = target_text or ""
    if not _GROWTH.search(f"{t} {metric}"):
        return None
    if m := _DIGITS.search(t):
        target = 10.0 if m.group(1).lower() == "double" else 100.0
        return GrowthTarget(target * 0.95, f"{m.group(0).lower()} growth (a {target:g}% target)")
    if m := _PCT_RANGE.search(t):
        low, high = float(m.group(1).replace(",", "")), float(m.group(2).replace(",", ""))
        if low <= high:
            return GrowthTarget(low, f"growth of {low:g}% to {high:g}%")
        return None
    if m := _PCT_ONE.search(t):
        target = float(m.group(1).replace(",", ""))
        share = 1.0 if _FLOOR_WORDS.search(t) else (0.9 if _ABOUT_WORDS.search(t) else 0.95)
        return GrowthTarget(target * share, f"growth of {t.strip()}")
    return None


@dataclass(frozen=True)
class GrowthCheck:
    row: NumberRow
    target: GrowthTarget

    @property
    def met(self) -> bool:
        return self.row.value >= self.target.floor


def growth_checks(
    target_text: str | None,
    metric: str | None,
    claim_type: str | None,
    deadline_year: int | None,
    numbers: list[NumberRow],
) -> list[GrowthCheck]:
    """The deadline year's reported revenue change against a total-revenue growth target."""
    target = growth_target(target_text, metric, claim_type)
    if target is None or deadline_year is None:
        return []
    return [
        GrowthCheck(n, target)
        for n in numbers
        if n.unit == "pct_change"
        and n.label.startswith("revenue change vs prior year")
        and n.fiscal_year == deadline_year
    ]


# The hold reason is shown on the promise's public page, so it names no figure, no draft
# status and no direction: "8.4%, below the target" would be an unreviewed finding.
GROWTH_HOLD = "the reported revenue growth for the deadline year and the draft status disagree"


def growth_conflicts(status: str, checks: list[GrowthCheck]) -> list[GrowthCheck]:
    """The checks a status contradicts: below the target but Delivered or On track (the
    deadline year is reported), or meeting it but anything other than Delivered."""
    return [
        c
        for c in checks
        if (not c.met and status in ("delivered", "on_track")) or (c.met and status != "delivered")
    ]


def growth_conflict(status: str, checks: list[GrowthCheck]) -> str | None:
    """The public hold reason if the reported growth contradicts a status, else None."""
    return GROWTH_HOLD if growth_conflicts(status, checks) else None
