"""Reported numbers for verification, from XBRL company facts, computed in code.

For a promise we build a small table of annual figures (and margins and year-over-year
changes) for the measures its claim type maps to. Each row gets an id (N1, N2, ...), and
the judge may only cite those ids, so every number in a verdict traces to a filing.
"""

from __future__ import annotations

import sqlite3
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

import yaml

from aipb.verify.calc import pct_change


@dataclass(frozen=True)
class NumberRow:
    nid: str
    label: str
    value: float
    unit: str
    kind: str  # fact | derived | ratio | change
    tag: str
    fiscal_year: int
    period_start: str
    period_end: str
    accession: str
    filed: str

    def to_dict(self) -> dict:
        return asdict(self)

    def display(self) -> str:
        if self.unit == "USD":
            v = self.value
            text = f"${v / 1e9:,.2f} billion" if abs(v) >= 1e9 else f"${v / 1e6:,.1f} million"
        elif self.unit in ("percent", "pct_change"):
            text = f"{self.value:.1f}%"
        elif self.unit == "percentage_points":
            text = f"{self.value:+.1f} percentage points"
        else:
            text = f"{self.value:,.2f} {self.unit}"
        return text


@dataclass
class EvidenceMap:
    version: str
    measures: dict[str, list[str]]
    ratios: dict[str, dict[str, str]]
    claim_types: dict[str, dict]

    @classmethod
    def load(cls, path: Path) -> EvidenceMap:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        return cls(raw["version"], raw["measures"], raw.get("ratios", {}), raw["claim_types"])

    def for_claim(self, claim_type: str) -> dict:
        return self.claim_types.get(claim_type) or self.claim_types.get("other", {})


def _days(a: str, b: str) -> int:
    return (date.fromisoformat(b) - date.fromisoformat(a)).days


def annual_series(conn: sqlite3.Connection, cik: int, tags: list[str]) -> tuple[str, dict]:
    """(tag used, {period_end: fact row}) of full-year values; the latest filing wins.

    A restated number in a later filing replaces the original (rubric: restated wins).
    """
    for tag in tags:
        rows = conn.execute(
            "SELECT * FROM xbrl_facts WHERE cik=? AND tag=? AND unit='USD' "
            "AND period_start != '' ORDER BY filed",
            (cik, tag),
        ).fetchall()
        annual = {}
        for r in rows:
            if 330 <= _days(r["period_start"], r["period_end"]) <= 380:
                annual[r["period_end"]] = r  # later filings overwrite earlier ones
        if annual:
            return tag, annual
    return "", {}


def fiscal_year_end(conn: sqlite3.Connection, cik: int) -> str:
    """Most common month-day of full-year period ends (e.g. "06-30" for Microsoft)."""
    ends = Counter()
    for r in conn.execute(
        "SELECT period_start, period_end FROM xbrl_facts WHERE cik=? AND fp='FY' "
        "AND period_start != '' LIMIT 5000",
        (cik,),
    ):
        if 330 <= _days(r["period_start"], r["period_end"]) <= 380:
            ends[r["period_end"][5:]] += 1
    return ends.most_common(1)[0][0] if ends else "12-31"


def deadline_end(year: int | None, fy_end: str) -> str | None:
    """Last day of the deadline's fiscal year (rubric: fiscal year unless 'calendar')."""
    if year is None:
        return None
    month_day = "02-28" if fy_end == "02-29" else fy_end
    return f"{year}-{month_day}"


# A fallback tag that measures something broader than its measure's name gets its own label,
# so the judge never reads total costs as operating expenses (evidence map em3, D41).
TAG_LABELS = {"CostsAndExpenses": "total costs and expenses (includes cost of sales)"}


