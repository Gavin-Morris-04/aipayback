"""Build one newsletter issue from published data. Templates carry the content.

Items come only from data/site (what the gate already allowed): promises first published
since the last sent issue, status changes, and corrections. One data-backed stat is
computed by code. The LLM writes only the intro (intro.py), from these same facts.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

from aipb import jsonl
from aipb.verify.gate import PENDING

FOOTER = (
    "Informational only. Not investment, legal or financial advice. This issue was generated "
    "automatically from SEC filings and checked by automated tests. Statuses describe what "
    "companies' later filings report; they are not judgments of management."
)


class IssueError(RuntimeError):
    """The issue can't be sent as is. Fail closed: send nothing."""


@dataclass
class Issue:
    key: str
    subject: str
    new: list[dict]
    changed: list[dict]
    corrections: list[dict]
    stat: str
    facts: dict
    intro: str = ""
    intro_source: str = "template"  # template | llm
    notes: list[str] = field(default_factory=list)

    @property
    def item_ids(self) -> list[str]:
        return [i["id"] for i in self.new + self.changed + self.corrections]

    def markdown(self, site_url: str) -> str:
        def line(i: dict) -> str:
            return (
                f"- **{i['company']} ({i['ticker']})**: {i['status']}. "
                f"“{i['quote']}” ({i['form']} filed {i['first_stated']}) "
                f"[Sources]({site_url}/promises/{i['id']}.html)"
            )

        parts = [self.intro, ""]
        if self.new:
            parts += ["## New promises tracked", "", *[line(i) for i in self.new], ""]
        if self.changed:
            parts += ["## Status changes", ""]
            parts += [line(i) + f" Previously: {i['previous']}." for i in self.changed]
            parts.append("")
        if self.corrections:
            parts += [
                "## Corrections",
                "",
                "After a reader report and a recheck, these statuses changed:",
                "",
            ]
            parts += [line(i) + f" Previously shown as: {i['previous']}." for i in self.corrections]
            parts.append("")
        parts += [
            "## One number",
            "",
            self.stat,
            "",
            f"All scorecards and the methodology: {site_url}",
            "",
            "---",
            "",
            FOOTER,
        ]
        return "\n".join(parts).strip() + "\n"


def body_sha(body: str) -> str:
    """Hash of the body with line endings and trailing whitespace normalized, so a harmless
    reformat by the platform doesn't block a send, but any real edit does."""
    lines = body.replace("\r\n", "\n").strip().split("\n")
    norm = "\n".join(line.rstrip() for line in lines)
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()


def last_sent_ts(log_path: Path) -> str:
    ts = ""
    for e in jsonl.read(log_path):
        if e.get("event") in ("sent", "sent_test"):
            ts = max(ts, e["ts"])
    return ts


def build_issue(site_dir: Path, sends_log: Path, key: str, *, name: str, min_items: int) -> Issue:
    data_path = site_dir / "site_data.json"
    if not data_path.exists():
        raise IssueError("No published data (data/site/site_data.json). Run aipb publish.")
    data = json.loads(data_path.read_text(encoding="utf-8"))
    by_cluster = {p["cluster_id"]: p for p in data["promises"]}
    since = last_sent_ts(sends_log)
    new, changed, corrections = [], [], []
    seen: set[str] = set()
    for e in reversed(list(jsonl.read(site_dir / "published_log.jsonl"))):
        if e["ts"] <= since or e["cluster_id"] in seen:
            continue
        seen.add(e["cluster_id"])  # the latest event per promise wins
        item = by_cluster.get(e["cluster_id"])
        if item is None or not item["publishable"] or item["status"] != e["label"]:
            continue  # only items that are still published, with the status we'd show
        row = {**item, "previous": e.get("previous")}
        if e["reason"] == "correction":
            corrections.append(row)
        elif e["reason"] == "first_publish" or e.get("previous") == PENDING:
            new.append(row)
        else:
            changed.append(row)
    for group in (new, changed, corrections):
        group.sort(key=lambda i: (i["ticker"], i["first_stated"]))
    total = len(new) + len(changed) + len(corrections)
    if total < min_items:
        raise IssueError(
            f"Only {total} new or changed items since the last issue (minimum "
            f"{min_items}). Nothing is sent this month."
        )
    stats = data["stats"]
    by_status = stats.get("by_status", {})
    stat = (
        f"Of the {stats['published']} AI promises with a published status, "
        f"{by_status.get('Delivered', 0)} are Delivered, {by_status.get('On track', 0)} "
        f"On track and {by_status.get('No evidence yet', 0)} show No evidence yet "
        f"(data as of {data['as_of']})."
    )
    facts = {
        "issue": key,
        "as_of": data["as_of"],
        "new_promises": len(new),
        "status_changes": len(changed),
        "corrections": len(corrections),
        "published_total": stats["published"],
        "by_status": by_status,
        "items": [
            {
                "company": i["company"],
                "ticker": i["ticker"],
                "status": i["status"],
                "first_stated": i["first_stated"],
            }
            for i in new + changed + corrections
        ],
    }
    month = key.split("-", 1)[1] if "-" in key else key
    return Issue(
        key=key,
        subject=f"{name}: {month}",
        new=new,
        changed=changed,
        corrections=corrections,
        stat=stat,
        facts=facts,
    )


def template_intro(issue: Issue) -> str:
    f = issue.facts
    bits = [
        f"{f['new_promises']} new AI promise{'s' if f['new_promises'] != 1 else ''}",
        f"{f['status_changes']} status change{'s' if f['status_changes'] != 1 else ''}",
    ]
    if f["corrections"]:
        bits.append(f"{f['corrections']} correction{'s' if f['corrections'] != 1 else ''}")
    return (
        f"This month: {', '.join(bits)}, based on SEC filings through {f['as_of']}. "
        "Every status below links to the filing sentences it relies on."
    )
