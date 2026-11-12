"""Where a reported figure sits against a promised dollar range, computed in code (D46).

The explainer is a language model, and in the pilot it wrote "$37.26 billion falls within
$30-37 billion" and "$72.22 billion is within the $70-72 billion range only at the top
end". Comparing a number with a range is arithmetic, and arithmetic is done in code. These
sentences go into the explainer's reported-figures document, so it can cite them.

Narrow on purpose: dollar ranges on capex promises, and only rows for the deadline year.
"""

from __future__ import annotations

import re

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
