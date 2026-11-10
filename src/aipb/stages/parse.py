"""Stage 2 (+3a): manifest documents -> passages, FTS index, XBRL facts, keyword prefilter.

Everything here is plain code and costs $0. It is idempotent: a filing is re-parsed only
when the parser version changes (or with force=True).
"""

from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from aipb.budget.ledger import utc_now
from aipb.parse.html import PARSER_VERSION, html_to_blocks
from aipb.parse.passages import Passage, build_passages, normalize_for_match
from aipb.parse.sections import split_sections
from aipb.sec.client import SecClient, SecError
from aipb.sec.manifest import Manifest, ManifestEntry
from aipb.sec.xbrl import fetch_companyfacts, iter_facts
from aipb.stages.ingest import fetch_entry, sha256
from aipb.stages.prefilter import Deduper, Lexicon

ROLE_ORDER = {"primary": 0, "ex13": 1, "ex99": 2}


@dataclass
class ParseReport:
    cik: int
    parsed: int = 0
    skipped: int = 0
    passages: int = 0
    facts: int = 0
    warnings: list[str] = field(default_factory=list)


def upsert_company(
    conn: sqlite3.Connection, *, cik: int, ticker: str, name: str, sector: str, universe: str,
    source: str, source_date: str,
) -> None:  # fmt: skip
    with conn:
        conn.execute(
            "INSERT INTO companies VALUES (?,?,?,?,?,?,?) ON CONFLICT(cik) DO UPDATE SET "
            "ticker=excluded.ticker, name=excluded.name, sector=excluded.sector, "
            "universe=excluded.universe, source=excluded.source, source_date=excluded.source_date",
            (cik, ticker, name, sector, universe, source, source_date),
        )


def _read_doc(
    entry: ManifestEntry, raw_dir: Path, client: SecClient | None, warnings: list[str]
) -> bytes | None:
    path = entry.raw_path(raw_dir)
    if path.exists():
        data = path.read_bytes()
        ok = sha256(data) == entry.sha256
    elif client is not None:
        try:
            data, ok = fetch_entry(client, raw_dir, entry)
        except SecError as exc:
            warnings.append(f"{entry.accession}/{entry.doc}: {exc}")
            return None
    else:
        warnings.append(f"{entry.accession}/{entry.doc}: not downloaded (run aipb ingest)")
        return None
    if not ok:
        warnings.append(
            f"{entry.accession}/{entry.doc}: sha256 differs from the manifest (SEC re-issued "
            "the document or the download is corrupt). Parsed anyway; check it."
        )
    return data


def parse_filing(entries: list[ManifestEntry], docs: dict[str, bytes]) -> list[Passage]:
    first = entries[0]
    passages: list[Passage] = []
    offset = 0
    for e in sorted(entries, key=lambda x: (ROLE_ORDER.get(x.role, 9), x.doc)):
        if e.doc not in docs:
            continue
        blocks = html_to_blocks(docs[e.doc])
        sections = split_sections(blocks, first.form, e.role)
        ps = build_passages(first.company_cik, first.accession, e.role, sections, offset=offset)
        passages.extend(ps)
        offset = ps[-1].char_end + 2 if ps else offset
    return passages


def _delete_filing(conn: sqlite3.Connection, accession: str) -> None:
    conn.execute(
        "DELETE FROM passages_fts WHERE passage_id IN "
        "(SELECT passage_id FROM passages WHERE accession=?)",
        (accession,),
    )
    conn.execute("DELETE FROM passages WHERE accession=?", (accession,))
    conn.execute("DELETE FROM filing_docs WHERE accession=?", (accession,))
    conn.execute("DELETE FROM filings WHERE accession=?", (accession,))


