"""filter -> extract -> dedupe through the CLI with a fake Claude: batches, cache, budget.

No network and no real key: the SDK is tests/fake_claude.py and the SEC is the fixture fake.
"""

import json
import sqlite3

import pytest
from typer.testing import CliRunner

from aipb import cli
from aipb.budget.ledger import Ledger

runner = CliRunner()


def run(*args, code=0):
    result = runner.invoke(cli.app, list(args))
    assert result.exit_code == code, result.output
    return result


def db(root):
    conn = sqlite3.connect(root / "data" / "aipb.sqlite")
    conn.row_factory = sqlite3.Row
    return conn


def ledger(root):
    return Ledger(root / "data" / "ledger")


def test_filter_extract_dedupe_end_to_end(llm_project, fake_claude):
    out = run("filter", "-u", "test").output
    assert "Classified" in out
    out = run("extract", "-u", "test").output
    assert "verified statements" in out

    conn = db(llm_project)
    labels = dict(conn.execute("SELECT label, COUNT(*) FROM classifications GROUP BY label"))
    assert labels.get("promise", 0) >= 2
    promises = conn.execute("SELECT * FROM promises WHERE kind='promise'").fetchall()
    assert promises
    # Every stored quote is the filing's own text, at the stored span.
    for p in promises:
        text = conn.execute(
            "SELECT text FROM passages WHERE passage_id=?", (p["passage_id"],)
        ).fetchone()[0]
        assert text[p["quote_start"] : p["quote_end"]] == p["quote"]
        assert p["cluster_id"]
    assert conn.execute("SELECT COUNT(*) FROM promise_clusters").fetchone()[0] >= 1
    conn.close()

    # Everything went through batches and was settled in the ledger at batch prices.
    calls = ledger(llm_project).calls()
    assert calls and all(c.is_batch and c.batch_id for c in calls)
    assert {c.stage for c in calls} == {"filter", "extract"}
    runs = ledger(llm_project).runs()
    assert runs and all(not r.is_open for r in runs.values())
    outputs = list((llm_project / "data" / "outputs").rglob("*.jsonl"))
    assert outputs  # committed outputs: never pay twice


def test_second_run_is_free_and_offline_replay_works(llm_project, fake_claude, monkeypatch):
    run("filter", "-u", "test")
    run("extract", "-u", "test")
    n_calls = len(fake_claude.calls)
    n_ledger = len(ledger(llm_project).calls())
    out = run("filter", "-u", "test").output
    assert "0 to send" in out
    run("extract", "-u", "test")
    assert len(fake_claude.calls) == n_calls  # all served from the output cache
    assert len(ledger(llm_project).calls()) == n_ledger

    # CI mode: offline, cache only. Rebuilding from committed outputs works.
    (llm_project / "data" / "aipb.sqlite").unlink()
    monkeypatch.setenv("AIPAYBACK_OFFLINE", "true")
    for cmd in ("parse", "prefilter", "filter", "extract"):
        run(cmd, "-u", "test")
    conn = db(llm_project)
    assert conn.execute("SELECT COUNT(*) FROM promises").fetchone()[0] > 0
    conn.close()
    assert len(fake_claude.calls) == n_calls


def test_offline_cache_miss_sends_nothing(llm_project, fake_claude, monkeypatch):
    monkeypatch.setenv("AIPAYBACK_OFFLINE", "true")
    result = run("filter", "-u", "test", code=2)
    assert "OfflineCacheMiss" in result.output
    assert fake_claude.calls == []


def test_misquoted_statement_is_retried_once_then_verified(llm_project, fake_claude):
    fake_claude.paraphrase_first = True
    run("filter", "-u", "test")
    out = run("extract", "-u", "test").output
    assert "Quote retries:" in out
    conn = db(llm_project)
    retried = conn.execute("SELECT COUNT(*) FROM promises WHERE retried=1").fetchone()[0]
    assert retried >= 1
    # No stored quote contains the paraphrase.
    quotes = [r[0] for r in conn.execute("SELECT quote FROM promises")]
    assert not any("anticipate" in q for q in quotes)
    conn.close()


def test_quote_that_never_matches_is_dropped(llm_project, fake_claude):
    from tests.fake_claude import Msg

    def bad_extract(params):
        system = " ".join(b["text"] for b in params["system"])
        if "You extract" in system:
            st = {
                "quote": "We guarantee AI will triple profits by 2025", "kind": "promise",
                "claim_type": "other", "metric": None, "target_text": None,
                "target_value": None, "target_unit": None, "baseline": None,
                "deadline_text": None, "deadline_year": 2025, "deadline_precision": "year",
                "specificity": 1, "confidence": "high",
            }  # fmt: skip
            return Msg(json.dumps({"statements": [st]}))
        return fake_claude_default.answer(params)

    from tests.fake_claude import FakeClaude

    fake_claude_default = FakeClaude()
    run("filter", "-u", "test")
    fake_claude.responder = bad_extract
    out = run("extract", "-u", "test").output
    assert "quotes dropped after retry: " in out
    conn = db(llm_project)
    assert conn.execute("SELECT COUNT(*) FROM promises").fetchone()[0] == 0
    logged = conn.execute(
        "SELECT COUNT(*) FROM extraction_log WHERE status='dropped_quotes'"
    ).fetchone()[0]
    assert logged >= 1
    conn.close()


