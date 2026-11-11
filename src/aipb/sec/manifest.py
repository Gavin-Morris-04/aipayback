"""data/manifests/filings.jsonl: every SEC document we parse, with its URL and sha256.

Committed to git (union merge), so any device can re-download exactly the same documents
and check they are byte-identical. One line per (accession, document).

`cik` is the registrant that filed the document (it builds the URL). `company_cik` is the
company we track. They differ when a company re-registers, e.g. ExxonMobil's 2026 holding
company (CIK 2115436) whose 2024-2025 filings sit under Exxon Mobil Corp (CIK 34088).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from aipb import jsonl


@dataclass(frozen=True)
class ManifestEntry:
    cik: int
    company_cik: int
    ticker: str
    accession: str
    form: str
    filing_date: str
    report_date: str
    items: str
    primary_doc: str
    role: str
    doc: str
    url: str
    sha256: str
    bytes: int
    fetched: str

    @property
    def key(self) -> tuple[str, str]:
        return (self.accession, self.doc)

    def raw_path(self, raw_dir: Path) -> Path:
        return raw_dir / "filings" / str(self.cik) / self.accession / self.doc


class Manifest:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._entries: dict[tuple[str, str], ManifestEntry] = {}
        for rec in jsonl.read(path):
            entry = ManifestEntry(**rec)
            # Union merges can duplicate lines; the first one wins.
            self._entries.setdefault(entry.key, entry)

    def __len__(self) -> int:
        return len(self._entries)

    def entries(self, cik: int | None = None) -> list[ManifestEntry]:
        items = self._entries.values()
        if cik is not None:
            items = [e for e in items if e.company_cik == cik]
        return sorted(
            items, key=lambda e: (e.company_cik, e.filing_date, e.accession, e.role, e.doc)
        )

    def ciks(self) -> dict[str, int]:
        """ticker -> company CIK for every company in the manifest."""
        return {e.ticker: e.company_cik for e in self._entries.values()}

    def filer_ciks(self, company_cik: int) -> set[int]:
        """Every registrant CIK that filed documents for this company."""
        return {e.cik for e in self._entries.values() if e.company_cik == company_cik}

    def accessions(self, company_cik: int) -> set[str]:
        return {e.accession for e in self._entries.values() if e.company_cik == company_cik}

    def get(self, accession: str, doc: str) -> ManifestEntry | None:
        return self._entries.get((accession, doc))

    def add(self, entries: list[ManifestEntry]) -> int:
        new = [e for e in entries if e.key not in self._entries]
        for e in new:
            self._entries[e.key] = e
        return jsonl.append(self.path, (asdict(e) for e in new))

    def missing_on_disk(self) -> list[ManifestEntry]:
        """Entries this process holds that the file no longer has.

        Another process can rewrite the file mid-run and silently drop appended lines.
        pre-commit's stash does this when a commit runs during an ingest (it cost six
        Cisco documents once).
        """
        on_disk = {(rec["accession"], rec["doc"]) for rec in jsonl.read(self.path)}
        return [e for k, e in sorted(self._entries.items()) if k not in on_disk]

    def repair(self) -> int:
        """Re-append entries that vanished from the file. Returns how many."""
        return jsonl.append(self.path, (asdict(e) for e in self.missing_on_disk()))
