"""XBRL company facts: the numbers companies report, by tag, period and filing.

Verification uses these for cost, margin, revenue, headcount and capex claims, so the
arithmetic is done in code on reported numbers rather than by the model.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from aipb.sec.client import SecClient

COMPANYFACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
COMPANYFACTS_MAX_AGE_S = 24 * 3600
# Facts filed before this date are not needed: promises start in 2024 and their baselines
# appear as prior-period comparatives in 2024+ filings, with two years of margin.
MIN_FILED = "2022-01-01"


@dataclass(frozen=True)
class Fact:
    cik: int
    taxonomy: str
    tag: str
    unit: str
    period_start: str
    period_end: str
    value: float
    fy: int | None
    fp: str
    form: str
    filed: str
    accession: str
    frame: str

    def row(self) -> tuple:
        return (
            self.cik,
            self.taxonomy,
            self.tag,
            self.unit,
            self.period_start,
            self.period_end,
            self.value,
            self.fy,
            self.fp,
            self.form,
            self.filed,
            self.accession,
            self.frame,
        )


def fetch_companyfacts(client: SecClient, raw_dir: Path, cik: int) -> dict:
    return client.get_json(
        COMPANYFACTS_URL.format(cik=cik),
        raw_dir / "companyfacts" / f"CIK{cik:010d}.json",
        max_age_s=COMPANYFACTS_MAX_AGE_S,
    )


def iter_facts(doc: dict, *, min_filed: str = MIN_FILED) -> Iterator[Fact]:
    cik = int(doc.get("cik", 0))
    for taxonomy, tags in (doc.get("facts") or {}).items():
        for tag, body in tags.items():
            for unit, facts in (body.get("units") or {}).items():
                for f in facts:
                    filed = f.get("filed", "")
                    if filed < min_filed or "val" not in f:
                        continue
                    try:
                        value = float(f["val"])
                    except (TypeError, ValueError):
                        continue
                    yield Fact(
                        cik=cik,
                        taxonomy=taxonomy,
                        tag=tag,
                        unit=unit,
                        period_start=f.get("start", "") or "",
                        period_end=f.get("end", "") or "",
                        value=value,
                        fy=f.get("fy"),
                        fp=f.get("fp", "") or "",
                        form=f.get("form", "") or "",
                        filed=filed,
                        accession=f.get("accn", "") or "",
                        frame=f.get("frame", "") or "",
                    )
