"""SQLite working database (git-ignored). Always rebuildable from committed files.

Phase 0: cost tables (from the ledger). Phase 1: companies, filings, documents, passages
(+ FTS5 index) and XBRL facts (from the filings manifest and a fresh SEC download).
Later phases add promises, verdicts and the rest of the data model in docs/PLAN.md.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from aipb.budget.ledger import Ledger

SCHEMA = """
CREATE TABLE IF NOT EXISTS llm_calls (
    call_id TEXT PRIMARY KEY,
    ts TEXT NOT NULL,
    run_id TEXT NOT NULL,
    stage TEXT NOT NULL,
    model TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    input_hash TEXT NOT NULL,
    is_batch INTEGER NOT NULL,
    batch_id TEXT,
    input_tokens INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    cache_read_tokens INTEGER NOT NULL,
    cache_write_5m_tokens INTEGER NOT NULL,
    cache_write_1h_tokens INTEGER NOT NULL,
    thinking_tokens INTEGER NOT NULL,
    latency_ms INTEGER,
    cost_usd TEXT NOT NULL,
    status TEXT NOT NULL,
    device TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    command TEXT,
    stage TEXT,
    estimate_usd TEXT,
    reserved_usd TEXT,
    actual_usd TEXT,
    calls INTEGER,
    git_sha TEXT,
    device TEXT,
    status TEXT,
    started TEXT,
    finished TEXT
);
CREATE TABLE IF NOT EXISTS companies (
    cik INTEGER PRIMARY KEY,
    ticker TEXT NOT NULL,
    name TEXT NOT NULL,
    sector TEXT,
    universe TEXT NOT NULL,
    source TEXT,
    source_date TEXT
);
CREATE TABLE IF NOT EXISTS filings (
    accession TEXT PRIMARY KEY,
    cik INTEGER NOT NULL,           -- the company we track
    filer_cik INTEGER NOT NULL,     -- registrant that filed it (differs after a re-registration)
    form TEXT NOT NULL,
    filing_date TEXT NOT NULL,
    report_date TEXT,
    items TEXT,
    primary_doc TEXT,
    parser_version TEXT,
    parsed_at TEXT,
    n_passages INTEGER
);
CREATE INDEX IF NOT EXISTS filings_cik ON filings(cik, filing_date);
CREATE TABLE IF NOT EXISTS filing_docs (
    accession TEXT NOT NULL,
    role TEXT NOT NULL,
    doc TEXT NOT NULL,
    url TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    bytes INTEGER NOT NULL,
    PRIMARY KEY (accession, doc)
);
CREATE TABLE IF NOT EXISTS passages (
    passage_id TEXT PRIMARY KEY,
    cik INTEGER NOT NULL,
    accession TEXT NOT NULL,
    form TEXT NOT NULL,
    filing_date TEXT NOT NULL,
    doc_role TEXT NOT NULL,
    section TEXT NOT NULL,
    seq INTEGER NOT NULL,
    text TEXT NOT NULL,
    text_sha256 TEXT NOT NULL,
    char_start INTEGER NOT NULL,
    char_end INTEGER NOT NULL,
    words INTEGER NOT NULL,
    kw_hits TEXT,
    fwd_cues TEXT,
    kw_version TEXT,
    dup_of TEXT
);
CREATE INDEX IF NOT EXISTS passages_filing ON passages(accession);
CREATE INDEX IF NOT EXISTS passages_cik ON passages(cik, filing_date);
CREATE VIRTUAL TABLE IF NOT EXISTS passages_fts USING fts5(
    passage_id UNINDEXED, cik UNINDEXED, filing_date UNINDEXED, text,
    tokenize = 'porter unicode61'
);
CREATE TABLE IF NOT EXISTS xbrl_facts (
    cik INTEGER NOT NULL,
    taxonomy TEXT NOT NULL,
    tag TEXT NOT NULL,
    unit TEXT NOT NULL,
    period_start TEXT NOT NULL,
    period_end TEXT NOT NULL,
    value REAL NOT NULL,
    fy INTEGER,
    fp TEXT,
    form TEXT,
    filed TEXT,
    accession TEXT NOT NULL,
    frame TEXT,
    PRIMARY KEY (cik, taxonomy, tag, unit, period_start, period_end, accession)
);
"""


# Phase 2: model outputs. `variant` is "default" or an A/B variant name from stages.yaml.
SCHEMA_LLM = """
CREATE TABLE IF NOT EXISTS classifications (
    passage_id TEXT NOT NULL,
    variant TEXT NOT NULL,
    label TEXT NOT NULL,            -- promise | hype | none | error
    confidence TEXT,                -- high | low
    prompt_version TEXT NOT NULL,
    model TEXT NOT NULL,
    PRIMARY KEY (passage_id, variant)
);
CREATE TABLE IF NOT EXISTS promises (
    promise_id TEXT PRIMARY KEY,    -- {variant}:{passage_id}:s{n}
    variant TEXT NOT NULL,
    passage_id TEXT NOT NULL,
    cik INTEGER NOT NULL,
    accession TEXT NOT NULL,
    filing_date TEXT NOT NULL,
    seq INTEGER NOT NULL,
    quote TEXT NOT NULL,            -- the filing's own characters (verbatim, checked by code)
    quote_start INTEGER NOT NULL,   -- span in the original passage text
    quote_end INTEGER NOT NULL,
    kind TEXT NOT NULL,             -- promise | hype
    claim_type TEXT NOT NULL,
    metric TEXT,
    target_text TEXT,
    target_value REAL,
    target_unit TEXT,
    baseline TEXT,
    deadline_text TEXT,
    deadline_year INTEGER,
    deadline_precision TEXT,
    specificity INTEGER,
    confidence TEXT,
    prompt_version TEXT NOT NULL,
    model TEXT NOT NULL,
    retried INTEGER NOT NULL DEFAULT 0,
    cluster_id TEXT
);
CREATE INDEX IF NOT EXISTS promises_variant ON promises(variant, cik);
CREATE TABLE IF NOT EXISTS extraction_log (
    passage_id TEXT NOT NULL,
    variant TEXT NOT NULL,
    status TEXT NOT NULL,           -- ok | dropped_quotes | error
    n_statements INTEGER NOT NULL,
    n_dropped INTEGER NOT NULL,
    detail TEXT,
    PRIMARY KEY (passage_id, variant)
);
CREATE TABLE IF NOT EXISTS promise_clusters (
    cluster_id TEXT PRIMARY KEY,
    variant TEXT NOT NULL,
    cik INTEGER NOT NULL,
    claim_type TEXT NOT NULL,
    canonical_promise_id TEXT NOT NULL,
    first_stated TEXT NOT NULL,
    last_stated TEXT NOT NULL,
    n_statements INTEGER NOT NULL,
    related_cluster_id TEXT         -- same metric, different target or deadline
);
"""


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(SCHEMA)
    conn.executescript(SCHEMA_LLM)
    return conn


def restore_costs(conn: sqlite3.Connection, ledger: Ledger) -> tuple[int, int]:
    """Rebuild llm_calls and runs from the committed ledger. Makes zero API calls."""
    calls = ledger.calls()
    runs = ledger.runs()
    with conn:
        conn.execute("DELETE FROM llm_calls")
        conn.execute("DELETE FROM runs")
        conn.executemany(
            "INSERT INTO llm_calls VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                (
                    c.call_id,
                    c.ts,
                    c.run_id,
                    c.stage,
                    c.model,
                    c.prompt_version,
                    c.input_hash,
                    int(c.is_batch),
                    c.batch_id,
                    c.input_tokens,
                    c.output_tokens,
                    c.cache_read_tokens,
                    c.cache_write_5m_tokens,
                    c.cache_write_1h_tokens,
                    c.thinking_tokens,
                    c.latency_ms,
                    str(c.cost_usd),
                    c.status,
                    c.device,
                )
                for c in calls
            ],
        )
        conn.executemany(
            "INSERT INTO runs VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                (
                    r.run_id,
                    r.start.command,
                    r.start.stage,
                    str(r.start.estimate_usd),
                    str(r.start.reserved_usd),
                    str(r.spent_usd),
                    r.calls,
                    r.start.git_sha,
                    r.start.device,
                    r.finish.status if r.finish else "open",
                    r.start.ts,
                    r.finish.ts if r.finish else None,
                )
                for r in runs.values()
            ],
        )
    return len(calls), len(runs)


def company_stats(conn: sqlite3.Connection, ciks: list[int]) -> dict[int, dict[str, int]]:
    """Counts per company for `aipb stats` and the Phase 1 acceptance table."""
    out: dict[int, dict[str, int]] = {}
    for cik in ciks:
        r: dict[str, int] = {}
        for row in conn.execute(
            "SELECT form, COUNT(*) n FROM filings WHERE cik=? GROUP BY form", (cik,)
        ):
            r[row["form"]] = row["n"]
        row = conn.execute(
            "SELECT COUNT(*) passages, "
            "SUM(kw_hits IS NOT NULL AND kw_hits != '[]') kw, "
            "SUM(kw_hits IS NOT NULL AND kw_hits != '[]' AND fwd_cues != '[]') kw_fwd, "
            "SUM(kw_hits IS NOT NULL AND kw_hits != '[]' AND dup_of IS NULL) kw_canonical "
            "FROM passages WHERE cik=?",
            (cik,),
        ).fetchone()
        r.update({k: row[k] or 0 for k in ("passages", "kw", "kw_fwd", "kw_canonical")})
        r["facts"] = conn.execute("SELECT COUNT(*) FROM xbrl_facts WHERE cik=?", (cik,)).fetchone()[
            0
        ]
        out[cik] = r
    return out


def window_counts(conn: sqlite3.Connection, ciks: list[int]) -> dict[str, int]:
    """Canonical passages in the promise window, with and without AI keywords."""
    if not ciks:
        return {"kw": 0, "nonkw": 0}
    marks = ",".join("?" * len(ciks))
    row = conn.execute(
        f"SELECT SUM(kw_hits != '[]') kw, SUM(kw_hits = '[]' AND words >= 40) nonkw "
        f"FROM passages WHERE cik IN ({marks}) AND dup_of IS NULL "
        "AND filing_date BETWEEN '2024-01-01' AND '2025-12-31'",
        ciks,
    ).fetchone()
    return {"kw": row["kw"] or 0, "nonkw": row["nonkw"] or 0}
