"""Stage 1: download filings for a universe and record them in the committed manifest.

Idempotent: filings already in the manifest are not looked up again, and every download
is cached on disk. A filing that cannot be fetched or has no usable document is logged
and skipped; it never stops the run.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from aipb.budget.ledger import utc_now
from aipb.sec import ciks
from aipb.sec import filings as sec_filings
from aipb.sec.client import SecClient, SecError
from aipb.sec.manifest import Manifest, ManifestEntry
from aipb.sec.xbrl import fetch_companyfacts
from aipb.universe import Member

PROMISE_WINDOW_START = date(2024, 1, 1)


@dataclass
class IngestReport:
    ticker: str
    cik: int = 0
    name: str = ""
    filings: int = 0
    new_docs: int = 0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def expected_periodic(start: date, today: date | None = None) -> int:
    """Rough floor on 10-K + 10-Q filings since `start` (4 per year), minus slack of 2."""
    today = today or date.today()
    years = max(0.0, (today - start).days / 365.25)
    return max(0, int(years * 4) - 2)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fetch_entry(client: SecClient, raw_dir: Path, entry: ManifestEntry) -> tuple[bytes, bool]:
    """Bytes of a manifest document (downloading if needed) and whether the hash matches."""
    data = client.get_bytes(entry.url, entry.raw_path(raw_dir))
    return data, sha256(data) == entry.sha256


def ingest(
    client: SecClient,
    raw_dir: Path,
    manifest: Manifest,
    members: list[Member],
    *,
    start: date = PROMISE_WINDOW_START,
    log: Callable[[str], None] = print,
) -> list[IngestReport]:
    ticker_map = ciks.load_ticker_map(client, raw_dir)
    reports: list[IngestReport] = []
    for m in members:
        rep = IngestReport(ticker=m.ticker)
        reports.append(rep)
        try:
            cid = ciks.resolve(m.ticker, ticker_map)
        except SecError as exc:
            rep.errors.append(str(exc))
            log(f"{m.ticker}: {exc}")
            continue
        rep.cik, rep.name = cid.cik, cid.name
        refs: list[sec_filings.FilingRef] = []
        try:
            # The current registrant plus any predecessors listed in the universe file.
            for filer in (cid.cik, *m.extra_ciks):
                rows = sec_filings.submission_rows(client, raw_dir, filer, start)
                refs += sec_filings.select_filings(rows, filer, start)
        except SecError as exc:
            rep.errors.append(f"filing list: {exc}")
            log(f"{m.ticker}: could not list filings: {exc}")
            continue
        # A filing made jointly by the old and new registrant appears under both CIKs.
        refs = list({r.accession: r for r in reversed(refs)}.values())[::-1]
        rep.filings = len(refs)
        periodic = sum(r.form in ("10-K", "10-Q") for r in refs)
        expected = expected_periodic(start)
        if periodic < expected:
            rep.warnings.append(
                f"only {periodic} 10-K/10-Q filings since {start} (expected about {expected}). "
                "The company may have re-registered under a new CIK: add the predecessor CIK "
                "to the extra_ciks column of the universe file."
            )
            log(f"{m.ticker}: WARNING {rep.warnings[-1]}")
        known = manifest.accessions(cid.cik)
        for ref in refs:
            if ref.accession in known:
                continue
            try:
                index_path = raw_dir / "filings" / str(ref.cik) / ref.accession / "_index.htm"
                index = sec_filings.parse_index(client.get_bytes(ref.index_url, index_path))
                docs = sec_filings.documents_to_parse(ref, index)
                if not docs:
                    raise SecError("no parseable document in the filing index")
                entries = []
                for role, doc in docs:
                    entry_path = raw_dir / "filings" / str(ref.cik) / ref.accession / doc
                    data = client.get_bytes(ref.doc_url(doc), entry_path)
                    entries.append(
                        ManifestEntry(
                            cik=ref.cik,
                            company_cik=cid.cik,
                            ticker=m.ticker,
                            accession=ref.accession,
                            form=ref.form,
                            filing_date=ref.filing_date,
                            report_date=ref.report_date,
                            items=ref.items,
                            primary_doc=ref.primary_doc,
                            role=role,
                            doc=doc,
                            url=ref.doc_url(doc),
                            sha256=sha256(data),
                            bytes=len(data),
                            fetched=utc_now(),
                        )
                    )
                rep.new_docs += manifest.add(entries)
            except SecError as exc:
                rep.errors.append(f"{ref.form} {ref.accession}: {exc}")
                log(f"{m.ticker}: skipped {ref.form} {ref.accession}: {exc}")
        for filer in (cid.cik, *m.extra_ciks):
            try:
                fetch_companyfacts(client, raw_dir, filer)
            except SecError as exc:
                rep.errors.append(f"company facts for CIK {filer}: {exc}")
                log(f"{m.ticker}: no XBRL company facts for CIK {filer}: {exc}")
        log(f"{m.ticker}: {rep.filings} filings, {rep.new_docs} new documents")
    return reports
