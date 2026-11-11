"""Stage 8: export what the site and newsletter may show to committed data files. $0.

- data/site/site_data.json   everything the static site renders (rebuilt each time)
- data/site/published_log.jsonl   append-only: when each promise's shown status first
  appeared or changed, and why (new evidence, or a correction after an error report)

Pending items carry the verified quote only: no explanation, evidence or numbers.
"""

from __future__ import annotations

import csv
import hashlib
import json
import sqlite3
from collections import Counter
from pathlib import Path

from aipb import jsonl
from aipb.budget.ledger import utc_now
from aipb.verify.gate import PENDING
from aipb.verify.numbers import NumberRow, deadline_end, fiscal_year_end

STATUS_ORDER = (
    "Delivered",
    "On track",
    "No evidence yet",
    "Walked back",
    "Walked back (silent)",
    PENDING,
)


def slug(ticker: str, first_stated: str, cluster_id: str) -> str:
    h = hashlib.sha256(cluster_id.encode()).hexdigest()[:6]
    return f"{ticker.lower()}-{first_stated}-{h}"


def _url(conn: sqlite3.Connection, passage_id: str) -> str:
    r = conn.execute(
        "SELECT d.url FROM passages p JOIN filing_docs d ON d.accession=p.accession "
        "AND d.role=p.doc_role WHERE p.passage_id=?",
        (passage_id,),
    ).fetchone()
    return r[0] if r else ""


def _with_markers(text: str, citations: list[dict]) -> tuple[str, list[dict]]:
    """Insert [n] markers where each cited sentence ends; return text and footnotes."""
    notes: list[dict] = []
    keyed: dict[tuple, int] = {}
    inserts: list[tuple[int, int]] = []
    for c in citations:
        k = (c["document_index"], c["start"], c["end"])
        if k not in keyed:
            keyed[k] = len(notes) + 1
            notes.append(
                {
                    "n": keyed[k],
                    "title": c["title"],
                    "cited_text": c["cited_text"],
                    "document_index": c["document_index"],
                }
            )
        inserts.append((min(c.get("after_char", len(text)), len(text)), keyed[k]))
    out = text
    for pos, n in sorted(set(inserts), reverse=True):
        out = out[:pos] + f"[{n}]" + out[pos:]
    return out, notes


def last_labels(log_path: Path) -> dict[str, dict]:
    latest: dict[str, dict] = {}
    for e in jsonl.read(log_path):
        latest[e["cluster_id"]] = e
    return latest


