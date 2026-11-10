"""A fake SEC EDGAR for tests: an httpx2 MockTransport serving fixtures. Never networked.

Fictional registrant: Exemplar Industries, Inc., ticker EXMP, CIK 99999999.
In the promise window (from 2024-01-01) it has: a 10-K with an EX-13 annual report, an
earnings 8-K (Item 2.02) with EX-99.1, and two 10-Qs that reuse the same document (so the
second one's passages are exact duplicates). Filings that must be excluded: a 10-K/A, an
8-K for Item 5.02, and (in the older paged history) a 2023 10-K and a 2024 Item 5.02 8-K.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import httpx2

FIXTURES = Path(__file__).parent / "fixtures" / "sec"
CIK = 99999999
TICKER = "EXMP"
NAME = "Exemplar Industries, Inc."

# (accession, form, filing_date, report_date, items, primary_doc, [(doc, type)])
FILINGS = [
    ("9999999999-25-000030", "10-Q", "2025-07-30", "2025-06-30", "", "exm-20250331.htm",
     [("exm-20250331.htm", "10-Q")]),
    ("9999999999-25-000020", "10-Q", "2025-04-30", "2025-03-31", "", "exm-20250331.htm",
     [("exm-20250331.htm", "10-Q")]),
    ("9999999999-25-000019", "8-K", "2025-04-29", "2025-04-29", "2.02,9.01", "exm-8k.htm",
     [("exm-8k.htm", "8-K"), ("exm-ex991.htm", "EX-99.1"), ("exm-ex992.htm", "EX-99.2")]),
    ("9999999999-25-000015", "10-K/A", "2025-03-15", "2024-12-31", "", "exm-10ka.htm",
     [("exm-10ka.htm", "10-K/A")]),
    ("9999999999-25-000012", "8-K", "2025-03-01", "2025-02-27", "5.02", "exm-8k-502.htm",
     [("exm-8k-502.htm", "8-K")]),
    ("9999999999-25-000010", "10-K", "2025-02-20", "2024-12-31", "", "exm-20241231.htm",
     [("exm-20241231.htm", "10-K"), ("exm-20241231_ex13.htm", "EX-13"),
      ("exm-ex21.htm", "EX-21"), ("exm-20241231_g1.jpg", "GRAPHIC")]),
]  # fmt: skip
OLD_PAGE = [
    ("9999999999-24-000005", "8-K", "2024-03-01", "2024-02-28", "5.02", "old-8k.htm"),
    ("9999999999-23-000004", "10-K", "2023-02-20", "2022-12-31", "", "old-10k.htm"),
]
IN_WINDOW = {"9999999999-25-000030", "9999999999-25-000020", "9999999999-25-000019",
             "9999999999-25-000010"}  # fmt: skip
PAGE_NAME = f"CIK{CIK:010d}-submissions-001.json"


def _columns(rows: list[tuple]) -> dict:
    keys = ("accessionNumber", "form", "filingDate", "reportDate", "items", "primaryDocument")
    out = {k: [r[i] for r in rows] for i, k in enumerate(keys)}
    out["isInlineXBRL"] = [1] * len(rows)
    return out


def submissions() -> dict:
    return {
        "cik": str(CIK),
        "name": NAME,
        "tickers": [TICKER],
        "filings": {
            "recent": _columns([f[:6] for f in FILINGS]),
            "files": [
                {
                    "name": PAGE_NAME,
                    "filingCount": 2,
                    "filingFrom": "2023-01-01",
                    "filingTo": "2024-06-30",
                }
            ],
        },
    }


def companyfacts() -> dict:
    def fact(start, end, val, accn, fy, fp, form, filed):
        return {"start": start, "end": end, "val": val, "accn": accn, "fy": fy, "fp": fp,
                "form": form, "filed": filed}  # fmt: skip

    return {
        "cik": CIK,
        "entityName": NAME,
        "facts": {
            "us-gaap": {
                "Revenues": {
                    "label": "Revenues",
                    "units": {
                        "USD": [
                            fact("2020-01-01", "2020-12-31", 9.0e9, "9999999999-21-000001",
                                 2020, "FY", "10-K", "2021-02-20"),
                            fact("2023-01-01", "2023-12-31", 11.022e9, "9999999999-25-000010",
                                 2024, "FY", "10-K", "2025-02-20"),
                            fact("2024-01-01", "2024-12-31", 12.345e9, "9999999999-25-000010",
                                 2024, "FY", "10-K", "2025-02-20"),
                            fact("2025-01-01", "2025-03-31", 3.101e9, "9999999999-25-000020",
                                 2025, "Q1", "10-Q", "2025-04-30"),
                        ]
                    },
                }
            },
            "dei": {
                "EntityCommonStockSharesOutstanding": {
                    "units": {"shares": [{"end": "2025-02-01", "val": 500000000,
                                          "accn": "9999999999-25-000010", "fy": 2024,
                                          "fp": "FY", "form": "10-K", "filed": "2025-02-20"}]}
                }
            },
        },
    }  # fmt: skip


def index_page(accession: str, docs: list[tuple[str, str]]) -> str:
    rows = "".join(
        f'<tr><td scope="row">{i}</td><td scope="row">{t}</td>'
        f'<td scope="row"><a href="/Archives/edgar/data/{CIK}/{accession.replace("-", "")}/{d}">'
        f'{d}</a></td><td scope="row">{t}</td><td scope="row">1234</td></tr>'
        for i, (d, t) in enumerate(docs, start=1)
    )
    return (
        '<html><body><table class="tableFile" summary="Document Format Files">'
        "<tr><th>Seq</th><th>Description</th><th>Document</th><th>Type</th><th>Size</th></tr>"
        f'{rows}</table><table class="tableFile" summary="Data Files"><tr><th>Seq</th></tr>'
        "</table></body></html>"
    )


class FakeSec:
    """Callable handler for httpx2.MockTransport. Records every path it serves."""

    def __init__(self, *, fail_once: set[str] | None = None, status_overrides=None) -> None:
        self.requests: list[str] = []
        self.user_agents: set[str] = set()
        self._fail_once = set(fail_once or ())
        self._status = dict(status_overrides or {})

    @property
    def counts(self) -> Counter:
        return Counter(self.requests)

    def transport(self) -> httpx2.MockTransport:
        return httpx2.MockTransport(self)

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        path = request.url.path
        self.requests.append(path)
        self.user_agents.add(request.headers.get("user-agent", ""))
        if path in self._status:
            return httpx2.Response(self._status[path])
        if path in self._fail_once:
            self._fail_once.discard(path)
            return httpx2.Response(429, headers={"Retry-After": "0"})
        if path == "/files/company_tickers.json":
            return httpx2.Response(
                200, json={"0": {"cik_str": CIK, "ticker": TICKER, "title": NAME}}
            )
        if path == f"/submissions/CIK{CIK:010d}.json":
            return httpx2.Response(200, json=submissions())
        if path == f"/submissions/{PAGE_NAME}":
            return httpx2.Response(200, json=_columns(OLD_PAGE))
        if path == f"/api/xbrl/companyfacts/CIK{CIK:010d}.json":
            return httpx2.Response(200, json=companyfacts())
        parts = path.split("/")
        if path.startswith(f"/Archives/edgar/data/{CIK}/") and len(parts) == 7:
            name = parts[6]
            for acc, *_rest, docs in FILINGS:
                if name == f"{acc}-index.htm":
                    return httpx2.Response(200, text=index_page(acc, docs))
            fixture = FIXTURES / name
            if fixture.exists():
                return httpx2.Response(200, content=fixture.read_bytes())
        return httpx2.Response(404)


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
