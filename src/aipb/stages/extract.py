"""Stage 4: Haiku extracts promise and hype statements (structured outputs), code checks quotes.

Every quote must appear verbatim in its passage (after the documented normalization). A
response with a failing quote gets ONE retry that names the failing quotes; any quote
that still fails is dropped and logged. Nothing unverified is ever stored.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field

from aipb.labeling.schema import CLAIM_TYPES, section_name
from aipb.llm.client import LLMResult, Request
from aipb.llm.params import OutputError, Prompt, build_params, nullable, obj, parse_json
from aipb.parse.passages import locate_quote
from aipb.stages.filter import routed_to_extraction

STAGE = "extract"
UNITS = ["USD", "percent", "percentage_points", "count", "other"]
PRECISION = ["day", "month", "quarter", "half", "year", "none"]

STATEMENT = obj(
    {
        "quote": {"type": "string"},
        "kind": {"type": "string", "enum": ["promise", "hype"]},
        "claim_type": {"type": "string", "enum": list(CLAIM_TYPES)},
        "metric": nullable({"type": "string"}),
        "target_text": nullable({"type": "string"}),
        "target_value": nullable({"type": "number"}),
        "target_unit": nullable({"type": "string", "enum": UNITS}),
        "baseline": nullable({"type": "string"}),
        "deadline_text": nullable({"type": "string"}),
        "deadline_year": nullable({"type": "integer"}),
        "deadline_precision": {"type": "string", "enum": PRECISION},
        "specificity": {"type": "integer", "enum": [1, 2, 3]},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
    }
)
SCHEMA = obj({"statements": {"type": "array", "items": STATEMENT}})


@dataclass
class Verified:
    statement: dict
    start: int
    end: int
    quote: str  # the filing's own characters


@dataclass
class ExtractStats:
    passages: int = 0
    statements: int = 0
    promises: int = 0
    hype: int = 0
    retried: int = 0
    dropped_quotes: int = 0
    errors: list[str] = field(default_factory=list)


def candidates(
    conn: sqlite3.Connection,
    cfg_filter: dict,
    ciks: list[int],
    *,
    variant: str = "default",
    filter_variant: str = "default",
    passage_ids: set[str] | None = None,
) -> list[sqlite3.Row]:
    marks = ",".join("?" * len(ciks))
    rows = conn.execute(
        f"""
        SELECT p.passage_id, p.cik, p.accession, p.form, p.filing_date, p.section, p.text,
               c.ticker, c.name, k.label, k.confidence
        FROM passages p
        JOIN companies c ON c.cik = p.cik
        JOIN classifications k ON k.passage_id = p.passage_id AND k.variant = ?
        WHERE p.cik IN ({marks})
        ORDER BY p.cik, p.filing_date, p.accession, p.char_start
        """,
        (filter_variant, *ciks),
    ).fetchall()
    rows = [r for r in rows if routed_to_extraction(cfg_filter, r["label"], r["confidence"])]
    if passage_ids is not None:
        rows = [r for r in rows if r["passage_id"] in passage_ids]
    return rows


def user_content(r: sqlite3.Row) -> str:
    return (
        f"Company: {r['name']} ({r['ticker']})\n"
        f"Filing: {r['form']} filed {r['filing_date']}\n"
        f"Section: {section_name(r['section'])}\n\n"
        f"<passage>\n{r['text']}\n</passage>"
    )


def build_request(r: sqlite3.Row, cfg: dict, prompt: Prompt) -> Request:
    params = build_params(cfg, prompt, user_content(r), SCHEMA)
    return Request(key=r["passage_id"], params=params, shard=str(r["cik"]))


def verify(passage_text: str, statements: list[dict]) -> tuple[list[Verified], list[dict]]:
    good: list[Verified] = []
    bad: list[dict] = []
    for st in statements:
        span = locate_quote(passage_text, st.get("quote", ""))
        if span is None:
            bad.append(st)
        else:
            good.append(Verified(st, span[0], span[1], passage_text[span[0] : span[1]]))
    return good, bad


def retry_request(first: Request, first_result: LLMResult, bad: list[dict]) -> Request:
    """Same request plus the model's answer and a correction turn naming the bad quotes."""
    failing = "\n".join(f"- {json.dumps(b.get('quote', ''), ensure_ascii=False)}" for b in bad)
    params = json.loads(json.dumps(first.params))
    params["messages"] = [
        *params["messages"],
        {"role": "assistant", "content": first_result.text()},
        {
            "role": "user",
            "content": (
                "These quotes are not exact substrings of the passage:\n"
                f"{failing}\n\n"
                "Return the complete list of statements again. Copy every quote character "
                "for character from the passage as one continuous piece of text; drop a "
                "statement if you cannot quote it exactly."
            ),
        },
    ]
    return Request(key=first.key, params=params, shard=first.shard)


def statements_of(result: LLMResult) -> list[dict]:
    data = parse_json(result)
    sts = data.get("statements", [])
    return [s for s in sts if isinstance(s, dict)]


def store_passage(
    conn: sqlite3.Connection,
    r: sqlite3.Row,
    verified: list[Verified],
    *,
    variant: str,
    prompt_id: str,
    model: str,
    retried: bool,
    dropped: int,
    status: str,
    detail: str = "",
) -> None:
    pid = r["passage_id"]
    with conn:
        conn.execute("DELETE FROM promises WHERE passage_id=? AND variant=?", (pid, variant))
        for n, v in enumerate(verified, start=1):
            st = v.statement
            conn.execute(
                "INSERT INTO promises (promise_id, variant, passage_id, cik, accession, "
                "filing_date, seq, quote, quote_start, quote_end, kind, claim_type, metric, "
                "target_text, target_value, target_unit, baseline, deadline_text, "
                "deadline_year, deadline_precision, specificity, confidence, prompt_version, "
                "model, retried) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    f"{variant}:{pid}:s{n}", variant, pid, r["cik"], r["accession"],
                    r["filing_date"], n, v.quote, v.start, v.end, st["kind"],
                    st["claim_type"], st.get("metric"), st.get("target_text"),
                    st.get("target_value"), st.get("target_unit"), st.get("baseline"),
                    st.get("deadline_text"), st.get("deadline_year"),
                    st.get("deadline_precision"), st.get("specificity"), st.get("confidence"),
                    prompt_id, model, int(retried),
                ),
            )  # fmt: skip
        conn.execute(
            "INSERT INTO extraction_log VALUES (?,?,?,?,?,?) ON CONFLICT(passage_id, variant) "
            "DO UPDATE SET status=excluded.status, n_statements=excluded.n_statements, "
            "n_dropped=excluded.n_dropped, detail=excluded.detail",
            (pid, variant, status, len(verified), dropped, detail),
        )


def first_pass(
    rows: list[sqlite3.Row], results: dict[str, LLMResult]
) -> tuple[dict[str, list[Verified]], dict[str, list[dict]], dict[str, str]]:
    """Per passage: verified statements, failing statements, and errors."""
    good: dict[str, list[Verified]] = {}
    bad: dict[str, list[dict]] = {}
    errors: dict[str, str] = {}
    for r in rows:
        pid = r["passage_id"]
        try:
            sts = statements_of(results[pid])
        except (OutputError, KeyError) as exc:
            errors[pid] = str(exc)
            continue
        good[pid], bad[pid] = verify(r["text"], sts)
    return good, bad, errors
