"""Which filings to fetch, and which document inside each one holds the text we parse.

Scope (docs/BRIEF.md section 3):
- 10-K and 10-Q: the primary document. When a 10-K incorporates its annual report by
  reference (IBM does), the MD&A lives in Exhibit 13, so we fetch EX-13 as well.
- 8-K: only earnings releases (Item 2.02), and only their press release (EX-99.1).
- Amendments (10-K/A, 10-Q/A, 8-K/A) are skipped in v1: they are mostly Part III or exhibit
  refilings. See docs/DECISIONS.md.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

from lxml import html as lxml_html

from aipb.sec.client import SecClient

SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
SUBMISSIONS_PAGE_URL = "https://data.sec.gov/submissions/{name}"
ARCHIVES = "https://www.sec.gov/Archives/edgar/data/{cik}/{acc_nodash}/"
SUBMISSIONS_MAX_AGE_S = 12 * 3600

FORMS = ("10-K", "10-Q", "8-K")
EARNINGS_ITEM = "2.02"


@dataclass(frozen=True)
class FilingRef:
    cik: int
    accession: str
    form: str
    filing_date: str
    report_date: str
    items: str
    primary_doc: str

    @property
    def acc_nodash(self) -> str:
        return self.accession.replace("-", "")

    @property
    def base_url(self) -> str:
        return ARCHIVES.format(cik=self.cik, acc_nodash=self.acc_nodash)

    @property
    def index_url(self) -> str:
        return f"{self.base_url}{self.accession}-index.htm"

    def doc_url(self, doc: str) -> str:
        return f"{self.base_url}{doc}"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class IndexDoc:
    seq: str
    description: str
    doc: str
    doc_type: str
    size: int


def _rows(block: dict) -> list[dict]:
    keys = list(block.keys())
    return [dict(zip(keys, vals, strict=True)) for vals in zip(*block.values(), strict=True)]


def submission_rows(client: SecClient, raw_dir: Path, cik: int, start: date) -> list[dict]:
    """All filing rows for a company on or after `start`, following the paged history."""
    sub_dir = raw_dir / "submissions"
    data = client.get_json(
        SUBMISSIONS_URL.format(cik=cik),
        sub_dir / f"CIK{cik:010d}.json",
        max_age_s=SUBMISSIONS_MAX_AGE_S,
    )
    rows = _rows(data["filings"]["recent"])
    for page in data["filings"].get("files", []):
        if page.get("filingTo", "") < start.isoformat():
            continue
        # Older pages never change once written, so they are cached forever.
        page_data = client.get_json(
            SUBMISSIONS_PAGE_URL.format(name=page["name"]), sub_dir / page["name"]
        )
        rows.extend(_rows(page_data))
    return [r for r in rows if r.get("filingDate", "") >= start.isoformat()]


def select_filings(
    rows: list[dict], cik: int, start: date, end: date | None = None
) -> list[FilingRef]:
    seen: set[str] = set()
    out: list[FilingRef] = []
    for r in rows:
        form = r.get("form", "")
        if form not in FORMS:
            continue
        filed = r.get("filingDate", "")
        if filed < start.isoformat() or (end is not None and filed > end.isoformat()):
            continue
        items = r.get("items", "") or ""
        if form == "8-K" and EARNINGS_ITEM not in [i.strip() for i in items.split(",")]:
            continue
        acc = r["accessionNumber"]
        if acc in seen:
            continue
        seen.add(acc)
        out.append(
            FilingRef(
                cik=cik,
                accession=acc,
                form=form,
                filing_date=filed,
                report_date=r.get("reportDate", "") or "",
                items=items,
                primary_doc=r.get("primaryDocument", "") or "",
            )
        )
    out.sort(key=lambda f: (f.filing_date, f.accession))
    return out


def parse_index(page: bytes) -> list[IndexDoc]:
    """Read the 'Document Format Files' table of a filing's -index.htm page."""
    tree = lxml_html.fromstring(page)
    docs: list[IndexDoc] = []
    for table in tree.xpath('//table[contains(@class, "tableFile")]'):
        if "Document Format Files" not in (table.get("summary") or ""):
            continue
        for tr in table.xpath(".//tr[td]"):
            cells = [" ".join(td.text_content().split()) for td in tr.xpath("./td")]
            hrefs = tr.xpath(".//a/@href")
            if len(cells) < 5 or not hrefs:
                continue
            doc = hrefs[0].split("/")[-1]
            try:
                size = int(cells[4])
            except ValueError:
                size = 0
            docs.append(IndexDoc(cells[0], cells[1], doc, cells[3].upper(), size))
    return docs


_EX99_1 = re.compile(r"^EX-99(\.0?1)?$")
_EX13 = re.compile(r"^EX-13(\.\d+)?$")


def documents_to_parse(ref: FilingRef, index: list[IndexDoc]) -> list[tuple[str, str]]:
    """(role, filename) pairs for the documents whose text we parse."""

    def is_html(d: IndexDoc) -> bool:
        return d.doc.lower().endswith((".htm", ".html", ".txt"))

    if ref.form == "8-K":
        exhibits = [d for d in index if d.doc_type.startswith("EX-99") and is_html(d)]
        best = [d for d in exhibits if _EX99_1.match(d.doc_type)] or exhibits
        if best:
            return [("ex99", best[0].doc)]
        return [("primary", ref.primary_doc)] if ref.primary_doc else []

    docs = [("primary", ref.primary_doc)] if ref.primary_doc else []
    if ref.form == "10-K":
        docs += [("ex13", d.doc) for d in index if _EX13.match(d.doc_type) and is_html(d)]
    return docs
