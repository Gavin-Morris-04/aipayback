"""Phase 4: publish -> site, and the newsletter with every safety rail. No network."""

import json

import pytest
from typer.testing import CliRunner

from aipb import cli
from aipb.newsletter import intro as nl_intro
from aipb.newsletter.services import Buttondown, GitHub
from tests.fake_services import FakeButtondown, FakeGitHub

runner = CliRunner()


def env(root, text):
    with (root / ".env").open("a", encoding="utf-8") as fh:
        fh.write(text)


def run(*args, code=0):
    result = runner.invoke(cli.app, list(args))
    assert result.exit_code == code, result.output
    return result


@pytest.fixture
def published(llm_project, fake_claude):
    for cmd in (("filter",), ("extract",), ("verify",), ("explain",)):
        run(*cmd, "-u", "test")
    run("publish")
    return llm_project


@pytest.fixture
def services(monkeypatch):
    bd, gh = FakeButtondown(), FakeGitHub()
    monkeypatch.setattr(
        cli,
        "_services",
        lambda ctx: (
            Buttondown("bd-test", transport=bd.transport()),
            GitHub("gh-test", "owner/repo", transport=gh.transport()),
        ),
    )
    return bd, gh


def test_publish_and_site(published):
    data = json.loads((published / "data" / "site" / "site_data.json").read_text(encoding="utf-8"))
    assert data["stats"]["promises"] >= 1
    pub = [p for p in data["promises"] if p["publishable"]]
    assert pub and all(p["explanation"]["citations"] for p in pub)
    pending = [p for p in data["promises"] if not p["publishable"]]
    assert all("explanation" not in p for p in pending)  # pending: the quote only
    log = (published / "data" / "site" / "published_log.jsonl").read_text(encoding="utf-8")
    assert "first_publish" in log
    run("publish")  # nothing changed: no new events
    assert (published / "data" / "site" / "published_log.jsonl").read_text(encoding="utf-8") == log

    out = run("site").output
    assert "Built" in out
    dist = published / "site" / "dist"
    home = (dist / "index.html").read_text(encoding="utf-8")
    assert "Not investment" in home and "Leaderboard" in home
    page = (dist / "promises" / f"{pub[0]['id']}.html").read_text(encoding="utf-8")
    assert "What later filings report" in page and "[1]" in page
    assert (dist / "companies" / "exmp.html").exists()
    sitemap = (dist / "sitemap.xml").read_text(encoding="utf-8")
    assert "promises/" in sitemap and "methodology.html" in sitemap


def test_fact_check():
    facts = {
        "as_of": "2025-07-30",
        "new_promises": 2,
        "status_changes": 0,
        "corrections": 0,
        "published_total": 2,
        "by_status": {"On track": 2},
        "items": [
            {
                "company": "Exemplar Industries",
                "ticker": "EXMP",
                "status": "On track",
                "first_stated": "2025-02-20",
            }
        ],
    }
    ok = "This month we track 2 new AI promises from Exemplar Industries (EXMP), both On track."
    assert nl_intro.fact_check(ok, facts, ["Exemplar Industries", "Other Corp"]) == []
    bad = "Other Corp (OTHR) delivered 3 promises and Exemplar failed one."
    problems = nl_intro.fact_check(bad, facts, ["Exemplar Industries", "Other Corp"])
    text = " ".join(problems)
    assert "number 3" in text and "OTHR" in text and "Other Corp" in text
    assert "Delivered" in text and "non-neutral" in text


def test_preview_renders_and_sends_nothing(published, services):
    bd, gh = services
    out = run("newsletter-preview", "--issue", "free-2026-12").output
    assert "items" in out
    html = (published / "exports" / "newsletter" / "free-2026-12.html").read_text(encoding="utf-8")
    assert "Not investment" in html and "<h2>New promises tracked</h2>" in html
    assert bd.emails == {} and gh.issues == {}


