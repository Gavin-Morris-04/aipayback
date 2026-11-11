"""verify -> explain -> gate end to end with the fake model. No network, no real key."""

import json
import sqlite3

from typer.testing import CliRunner

from aipb import cli

runner = CliRunner()


def run(*args, code=0):
    result = runner.invoke(cli.app, list(args))
    assert result.exit_code == code, result.output
    return result


def db(root):
    conn = sqlite3.connect(root / "data" / "aipb.sqlite")
    conn.row_factory = sqlite3.Row
    return conn


def pipeline(project):
    run("filter", "-u", "test")
    run("extract", "-u", "test")


def test_verify_explain_gate_publishes_cited_statuses(llm_project, fake_claude):
    pipeline(llm_project)
    out = run("verify", "-u", "test").output
    assert "Tier 1:" in out
    out = run("explain", "-u", "test").output
    assert "passed citation and wording checks" in out
    conn = db(llm_project)
    final = conn.execute("SELECT * FROM final_status").fetchall()
    assert final and any(r["publishable"] for r in final)
    for r in final:
        if r["publishable"]:
            e = conn.execute(
                "SELECT * FROM explanations WHERE cluster_id=?", (r["cluster_id"],)
            ).fetchone()
            assert e["citations_valid"] and e["lint_ok"]
            cites = json.loads(e["citations"])
            assert {c["document_index"] for c in cites} >= {0}
    assert conn.execute("SELECT COUNT(*) FROM evidence").fetchone()[0] > 0
    conn.close()
    assert "Promise statuses" in run("status").output


def test_low_confidence_escalates_to_the_agent(llm_project, fake_claude):
    pipeline(llm_project)
    fake_claude.t1 = lambda user: {
        "status": "no_evidence_yet",
        "walked_back_kind": "none",
        "confidence": 0.4,
        "evidence_ids": [],
        "number_ids": [],
        "key_finding": "Unclear from these passages.",
    }
    out = run("verify", "-u", "test").output
    assert "Tier 2 ran" in out and "submitted" in out
    conn = db(llm_project)
    t2 = conn.execute("SELECT * FROM verdicts WHERE tier='2'").fetchall()
    assert t2 and all(r["stop"] == "submitted" for r in t2)
    conn.close()
    run("explain", "-u", "test")
    conn = db(llm_project)
    tiers = {
        r["source_tier"] for r in conn.execute("SELECT * FROM final_status WHERE publishable=1")
    }
    assert tiers <= {"2"} and tiers
    conn.close()


def test_walked_back_needs_two_agreeing_checks(llm_project, fake_claude):
    pipeline(llm_project)
    walked = {
        "status": "walked_back",
        "walked_back_kind": "explicit",
        "confidence": 0.9,
        "evidence_ids": ["E1"],
        "number_ids": [],
        "key_finding": "A later filing lowers the target.",
    }
    fake_claude.t1 = lambda user: walked if "<evidence" in user else None
    run("verify", "-u", "test")  # Tier 2 (default answer: on track) disagrees
    run("explain", "-u", "test")
    conn = db(llm_project)
    labels = {r["label"] for r in conn.execute("SELECT label FROM final_status")}
    assert "Walked back" not in labels
    reasons = [r["reason"] for r in conn.execute("SELECT reason FROM final_status")]
    assert any("disagree" in r for r in reasons)
    conn.close()

    fake_claude.t2 = lambda user: walked if "<evidence" in user else None
    # A new Tier 2 answer means new requests: clear the cached agent outputs for this test.
    for f in (llm_project / "data" / "outputs" / "verify_t2").glob("*.jsonl"):
        f.unlink()
    run("verify", "-u", "test")
    run("explain", "-u", "test")
    conn = db(llm_project)
    labels = {r["label"] for r in conn.execute("SELECT label FROM final_status")}
    assert "Walked back" in labels
    conn.close()


def test_non_neutral_explanation_stays_pending(llm_project, fake_claude):
    pipeline(llm_project)
    fake_claude.explain_bad_word = True
    run("verify", "-u", "test")
    run("explain", "-u", "test")
    conn = db(llm_project)
    assert conn.execute("SELECT COUNT(*) FROM final_status WHERE publishable=1").fetchone()[0] == 0
    assert all(not r["lint_ok"] for r in conn.execute("SELECT lint_ok FROM explanations"))
    conn.close()


