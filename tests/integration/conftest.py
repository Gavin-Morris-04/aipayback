"""Shared fixtures for CLI integration tests: a project root wired to the fake SEC."""

import pytest

from aipb import cli
from aipb.context import AppContext
from aipb.sec.client import SecClient
from tests.fake_sec import FakeSec


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
