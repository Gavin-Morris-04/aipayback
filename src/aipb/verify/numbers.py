"""Reported numbers for verification, from XBRL company facts, computed in code.

For a promise we build a small table of annual figures (and margins and year-over-year
changes) for the measures its claim type maps to. Each row gets an id (N1, N2, ...), and
the judge may only cite those ids, so every number in a verdict traces to a filing.
"""

from __future__ import annotations

import operator
import re
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


def _paired(a: dict, b: dict, op) -> dict[str, dict]:
    """op(a, b) for fiscal years where both series cover the same period (later filing cited)."""
    out: dict[str, dict] = {}
    for end in sorted(set(a) & set(b)):
        x, y = a[end], b[end]
        if abs(_days(x["period_start"], y["period_start"])) > 7:
            continue
        later = x if x["filed"] >= y["filed"] else y
        out[end] = {
            "value": op(x["value"], y["value"]),
            "period_start": x["period_start"],
            "period_end": end,
            "accession": later["accession"],
            "filed": later["filed"],
        }
    return out


def derived_gross_profit(
    conn: sqlite3.Connection, em: EvidenceMap, cik: int
) -> tuple[str, dict[str, dict]]:
    """Revenue minus cost of revenue, for a company that doesn't report GrossProfit.

    Nick's evidence map: "otherwise revenue minus CostOfRevenue or
    CostOfGoodsAndServicesSold". Only fiscal years where both cover the same period.
    """
    rev_tag, rev = annual_series(conn, cik, em.measures.get("revenue", []))
    cor_tag, cor = annual_series(conn, cik, em.measures.get("cost_of_revenue", []))
    out = _paired(rev, cor, operator.sub)
    return (f"derived: {rev_tag} minus {cor_tag}" if out else ""), out


# A company's own capex definition, as its filings state it (D44). A capex promise that
# doesn't say which definition it uses is judged on the company's usual one. Narrow on
# purpose: a phrasing is recognized only when what it adds is a reported XBRL measure, so
# code does the sum. {measure added to capex: (the company's phrasing, what the sum is)}
CAPEX_DEFINITIONS = {
    "finance_lease_principal": (
        re.compile(
            r"capital expenditures,?\s+including\s+principal\s+payments\s+on\s+finance\s+leases",
            re.IGNORECASE,
        ),
        "purchases of property and equipment plus principal payments on finance leases",
    ),
}
CAPEX_DEFINITION_MIN_FILINGS = 2  # "usual": stated in at least two filings


@dataclass(frozen=True)
class CapexDefinition:
    adds: str  # the measure added to capex
    phrase: str  # the company's words, verbatim, from the latest filing that uses them
    meaning: str
    filings: int  # distinct filings using the phrase, up to the promise date
    accession: str
    filed: str

    def describe(self) -> str:
        return (
            f'"{self.phrase}" (in {self.filings} filings up to the promise date; '
            f"latest filed {self.filed})"
        )


def capex_definition(conn: sqlite3.Connection, cik: int, by_date: str) -> CapexDefinition | None:
    """The company's usual capex definition, from its filings on or before `by_date`."""
    for adds, (pattern, meaning) in CAPEX_DEFINITIONS.items():
        seen: dict[str, tuple[str, str]] = {}
        for r in conn.execute(
            "SELECT accession, filing_date, text FROM passages WHERE cik=? AND filing_date <= ? "
            "AND text LIKE '%finance lease%' ORDER BY filing_date",
            (cik, by_date),
        ):
            if m := pattern.search(r["text"]):
                seen[r["accession"]] = (r["filing_date"], " ".join(m.group(0).split()))
        if len(seen) >= CAPEX_DEFINITION_MIN_FILINGS:
            accession, (filed, phrase) = max(seen.items(), key=lambda kv: (kv[1][0], kv[0]))
            return CapexDefinition(adds, phrase, meaning, len(seen), accession, filed)
    return None


def derived_company_capex(
    conn: sqlite3.Connection, em: EvidenceMap, cik: int, cdef: CapexDefinition
) -> tuple[str, dict[str, dict]]:
    """Capex on the company's own definition: purchases of property and equipment plus
    the measure its definition adds, for fiscal years where both cover the same period."""
    cap_tag, cap = annual_series(conn, cik, em.measures.get("capex", []))
    add_tag, add = annual_series(conn, cik, em.measures.get(cdef.adds, []))
    out = _paired(cap, add, operator.add)
    return (f"derived: {cap_tag} plus {add_tag}" if out else ""), out


def company_capex_name(cdef: CapexDefinition) -> str:
    return f"capital expenditures as the company defines them (computed by code: {cdef.meaning})"


def number_table(
    conn: sqlite3.Connection,
    em: EvidenceMap,
    cik: int,
    claim_type: str,
    from_year: int,
    capex_def: CapexDefinition | None = None,
) -> list[NumberRow]:
    """Annual values from `from_year` on, plus margins and year-over-year changes.

    With `capex_def`, capex is also given on the company's own definition (D44).
    """
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
    to_emit: list[tuple[str, str, dict, bool]] = []  # (name, tag, annual values, derived)
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
        to_emit.append((name, tag if derived else f"us-gaap:{tag}", annual, derived))
        if measure == "capex" and capex_def is not None:
            ctag, cannual = derived_company_capex(conn, em, cik, capex_def)
            if cannual:
                to_emit.append((company_capex_name(capex_def), ctag, cannual, True))
    for name, full_tag, annual, derived in to_emit:
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
