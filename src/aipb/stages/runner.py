"""Runs the LLM stages under the budget guard: plan -> estimate -> reserve -> run -> store.

Every paid stage goes through here, so every run prints its worst-case cost first,
refuses above the cap, needs --confirm above $0.50, and settles into the ledger.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal

from aipb.budget.guard import usd
from aipb.context import AppContext
from aipb.llm.client import LLMClient, LLMResult, MissingApiKey, OfflineCacheMiss, Plan, Request
from aipb.llm.params import OutputError, load_prompt, stage_settings
from aipb.stages import ai_products
from aipb.stages import dedupe as dedupe_mod
from aipb.stages import extract as ex
from aipb.stages import filter as fl

Log = Callable[[str], None]


@dataclass
class StageOutcome:
    plan: Plan
    ran: bool
    stats: object | None = None


def _paid_call(
    ctx: AppContext,
    llm: LLMClient,
    *,
    stage: str,
    prompt_id: str,
    requests: list[Request],
    batch: bool,
    plan: Plan,
    command: str,
    confirm: bool,
    log: Log,
) -> dict[str, LLMResult]:
    if plan.to_send == 0:
        return llm.run_many(
            run=None, stage=stage, prompt_version=prompt_id, items=requests, batch=batch
        )
    if not llm.offline and not ctx.settings.api_key():
        raise MissingApiKey(
            f"{plan.to_send} request(s) need the API but AIPAYBACK_API_KEY is not set in .env. "
            "Nothing was reserved or sent."
        )
    with ctx.guard.start_run(
        command=command, stage=stage, estimate=plan.worst_case_usd, confirm=confirm
    ) as run:
        return llm.run_many(
            run=run, stage=stage, prompt_version=prompt_id, items=requests, batch=batch, log=log
        )


def describe(plan: Plan, what: str) -> str:
    return (
        f"{what}: {plan.total} request(s), {plan.cached} already cached ($0), "
        f"{plan.to_send} to send. Worst-case cost {usd(plan.worst_case_usd)}."
    )


def run_filter(
    ctx: AppContext,
    conn: sqlite3.Connection,
    ciks: list[int],
    *,
    variant: str = "default",
    confirm: bool = False,
    dry_run: bool = False,
    passage_ids: set[str] | None = None,
    llm: LLMClient | None = None,
    log: Log = print,
) -> StageOutcome:
    llm = llm or ctx.llm
    cfg = stage_settings(ctx.stages, fl.STAGE, variant)
    prompt = load_prompt(ctx.paths.prompts_dir, fl.STAGE, cfg["prompt"])
    rows = fl.candidates(conn, ciks, passage_ids)
    requests, groups = fl.build_requests(rows, cfg, prompt)
    batch = bool(cfg.get("batch", True))
    plan = llm.plan(fl.STAGE, prompt.id, requests, batch=batch)
    log(
        describe(
            plan, f"Filter ({prompt.id}, {cfg['model']}, variant {variant}, {len(rows)} passages)"
        )
    )
    if dry_run:
        return StageOutcome(plan, ran=False)
    results = _paid_call(
        ctx,
        llm,
        stage=fl.STAGE,
        prompt_id=prompt.id,
        requests=requests,
        batch=batch,
        plan=plan,
        command=f"filter --variant {variant}",
        confirm=confirm,
        log=log,
    )
    stats = fl.store_results(
        conn, groups, results, variant=variant, prompt_id=prompt.id, model=cfg["model"]
    )
    return StageOutcome(plan, ran=True, stats=stats)


def run_extract(
    ctx: AppContext,
    conn: sqlite3.Connection,
    ciks: list[int],
    *,
    variant: str = "default",
    filter_variant: str = "default",
    confirm: bool = False,
    dry_run: bool = False,
    passage_ids: set[str] | None = None,
    llm: LLMClient | None = None,
    log: Log = print,
) -> StageOutcome:
    llm = llm or ctx.llm
    cfg = stage_settings(ctx.stages, ex.STAGE, variant)
    fcfg = stage_settings(ctx.stages, fl.STAGE, filter_variant)
    prompt = load_prompt(ctx.paths.prompts_dir, ex.STAGE, cfg["prompt"])
    rows = ex.candidates(
        conn, fcfg, ciks, variant=variant, filter_variant=filter_variant, passage_ids=passage_ids
    )
    # Risk factors are not promises (rubric section 2, D48): never sent, and any statements
    # stored for them by earlier runs are cleared below.
    skipped = [r for r in rows if ex.is_risk_factor(r["section"])]
    rows = [r for r in rows if not ex.is_risk_factor(r["section"])]
    requests = {r["passage_id"]: ex.build_request(r, cfg, prompt) for r in rows}
    batch = bool(cfg.get("batch", True))
    plan = llm.plan(ex.STAGE, prompt.id, list(requests.values()), batch=batch)
    log(
        describe(
            plan, f"Extract ({prompt.id}, {cfg['model']}, variant {variant}, {len(rows)} passages)"
        )
    )
    if skipped:
        log(f"Skipped {len(skipped)} risk-factor passages (not promises, rubric section 2).")
    if dry_run:
        return StageOutcome(plan, ran=False)
    for r in skipped:
        ex.store_passage(
            conn, r, [], variant=variant, prompt_id=prompt.id, model=cfg["model"],
            retried=False, dropped=0, status="skipped_risk_factor",
            detail="risk factors are not promises (rubric section 2)",
        )  # fmt: skip
    results = _paid_call(
        ctx,
        llm,
        stage=ex.STAGE,
        prompt_id=prompt.id,
        requests=list(requests.values()),
        batch=batch,
        plan=plan,
        command=f"extract --variant {variant}",
        confirm=confirm,
        log=log,
    )
    good, bad, errors = ex.first_pass(rows, results)
    stats = ex.ExtractStats(passages=len(rows), risk_factor=len(skipped))
    lexicon = ctx.lexicon
    # A link may also name an AI product the company's own filings tie to AI (D45).
    names_ai_by_cik: dict[int, Callable[[str], bool]] = {}
    for r in rows:
        if r["cik"] not in names_ai_by_cik:
            confirmed = ctx.ai_products.confirmed(conn, r["cik"], r["ticker"], lexicon)
            names_ai_by_cik[r["cik"]] = ai_products.names_ai_for(lexicon, confirmed)
            if confirmed:
                names = ", ".join(p.name for p in confirmed)
                log(f"{r['ticker']}: AI products confirmed in its filings: {names}")

    retried: set[str] = set()

    retry_ids = [pid for pid, b in bad.items() if b] if int(cfg.get("quote_retries", 1)) else []
    if retry_ids:
        retry_reqs = [ex.retry_request(requests[p], results[p], bad[p]) for p in retry_ids]
        rplan = llm.plan(ex.STAGE, prompt.id, retry_reqs, batch=batch)
        log(describe(rplan, f"Quote retries ({len(retry_ids)} passages)"))
        rres = _paid_call(
            ctx,
            llm,
            stage=ex.STAGE,
            prompt_id=prompt.id,
            requests=retry_reqs,
            batch=batch,
            plan=rplan,
            command=f"extract-retry --variant {variant}",
            confirm=confirm,
            log=log,
        )
        by_id = {r["passage_id"]: r for r in rows}
        for pid in retry_ids:
            retried.add(pid)
            try:
                g2, b2 = ex.verify(by_id[pid]["text"], ex.statements_of(rres[pid]))
            except (OutputError, KeyError) as exc:
                errors.setdefault(pid, f"retry failed: {exc}")
                g2, b2 = [], bad[pid]
            spans = {(v.start, v.end) for v in good[pid]}
            good[pid] += [v for v in g2 if (v.start, v.end) not in spans]
            bad[pid] = b2
    for r in rows:
        pid = r["passage_id"]
        if pid in errors and pid not in good:
            ex.store_passage(
                conn,
                r,
                [],
                variant=variant,
                prompt_id=prompt.id,
                model=cfg["model"],
                retried=pid in retried,
                dropped=0,
                status="error",
                detail=errors[pid],
            )
            stats.errors.append(f"{pid}: {errors[pid]}")
            continue
        # Only statements whose outcome the passage itself ties to AI are kept (D42).
        verified, unlinked = ex.split_linked(
            r["text"], good.get(pid, []), names_ai_by_cik[r["cik"]]
        )
        # ...and only the company's own commitments: not analysts' forecasts or market sizes (D57).
        verified, not_own = ex.split_own(r["text"], verified)
        dropped = len(bad.get(pid, []))
        detail = [b.get("quote", "")[:80] for b in bad.get(pid, [])]
        detail += [f"{v.quote[:60]} ({why})" for v, why in unlinked + not_own]
        status = (
            "dropped_quotes"
            if dropped
            else ("dropped_unlinked" if unlinked else ("dropped_not_own" if not_own else "ok"))
        )
        ex.store_passage(
            conn,
            r,
            verified,
            variant=variant,
            prompt_id=prompt.id,
            model=cfg["model"],
            retried=pid in retried,
            dropped=dropped + len(unlinked) + len(not_own),
            status=status,
            detail="; ".join(detail),
        )
        stats.statements += len(verified)
        stats.promises += sum(v.statement["kind"] == "promise" for v in verified)
        stats.hype += sum(v.statement["kind"] == "hype" for v in verified)
        stats.dropped_quotes += dropped
        stats.unlinked += len(unlinked)
        stats.not_own += len(not_own)
    stats.retried = len(retried)
    return StageOutcome(plan, ran=True, stats=stats)


def run_dedupe(conn: sqlite3.Connection, variant: str = "default") -> dict[str, int]:
    return dedupe_mod.dedupe(conn, variant)


def total_cost(results: dict[str, LLMResult]) -> Decimal:
    return sum((r.cost_usd for r in results.values()), Decimal(0))


def cached_only(llm: LLMClient, stage: str, prompt_id: str, requests: list[Request]) -> set[str]:
    """Keys of the requests whose outputs are already cached (replay without spending)."""
    from aipb.llm.cache import CacheKey, input_hash

    keep = set()
    for r in requests:
        if llm.cache.get(stage, CacheKey(input_hash(r.params), prompt_id, r.params["model"])):
            keep.add(r.key)
    return keep


def replay(ctx: AppContext, conn: sqlite3.Connection, ciks: list[int], log: Log = print) -> None:
    """Rebuild classifications, promises and clusters from committed outputs. $0, offline.

    Only requests whose outputs are cached are replayed; anything else is reported as not
    run yet. Used by `aipb restore` on a fresh clone.
    """
    offline = LLMClient(
        guard=ctx.guard,
        cache=ctx.cache,
        estimator=ctx.estimator,
        api_key=None,
        offline=True,
        device=ctx.settings.aipayback_device,
    )
    cfg = stage_settings(ctx.stages, fl.STAGE, None)
    prompt = load_prompt(ctx.paths.prompts_dir, fl.STAGE, cfg["prompt"])
    rows = fl.candidates(conn, ciks)
    requests, _groups = fl.build_requests(rows, cfg, prompt)
    have = cached_only(offline, fl.STAGE, prompt.id, requests)
    if not have:
        log("  filter: no cached outputs yet (not run).")
        return
    group_pids = {pid for k in have for pid in _groups[k].passage_ids}
    out = run_filter(ctx, conn, ciks, passage_ids=group_pids, llm=offline, log=lambda _m: None)
    log(f"  filter: replayed {out.stats.passages} passages from cache.")
    ecfg = stage_settings(ctx.stages, ex.STAGE, None)
    eprompt = load_prompt(ctx.paths.prompts_dir, ex.STAGE, ecfg["prompt"])
    erows = ex.candidates(conn, cfg, ciks)
    ereqs = [ex.build_request(r, ecfg, eprompt) for r in erows]
    ehave = cached_only(offline, ex.STAGE, eprompt.id, ereqs)
    if not ehave:
        log("  extract: no cached outputs yet (not run).")
        return
    try:
        eout = run_extract(ctx, conn, ciks, passage_ids=ehave, llm=offline, log=lambda _m: None)
    except Exception as exc:  # a retry that was never cached: report, don't fail restore
        log(f"  extract: replay incomplete ({type(exc).__name__}: {exc}).")
        return
    counts = run_dedupe(conn)
    log(f"  extract: replayed {eout.stats.statements} statements; {counts['clusters']} clusters.")


def replay_verification(
    ctx: AppContext, conn: sqlite3.Connection, ciks: list[int], log: Log = print
) -> None:
    """Rebuild verdicts, explanations and the gate from committed outputs. $0, offline."""
    from aipb.stages import verify_runner

    offline = LLMClient(
        guard=ctx.guard,
        cache=ctx.cache,
        estimator=ctx.estimator,
        api_key=None,
        offline=True,
        device=ctx.settings.aipayback_device,
    )
    if not conn.execute("SELECT 1 FROM promise_clusters LIMIT 1").fetchone():
        return
    try:
        _plan, st = verify_runner.run_verify(ctx, conn, ciks, llm=offline, log=lambda _m: None)
        _plan, counts = verify_runner.run_explain(ctx, conn, ciks, llm=offline, log=lambda _m: None)
    except OfflineCacheMiss:
        log("  verify/explain: not run yet (no cached outputs for some promises).")
        return
    gate = verify_runner.run_gate(ctx, conn)
    log(
        f"  verify: replayed {st.clusters} promises; explanations ok {counts.get('ok', 0)}; "
        f"gate: {', '.join(f'{k} {v}' for k, v in sorted(gate.items()))}."
    )
