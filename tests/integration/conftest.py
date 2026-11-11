"""Shared fixtures for CLI integration tests: a project root wired to the fake SEC."""

import pytest

from aipb import cli
from aipb.context import AppContext
from aipb.sec.client import SecClient
from tests.fake_claude import FakeClaude, factory
from tests.fake_sec import FakeSec


@pytest.fixture
def fake_sec():
    return FakeSec()


@pytest.fixture
def fake_claude():
    return FakeClaude()


@pytest.fixture
def project(root, monkeypatch, fake_sec, fake_claude):
    (root / "config" / "universe" / "test.csv").write_text(
        "ticker,name,sector\nEXMP,Exemplar Industries,Industrials\n", encoding="utf-8"
    )
    (root / ".env").write_text("SEC_CONTACT_EMAIL=ops@example.com\n", encoding="utf-8")

    def make_ctx() -> AppContext:
        ctx = AppContext.create(sdk_factory=factory(fake_claude))
        ctx.__dict__["sec"] = SecClient(
            ctx.settings.sec_contact_email,
            offline=ctx.settings.aipayback_offline,
            transport=fake_sec.transport(),
            sleep=lambda s: None,
        )
        return ctx

    monkeypatch.setattr(cli, "_ctx", make_ctx)
    return root


@pytest.fixture
def llm_project(project):
    """A project with a (fake) app key in .env and the EXMP corpus ingested and filtered."""
    from typer.testing import CliRunner

    with (project / ".env").open("a", encoding="utf-8") as fh:
        fh.write("AIPAYBACK_API_KEY=test-key-not-real\n")
    runner = CliRunner()
    for cmd in ("ingest", "parse", "prefilter"):
        result = runner.invoke(cli.app, [cmd, "-u", "test"])
        assert result.exit_code == 0, result.output
    return project
