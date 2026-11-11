"""Phase 3 orchestration: Tier 1 (batch) -> Tier 2 escalations (capped) -> explain -> gate."""

from __future__ import annotations

import csv
import json
import sqlite3
from dataclasses import dataclass, field
from decimal import Decimal

import yaml

from aipb.budget.guard import BudgetError, usd
from aipb.context import AppContext
from aipb.llm.client import LLMClient, MissingApiKey, Plan, Request
from aipb.llm.params import load_prompt, stage_settings
from aipb.stages import explain as ex
from aipb.stages.runner import Log, _paid_call, describe
from aipb.verify import gate, tier1, tier2
from aipb.verify.context import VerifyContext, build_context
from aipb.verify.numbers import EvidenceMap


@dataclass
class VerifyStats:
    clusters: int = 0
    tier1: dict[str, int] = field(default_factory=dict)
    escalated: int = 0
    tier2_done: int = 0
    tier2_skipped_cap: int = 0
    tier2_stops: dict[str, int] = field(default_factory=dict)


def gate_threshold(ctx: AppContext) -> float:
    raw = yaml.safe_load(ctx.paths.stages_config.read_text(encoding="utf-8")) or {}
    return float((raw.get("gate") or {}).get("confidence_threshold", gate.DEFAULT_THRESHOLD))


def clusters_for(conn: sqlite3.Connection, ciks: list[int], variant: str) -> list[str]:
    marks = ",".join("?" * len(ciks))
    return [
        r[0]
        for r in conn.execute(
            f"SELECT cluster_id FROM promise_clusters WHERE variant=? AND cik IN ({marks}) "
            "ORDER BY cik, first_stated, cluster_id",
            (variant, *ciks),
        )
    ]


def _store_context(conn: sqlite3.Connection, c: VerifyContext) -> None:
    with conn:
        conn.execute(
            "DELETE FROM evidence WHERE cluster_id=? AND variant=?", (c.cluster_id, c.variant)
        )
        conn.execute(
            "DELETE FROM numbers WHERE cluster_id=? AND variant=?", (c.cluster_id, c.variant)
        )
        conn.executemany(
            "INSERT INTO evidence VALUES (?,?,?,?,?,?,?)",
            [
                (c.cluster_id, c.variant, e.eid, e.passage_id, e.form, e.filing_date, "retrieval")
                for e in c.evidence
            ],
        )
        conn.executemany(
            "INSERT INTO numbers VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                (
                    c.cluster_id,
                    c.variant,
                    n.nid,
                    n.label,
                    n.value,
                    n.unit,
                    n.kind,
                    n.tag,
                    n.fiscal_year,
                    n.period_start,
                    n.period_end,
                    n.accession,
                    n.filed,
                )
                for n in c.numbers
            ],
        )


def _store_verdict(conn, cid, variant, v: tier1.Verdict | None, *, tier, stop, prompt_id, model):
    with conn:
        conn.execute(
            "INSERT OR REPLACE INTO verdicts VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                cid,
                variant,
                tier,
                v.status if v else None,
                v.walked_back_kind if v else None,
                v.confidence if v else None,
                json.dumps(v.evidence_ids if v else []),
                json.dumps(v.number_ids if v else []),
                v.key_finding if v else None,
                int(bool(v and v.valid)),
                json.dumps(v.problems if v else [stop]),
                stop,
                prompt_id,
                model,
            ),
        )


def load_verdict(conn: sqlite3.Connection, cid: str, variant: str, tier: str):
    r = conn.execute(
        "SELECT * FROM verdicts WHERE cluster_id=? AND variant=? AND tier=?", (cid, variant, tier)
    ).fetchone()
    if r is None or r["status"] is None:
        return None
    return tier1.Verdict(
        r["tier"],
        r["status"],
        r["walked_back_kind"],
        r["confidence"],
        json.loads(r["evidence_ids"]),
        json.loads(r["number_ids"]),
        r["key_finding"],
        bool(r["valid"]),
        json.loads(r["problems"]),
    )


