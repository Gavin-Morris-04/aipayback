"""Everything the judge sees about one promise, assembled by code (Tier 1 retrieval).

- The canonical promise and its restatements.
- Deadline facts: fiscal-year end, deadline end date, whether it has passed, whether the
  results for that period have been filed. "As of" is the company's latest filing date,
  not the wall clock, so the request (and its cache key) only changes when a new filing
  arrives.
- Evidence: FTS5 BM25 search over the company's LATER filings (top 8, at most 2 per
  filing), each with an id E1..E8.
- Numbers: the XBRL table for the claim type (N1..), computed in code.
- Silent walk-back facts: periodic filings after the deadline, and later passages that
  still mention the promise. The gate uses these, not the model's opinion.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field

from aipb.parse.passages import normalize_for_match
from aipb.stages.dedupe import words
from aipb.verify.numbers import EvidenceMap, NumberRow, deadline_end, fiscal_year_end, number_table

TOP_K = 8
PER_FILING = 2
MENTION_OVERLAP = 0.3


@dataclass
class EvidencePassage:
    eid: str
    passage_id: str
    form: str
    filing_date: str
    section: str
    text: str
    score: float


@dataclass
class VerifyContext:
    cluster_id: str
    variant: str
    cik: int
    ticker: str
    company: str
    promise: dict
    restatements: list[dict]
    promise_passage: str
    first_stated: str
    as_of: str
    fy_end: str
    deadline_end: str | None
    deadline_passed: bool
    deadline_results_filed: bool
    periodic_after_deadline: int
    mentions_after_deadline: int
    evidence: list[EvidencePassage] = field(default_factory=list)
    numbers: list[NumberRow] = field(default_factory=list)
    deadline_period_filed: bool = False  # a 10-K/10-Q covering the deadline period is in

    @property
    def silent_walkback_possible(self) -> bool:
        """Nick's final rubric (section 4), the parts code can check:
        (a) the deadline has passed; (b) at least two later 10-K/10-Qs, one of them the
        filing that covers the deadline period; (c) no later passage, earnings releases
        included, still mentions it. Specificity-1 promises have no deadline and can never
        be silent. Condition (d), a named program, is the judge's call.
        """
        return (
            self.deadline_passed
            and self.periodic_after_deadline >= 2
            and self.deadline_period_filed
            and self.mentions_after_deadline == 0
            and self.promise.get("specificity") != 1
        )

    def evidence_ids(self) -> set[str]:
        return {e.eid for e in self.evidence}

    def number_ids(self) -> set[str]:
        return {n.nid for n in self.numbers}


def query_terms(promise: dict, claim_spec: dict) -> list[str]:
    terms: list[str] = []
    for w in sorted(words(promise["quote"]) | words(promise.get("metric")), key=str):
        if len(w) >= 4 and not re.fullmatch(r"[\d$%.,]+", w):
            terms.append(w)
    terms += claim_spec.get("search_terms", [])
    seen, out = set(), []
    for t in terms:
        t = t.replace('"', "").strip()
        if t and t.lower() not in seen:
            seen.add(t.lower())
            out.append(t)
    return out[:24]


def fts_query(terms: list[str]) -> str:
    return " OR ".join(f'"{t}"' for t in terms)


def search(
    conn: sqlite3.Connection,
    cik: int,
    terms: list[str],
    *,
    after: str,
    exclude_accession: str,
    limit: int = 60,
) -> list[sqlite3.Row]:
    if not terms:
        return []
    return conn.execute(
        """
        SELECT p.passage_id, p.form, p.filing_date, p.section, p.text, p.text_sha256,
               p.accession, bm25(passages_fts) AS score
        FROM passages_fts JOIN passages p ON p.passage_id = passages_fts.passage_id
        WHERE passages_fts MATCH ? AND p.cik = ? AND p.filing_date > ? AND p.accession != ?
        ORDER BY score LIMIT ?
        """,
        (fts_query(terms), cik, after, exclude_accession, limit),
    ).fetchall()


def pick_evidence(rows: list[sqlite3.Row], k: int = TOP_K) -> list[EvidencePassage]:
    out: list[EvidencePassage] = []
    per_filing: dict[str, int] = {}
    seen_text: set[str] = set()
    for r in rows:
        if r["text_sha256"] in seen_text or per_filing.get(r["accession"], 0) >= PER_FILING:
            continue
        seen_text.add(r["text_sha256"])
        per_filing[r["accession"]] = per_filing.get(r["accession"], 0) + 1
        out.append(
            EvidencePassage(
                f"E{len(out) + 1}",
                r["passage_id"],
                r["form"],
                r["filing_date"],
                r["section"],
                r["text"],
                r["score"],
            )
        )
        if len(out) == k:
            break
    out.sort(key=lambda e: (e.filing_date, e.passage_id))
    for i, e in enumerate(out, start=1):
        e.eid = f"E{i}"
    return out


def mentions(promise: dict, text: str) -> bool:
    key = {w for w in words(promise["quote"]) if len(w) >= 4}
    if not key:
        return False
    return len(key & words(text)) / len(key) >= MENTION_OVERLAP


def build_context(
    conn: sqlite3.Connection, em: EvidenceMap, cluster_id: str, variant: str = "default"
) -> VerifyContext:
    cl = conn.execute(
        "SELECT * FROM promise_clusters WHERE cluster_id=? AND variant=?", (cluster_id, variant)
    ).fetchone()
    members = [
        dict(r)
        for r in conn.execute(
            "SELECT * FROM promises WHERE cluster_id=? AND variant=? "
            "ORDER BY filing_date, promise_id",
            (cluster_id, variant),
        )
    ]
    promise = next(m for m in members if m["promise_id"] == cl["canonical_promise_id"])
    co = conn.execute("SELECT ticker, name FROM companies WHERE cik=?", (cl["cik"],)).fetchone()
    passage = conn.execute(
        "SELECT text FROM passages WHERE passage_id=?", (promise["passage_id"],)
    ).fetchone()[0]
    as_of = conn.execute(
        "SELECT MAX(filing_date) FROM filings WHERE cik=?", (cl["cik"],)
    ).fetchone()[0]
    fy_end = fiscal_year_end(conn, cl["cik"])
    years = [m["deadline_year"] for m in members if m["deadline_year"]]
    d_end = deadline_end(max(years) if years else None, fy_end)
    passed = bool(d_end and as_of > d_end)
    periodic_after = 0
    results_filed = period_filed = False
    if d_end:
        periodic_after = conn.execute(
            "SELECT COUNT(*) FROM filings WHERE cik=? AND form IN ('10-K','10-Q') "
            "AND filing_date > ?",
            (cl["cik"], d_end),
        ).fetchone()[0]
        results_filed = bool(
            conn.execute(
                "SELECT 1 FROM filings WHERE cik=? AND report_date >= ? LIMIT 1", (cl["cik"], d_end)
            ).fetchone()
        )
        # The 10-K (or 10-Q) whose period ends at the deadline. Fiscal years that end on
        # the last Saturday of a month can end a few days before or after the nominal date.
        period_filed = bool(
            conn.execute(
                "SELECT 1 FROM filings WHERE cik=? AND form IN ('10-K','10-Q') AND "
                "report_date BETWEEN date(?, '-10 days') AND date(?, '+10 days') LIMIT 1",
                (cl["cik"], d_end, d_end),
            ).fetchone()
        )
    spec = em.for_claim(promise["claim_type"])
    terms = query_terms(promise, spec)
    rows = search(
        conn, cl["cik"], terms, after=cl["first_stated"], exclude_accession=promise["accession"]
    )
    evidence = pick_evidence(rows)
    mentions_after = 0
    if d_end:
        later = search(conn, cl["cik"], terms, after=d_end, exclude_accession="", limit=200)
        mentions_after = sum(1 for r in later if mentions(promise, r["text"]))
    from_year = int(cl["first_stated"][:4]) - 1
    numbers = number_table(conn, em, cl["cik"], promise["claim_type"], from_year)
    return VerifyContext(
        cluster_id=cluster_id,
        variant=variant,
        cik=cl["cik"],
        ticker=co["ticker"],
        company=co["name"],
        promise=promise,
        restatements=members,
        promise_passage=passage,
        first_stated=cl["first_stated"],
        as_of=as_of,
        fy_end=fy_end,
        deadline_end=d_end,
        deadline_passed=passed,
        deadline_results_filed=results_filed,
        periodic_after_deadline=periodic_after,
        mentions_after_deadline=mentions_after,
        evidence=evidence,
        numbers=numbers,
        deadline_period_filed=period_filed,
    )


def render(ctx: VerifyContext) -> str:
    """The judge's user message: promise, facts, numbers, evidence. Deterministic."""
    p = ctx.promise
    fields = {
        k: p.get(k)
        for k in (
            "claim_type",
            "metric",
            "target_text",
            "target_value",
            "target_unit",
            "baseline",
            "deadline_text",
            "deadline_year",
            "deadline_precision",
            "specificity",
        )
    }
    lines = [
        f"Company: {ctx.company} ({ctx.ticker})",
        f"Information available as of: {ctx.as_of} (latest filing in our data)",
        "",
        "<promise>",
        f"Quote: {normalize_for_match(p['quote'])}",
        f"First stated: {ctx.first_stated}; restated in "
        f"{max(0, len(ctx.restatements) - 1)} later filing(s)",
        "Fields: " + "; ".join(f"{k}={v}" for k, v in fields.items() if v is not None),
        "</promise>",
        "",
        "<facts computed by code>",
        f"Fiscal year ends: {ctx.fy_end}",
        f"Deadline period ends: {ctx.deadline_end or 'no deadline stated'}",
        f"Deadline passed as of {ctx.as_of}: {'yes' if ctx.deadline_passed else 'no'}",
        f"Results for the deadline period filed: {'yes' if ctx.deadline_results_filed else 'no'}",
        f"10-K/10-Q covering the deadline period filed: "
        f"{'yes' if ctx.deadline_period_filed else 'no'}",
        f"10-K/10-Q filings after the deadline: {ctx.periodic_after_deadline}",
        f"Later passages that still mention this promise: {ctx.mentions_after_deadline}",
        "</facts computed by code>",
        "",
        "<reported numbers>",
    ]
    if ctx.numbers:
        lines += [
            f"{n.nid}: {n.label}: {n.display()} ({n.tag}, filed {n.filed})" for n in ctx.numbers
        ]
    else:
        lines.append("(none: this claim type has no reported XBRL measure)")
    lines += ["</reported numbers>", ""]
    for e in ctx.evidence:
        lines += [
            f'<evidence id="{e.eid}" form="{e.form}" filed="{e.filing_date}">',
            e.text,
            "</evidence>",
            "",
        ]
    if not ctx.evidence:
        lines.append("(no later passages matched this promise)")
    return "\n".join(lines).strip()
