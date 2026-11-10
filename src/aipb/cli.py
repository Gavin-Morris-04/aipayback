"""`aipb`: the AIPayback command line. Every Makefile target is a thin wrapper around this."""

from __future__ import annotations

import shutil
import sys
import uuid
from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from aipb import db
from aipb.budget.guard import BudgetError, usd
from aipb.context import AppContext
from aipb.llm.client import MissingApiKey, OfflineCacheMiss
from aipb.settings import anthropic_key_warnings

app = typer.Typer(
    help="AIPayback: did the AI promises in SEC filings pay off?",
    no_args_is_help=True,
    add_completion=False,
)
out = Console()
err = Console(stderr=True)


def _ctx() -> AppContext:
    return AppContext.create()


@app.callback()
def _main() -> None:
    ctx = _ctx()
    for warning in anthropic_key_warnings(dotenv=ctx.paths.dotenv):
        err.print(f"[bold red]WARNING:[/] {warning}")


def _fail(exc: Exception) -> None:
    err.print(f"[bold red]{type(exc).__name__}:[/] {exc}")
    raise typer.Exit(code=2)


def thinking_params(stage_cfg: dict) -> dict:
    """Translate a stage's thinking/effort settings into request parameters."""
    params: dict = {}
    thinking = stage_cfg.get("thinking")
    if thinking == "disabled":
        params["thinking"] = {"type": "disabled"}
    elif thinking == "adaptive":
        params["thinking"] = {"type": "adaptive"}
    if stage_cfg.get("effort"):
        params["output_config"] = {"effort": stage_cfg["effort"]}
    return params


# ---------------------------------------------------------------------------- budget


@app.command()
def budget() -> None:
    """Show spent, reserved and remaining budget, by stage and by model."""
    ctx = _ctx()
    try:
        st = ctx.guard.status()
        calls = ctx.ledger.calls()
        runs = ctx.ledger.runs()
    except Exception as exc:  # corrupt ledger: fail closed
        _fail(exc)
        return

    summary = Table(title="AIPayback API budget", show_header=False, min_width=48)
    summary.add_row("Total API credit", usd(st.total_credit))
    summary.add_row("App cap (enforced)", usd(st.cap))
    summary.add_row("Reserve (locked)", usd(st.reserve_locked))
    summary.add_row("Spent", usd(st.spent))
    summary.add_row("Reserved by open runs", usd(st.reserved))
    summary.add_row("[bold]Remaining under cap[/]", f"[bold]{usd(st.remaining)}[/]")
    summary.add_row("Pricing verified on", ctx.pricing.verified_on)
    out.print(summary)

    for label, keyfn in (("stage", lambda c: c.stage), ("model", lambda c: c.model)):
        totals: dict[str, Decimal] = defaultdict(Decimal)
        counts: dict[str, int] = defaultdict(int)
        for c in calls:
            totals[keyfn(c)] += c.cost_usd
            counts[keyfn(c)] += 1
        table = Table(title=f"Spend by {label}")
        table.add_column(label)
        table.add_column("calls", justify="right")
        table.add_column("cost", justify="right")
        for name in sorted(totals, key=lambda n: totals[n], reverse=True):
            table.add_row(name, str(counts[name]), usd(totals[name]))
        if not totals:
            table.add_row("(nothing spent yet)", "0", usd(Decimal(0)))
        out.print(table)

    open_runs = [r for r in runs.values() if r.is_open]
    if open_runs:
        table = Table(title="Open runs holding reservations")
        for col in ("run_id", "command", "reserved", "spent", "started"):
            table.add_column(col)
        for r in open_runs:
            table.add_row(
                r.run_id, r.start.command, usd(r.start.reserved_usd), usd(r.spent_usd), r.start.ts
            )
        out.print(table)
        out.print("Release a crashed run only after checking it: aipb release-run <run_id> --yes")


@app.command("cost-report")
def cost_report() -> None:
    """Token and cost breakdown per stage and model, plus every run."""
    ctx = _ctx()
    try:
        calls = ctx.ledger.calls()
        runs = ctx.ledger.runs()
    except Exception as exc:
        _fail(exc)
        return

    groups: dict[tuple[str, str], list] = defaultdict(list)
    for c in calls:
        groups[(c.stage, c.model)].append(c)

    table = Table(title="LLM cost report (from data/ledger/llm_calls.jsonl)")
    cols = (
        "stage",
        "model",
        "calls",
        "errors",
        "input",
        "cache read",
        "cache write",
        "output",
        "thinking",
        "batch %",
        "cost",
        "avg ms",
    )
    for col in cols:
        table.add_column(col, justify="left" if col in ("stage", "model") else "right")
    for (stage, model), items in sorted(groups.items()):
        n = len(items)
        lat = [c.latency_ms for c in items if c.latency_ms is not None]
        table.add_row(
            stage,
            model,
            str(n),
            str(sum(c.status != "ok" for c in items)),
            f"{sum(c.input_tokens for c in items):,}",
            f"{sum(c.cache_read_tokens for c in items):,}",
            f"{sum(c.cache_write_5m_tokens + c.cache_write_1h_tokens for c in items):,}",
            f"{sum(c.output_tokens for c in items):,}",
            f"{sum(c.thinking_tokens for c in items):,}",
            f"{100 * sum(c.is_batch for c in items) / n:.0f}",
            usd(sum((c.cost_usd for c in items), Decimal(0))),
            f"{sum(lat) / len(lat):.0f}" if lat else "-",
        )
    if not groups:
        table.add_row("(no calls yet)", *[""] * (len(cols) - 1))
    out.print(table)

    run_table = Table(title="Runs")
    for col in ("run_id", "command", "estimate", "actual", "calls", "status", "git"):
        run_table.add_column(col)
    for r in sorted(runs.values(), key=lambda r: r.start.ts):
        run_table.add_row(
            r.run_id,
            r.start.command,
            usd(r.start.estimate_usd),
            usd(r.spent_usd),
            str(r.calls),
            r.finish.status if r.finish else "OPEN",
            r.start.git_sha,
        )
    out.print(run_table)