def tier2_estimate(llm: LLMClient, first_params: dict, cfg: dict) -> Decimal:
    """Worst case for one agent run: every turn re-sends a growing conversation."""
    per_turn_growth = int(cfg["max_tokens"]) + 2000  # the answer plus a tool result
    base = llm.estimator.input_tokens(first_params)
    total = Decimal(0)
    pricing = llm.guard.pricing
    for turn in range(int(cfg.get("max_turns", tier2.MAX_TURNS))):
        from aipb.budget.pricing import TokenUsage

        total += pricing.cost(
            cfg["model"],
            TokenUsage(
                input_tokens=base + turn * per_turn_growth, output_tokens=int(cfg["max_tokens"])
            ),
            batch=False,
        )
    return total


def run_verify(
    ctx: AppContext,
    conn: sqlite3.Connection,
    ciks: list[int],
    *,
    variant: str = "default",
    t2_variant: str = "default",
    tier2_on: bool = True,
    confirm: bool = False,
    dry_run: bool = False,
    llm: LLMClient | None = None,
    log: Log = print,
) -> tuple[Plan, VerifyStats]:
    llm = llm or ctx.llm
    em = EvidenceMap.load(ctx.paths.evidence_map)
    threshold = gate_threshold(ctx)
    cfg1 = stage_settings(ctx.stages, tier1.STAGE, None)
    p1 = load_prompt(ctx.paths.prompts_dir, tier1.STAGE, cfg1["prompt"])
    stats = VerifyStats()
    contexts = {
        cid: build_context(conn, em, cid, variant) for cid in clusters_for(conn, ciks, variant)
    }
    stats.clusters = len(contexts)
    for c in contexts.values():
        _store_context(conn, c)
    reqs = [
        Request(cid, tier1.build_request_params(c, cfg1, p1), str(c.cik))
        for cid, c in contexts.items()
    ]
    batch = bool(cfg1.get("batch", True))
    plan = llm.plan(tier1.STAGE, p1.id, reqs, batch=batch)
    log(describe(plan, f"Tier 1 verify ({p1.id}, {cfg1['model']}, {len(reqs)} promises)"))
    cfg2 = stage_settings(ctx.stages, tier2.STAGE, t2_variant)
    if dry_run:
        if reqs:
            per = tier2_estimate(llm, reqs[0].params, cfg2)
            log(
                f"Tier 2 worst case: {usd(per)} per escalated promise, capped at "
                f"{usd(Decimal(str(cfg2.get('run_cap_usd', '0.50'))))} per run."
            )
        return plan, stats
    results = _paid_call(
        ctx,
        llm,
        stage=tier1.STAGE,
        prompt_id=p1.id,
        requests=reqs,
        batch=batch,
        plan=plan,
        command="verify --tier 1",
        confirm=confirm,
        log=log,
    )
    t1: dict[str, tier1.Verdict] = {}
    for cid, c in contexts.items():
        v = tier1.parse(results[cid], c)
        t1[cid] = v
        stats.tier1[v.status or "invalid"] = stats.tier1.get(v.status or "invalid", 0) + 1
        _store_verdict(
            conn, cid, variant, v, tier="1", stop="submitted", prompt_id=p1.id, model=cfg1["model"]
        )
    escalate = [cid for cid, v in t1.items() if gate.needs_tier2(v, threshold)]
    stats.escalated = len(escalate)
    if not (tier2_on and escalate):
        return plan, stats
    p2 = load_prompt(ctx.paths.prompts_dir, tier2.STAGE, cfg2["prompt"])
    cap = Decimal(str(cfg2.get("run_cap_usd", "0.50")))
    per = tier2_estimate(llm, reqs[0].params, cfg2)
    fit = min(len(escalate), int(cap / per) if per > 0 else len(escalate))
    if fit < len(escalate):
        stats.tier2_skipped_cap = len(escalate) - fit
        log(
            f"Tier 2: {len(escalate)} escalations, {fit} fit under the {usd(cap)} run cap; the "
            "rest stay pending until the next run."
        )
    todo = escalate[:fit]
    if not todo:
        return plan, stats
    if not llm.offline and not ctx.settings.api_key():
        raise MissingApiKey("Tier 2 needs AIPAYBACK_API_KEY. Nothing was reserved or sent.")
    estimate = per * len(todo)
    log(f"Tier 2: {len(todo)} promises, worst case {usd(estimate)}.")
    with ctx.guard.start_run(
        command="verify --tier 2", stage=tier2.STAGE, estimate=estimate, confirm=confirm
    ) as run:
        for cid in todo:
            c = contexts[cid]
            v1 = t1[cid]
            summary = (
                f"status={v1.status or 'invalid'}, kind={v1.walked_back_kind}, "
                f"confidence={v1.confidence:.2f}, finding={v1.key_finding}"
            )
            try:
                agent = tier2.run_agent(conn, llm, run, em, c, cfg2, p2, tier1_summary=summary)
            except BudgetError as exc:
                log(f"Tier 2 stopped: {exc}")
                break
            stats.tier2_done += 1
            stats.tier2_stops[agent.stop] = stats.tier2_stops.get(agent.stop, 0) + 1
            _store_verdict(
                conn,
                cid,
                variant,
                agent.verdict,
                tier="2",
                stop=agent.stop,
                prompt_id=p2.id,
                model=cfg2["model"],
            )
            extra = [e for eid, e in agent.evidence.items() if eid not in c.evidence_ids()]
            extra_n = [n for nid, n in agent.numbers.items() if nid not in c.number_ids()]
            with conn:
                conn.executemany(
                    "INSERT OR REPLACE INTO evidence VALUES (?,?,?,?,?,?,?)",
                    [
                        (cid, variant, e.eid, e.passage_id, e.form, e.filing_date, "tier2")
                        for e in extra
                    ],
                )
                conn.executemany(
                    "INSERT OR REPLACE INTO numbers VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    [
                        (
                            cid,
                            variant,
                            n.nid,
                            n.label,
                            n.value,
                            n.unit,
                            n.kind,
                            n.tag,
                            n.fiscal_year,
                            n.period_start,
                            n.period_end,
                            n.accession,
                            n.filed,
                        )
                        for n in extra_n
                    ],
                )
    return plan, stats


