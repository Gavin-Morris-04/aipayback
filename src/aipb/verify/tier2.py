"""Tier 2: a capped tool-using agent for escalations and the second check on walk-backs.

A manual loop (not the SDK tool runner) so every turn goes through the budget-guarded,
cached gateway and is logged. Caps: MAX_TURNS turns and MAX_TOKENS tokens per promise,
plus the run's dollar reservation. Tools are strict; tool_choice stays "auto" and the
prompt asks for exactly one submit_verdict call. No submit_verdict -> "inconclusive",
which is never published.

Every turn's request is deterministic given the previous answers, so a replay of the
same loop is served entirely from the output cache ($0).
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field

from aipb.budget.guard import Run
from aipb.llm.client import LLMClient
from aipb.llm.params import Prompt, thinking_params
from aipb.verify.calc import CalcError, calculate
from aipb.verify.context import EvidencePassage, VerifyContext, fts_query, render
from aipb.verify.numbers import EvidenceMap, NumberRow, annual_series
from aipb.verify.tier1 import VERDICT_SCHEMA, Verdict, validate

STAGE = "verify_t2"
MAX_TURNS = 8
MAX_TOKENS = 60_000
_BLOCK_KEYS = {
    "text": ("type", "text"),
    "tool_use": ("type", "id", "name", "input"),
    "thinking": ("type", "thinking", "signature"),
    "redacted_thinking": ("type", "data"),
}


def tools(em: EvidenceMap) -> list[dict]:
    def tool(name: str, description: str, props: dict) -> dict:
        return {
            "name": name,
            "description": description,
            "strict": True,
            "input_schema": {
                "type": "object",
                "properties": props,
                "required": list(props),
                "additionalProperties": False,
            },
        }

    return [
        tool(
            "search_company_filings",
            "Full-text search of this company's filings made after the promise. Returns up "
            "to 5 passages (id, form, date, text). Use specific words: the program name, "
            "the metric, the target.",
            {"query": {"type": "string"}},
        ),
        tool(
            "get_passage",
            "The full text of one passage by its id (E-number).",
            {"evidence_id": {"type": "string"}},
        ),
        tool(
            "get_reported_metric",
            "Full-year values a company reported in XBRL for one measure, each with an id "
            "(N-number) you can cite.",
            {"measure": {"type": "string", "enum": sorted(em.measures)}},
        ),
        tool(
            "calculate",
            "Exact arithmetic on numbers: + - * / and parentheses.",
            {"expression": {"type": "string"}},
        ),
        tool(
            "submit_verdict",
            "Submit your final verdict. Call exactly once, at the end.",
            VERDICT_SCHEMA["properties"],
        ),
    ]


@dataclass
class AgentRun:
    verdict: Verdict | None
    turns: int
    tokens: int
    stop: str
    evidence: dict[str, EvidencePassage] = field(default_factory=dict)
    numbers: dict[str, NumberRow] = field(default_factory=dict)
    tool_log: list[dict] = field(default_factory=list)


class _Registry:
    """Ids the agent may cite: the Tier 1 context plus anything its tools returned."""

    def __init__(self, ctx: VerifyContext) -> None:
        self.ctx = ctx
        self.evidence = {e.eid: e for e in ctx.evidence}
        self.by_pid = {e.passage_id: e.eid for e in ctx.evidence}
        self.numbers = {n.nid: n for n in ctx.numbers}

    def add_passage(self, row: sqlite3.Row) -> str:
        if row["passage_id"] in self.by_pid:
            return self.by_pid[row["passage_id"]]
        eid = f"E{len(self.evidence) + 1}"
        self.evidence[eid] = EvidencePassage(
            eid,
            row["passage_id"],
            row["form"],
            row["filing_date"],
            row["section"],
            row["text"],
            0.0,
        )
        self.by_pid[row["passage_id"]] = eid
        return eid

    def add_number(self, row: NumberRow) -> str:
        for nid, n in self.numbers.items():
            if (n.tag, n.period_end, n.kind) == (row.tag, row.period_end, row.kind):
                return nid
        nid = f"N{len(self.numbers) + 1}"
        self.numbers[nid] = NumberRow(nid, *list(row.to_dict().values())[1:])
        return nid


def run_tool(
    conn: sqlite3.Connection, em: EvidenceMap, reg: _Registry, name: str, args: dict
) -> str:
    ctx = reg.ctx
    if name == "search_company_filings":
        terms = [t for t in str(args.get("query", "")).replace('"', " ").split() if len(t) > 2]
        if not terms:
            return "Give a query with at least one word of three or more letters."
        rows = conn.execute(
            "SELECT p.* FROM passages_fts JOIN passages p "
            "ON p.passage_id = passages_fts.passage_id "
            "WHERE passages_fts MATCH ? AND p.cik=? AND p.filing_date > ? "
            "ORDER BY bm25(passages_fts) LIMIT 5",
            (fts_query(terms[:12]), ctx.cik, ctx.first_stated),
        ).fetchall()
        if not rows:
            return "No later passages matched."
        out = []
        for r in rows:
            eid = reg.add_passage(r)
            out.append(f"[{eid}] {r['form']} filed {r['filing_date']}: {r['text'][:1200]}")
        return "\n\n".join(out)
    if name == "get_passage":
        e = reg.evidence.get(str(args.get("evidence_id")))
        return e.text if e else "Unknown evidence id."
    if name == "get_reported_metric":
        measure = args.get("measure")
        tag, annual = annual_series(conn, ctx.cik, em.measures.get(measure, []))
        if not annual:
            return f"{ctx.ticker} reports no full-year XBRL value for {measure}."
        lines = []
        for end in sorted(annual):
            f = annual[end]
            row = NumberRow(
                "",
                f"{measure} for the fiscal year ended {end}",
                f["value"],
                "USD",
                "fact",
                f"us-gaap:{tag}",
                int(end[:4]),
                f["period_start"],
                end,
                f["accession"],
                f["filed"],
            )
            nid = reg.add_number(row)
            lines.append(f"{nid}: {row.label}: {row.display()} (filed {f['filed']})")
        return "\n".join(lines)
    if name == "calculate":
        try:
            return f"{calculate(str(args.get('expression', ''))):.6g}"
        except CalcError as exc:
            return f"Error: {exc}"
    return f"Unknown tool {name}."


def _clean(blocks: list[dict]) -> list[dict]:
    """Pass blocks back as the API expects: known fields only, thinking kept unchanged."""
    out = []
    for b in blocks:
        keys = _BLOCK_KEYS.get(b.get("type"))
        if keys:
            out.append({k: b[k] for k in keys if k in b and b[k] is not None})
    return out


def run_agent(
    conn: sqlite3.Connection,
    llm: LLMClient,
    run: Run | None,
    em: EvidenceMap,
    ctx: VerifyContext,
    cfg: dict,
    prompt: Prompt,
    *,
    tier1_summary: str = "",
) -> AgentRun:
    reg = _Registry(ctx)
    intro = render(ctx)
    if tier1_summary:
        intro += f"\n\n<first check>\n{tier1_summary}\n</first check>"
    messages: list[dict] = [{"role": "user", "content": intro}]
    base = {
        "model": cfg["model"],
        "max_tokens": int(cfg["max_tokens"]),
        "system": [{"type": "text", "text": prompt.text, "cache_control": {"type": "ephemeral"}}],
        "tools": tools(em),
        "tool_choice": {"type": "auto"},
        **thinking_params(cfg),
    }
    tokens = 0
    log: list[dict] = []
    max_turns = int(cfg.get("max_turns", MAX_TURNS))
    for turn in range(1, max_turns + 1):
        params = {**base, "messages": json.loads(json.dumps(messages))}
        res = llm.create(
            run=run, stage=STAGE, prompt_version=prompt.id, params=params, shard=str(ctx.cik)
        )
        usage = res.response.get("usage", {})
        tokens += int(usage.get("input_tokens", 0)) + int(usage.get("output_tokens", 0))
        if res.status != "ok":
            return AgentRun(None, turn, tokens, res.status, reg.evidence, reg.numbers, log)
        blocks = res.response.get("content", [])
        uses = [b for b in blocks if b.get("type") == "tool_use"]
        for u in uses:
            if u["name"] == "submit_verdict":
                v = validate(u.get("input") or {}, ctx, "2", set(reg.evidence), set(reg.numbers))
                log.append({"turn": turn, "tool": "submit_verdict", "input": u.get("input")})
                return AgentRun(v, turn, tokens, "submitted", reg.evidence, reg.numbers, log)
        if not uses:
            return AgentRun(None, turn, tokens, "no_verdict", reg.evidence, reg.numbers, log)
        if tokens >= int(cfg.get("max_agent_tokens", MAX_TOKENS)):
            return AgentRun(None, turn, tokens, "token_cap", reg.evidence, reg.numbers, log)
        results = []
        for u in uses:
            output = run_tool(conn, em, reg, u["name"], u.get("input") or {})
            log.append({"turn": turn, "tool": u["name"], "input": u.get("input")})
            results.append({"type": "tool_result", "tool_use_id": u["id"], "content": output})
        messages.append({"role": "assistant", "content": _clean(blocks)})
        messages.append({"role": "user", "content": results})
    return AgentRun(None, max_turns, tokens, "turn_cap", reg.evidence, reg.numbers, log)