def test_stage_then_send_in_test_mode_then_live(published, services, monkeypatch):
    bd, gh = services
    env(published, "FOUNDER_EMAILS=a@example.com,b@example.com\nNEWSLETTER_AUTOSEND=true\n")
    run("newsletter-stage", "--issue", "free-2026-12")
    assert len(bd.emails) == 1 and bd.test_sends[0][1] == ["a@example.com", "b@example.com"]
    assert "Newsletter preview" in gh.issues[1]["title"] and "`hold`" in gh.issues[1]["body"]
    run("newsletter-stage", "--issue", "free-2026-12")  # idempotent: no second draft
    assert len(bd.emails) == 1

    out = run("newsletter-send", "--issue", "free-2026-12").output
    assert "sent_test" in out and "ramp-up" in out  # issue 1 of 2: founders only
    assert bd.sent == []
    run("newsletter-send", "--issue", "free-2026-12")  # idempotent
    assert bd.sent == []

    # Two test issues later, sends go to subscribers.
    log = published / "data" / "sends" / "newsletter_log.jsonl"
    lines = log.read_text(encoding="utf-8").splitlines()
    fake = json.loads(lines[-1])
    fake["issue_key"] = "free-2026-11"
    with log.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(fake) + "\n")
    site_log = published / "data" / "site" / "published_log.jsonl"
    site_log.write_text(
        site_log.read_text(encoding="utf-8").replace('"ts":"', '"ts":"9'), encoding="utf-8"
    )  # make the items newer than the last send
    run("newsletter-stage", "--issue", "free-2027-01")
    out = run("newsletter-send", "--issue", "free-2027-01").output
    assert "sent" in out and len(bd.sent) == 1


def test_hold_label_cancels(published, services):
    bd, gh = services
    env(published, "FOUNDER_EMAILS=a@example.com\nNEWSLETTER_AUTOSEND=true\n")
    run("newsletter-stage", "--issue", "free-2026-12")
    gh.add_label(1, "hold")
    out = run("newsletter-send", "--issue", "free-2026-12").output
    assert "cancelled" in out and bd.sent == []
    assert any("Cancelled" in c for c in gh.issues[1]["comments"])


def test_kill_switch_off_means_test_mode(published, services):
    bd, _gh = services
    env(published, "FOUNDER_EMAILS=a@example.com\n")
    run("newsletter-stage", "--issue", "free-2026-12")
    out = run("newsletter-send", "--issue", "free-2026-12").output
    assert "NEWSLETTER_AUTOSEND is off" in out and bd.sent == []


def test_edited_draft_or_unstaged_issue_fails_closed(published, services):
    bd, gh = services
    env(published, "FOUNDER_EMAILS=a@example.com\nNEWSLETTER_AUTOSEND=true\n")
    result = run("newsletter-send", "--issue", "free-2099-01", code=2)
    assert "never staged" in result.output
    assert any("Newsletter not sent" in i["title"] for i in gh.issues.values())
    run("newsletter-stage", "--issue", "free-2026-12")
    bd.emails["em_1"]["body"] += "\nAn edit nobody previewed."
    result = run("newsletter-send", "--issue", "free-2026-12", code=2)
    assert "edited after the preview" in result.output and bd.sent == []


def test_too_few_items_sends_nothing(published, services):
    bd, gh = services
    env(published, "FOUNDER_EMAILS=a@example.com\n")
    log = published / "data" / "sends" / "newsletter_log.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(
        json.dumps(
            {"issue_key": "free-2099-12", "event": "sent", "ts": "9999-01-01T00:00:00+00:00"}
        )
        + "\n",
        encoding="utf-8",
    )
    result = run("newsletter-stage", "--issue", "free-2100-01", code=2)
    assert "Nothing is sent" in result.output and bd.emails == {}
    assert any("Newsletter not sent" in i["title"] for i in gh.issues.values())
