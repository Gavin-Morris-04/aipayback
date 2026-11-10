"""ingest -> parse -> prefilter -> stats -> restore, end to end through the CLI.

The SEC is the in-memory fake in tests/fake_sec.py. No network, no API key, $0.
"""

import shutil
import sqlite3

import pytest
from typer.testing import CliRunner

from aipb import cli
from aipb.context import AppContext
from aipb.sec.client import SecClient
from tests.fake_sec import CIK, FakeSec

runner = CliRunner()


@pytest.fixture
def fake_sec():
    return FakeSec()


@pytest.fixture
def project(root, monkeypatch, fake_sec):
    (root / "config" / "universe" / "test.csv").write_text(
        "ticker,name,sector\nEXMP,Exemplar Industries,Industrials\n", encoding="utf-8"
    )
    (root / ".env").write_text("SEC_CONTACT_EMAIL=ops@example.com\n", encoding="utf-8")

    def make_ctx() -> AppContext:
        ctx = AppContext.create()
        ctx.__dict__["sec"] = SecClient(
            ctx.settings.sec_contact_email,
            offline=ctx.settings.aipayback_offline,
            transport=fake_sec.transport(),
            sleep=lambda s: None,
        )
        return ctx

    monkeypatch.setattr(cli, "_ctx", make_ctx)
    return root


def run(*args):
    result = runner.invoke(cli.app, list(args))
    assert result.exit_code == 0, result.output
    return result


def db(root):
    conn = sqlite3.connect(root / "data" / "aipb.sqlite")
    conn.row_factory = sqlite3.Row
    return conn


def doc_requests(fake):
    return [p for p in fake.requests if p.endswith(".htm") and "-index" not in p]


def test_full_pipeline(project, fake_sec):
    out = run("ingest", "-u", "test").output
    assert "EXMP" in out
    manifest = (project / "data" / "manifests" / "filings.jsonl").read_text(encoding="utf-8")
    assert manifest.count("\n") == 5  # 10-K + EX-13, EX-99.1, two 10-Qs
    assert fake_sec.user_agents == {"AIPayback/0.1 (ops@example.com)"}

    run("parse", "-u", "test")
    run("prefilter", "-u", "test")
    stats = run("stats", "-u", "test").output
    assert "EXMP" in stats

    conn = db(project)
    forms = dict(conn.execute("SELECT form, COUNT(*) FROM filings GROUP BY form").fetchall())
    assert forms == {"10-K": 1, "10-Q": 2, "8-K": 1}
    sections = {r[0] for r in conn.execute("SELECT DISTINCT section FROM passages")}
    assert {"item1a", "item7", "ex13", "ex99", "p1item2"} <= sections
    assert conn.execute("SELECT COUNT(*) FROM xbrl_facts").fetchone()[0] == 4

    # The second 10-Q repeats the first one word for word: all of it is marked duplicate.
    later = conn.execute(
        "SELECT dup_of FROM passages WHERE accession='9999999999-25-000030'"
    ).fetchall()
    assert later and all(r["dup_of"] for r in later)
    earlier = conn.execute(
        "SELECT dup_of FROM passages WHERE accession='9999999999-25-000020'"
    ).fetchall()
    assert all(r["dup_of"] is None for r in earlier)

    # The AI promise in the 10-K MD&A is a keyword + forward-cue candidate.
    row = conn.execute(
        "SELECT kw_hits, fwd_cues FROM passages WHERE section='item7' AND text LIKE '%run-rate%'"
    ).fetchone()
    assert "generative" in row["kw_hits"] and "expect" in row["fwd_cues"]

    # Full-text search works on normalized text (ligature folded, stemming on).
    hits = conn.execute(
        "SELECT passage_id FROM passages_fts WHERE passages_fts MATCH 'artificial AND intelligence'"
    ).fetchall()
    assert hits
    conn.close()


def test_ingest_is_idempotent(project, fake_sec):
    run("ingest", "-u", "test")
    n = len(fake_sec.requests)
    run("ingest", "-u", "test")
    assert len(fake_sec.requests) == n  # everything served from cache
    run("parse", "-u", "test")
    out = run("parse", "-u", "test").output
    assert "4" in out  # four filings already up to date


def test_restore_on_a_fresh_clone_redownloads_and_spends_nothing(project, fake_sec, tmp_path):
    run("ingest", "-u", "test")
    # Simulate a fresh clone: committed files only (no raw cache, no database).
    shutil.rmtree(project / "data" / "raw")
    before = len(doc_requests(fake_sec))
    out = run("restore").output
    assert "Restored 0 LLM calls" in out
    assert len(doc_requests(fake_sec)) - before == 5  # every manifest document, once
    assert not (project / "data" / "ledger" / "llm_calls.jsonl").exists()
    conn = db(project)
    assert conn.execute("SELECT COUNT(*) FROM filings").fetchone()[0] == 4
    assert conn.execute("SELECT ticker FROM companies").fetchone()[0] == "EXMP"
    assert conn.execute("SELECT cik FROM companies").fetchone()[0] == CIK
    conn.close()


def test_restore_offline_without_raw_files_fails_soft(project, fake_sec, monkeypatch):
    run("ingest", "-u", "test")
    shutil.rmtree(project / "data" / "raw")
    monkeypatch.setenv("AIPAYBACK_OFFLINE", "true")
    n = len(fake_sec.requests)
    result = runner.invoke(cli.app, ["restore"])
    assert result.exit_code == 0, result.output
    assert len(fake_sec.requests) == n  # offline: no SEC traffic at all
    assert "0 filings parsed" in result.output


def test_unknown_ticker_is_a_clear_error(project):
    result = runner.invoke(cli.app, ["ingest", "-u", "test", "-t", "NOPE"])
    assert result.exit_code == 2
    assert "Not in test.csv: NOPE" in result.output


def test_parse_before_ingest_says_what_to_do(project):
    result = runner.invoke(cli.app, ["parse", "-u", "test"])
    assert "run aipb ingest first" in result.output