def store_filing(
    conn: sqlite3.Connection, entries: list[ManifestEntry], passages: list[Passage]
) -> None:
    f = entries[0]
    with conn:
        _delete_filing(conn, f.accession)
        conn.execute(
            "INSERT INTO filings VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                f.accession, f.company_cik, f.cik, f.form, f.filing_date, f.report_date,
                f.items, f.primary_doc, PARSER_VERSION, utc_now(), len(passages),
            ),
        )  # fmt: skip
        conn.executemany(
            "INSERT INTO filing_docs VALUES (?,?,?,?,?,?)",
            [(e.accession, e.role, e.doc, e.url, e.sha256, e.bytes) for e in entries],
        )
        conn.executemany(
            "INSERT INTO passages (passage_id, cik, accession, form, filing_date, doc_role, "
            "section, seq, text, text_sha256, char_start, char_end, words) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                (
                    p.passage_id, p.cik, p.accession, f.form, f.filing_date, p.doc_role,
                    p.section, p.seq, p.text, p.text_sha256, p.char_start, p.char_end, p.words,
                )
                for p in passages
            ],
        )  # fmt: skip
        conn.executemany(
            "INSERT INTO passages_fts (passage_id, cik, filing_date, text) VALUES (?,?,?,?)",
            [(p.passage_id, p.cik, f.filing_date, normalize_for_match(p.text)) for p in passages],
        )


def parse_company(
    conn: sqlite3.Connection,
    manifest: Manifest,
    raw_dir: Path,
    cik: int,
    *,
    client: SecClient | None = None,
    force: bool = False,
    log: Callable[[str], None] = print,
) -> ParseReport:
    rep = ParseReport(cik=cik)
    by_acc: dict[str, list[ManifestEntry]] = defaultdict(list)
    for e in manifest.entries(cik):
        by_acc[e.accession].append(e)
    done = {
        row["accession"]
        for row in conn.execute(
            "SELECT accession FROM filings WHERE cik=? AND parser_version=?", (cik, PARSER_VERSION)
        )
    }
    for acc, entries in by_acc.items():
        if acc in done and not force:
            rep.skipped += 1
            continue
        docs = {}
        for e in entries:
            data = _read_doc(e, raw_dir, client, rep.warnings)
            if data is not None:
                docs[e.doc] = data
        if not docs:
            continue
        try:
            passages = parse_filing(entries, docs)
        except Exception as exc:  # malformed filing: log and skip, never stop the run
            rep.warnings.append(f"{acc}: parse failed: {type(exc).__name__}: {exc}")
            continue
        store_filing(conn, entries, passages)
        rep.parsed += 1
        rep.passages += len(passages)
    for w in rep.warnings:
        log(f"CIK {cik}: {w}")
    return rep


def load_xbrl(
    conn: sqlite3.Connection,
    raw_dir: Path,
    cik: int,
    client: SecClient | None,
    filer_ciks: set[int] | None = None,
) -> int:
    """Load XBRL facts for a company from every registrant that filed for it."""
    rows: list[tuple] = []
    for filer in sorted({cik, *(filer_ciks or set())}):
        path = raw_dir / "companyfacts" / f"CIK{filer:010d}.json"
        if path.exists():
            doc = json.loads(path.read_bytes())
        elif client is not None:
            doc = fetch_companyfacts(client, raw_dir, filer)
        else:
            continue
        rows += [(cik, *f.row()[1:]) for f in iter_facts(doc)]
    with conn:
        conn.execute("DELETE FROM xbrl_facts WHERE cik=?", (cik,))
        conn.executemany(
            "INSERT OR IGNORE INTO xbrl_facts VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", rows
        )
    return len(rows)


def prefilter_company(conn: sqlite3.Connection, cik: int, lexicon: Lexicon) -> dict[str, int]:
    """Tag keyword and forward-cue hits, then mark boilerplate duplicates (earliest wins)."""
    rows = conn.execute(
        "SELECT passage_id, text FROM passages WHERE cik=? "
        "ORDER BY filing_date, accession, char_start",
        (cik,),
    ).fetchall()
    near = Deduper()  # keyword passages: near-duplicate check (same numbers required)
    exact = Deduper(threshold=2.0)  # everything else: exact duplicates only
    updates = []
    stats = {"passages": len(rows), "kw": 0, "kw_fwd": 0, "kw_canonical": 0, "dups": 0}
    for row in rows:
        kw, fwd = lexicon.scan(row["text"])
        dup = (near if kw else exact).check(row["passage_id"], row["text"])
        if kw:
            stats["kw"] += 1
            stats["kw_fwd"] += bool(fwd)
            stats["kw_canonical"] += dup is None
        stats["dups"] += dup is not None
        updates.append((json.dumps(kw), json.dumps(fwd), lexicon.version, dup, row["passage_id"]))
    with conn:
        conn.executemany(
            "UPDATE passages SET kw_hits=?, fwd_cues=?, kw_version=?, dup_of=? WHERE passage_id=?",
            updates,
        )
    return stats