# ---------------------------------------------------------------------------- explain + gate


def open_error_reports(ctx: AppContext) -> set[str]:
    path = ctx.paths.error_reports
    if not path.exists():
        return set()
    with path.open(encoding="utf-8", newline="") as fh:
        return {r["cluster_id"] for r in csv.DictReader(fh) if r.get("status", "open") == "open"}


def _evidence_docs(conn, cid, variant, verdict: tier1.Verdict):
    from aipb.verify.context import EvidencePassage
    from aipb.verify.numbers import NumberRow

    ev = []
    for eid in verdict.evidence_ids:
        r = conn.execute(
            "SELECT e.*, p.text, p.section FROM evidence e JOIN passages p "
            "ON p.passage_id = e.passage_id WHERE e.cluster_id=? AND e.variant=? AND e.eid=?",
            (cid, variant, eid),
        ).fetchone()
        if r:
            ev.append(
                EvidencePassage(
                    eid, r["passage_id"], r["form"], r["filing_date"], r["section"], r["text"], 0.0
                )
            )
    nums = []
    for nid in verdict.number_ids:
        r = conn.execute(
            "SELECT * FROM numbers WHERE cluster_id=? AND variant=? AND nid=?", (cid, variant, nid)
        ).fetchone()
        if r:
            nums.append(
                NumberRow(
                    nid,
                    r["label"],
                    r["value"],
                    r["unit"],
                    r["kind"],
                    r["tag"],
                    r["fiscal_year"],
                    r["period_start"],
                    r["period_end"],
                    r["accession"],
                    r["filed"],
                )
            )
    return ev, nums


def chosen_verdict(
    conn, cid, variant, threshold, errors
) -> tuple[gate.Decision, tier1.Verdict | None]:
    t1 = load_verdict(conn, cid, variant, "1")
    t2 = load_verdict(conn, cid, variant, "2")
    d = gate.decide(
        t1, t2, explanation_ok=True, open_error_report=cid in errors, threshold=threshold
    )
    if not d.publishable:
        return d, None
    return d, (t2 if d.source_tier == "2" else t1)