def test_open_error_report_holds_the_item(llm_project, fake_claude):
    pipeline(llm_project)
    run("verify", "-u", "test")
    run("explain", "-u", "test")
    conn = db(llm_project)
    cid = conn.execute("SELECT cluster_id FROM final_status WHERE publishable=1").fetchone()[0]
    conn.close()
    (llm_project / "data" / "error_reports.csv").write_text(
        f"report_id,cluster_id,status,received,notes\nR1,{cid},open,2026-11-10,reader email\n",
        encoding="utf-8",
    )
    run("gate")
    conn = db(llm_project)
    row = conn.execute("SELECT * FROM final_status WHERE cluster_id=?", (cid,)).fetchone()
    assert not row["publishable"] and row["reason"] == "open error report"
    conn.close()


def test_verify_replays_from_cache_and_dry_run_prices_tier2(llm_project, fake_claude):
    pipeline(llm_project)
    fake_claude.t1 = lambda user: {
        "status": "no_evidence_yet",
        "walked_back_kind": "none",
        "confidence": 0.4,
        "evidence_ids": [],
        "number_ids": [],
        "key_finding": "Unclear.",
    }
    run("verify", "-u", "test")
    n = len(fake_claude.calls)
    run("verify", "-u", "test")  # Tier 1 and the whole agent loop come from the cache
    assert len(fake_claude.calls) == n
    out = run("verify", "-u", "test", "--dry-run").output
    assert "Tier 2 worst case" in out


def test_status_packet_label_import_and_eval(llm_project, fake_claude):
    from openpyxl import load_workbook

    pipeline(llm_project)
    run("verify", "-u", "test")
    run("explain", "-u", "test")
    run("status-packets", "--n", "10")
    path = llm_project / "exports" / "packets" / "status_packet_v1.xlsx"
    wb = load_workbook(path)
    ws = wb["Promises"]
    col = {c.value: c.column for c in ws[1]}
    for r in range(2, ws.max_row + 1):
        ws.cell(r, col["Your status"], "On track")
    returned = llm_project / "evals" / "gold" / "returned"
    returned.mkdir(parents=True, exist_ok=True)
    wb.save(returned / path.name)
    out = run("import-statuses").output
    assert "labeled" in out
    out = run("eval-status").output
    assert "Status eval" in out and "| Threshold |" in out
    results = list((llm_project / "evals" / "results").glob("*_status_default.json"))
    data = json.loads(results[0].read_text(encoding="utf-8"))
    assert data["matched_to_a_cluster"] == data["gold_items"] > 0
    # The fake judge says on_track for these, and gold says On track: published = correct.
    a = data["at_threshold"]
    assert a["published"] == a["correct"]
    # Re-running status-packets would orphan labels: it refuses without --force.
    assert "already exists" in " ".join(run("status-packets", code=2).output.split())


def test_restore_replays_verification_without_touching_the_ledger(llm_project, fake_claude):
    from aipb.budget.ledger import Ledger

    pipeline(llm_project)
    fake_claude.t1 = lambda user: {
        "status": "no_evidence_yet", "walked_back_kind": "none", "confidence": 0.4,
        "evidence_ids": [], "number_ids": [], "key_finding": "Unclear.",
    }  # fmt: skip
    run("verify", "-u", "test")
    run("explain", "-u", "test")
    conn = db(llm_project)
    before = {r["cluster_id"]: r["label"] for r in conn.execute("SELECT * FROM final_status")}
    conn.close()
    ledger_before = (llm_project / "data" / "ledger" / "runs.jsonl").read_text(encoding="utf-8")
    n = len(fake_claude.calls)
    (llm_project / "data" / "aipb.sqlite").unlink()
    out = run("restore").output
    assert "verify: replayed" in out
    conn = db(llm_project)
    after = {r["cluster_id"]: r["label"] for r in conn.execute("SELECT * FROM final_status")}
    conn.close()
    assert after == before and before
    assert len(fake_claude.calls) == n  # zero API calls
    assert (llm_project / "data" / "ledger" / "runs.jsonl").read_text(
        encoding="utf-8"
    ) == ledger_before
    assert Ledger(llm_project / "data" / "ledger").runs()
