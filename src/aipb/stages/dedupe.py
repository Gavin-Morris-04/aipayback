"""Stage 5: merge restatements of the same promise into clusters. Plain code, $0.

Two promise statements from the same company are the same promise when they have the
same claim type and either (a) their quotes are similar (word Jaccard >= 0.5), or (b) they
name the same metric with the same target and deadline. The earliest statement is
canonical, and cluster ids derive from it, so they stay stable as new filings arrive.

A statement with the same metric but a DIFFERENT target or deadline is never merged: it
starts its own cluster and records `related_cluster_id`. A raised or lowered target is
exactly what verification needs to see.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field

from aipb.parse.passages import normalize_for_match

SIMILARITY = 0.5
_STOP = frozenset(
    [
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "for",
        "from",
        "in",
        "is",
        "it",
        "its",
        "of",
        "on",
        "or",
        "our",
        "that",
        "the",
        "this",
        "to",
        "we",
        "will",
        "with",
        "which",
        "over",
        "through",
        "about",
    ]
)


def words(text: str | None) -> frozenset[str]:
    toks = re.findall(r"[a-z0-9$%.]+", normalize_for_match(text or "").lower())
    return frozenset(t.strip(".") for t in toks if t.strip(".") and t not in _STOP)


def jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


@dataclass
class _Cluster:
    cluster_id: str
    claim_type: str
    canonical: sqlite3.Row
    members: list[sqlite3.Row] = field(default_factory=list)
    related: str | None = None


def _same_metric(a: sqlite3.Row, b: sqlite3.Row) -> bool:
    return bool(a["metric"]) and jaccard(words(a["metric"]), words(b["metric"])) >= 0.6


def _same_target(a: sqlite3.Row, b: sqlite3.Row) -> bool:
    return a["target_value"] == b["target_value"] and a["deadline_year"] == b["deadline_year"]


def cluster_company(rows: list[sqlite3.Row]) -> list[_Cluster]:
    clusters: list[_Cluster] = []
    for r in rows:
        best = None
        related = None
        for c in clusters:
            if c.claim_type != r["claim_type"]:
                continue
            canon = c.canonical
            same_metric = _same_metric(canon, r)
            if same_metric and not _same_target(canon, r):
                related = related or c.cluster_id  # a changed target: never merged
                continue
            if jaccard(words(canon["quote"]), words(r["quote"])) >= SIMILARITY or (
                same_metric and _same_target(canon, r)
            ):
                best = c
                break
        if best is None:
            variant, pid = r["promise_id"].split(":", 1)
            cid = f"c-{pid}" if variant == "default" else f"c-{variant}-{pid}"
            best = _Cluster(cid, r["claim_type"], r, related=related)
            clusters.append(best)
        best.members.append(r)
    return clusters


def dedupe(conn: sqlite3.Connection, variant: str = "default") -> dict[str, int]:
    rows = conn.execute(
        "SELECT * FROM promises WHERE variant=? AND kind='promise' "
        "ORDER BY cik, filing_date, accession, passage_id, seq",
        (variant,),
    ).fetchall()
    by_cik: dict[int, list[sqlite3.Row]] = {}
    for r in rows:
        by_cik.setdefault(r["cik"], []).append(r)
    n_clusters = 0
    with conn:
        conn.execute("DELETE FROM promise_clusters WHERE variant=?", (variant,))
        conn.execute("UPDATE promises SET cluster_id=NULL WHERE variant=?", (variant,))
        for cik, items in by_cik.items():
            for c in cluster_company(items):
                n_clusters += 1
                dates = [m["filing_date"] for m in c.members]
                conn.execute(
                    "INSERT INTO promise_clusters VALUES (?,?,?,?,?,?,?,?,?)",
                    (
                        c.cluster_id, variant, cik, c.claim_type, c.canonical["promise_id"],
                        min(dates), max(dates), len(c.members), c.related,
                    ),
                )  # fmt: skip
                conn.executemany(
                    "UPDATE promises SET cluster_id=? WHERE promise_id=?",
                    [(c.cluster_id, m["promise_id"]) for m in c.members],
                )
    return {"statements": len(rows), "clusters": n_clusters}