def run_explain(
    ctx: AppContext,
    conn: sqlite3.Connection,
    ciks: list[int],
    *,
    variant: str = "default",
    confirm: bool = False,
    dry_run: bool = False,
    llm: LLMClient | None = None,
    log: Log = print,
) -> tuple[Plan, dict[str, int]]:
    llm = llm or ctx.llm
    cfg = stage_settings(ctx.stages, ex.STAGE, None)
    prompt = load_prompt(ctx.paths.prompts_dir, ex.STAGE, cfg["prompt"])
    threshold = gate_threshold(ctx)
    errors = open_error_reports(ctx)
    reqs, docs_by, status_by = [], {}, {}
    for cid in clusters_for(conn, ciks, variant):
        _decision, verdict = chosen_verdict(conn, cid, variant, threshold, errors)
        if verdict is None:
            continue  # pending items show the verified quote only; no explanation needed
        cl = conn.execute(
            "SELECT * FROM promise_clusters WHERE cluster_id=? AND variant=?", (cid, variant)
        ).fetchone()
        p = conn.execute(
            "SELECT * FROM promises WHERE promise_id=?", (cl["canonical_promise_id"],)
        ).fetchone()
        ptext = conn.execute(
            "SELECT text FROM passages WHERE passage_id=?", (p["passage_id"],)
        ).fetchone()[0]
        f = conn.execute("SELECT form FROM filings WHERE accession=?", (p["accession"],)).fetchone()
        co = conn.execute("SELECT name, ticker FROM companies WHERE cik=?", (cl["cik"],)).fetchone()
        ev, nums = _evidence_docs(conn, cid, variant, verdict)
        docs = ex.documents(p["quote"], f"{f['form']} filed {p['filing_date']}", ptext, ev, nums)
        reqs.append(
            Request(
                cid,
                ex.build_params(cfg, prompt, docs, verdict, f"{co['name']} ({co['ticker']})"),
                str(cl["cik"]),
            )
        )
        docs_by[cid], status_by[cid] = docs, verdict.status
    batch = bool(cfg.get("batch", True))
    plan = llm.plan(ex.STAGE, prompt.id, reqs, batch=batch)
    log(describe(plan, f"Explain ({prompt.id}, {cfg['model']}, {len(reqs)} statuses)"))
    if dry_run:
        return plan, {}
    results = _paid_call(
        ctx,
        llm,
        stage=ex.STAGE,
        prompt_id=prompt.id,
        requests=reqs,
        batch=batch,
        plan=plan,
        command="explain",
        confirm=confirm,
        log=log,
    )
    counts = {"ok": 0, "failed_checks": 0}
    for cid, docs in docs_by.items():
        e = ex.check(results[cid], docs, status_by[cid])
        counts["ok" if e.ok else "failed_checks"] += 1
        with conn:
            conn.execute(
                "INSERT OR REPLACE INTO explanations VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    cid,
                    variant,
                    status_by[cid],
                    e.text,
                    json.dumps(e.citations),
                    int(e.citations_valid),
                    int(e.lint_ok),
                    json.dumps(e.problems),
                    prompt.id,
                    cfg["model"],
                ),
            )
    return plan, counts


def run_gate(ctx: AppContext, conn: sqlite3.Connection, variant: str = "default") -> dict[str, int]:
    threshold = gate_threshold(ctx)
    errors = open_error_reports(ctx)
    counts: dict[str, int] = {}
    rows = []
    for (cid,) in conn.execute(
        "SELECT cluster_id FROM promise_clusters WHERE variant=?", (variant,)
    ).fetchall():
        e = conn.execute(
            "SELECT * FROM explanations WHERE cluster_id=? AND variant=?", (cid, variant)
        ).fetchone()
        t1 = load_verdict(conn, cid, variant, "1")
        t2 = load_verdict(conn, cid, variant, "2")
        d = gate.decide(
            t1,
            t2,
            explanation_ok=bool(e and e["citations_valid"] and e["lint_ok"]),
            open_error_report=cid in errors,
            threshold=threshold,
        )
        if d.publishable and e is not None and e["status"] != d.status:
            d = gate.Decision(
                "", gate.PENDING, False, False, "explanation was written for a different status", ""
            )
        counts[d.label] = counts.get(d.label, 0) + 1
        rows.append(
            (
                cid,
                variant,
                d.status,
                d.label,
                int(d.publishable),
                int(d.silent),
                d.reason,
                d.source_tier,
            )
        )
    with conn:
        conn.execute("DELETE FROM final_status WHERE variant=?", (variant,))
        conn.executemany("INSERT INTO final_status VALUES (?,?,?,?,?,?,?,?)", rows)
    return counts
