"""CLI end to end against a temp project root. No network, no real keys."""

from typer.testing import CliRunner

from aipb.cli import app

runner = CliRunner()


def test_budget_on_a_fresh_project(root):
    result = runner.invoke(app, ["budget"])
    assert result.exit_code == 0, result.output
    assert "$15.00" in result.output
    assert "$4.00" in result.output
    assert "nothing spent yet" in result.output


def test_cost_report_and_restore_are_free(root):
    assert runner.invoke(app, ["cost-report"]).exit_code == 0
    result = runner.invoke(app, ["restore"])
    assert result.exit_code == 0, result.output
    assert "Restored 0 LLM calls" in result.output
    assert (root / "data" / "aipb.sqlite").exists()


def test_smoke_without_key_refuses(root):
    result = runner.invoke(app, ["smoke"])
    assert result.exit_code == 2
    assert "MissingApiKey" in result.output
    assert "llm_calls.jsonl" not in [p.name for p in (root / "data" / "ledger").iterdir()]


def test_smoke_offline_refuses_on_cache_miss(root, monkeypatch):
    monkeypatch.setenv("AIPAYBACK_OFFLINE", "true")
    result = runner.invoke(app, ["smoke"])
    assert result.exit_code == 2
    assert "OfflineCacheMiss" in result.output


def test_anthropic_key_warning_is_shown(root, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    result = runner.invoke(app, ["budget"])
    assert "ANTHROPIC_API_KEY is set" in result.output