def test_refusal_is_not_cached_and_routes_passages_onward(llm_project, fake_claude):
    fake_claude.refuse = ("EXEMPLAR REPORTS",)  # the earnings release request
    run("filter", "-u", "test")
    conn = db(llm_project)
    errors = conn.execute("SELECT COUNT(*) FROM classifications WHERE label='error'").fetchone()[0]
    assert errors >= 1
    conn.close()
    calls = ledger(llm_project).calls()
    assert any(c.status == "refusal" for c in calls)
    # Refusals are not cached: a later run asks again.
    fake_claude.refuse = ()
    out = run("filter", "-u", "test").output
    assert "1 to send" in out


def test_confirm_threshold_and_cap_are_enforced(llm_project, fake_claude):
    budget = llm_project / "config" / "budget.yaml"
    text = budget.read_text(encoding="utf-8")
    budget.write_text(
        text.replace('confirm_threshold_usd: "0.50"', 'confirm_threshold_usd: "0.0001"'),
        encoding="utf-8",
    )
    result = run("filter", "-u", "test", code=2)
    assert "ConfirmationRequired" in result.output
    assert fake_claude.calls == []
    run("filter", "-u", "test", "--confirm")
    assert fake_claude.calls


def test_missing_key_refuses_before_reserving(project, fake_claude):
    for cmd in ("ingest", "parse", "prefilter"):
        run(cmd, "-u", "test")
    result = run("filter", "-u", "test", code=2)
    assert "MissingApiKey" in result.output and "Nothing was reserved" in result.output
    assert ledger(project).runs() == {}


def test_dry_run_sends_nothing(llm_project, fake_claude):
    out = run("filter", "-u", "test", "--dry-run").output
    assert "Worst-case cost" in out
    assert fake_claude.calls == [] and ledger(llm_project).runs() == {}


def test_interrupted_batch_is_collected_not_paid_twice(llm_project, fake_claude, monkeypatch):
    from aipb.llm import client as client_mod

    original = client_mod.LLMClient.collect

    def crash(self, batch_id, run=None):
        raise KeyboardInterrupt  # the laptop lid closes while waiting

    monkeypatch.setattr(client_mod.LLMClient, "collect", crash)
    result = runner.invoke(cli.app, ["filter", "-u", "test"])
    assert result.exit_code != 0  # click reports Ctrl-C as "Aborted!"
    monkeypatch.setattr(client_mod.LLMClient, "collect", original)
    # The batch is billed even though nobody read it: its reservation stays held.
    held = [r for r in ledger(llm_project).runs().values() if r.is_open]
    assert len(held) == 1 and held[0].outstanding_reservation > 0

    out = run("batches").output
    assert "msgbatch_" in out
    batch_id = out.split()[0]
    run("batch-collect", batch_id)
    assert run("batches").output.startswith("No uncollected batches")
    assert not [r for r in ledger(llm_project).runs().values() if r.is_open]
    assert any(c.batch_id == batch_id for c in ledger(llm_project).calls())
    n = len(fake_claude.batches)
    out = run("filter", "-u", "test").output
    assert "0 to send" in out
    assert len(fake_claude.batches) == n  # nothing resubmitted
    result = run("batch-collect", batch_id, code=2)
    assert "already collected" in result.output


@pytest.mark.parametrize("variant", ["effort_low"])
def test_variants_are_stored_separately(llm_project, fake_claude, variant):
    run("filter", "-u", "test")
    run("filter", "-u", "test", "--variant", variant)
    conn = db(llm_project)
    variants = {r[0] for r in conn.execute("SELECT DISTINCT variant FROM classifications")}
    assert variants == {"default", variant}
    conn.close()
    sent = [c for c in fake_claude.calls if c.get("thinking", {}).get("type") == "adaptive"]
    assert sent  # the variant's settings reached the request


def test_restore_replays_model_outputs_for_free(llm_project, fake_claude):
    run("filter", "-u", "test")
    run("extract", "-u", "test")
    conn = db(llm_project)
    before = conn.execute("SELECT COUNT(*) FROM promises").fetchone()[0]
    conn.close()
    n = len(fake_claude.calls)
    (llm_project / "data" / "aipb.sqlite").unlink()
    out = run("restore").output
    assert "replayed" in out
    conn = db(llm_project)
    assert conn.execute("SELECT COUNT(*) FROM promises").fetchone()[0] == before
    assert conn.execute("SELECT COUNT(*) FROM promise_clusters").fetchone()[0] >= 1
    conn.close()
    assert len(fake_claude.calls) == n  # zero API calls