@app.command("release-run")
def release_run(
    run_id: str,
    yes: Annotated[bool, typer.Option("--yes", help="Confirm you checked this run.")] = False,
) -> None:
    """Release the reservation of a run that crashed (check for pending batches first)."""
    if not yes:
        err.print("Check that the run has no pending batch or in-flight call, then add --yes.")
        raise typer.Exit(code=2)
    ctx = _ctx()
    try:
        ctx.guard.release_run(run_id)
    except BudgetError as exc:
        _fail(exc)
    out.print(f"Released {run_id}.")


# ---------------------------------------------------------------------------- setup checks


@app.command()
def doctor() -> None:
    """Check billing safety and setup. Spends nothing."""
    ctx = _ctx()
    ok = True

    def line(passed: bool, text: str, warn_only: bool = False) -> None:
        nonlocal ok
        mark = "[green]OK  [/]" if passed else ("[yellow]WARN[/]" if warn_only else "[red]FAIL[/]")
        if not passed and not warn_only:
            ok = False
        out.print(f"{mark} {text}")

    warnings = anthropic_key_warnings(dotenv=ctx.paths.dotenv)
    line(not warnings, "ANTHROPIC_API_KEY is not set (Claude Code bills your subscription)")
    for w in warnings:
        out.print(f"     {w}")
    line(ctx.paths.dotenv.exists(), ".env exists (copy .env.example)")
    line(ctx.settings.api_key() is not None, "AIPAYBACK_API_KEY is set (value not shown)")
    line(
        bool(ctx.settings.sec_contact_email),
        "SEC_CONTACT_EMAIL is set (needed in Phase 1)",
        warn_only=True,
    )
    age = (date.today() - date.fromisoformat(ctx.pricing.verified_on)).days
    line(age <= 30, f"Pricing verified {age} days ago ({ctx.pricing.verified_on})", warn_only=True)
    try:
        st = ctx.guard.status()
        line(True, f"Ledger readable: spent {usd(st.spent)}, remaining {usd(st.remaining)}")
    except Exception as exc:
        line(False, f"Ledger unreadable: {exc}")
    line(
        not ctx.settings.aipayback_offline,
        "Online mode (offline mode never calls the API)",
        warn_only=True,
    )
    line(
        shutil.which("make") is not None,
        "make installed (optional; `uv run aipb <command>` works without it)",
        warn_only=True,
    )
    raise typer.Exit(code=0 if ok else 1)


@app.command()
def smoke(
    fresh: Annotated[
        bool, typer.Option("--fresh", help="Add a nonce so the call is not served from cache.")
    ] = False,
    confirm: Annotated[bool, typer.Option("--confirm")] = False,
) -> None:
    """One tiny Haiku call to prove billing, the ledger and the cache work (~$0.00002)."""
    ctx = _ctx()
    cfg = ctx.stages["smoke"]
    prompt = "Reply with exactly: OK"
    if fresh:
        prompt += f" (nonce {uuid.uuid4().hex[:8]})"
    params = {
        "model": cfg["model"],
        "max_tokens": int(cfg["max_tokens"]),
        "messages": [{"role": "user", "content": prompt}],
        **thinking_params(cfg),
    }
    estimate = ctx.estimator.worst_case_cost(ctx.pricing, params, batch=False)
    out.print(f"Worst-case estimate: {usd(estimate)}")
    try:
        with ctx.guard.start_run(
            command="smoke", stage="smoke", estimate=estimate, confirm=confirm
        ) as run:
            result = ctx.llm.create(
                run=run, stage="smoke", prompt_version="smoke-v1", params=params
            )
    except (BudgetError, MissingApiKey, OfflineCacheMiss) as exc:
        _fail(exc)
        return
    source = "cache (no API call, $0)" if result.cached else f"API, cost {usd(result.cost_usd)}"
    out.print(f"Reply: {result.text()!r}  [{source}]  stop_reason={result.stop_reason}")
    if not result.cached:
        u = result.response.get("usage", {})
        out.print(
            f"Usage: input={u.get('input_tokens')} output={u.get('output_tokens')}. "
            "Compare with the Console usage page."
        )


@app.command()
def restore() -> None:
    """Rebuild the local SQLite database from committed files. Makes zero API calls."""
    ctx = _ctx()
    conn = db.connect(ctx.paths.database)
    try:
        n_calls, n_runs = db.restore_costs(conn, ctx.ledger)
    finally:
        conn.close()
    out.print(f"Restored {n_calls} LLM calls and {n_runs} runs into {ctx.paths.database.name}.")
    out.print("(Phase 1 adds re-downloading SEC filings and rebuilding passages.)")


def main() -> None:  # pragma: no cover
    sys.exit(app())
