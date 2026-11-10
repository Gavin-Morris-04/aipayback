"""SQLite working database (git-ignored). Always rebuildable from committed JSONL.

Phase 0 holds only the cost tables. Later phases add companies, filings, passages
(FTS5), promises, verdicts and the rest of the data model in docs/PLAN.md.
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
"""


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
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