def derived_gross_profit(
    conn: sqlite3.Connection, em: EvidenceMap, cik: int
) -> tuple[str, dict[str, dict]]:
    """Revenue minus cost of revenue, for a company that doesn't report GrossProfit.

    Nick's evidence map: "otherwise revenue minus CostOfRevenue or
    CostOfGoodsAndServicesSold". Only fiscal years where both cover the same period.
    """
    rev_tag, rev = annual_series(conn, cik, em.measures.get("revenue", []))
    cor_tag, cor = annual_series(conn, cik, em.measures.get("cost_of_revenue", []))
    out: dict[str, dict] = {}
    for end in sorted(set(rev) & set(cor)):
        r, c = rev[end], cor[end]
        if abs(_days(r["period_start"], c["period_start"])) > 7:
            continue
        later = r if r["filed"] >= c["filed"] else c
        out[end] = {
            "value": r["value"] - c["value"],
            "period_start": r["period_start"],
            "period_end": end,
            "accession": later["accession"],
            "filed": later["filed"],
        }
    return (f"derived: {rev_tag} minus {cor_tag}" if out else ""), out


def number_table(
    conn: sqlite3.Connection, em: EvidenceMap, cik: int, claim_type: str, from_year: int
) -> list[NumberRow]:
    """Annual values from `from_year` on, plus margins and year-over-year changes."""
    spec = em.for_claim(claim_type)
    rows: list[NumberRow] = []
    series: dict[str, dict] = {}
    n = 0

    def add(**kw) -> None:
        nonlocal n
        n += 1
        rows.append(NumberRow(nid=f"N{n}", **kw))

    names = list(
        dict.fromkeys(
            spec.get("measures", [])
            + [m for r in spec.get("ratios", []) for m in em.ratios[r].values()]
        )
    )
    for measure in names:
        tag, annual = annual_series(conn, cik, em.measures.get(measure, []))
        derived = False
        if not annual and measure == "gross_profit":
            tag, annual = derived_gross_profit(conn, em, cik)
            derived = bool(annual)
        series[measure] = annual
        name = TAG_LABELS.get(tag, measure.replace("_", " "))
        if derived:
            name = "gross profit (computed by code: revenue minus cost of revenue)"
        full_tag = tag if derived else f"us-gaap:{tag}"
        prev = None
        for end in sorted(annual):
            fact = annual[end]
            fy = int(end[:4])
            if fy < from_year:
                prev = fact
                continue
            label = f"{name} for the fiscal year ended {end}"
            add(
                label=label,
                value=fact["value"],
                unit="USD",
                kind="derived" if derived else "fact",
                tag=full_tag,
                fiscal_year=fy,
                period_start=fact["period_start"],
                period_end=end,
                accession=fact["accession"],
                filed=fact["filed"],
            )
            if prev is not None and (ch := pct_change(prev["value"], fact["value"])) is not None:
                add(
                    label=f"{name} change vs prior year, FY ended {end}",
                    value=ch,
                    unit="pct_change",
                    kind="change",
                    tag=full_tag,
                    fiscal_year=fy,
                    period_start=prev["period_end"],
                    period_end=end,
                    accession=fact["accession"],
                    filed=fact["filed"],
                )
            prev = fact
    for ratio in spec.get("ratios", []):
        num, den = em.ratios[ratio]["numerator"], em.ratios[ratio]["denominator"]
        prev_end, prev_value = None, None
        for end in sorted(set(series.get(num, {})) & set(series.get(den, {}))):
            if not series[den][end]["value"]:
                continue
            value = series[num][end]["value"] / series[den][end]["value"] * 100.0
            if int(end[:4]) < from_year:
                prev_end, prev_value = end, value
                continue
            add(
                label=f"{ratio.replace('_', ' ')} for the fiscal year ended {end}",
                value=value,
                unit="percent",
                kind="ratio",
                tag=f"{num}/{den}",
                fiscal_year=int(end[:4]),
                period_start=series[den][end]["period_start"],
                period_end=end,
                accession=series[den][end]["accession"],
                filed=series[den][end]["filed"],
            )
            if prev_value is not None:
                # Margin promises are stated in points (Nick's evidence map), so the change
                # is a difference in percentage points, never a percent change.
                add(
                    label=f"{ratio.replace('_', ' ')} change vs prior year, FY ended {end}",
                    value=value - prev_value,
                    unit="percentage_points",
                    kind="change",
                    tag=f"{num}/{den}",
                    fiscal_year=int(end[:4]),
                    period_start=prev_end,
                    period_end=end,
                    accession=series[den][end]["accession"],
                    filed=series[den][end]["filed"],
                )
            prev_end, prev_value = end, value
    return rows
