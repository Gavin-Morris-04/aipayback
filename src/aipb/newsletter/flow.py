"""Stage and send an issue with every safety rail from the brief (section 9.1).

stage (the day before):  build the issue -> Buttondown draft -> test copy to the founders
                         -> GitHub preview issue ("add the label `hold` to cancel")
send (24 hours later):   idempotent -> kill switch -> ramp-up (first issues founders-only)
                         -> no `hold` label -> the draft is unchanged -> send
Any failure: nothing is sent, the reason is logged and (in Actions) opened as an issue.
Every step is logged to data/sends/newsletter_log.jsonl (committed).
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass
from pathlib import Path

from aipb import jsonl
from aipb.budget.ledger import utc_now
from aipb.newsletter.issue import Issue, body_sha
from aipb.newsletter.services import Buttondown, GitHub, ServiceError


class SendBlocked(RuntimeError):
    """A rail stopped the send. Not an error in the system: the rail worked."""


@dataclass
class Rails:
    autosend: bool
    ramp_up_test_issues: int
    hold_label: str
    founders: list[str]


def events(log: Path, key: str | None = None) -> list[dict]:
    return [e for e in jsonl.read(log) if key is None or e["issue_key"] == key]


def log_event(log: Path, key: str, event: str, **fields) -> dict:
    rec = {"issue_key": key, "event": event, "ts": utc_now(), **fields}
    jsonl.append(log, [rec])
    return rec


def stage(
    issue: Issue, body: str, log: Path, bd: Buttondown, gh: GitHub, rails: Rails, send_after: str
) -> dict:
    done = [e for e in events(log, issue.key) if e["event"] in ("sent", "sent_test")]
    if done:
        raise SendBlocked(f"{issue.key} was already sent ({done[-1]['event']}); not staging again.")
    staged = [e for e in events(log, issue.key) if e["event"] == "staged"]
    if staged:
        return staged[-1]  # idempotent: one draft per issue key
    sha = body_sha(body)
    email = bd.create_draft(issue.subject, body, {"issue_key": issue.key, "body_sha256": sha})
    bd.send_test(email["id"], rails.founders)
    preview = (
        f"**Newsletter preview: `{issue.key}`**\n\nIt sends automatically after {send_after} "
        f"unless someone adds the label `{rails.hold_label}` to this issue. Nothing else is "
        "needed. A test copy went to the founders.\n\n"
        f"Intro source: {issue.intro_source}. Items: {len(issue.item_ids)}.\n\n---\n\n{body}"
    )
    number = gh.open_issue(f"Newsletter preview: {issue.key}", preview)
    return log_event(
        log,
        issue.key,
        "staged",
        email_id=email["id"],
        body_sha256=sha,
        github_issue=number,
        items=issue.item_ids,
        intro_source=issue.intro_source,
        notes=issue.notes,
    )


def send(key: str, log: Path, bd: Buttondown, gh: GitHub, rails: Rails) -> dict:
    evs = events(log, key)
    if done := [e for e in evs if e["event"] in ("sent", "sent_test")]:
        return done[-1]  # idempotent: never send twice
    staged = [e for e in evs if e["event"] == "staged"]
    if not staged:
        raise SendBlocked(f"{key} was never staged (no preview, no veto window). Not sending.")
    st = staged[-1]
    if [e for e in evs if e["event"] == "cancelled" and e["ts"] >= st["ts"]]:
        raise SendBlocked(f"{key} was cancelled.")
    try:
        labels = gh.labels(st["github_issue"])
    except ServiceError as exc:
        raise SendBlocked(f"Couldn't check the preview issue for a hold label ({exc}).") from exc
    if rails.hold_label in labels:
        log_event(log, key, "cancelled", reason=f"'{rails.hold_label}' label")
        gh.comment(st["github_issue"], f"Cancelled: the `{rails.hold_label}` label is set.")
        raise SendBlocked(f"{key}: cancelled by the '{rails.hold_label}' label.")
    email = bd.get(st["email_id"])
    if (email.get("metadata") or {}).get("body_sha256") != st["body_sha256"]:
        raise SendBlocked(f"{key}: the Buttondown draft no longer matches what was previewed.")
    if body_sha(email.get("body", "")) != st["body_sha256"]:
        raise SendBlocked(f"{key}: the draft's body was edited after the preview.")
    if email.get("status") != "draft":
        raise SendBlocked(f"{key}: the email's status is {email.get('status')!r}, not draft.")
    prior = [e for e in events(log) if e["event"] in ("sent", "sent_test")]
    test_mode = (not rails.autosend) or len(prior) < rails.ramp_up_test_issues
    if test_mode:
        why = (
            "NEWSLETTER_AUTOSEND is off"
            if not rails.autosend
            else f"ramp-up: issue {len(prior) + 1} of {rails.ramp_up_test_issues}"
        )
        rec = log_event(log, key, "sent_test", email_id=st["email_id"], reason=why)
        gh.comment(
            st["github_issue"], f"Founders-only (test mode: {why}). Not sent to subscribers."
        )
    else:
        bd.send(st["email_id"])
        rec = log_event(log, key, "sent", email_id=st["email_id"])
        gh.comment(st["github_issue"], "Sent to subscribers.")
    gh.close(st["github_issue"])
    return rec


def report_failure(gh: GitHub | None, key: str, reason: str, log: Path) -> None:
    log_event(log, key, "failed", reason=reason)
    if gh is not None:
        with contextlib.suppress(ServiceError):
            gh.open_issue(f"Newsletter not sent: {key}", f"Nothing was sent.\n\nReason: {reason}")