def closed_reports(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8", newline="") as fh:
        return {
            r["cluster_id"]: r.get("received", "")
            for r in csv.DictReader(fh)
            if r.get("status") == "closed"
        }


def build_site_data(conn: sqlite3.Connection, *, variant: str = "default") -> dict:
    companies = {r["cik"]: dict(r) for r in conn.execute("SELECT * FROM companies")}
    rows = conn.execute(
        "SELECT k.*, f.label, f.publishable, f.reason, f.status AS code FROM promise_clusters k "
        "LEFT JOIN final_status f ON f.cluster_id=k.cluster_id AND f.variant=k.variant "
        "WHERE k.variant=? ORDER BY k.cik, k.first_stated, k.cluster_id",
        (variant,),
    ).fetchall()
    promises = []
    for k in rows:
        co = companies[k["cik"]]
        p = conn.execute(
            "SELECT * FROM promises WHERE promise_id=?", (k["canonical_promise_id"],)
        ).fetchone()
        members = conn.execute(
            "SELECT p.passage_id, p.filing_date, f.form FROM promises p JOIN filings f "
            "ON f.accession=p.accession WHERE p.cluster_id=? AND p.variant=? "
            "ORDER BY p.filing_date",
            (k["cluster_id"], variant),
        ).fetchall()
        label = k["label"] or PENDING
        publishable = bool(k["publishable"])
        item = {
            "id": slug(co["ticker"], k["first_stated"], k["cluster_id"]),
            "cluster_id": k["cluster_id"],
            "ticker": co["ticker"],
            "company": co["name"],
            "quote": p["quote"],
            "first_stated": k["first_stated"],
            "form": members[0]["form"] if members else "",
            "filing_url": _url(conn, p["passage_id"]),
            "claim_type": p["claim_type"],
            "metric": p["metric"],
            "target_text": p["target_text"],
            "deadline_text": p["deadline_text"],
            "deadline_end": deadline_end(p["deadline_year"], fiscal_year_end(conn, k["cik"])),
            "restatements": [
                {"date": m["filing_date"], "form": m["form"], "url": _url(conn, m["passage_id"])}
                for m in members[1:]
            ],
            "status": label if publishable else PENDING,
            "status_code": k["code"] if publishable else "",
            "publishable": publishable,
            "pending_reason": "" if publishable else (k["reason"] or "not verified yet"),
        }
        if publishable:
            from aipb.stages.verify_runner import load_explanation

            e = load_explanation(conn, k["cluster_id"], variant)
            if e is None:  # the gate only publishes with a matching explanation
                raise RuntimeError(f"{k['cluster_id']}: publishable but no current explanation")
            text, notes = _with_markers(e["text"], json.loads(e["citations"]))
            ev_rows = conn.execute(
                "SELECT e.eid, e.passage_id, e.form, e.filing_date, s.text FROM evidence e "
                "JOIN passages s ON s.passage_id=e.passage_id WHERE e.cluster_id=? AND "
                "e.variant=? ORDER BY e.filing_date",
                (k["cluster_id"], variant),
            ).fetchall()
            docs = [p["passage_id"], *[r["passage_id"] for r in ev_rows]]
            for n in notes:
                idx = n["document_index"]
                n["url"] = _url(conn, docs[idx]) if idx < len(docs) else ""
            nums = conn.execute(
                "SELECT * FROM numbers WHERE cluster_id=? AND variant=? ORDER BY nid",
                (k["cluster_id"], variant),
            ).fetchall()
            item.update(
                explanation={"text": text, "citations": notes},
                evidence=[
                    {
                        "eid": r["eid"],
                        "form": r["form"],
                        "date": r["filing_date"],
                        "url": _url(conn, r["passage_id"]),
                        "excerpt": r["text"][:600],
                    }
                    for r in ev_rows
                ],
                numbers=[
                    {
                        "label": r["label"],
                        "tag": r["tag"],
                        "filed": r["filed"],
                        "display": NumberRow(
                            *[
                                r[c]
                                for c in (
                                    "nid",
                                    "label",
                                    "value",
                                    "unit",
                                    "kind",
                                    "tag",
                                    "fiscal_year",
                                    "period_start",
                                    "period_end",
                                    "accession",
                                    "filed",
                                )
                            ]
                        ).display(),
                    }
                    for r in nums
                ],
            )
        promises.append(item)
    hype = conn.execute(
        "SELECT COUNT(*) FROM promises WHERE variant=? AND kind='hype'", (variant,)
    ).fetchone()[0]
    statements = conn.execute(
        "SELECT COUNT(*) FROM promises WHERE variant=? AND kind='promise'", (variant,)
    ).fetchone()[0]
    by_co: dict[str, list] = {}
    for item in promises:
        by_co.setdefault(item["ticker"], []).append(item)
    company_list = []
    for c in sorted(companies.values(), key=lambda c: c["ticker"]):
        items = by_co.get(c["ticker"], [])
        company_list.append(
            {
                "ticker": c["ticker"],
                "name": c["name"],
                "sector": c["sector"],
                "promises": len(items),
                "counts": dict(Counter(i["status"] for i in items)),
            }
        )
    as_of = conn.execute("SELECT MAX(filing_date) FROM filings").fetchone()[0]
    return {
        "generated": utc_now(),
        "as_of": as_of,
        "status_order": list(STATUS_ORDER),
        "stats": {
            "companies": len(companies),
            "promises": len(promises),
            "published": sum(i["publishable"] for i in promises),
            "by_status": dict(Counter(i["status"] for i in promises)),
            "promise_statements": statements,
            "hype_statements": hype,
            "checkable_share": statements / (statements + hype) if statements + hype else None,
        },
        "companies": company_list,
        "promises": promises,
    }


def publish(
    conn: sqlite3.Connection, site_dir: Path, error_reports: Path, variant: str = "default"
) -> dict:
    data = build_site_data(conn, variant=variant)
    site_dir.mkdir(parents=True, exist_ok=True)
    log_path = site_dir / "published_log.jsonl"
    before = last_labels(log_path)
    corrected = closed_reports(error_reports)
    events = []
    for item in data["promises"]:
        prev = before.get(item["cluster_id"])
        if prev is not None and prev["label"] == item["status"]:
            continue
        if prev is None:
            reason = "first_publish"
        elif item["cluster_id"] in corrected and corrected[item["cluster_id"]] >= prev["ts"][:10]:
            reason = "correction"
        else:
            reason = "status_change"
        events.append(
            {
                "cluster_id": item["cluster_id"],
                "id": item["id"],
                "ticker": item["ticker"],
                "label": item["status"],
                "previous": prev["label"] if prev else None,
                "reason": reason,
                "ts": data["generated"],
            }
        )
    jsonl.append(log_path, events)
    (site_dir / "site_data.json").write_text(
        json.dumps(data, indent=1, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return {
        "promises": len(data["promises"]),
        "published": data["stats"]["published"],
        "events": len(events),
    }
