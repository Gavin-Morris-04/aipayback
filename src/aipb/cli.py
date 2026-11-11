"""`aipb`: the AIPayback command line. Every Makefile target is a thin wrapper around this."""

from __future__ import annotations

import json
import shutil
import sys
import uuid
from collections import defaultdict
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from aipb import db
from aipb import publish as publish_mod
from aipb.budget.guard import BudgetError, _git_sha, usd
from aipb.budget.ledger import utc_now
from aipb.context import AppContext
from aipb.evals import compare as compare_mod
from aipb.evals import run as eval_mod
from aipb.evals import split as split_mod
from aipb.evals import status_eval as status_eval_mod
from aipb.labeling import disagreements as disagree_mod
from aipb.labeling import import_labels as import_mod
from aipb.labeling import packets as packets_mod
from aipb.labeling import status_packets as status_mod
from aipb.llm.client import MissingApiKey, OfflineCacheMiss
from aipb.llm.params import load_prompt, stage_settings, thinking_params
from aipb.newsletter import flow as nl_flow
from aipb.newsletter import intro as nl_intro
from aipb.newsletter import issue as nl_issue
from aipb.newsletter import render as nl_render
from aipb.newsletter import services as nl_services
from aipb.sec.client import SecError
from aipb.settings import anthropic_key_warnings
from aipb.site import build as site_mod
from aipb.stages import filter as fl_mod
from aipb.stages import ingest as ingest_stage
from aipb.stages import parse as parse_stage
from aipb.stages import runner, verify_runner
from aipb.universe import Member, UniverseError, load_universe

app = typer.Typer(
    help="AIPayback: did the AI promises in SEC filings pay off?",
    no_args_is_help=True,
    add_completion=False,
)
# Wide enough for the stats tables when output is piped or captured (rich defaults to 80).
_WIDTH = None if sys.stdout.isatty() else 160
out = Console(width=_WIDTH)
err = Console(stderr=True, width=_WIDTH)


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
def restore(
    no_download: Annotated[
        bool, typer.Option("--no-download", help="Use only files already on disk.")
    ] = False,
) -> None:
    """Rebuild the local database from committed files. Zero API calls; SEC downloads only.

    Costs come from the ledger. Filings are re-downloaded from the manifest (and checked
    against their sha256), then re-parsed, re-indexed and re-filtered.
    """
    ctx = _ctx()
    conn = db.connect(ctx.paths.database)
    try:
        n_calls, n_runs = db.restore_costs(conn, ctx.ledger)
        out.print(f"Restored {n_calls} LLM calls and {n_runs} runs from the ledger.")
        manifest = ctx.manifest
        if not len(manifest):
            out.print("The filings manifest is empty: nothing to download yet (run aipb ingest).")
            return
        client = None if no_download else ctx.sec
        ticker_cik = manifest.ciks()
        _register_companies(ctx, conn, ticker_cik)
        for ticker, cik in sorted(ticker_cik.items()):
            rep = parse_stage.parse_company(
                conn, manifest, ctx.paths.raw_dir, cik, client=client, log=err.print
            )
            facts = parse_stage.load_xbrl(
                conn, ctx.paths.raw_dir, cik, client, manifest.filer_ciks(cik)
            )
            stats = parse_stage.prefilter_company(conn, cik, ctx.lexicon)
            out.print(
                f"{ticker}: {rep.parsed} filings parsed ({rep.skipped} up to date), "
                f"{stats['passages']} passages, {stats['kw']} keyword hits, {facts} XBRL facts"
            )
        out.print("Model outputs (from data/outputs, offline, $0):")
        runner.replay(ctx, conn, sorted(ticker_cik.values()), log=out.print)
    except SecError as exc:
        _fail(exc)
    finally:
        conn.close()
        if "sec" in ctx.__dict__:
            ctx.sec.close()


# ---------------------------------------------------------------------------- SEC pipeline

UniverseOpt = Annotated[
    str, typer.Option("--universe", "-u", help="Company list: config/universe/<name>.csv")
]
TickerOpt = Annotated[
    list[str] | None, typer.Option("--ticker", "-t", help="Only this ticker (repeatable).")
]


def _members(ctx: AppContext, universe: str, tickers: list[str] | None) -> list[Member]:
    try:
        members = load_universe(ctx.paths.universe_dir, universe)
    except UniverseError as exc:
        _fail(exc)
        raise
    if tickers:
        wanted = {t.upper() for t in tickers}
        unknown = wanted - {m.ticker for m in members}
        if unknown:
            _fail(UniverseError(f"Not in {universe}.csv: {', '.join(sorted(unknown))}"))
        members = [m for m in members if m.ticker in wanted]
    return members


def _register_companies(ctx: AppContext, conn, ticker_cik: dict[str, int]) -> None:
    """Write the companies table from every universe file, using CIKs from the manifest."""
    for path in sorted(ctx.paths.universe_dir.glob("*.csv")):
        for m in load_universe(ctx.paths.universe_dir, path.stem):
            if m.ticker in ticker_cik:
                parse_stage.upsert_company(
                    conn, cik=ticker_cik[m.ticker], ticker=m.ticker, name=m.name,
                    sector=m.sector, universe=path.stem, source=m.source,
                    source_date=m.source_date,
                )  # fmt: skip


@app.command()
def ingest(
    universe: UniverseOpt = "pilot",
    ticker: TickerOpt = None,
    since: Annotated[str, typer.Option(help="First filing date (YYYY-MM-DD).")] = "2024-01-01",
) -> None:
    """Download 10-K, 10-Q and 8-K (Item 2.02) filings plus XBRL facts from SEC EDGAR."""
    ctx = _ctx()
    members = _members(ctx, universe, ticker)
    try:
        start = date.fromisoformat(since)
    except ValueError:
        _fail(ValueError(f"--since must be YYYY-MM-DD, got {since!r}"))
        return
    try:
        reports = ingest_stage.ingest(
            ctx.sec, ctx.paths.raw_dir, ctx.manifest, members, start=start, log=err.print
        )
    except SecError as exc:
        _fail(exc)
        return
    finally:
        ctx.sec.close()
    table = Table(title=f"Ingest: {universe} ({len(members)} companies)")
    for col in ("ticker", "CIK", "filings", "new docs", "errors"):
        table.add_column(col, justify="left" if col == "ticker" else "right")
    for r in reports:
        table.add_row(r.ticker, str(r.cik), str(r.filings), str(r.new_docs), str(len(r.errors)))
    out.print(table)
    st = ctx.sec.stats
    out.print(
        f"SEC requests: {st.requests}, cache hits: {st.cache_hits}, retries: {st.retries}, "
        f"downloaded: {st.bytes_downloaded / 1e6:.1f} MB. Manifest: {len(ctx.manifest)} documents."
    )
    if any(r.errors for r in reports):
        raise typer.Exit(code=1)


def _ciks_for(ctx: AppContext, members: list[Member]) -> dict[str, int]:
    known = ctx.manifest.ciks()
    missing = [m.ticker for m in members if m.ticker not in known]
    if missing:
        err.print(f"Not ingested yet (run aipb ingest first): {', '.join(missing)}")
    return {m.ticker: known[m.ticker] for m in members if m.ticker in known}


@app.command()
def parse(
    universe: UniverseOpt = "pilot",
    ticker: TickerOpt = None,
    force: Annotated[bool, typer.Option("--force", help="Re-parse even if up to date.")] = False,
) -> None:
    """Parse downloaded filings into passages (FTS-indexed) and load XBRL facts. Costs $0."""
    ctx = _ctx()
    members = _members(ctx, universe, ticker)
    ticker_cik = _ciks_for(ctx, members)
    conn = db.connect(ctx.paths.database)
    try:
        _register_companies(ctx, conn, ticker_cik)
        table = Table(title="Parse")
        for col in ("ticker", "parsed", "up to date", "passages", "XBRL facts", "warnings"):
            table.add_column(col, justify="left" if col == "ticker" else "right")
        for t, cik in ticker_cik.items():
            rep = parse_stage.parse_company(
                conn, ctx.manifest, ctx.paths.raw_dir, cik, client=ctx.sec, force=force,
                log=err.print,
            )  # fmt: skip
            facts = parse_stage.load_xbrl(
                conn, ctx.paths.raw_dir, cik, ctx.sec, ctx.manifest.filer_ciks(cik)
            )
            table.add_row(
                t, str(rep.parsed), str(rep.skipped), str(rep.passages), str(facts),
                str(len(rep.warnings)),
            )  # fmt: skip
        out.print(table)
    except SecError as exc:
        _fail(exc)
    finally:
        conn.close()
        ctx.sec.close()


@app.command()
def prefilter(universe: UniverseOpt = "pilot", ticker: TickerOpt = None) -> None:
    """Tag AI keywords and forward-looking cues; mark boilerplate duplicates. Costs $0."""
    ctx = _ctx()
    members = _members(ctx, universe, ticker)
    ticker_cik = _ciks_for(ctx, members)
    conn = db.connect(ctx.paths.database)
    try:
        table = Table(title=f"Prefilter ({ctx.lexicon.version})")
        for col in ("ticker", "passages", "AI keyword", "+ forward cue", "unique AI", "dups"):
            table.add_column(col, justify="left" if col == "ticker" else "right")
        for t, cik in ticker_cik.items():
            s = parse_stage.prefilter_company(conn, cik, ctx.lexicon)
            table.add_row(
                t, str(s["passages"]), str(s["kw"]), str(s["kw_fwd"]), str(s["kw_canonical"]),
                str(s["dups"]),
            )  # fmt: skip
        out.print(table)
    finally:
        conn.close()


@app.command()
def stats(universe: UniverseOpt = "pilot", ticker: TickerOpt = None) -> None:
    """Per-company counts: filings, passages, keyword hits, dedup rate, XBRL facts."""
    ctx = _ctx()
    members = _members(ctx, universe, ticker)
    ticker_cik = _ciks_for(ctx, members)
    conn = db.connect(ctx.paths.database)
    try:
        rows = db.company_stats(conn, list(ticker_cik.values()))
    finally:
        conn.close()
    sector = {m.ticker: m.sector for m in members}
    table = Table(title=f"Corpus: {universe}")
    cols = (
        "ticker", "sector", "10-K", "10-Q", "8-K", "passages", "AI kw", "kw+fwd",
        "unique AI", "dedup %", "XBRL facts",
    )  # fmt: skip
    for col in cols:
        table.add_column(col, justify="left" if col in ("ticker", "sector") else "right")
    totals = defaultdict(int)
    for t, cik in ticker_cik.items():
        r = rows.get(cik, {})
        kw, uniq = r.get("kw", 0), r.get("kw_canonical", 0)
        for k in ("10-K", "10-Q", "8-K", "passages", "kw", "kw_fwd", "kw_canonical", "facts"):
            totals[k] += r.get(k, 0)
        table.add_row(
            t, sector.get(t, ""), str(r.get("10-K", 0)), str(r.get("10-Q", 0)),
            str(r.get("8-K", 0)), f"{r.get('passages', 0):,}", str(kw), str(r.get("kw_fwd", 0)),
            str(uniq), f"{100 * (kw - uniq) / kw:.0f}" if kw else "-", f"{r.get('facts', 0):,}",
        )  # fmt: skip
    kw, uniq = totals["kw"], totals["kw_canonical"]
    table.add_row(
        "[bold]total[/]", "", str(totals["10-K"]), str(totals["10-Q"]), str(totals["8-K"]),
        f"{totals['passages']:,}", str(kw), str(totals["kw_fwd"]), str(uniq),
        f"{100 * (kw - uniq) / kw:.0f}" if kw else "-", f"{totals['facts']:,}",
    )  # fmt: skip
    out.print(table)


def main() -> None:  # pragma: no cover
    sys.exit(app())


# ---------------------------------------------------------------------------- labeling


@app.command()
def packets(
    universe: UniverseOpt = "pilot",
    total: Annotated[int, typer.Option(help="Rows across all companies (~1 min each).")] = 450,
    non_keyword_share: Annotated[
        float, typer.Option(help="Share of random rows with no AI keyword (recall check).")
    ] = 0.05,
    force: Annotated[
        bool, typer.Option("--force", help="Overwrite existing packets and their keys.")
    ] = False,
) -> None:
    """Write Excel labeling packets (one per company) for the finance student. Costs $0."""
    ctx = _ctx()
    members = _members(ctx, universe, None)
    ticker_cik = _ciks_for(ctx, members)
    conn = db.connect(ctx.paths.database)
    try:
        selected = packets_mod.build_packets(
            conn, ticker_cik, ctx.lexicon, exports_dir=ctx.paths.exports_dir,
            gold_dir=ctx.paths.gold_dir, total=total, non_keyword_share=non_keyword_share,
            force=force,
        )  # fmt: skip
    except packets_mod.PacketsExist as exc:
        _fail(exc)
        return
    finally:
        conn.close()
    table = Table(title=f"Labeling packets ({universe})")
    for col in ("ticker", "rows", "AI keyword", "random (no keyword)"):
        table.add_column(col, justify="left" if col == "ticker" else "right")
    for t, rows in selected.items():
        kw = sum(r.sampled_as == "keyword" for r in rows)
        table.add_row(t, str(len(rows)), str(kw), str(len(rows) - kw))
    n = sum(len(r) for r in selected.values())
    table.add_row("[bold]total[/]", str(n), "", "")
    out.print(table)
    out.print(
        f"Excel files: {ctx.paths.exports_dir / 'packets'} (upload these to the shared Drive).\n"
        f"Keys (commit these): {ctx.paths.gold_dir / 'packets'}"
    )


@app.command("import-labels")
def import_labels_cmd(
    folder: Annotated[
        str | None, typer.Option("--dir", help="Folder of returned .xlsx files.")
    ] = None,
) -> None:
    """Check returned packets and write evals/gold/{passages,promises}.csv. Costs $0."""
    ctx = _ctx()
    returned = Path(folder) if folder else ctx.paths.gold_dir / "returned"
    if not returned.is_dir() or not any(returned.glob("*.xlsx")):
        _fail(FileNotFoundError(f"No .xlsx files in {returned}. Put the returned packets there."))
    reports = import_mod.import_labels(returned, ctx.paths.gold_dir)
    table = Table(title="Label import")
    for col in ("file", "company", "labeled", "not labeled yet", "promises", "problems"):
        table.add_column(col, justify="left" if col in ("file", "company") else "right")
    for r in reports:
        table.add_row(
            r.file, r.ticker, str(r.labeled), str(r.unlabeled), str(r.promises),
            f"[red]{len(r.problems)}[/]" if r.problems else "0",
        )  # fmt: skip
    out.print(table)
    report = ctx.paths.gold_dir / "import_report.md"
    if any(r.problems for r in reports):
        out.print(f"[yellow]Some rows need fixing. Send this to the finance student:[/] {report}")
        raise typer.Exit(code=1)
    out.print(f"All rows passed. Report: {report}")


# ---------------------------------------------------------------------------- LLM stages

VariantOpt = Annotated[
    str, typer.Option("--variant", help="Settings variant from config/stages.yaml (A/B tests).")
]
ConfirmOpt = Annotated[
    bool, typer.Option("--confirm", help="Allow a run whose worst case is above $0.50.")
]
DryRunOpt = Annotated[
    bool, typer.Option("--dry-run", help="Print the plan and worst-case cost; send nothing.")
]


def _llm_stage(fn, ctx, conn, ciks, **kw):
    try:
        return fn(ctx, conn, ciks, log=out.print, **kw)
    except (BudgetError, MissingApiKey, OfflineCacheMiss) as exc:
        _fail(exc)


@app.command("filter")
def filter_cmd(
    universe: UniverseOpt = "pilot",
    ticker: TickerOpt = None,
    variant: VariantOpt = "default",
    confirm: ConfirmOpt = False,
    dry_run: DryRunOpt = False,
) -> None:
    """Haiku labels keyword passages promise / hype / none (batched, cached)."""
    ctx = _ctx()
    ciks = list(_ciks_for(ctx, _members(ctx, universe, ticker)).values())
    conn = db.connect(ctx.paths.database)
    try:
        res = _llm_stage(runner.run_filter, ctx, conn, ciks, variant=variant, confirm=confirm,
                         dry_run=dry_run)  # fmt: skip
    finally:
        conn.close()
    if res and res.ran:
        st = res.stats
        labels = ", ".join(f"{k} {v}" for k, v in sorted(st.by_label.items()))
        out.print(f"Classified {st.passages} passages in {st.requests} requests: {labels}.")
        for e in st.errors[:10]:
            err.print(f"  {e}")


@app.command("extract")
def extract_cmd(
    universe: UniverseOpt = "pilot",
    ticker: TickerOpt = None,
    variant: VariantOpt = "default",
    filter_variant: Annotated[str, typer.Option(help="Which filter results to use.")] = "default",
    confirm: ConfirmOpt = False,
    dry_run: DryRunOpt = False,
) -> None:
    """Haiku extracts promise and hype statements; code verifies every quote verbatim."""
    ctx = _ctx()
    ciks = list(_ciks_for(ctx, _members(ctx, universe, ticker)).values())
    conn = db.connect(ctx.paths.database)
    try:
        res = _llm_stage(
            runner.run_extract, ctx, conn, ciks, variant=variant,
            filter_variant=filter_variant, confirm=confirm, dry_run=dry_run,
        )  # fmt: skip
        if res and res.ran:
            counts = runner.run_dedupe(conn, variant)
    finally:
        conn.close()
    if res and res.ran:
        st = res.stats
        out.print(
            f"Extracted {st.statements} verified statements ({st.promises} promises, "
            f"{st.hype} hype) from {st.passages} passages. Quote retries: {st.retried}; "
            f"quotes dropped after retry: {st.dropped_quotes}; errors: {len(st.errors)}. "
            f"Promise clusters: {counts['clusters']}."
        )
        for e in st.errors[:10]:
            err.print(f"  {e}")


@app.command("dedupe")
def dedupe_cmd(variant: VariantOpt = "default") -> None:
    """Merge restatements of the same promise into clusters. Costs $0."""
    ctx = _ctx()
    conn = db.connect(ctx.paths.database)
    try:
        counts = runner.run_dedupe(conn, variant)
    finally:
        conn.close()
    out.print(f"{counts['statements']} promise statements -> {counts['clusters']} clusters.")


@app.command("batches")
def batches_cmd() -> None:
    """List submitted batches whose results have not been collected yet."""
    ctx = _ctx()
    pending = ctx.llm.batch_log.uncollected()
    if not pending:
        out.print("No uncollected batches.")
        return
    for b in pending:
        out.print(f"{b['batch_id']}  stage={b['stage']}  run={b['run_id']}  "
                  f"requests={len(b['requests'])}  submitted={b['ts']}")  # fmt: skip
    out.print("Collect one with: aipb batch-collect <batch_id> (it is already paid for).")


@app.command("batch-collect")
def batch_collect_cmd(batch_id: str) -> None:
    """Collect an ended batch from an interrupted run, so its outputs are never paid twice."""
    ctx = _ctx()
    try:
        res = ctx.llm.collect(batch_id)
    except (RuntimeError, MissingApiKey) as exc:
        _fail(exc)
        return
    ok = sum(r.status == "ok" for r in res.values())
    out.print(f"Collected {len(res)} results ({ok} ok) into the cache and ledger. Re-run the "
              "stage command to store them; it will be served from cache at $0.")  # fmt: skip


# ---------------------------------------------------------------------------- evals


@app.command("split")
def split_cmd(
    universe: UniverseOpt = "pilot",
    force: Annotated[bool, typer.Option("--force", help="Replace the frozen split.")] = False,
) -> None:
    """Freeze the dev / held-out test split (grouped by company) in evals/splits.json."""
    ctx = _ctx()
    members = _members(ctx, universe, None)
    path = ctx.paths.evals_dir / "splits.json"
    rec = split_mod.freeze_split(path, {m.ticker: m.sector for m in members}, force=force)
    out.print(f"dev:  {', '.join(rec['dev'])}\ntest: {', '.join(rec['test'])}\n({path})")


@app.command("eval")
def eval_cmd(
    split: Annotated[str, typer.Option(help="dev (tune on it) or test (milestones only).")] = "dev",
    variant: VariantOpt = "default",
    filter_variant: Annotated[str, typer.Option(help="Which filter results to score.")] = "default",
    milestone: Annotated[
        str | None, typer.Option(help="Required for --split test: why test is reported now.")
    ] = None,
    universe: UniverseOpt = "pilot",
) -> None:
    """Score stored outputs against the gold labels. Costs $0 (no API calls)."""
    ctx = _ctx()
    if split not in ("dev", "test"):
        _fail(ValueError("--split must be dev or test"))
    if split == "test" and not milestone:
        _fail(ValueError("The held-out test set is reported only at milestones. Add "
                         "--milestone \"<reason>\" (it is recorded in the results)."))  # fmt: skip
    members = _members(ctx, universe, None)
    rec = split_mod.freeze_split(
        ctx.paths.evals_dir / "splits.json", {m.ticker: m.sector for m in members}
    )
    tickers = set(rec[split])
    gold = eval_mod.load_gold(ctx.paths.gold_dir, tickers)
    if not gold:
        _fail(eval_mod.NoGold(
            f"No gold labels for the {split} companies ({', '.join(sorted(tickers))}) yet. "
            "Nick labels the packets, then run aipb import-labels."))  # fmt: skip
    fcfg = stage_settings(ctx.stages, "filter", filter_variant)
    ecfg = stage_settings(ctx.stages, "extract", variant)
    conn = db.connect(ctx.paths.database)
    try:
        ciks = list(_ciks_for(ctx, [m for m in members if m.ticker in tickers]).values())
        counts = db.window_counts(conn, ciks)
        result = eval_mod.evaluate(
            conn, gold, variant=variant, filter_variant=filter_variant,
            route=lambda label, conf: fl_mod.routed_to_extraction(fcfg, label, conf),
            corpus_counts=counts,
        )  # fmt: skip
    finally:
        conn.close()
    sha = _git_sha(ctx.paths.root)
    prompts = sorted({f"filter/{fcfg['prompt']}", f"extract/{ecfg['prompt']}"})
    models = sorted({fcfg["model"], ecfg["model"]})
    result.update(
        created=utc_now(), git_sha=sha, split=split, variant=variant,
        filter_variant=filter_variant, prompts=prompts, models=models, milestone=milestone,
        cost_usd=eval_mod.costs(ctx.ledger, set(models), set(prompts)),
    )  # fmt: skip
    stamp = f"{eval_mod.timestamp(sha)}_{split}_{variant}"
    dis = disagree_mod.write_disagreements(
        ctx.paths.exports_dir / "disagreements" / f"{stamp}.xlsx",
        result["disagreements"], f"{split} split, variant {variant}, {stamp}",
    )  # fmt: skip
    result["disagreements_file"] = str(dis.relative_to(ctx.paths.root))
    jpath, mpath = eval_mod.write_results(ctx.paths.evals_dir / "results", result, stamp)
    eval_mod.update_readme(ctx.paths.root / "README.md", eval_mod.history_row(result))
    out.print(eval_mod.render_markdown(result))
    out.print(f"Results: {jpath.name} and {mpath.name} in evals/results/. "
              f"Disagreements for Nick: {result['disagreements_file']}")  # fmt: skip


@app.command("compare")
def compare_cmd(split: Annotated[str, typer.Option(help="dev or test.")] = "dev") -> None:
    """A/B table from saved eval results: F1 with intervals, cost, cost per F1 point. $0."""
    ctx = _ctx()
    results = compare_mod.latest_results(ctx.paths.evals_dir / "results", split)
    if not results:
        _fail(FileNotFoundError(f"No {split} eval results yet. Run aipb eval first."))
    text = compare_mod.table(results)
    out.print(text)
    path = ctx.paths.evals_dir / "results" / f"ab_{split}.md"
    body = f"# A/B comparison ({split} split)\n\n{text}\n"
    path.write_text(body, encoding="utf-8", newline="\n")
    out.print(f"Saved to {path.relative_to(ctx.paths.root)}")


@app.command("calibrate")
def calibrate_cmd(
    stage: Annotated[str, typer.Option(help="filter or extract.")] = "filter",
    sample: Annotated[int, typer.Option(help="Requests to count.")] = 20,
    universe: UniverseOpt = "pilot",
) -> None:
    """Check the cost estimator against the free count_tokens endpoint (needs the key, $0)."""
    ctx = _ctx()
    ciks = list(_ciks_for(ctx, _members(ctx, universe, None)).values())
    conn = db.connect(ctx.paths.database)
    try:
        cfg = stage_settings(ctx.stages, stage, None)
        prompt = load_prompt(ctx.paths.prompts_dir, stage, cfg["prompt"])
        if stage == "filter":
            reqs, _ = fl_mod.build_requests(fl_mod.candidates(conn, ciks), cfg, prompt)
        else:
            from aipb.stages import extract as ex_mod

            rows = ex_mod.candidates(conn, stage_settings(ctx.stages, "filter", None), ciks)
            reqs = [ex_mod.build_request(r, cfg, prompt) for r in rows]
    finally:
        conn.close()
    if not reqs:
        _fail(ValueError(f"No {stage} requests to sample (run the earlier stages first)."))
    step = max(1, len(reqs) // sample)
    picked = reqs[::step][:sample]
    est = actual = 0
    chars = 0
    try:
        for r in picked:
            est += ctx.estimator.input_tokens(r.params)
            actual += ctx.llm.count_tokens(r.params)
            body = {k: r.params[k] for k in ("system", "messages") if k in r.params}
            chars += len(json.dumps(body, ensure_ascii=False))
    except (MissingApiKey, OfflineCacheMiss) as exc:
        _fail(exc)
    out.print(
        f"{len(picked)} {stage} requests: estimator {est:,} tokens vs count_tokens {actual:,} "
        f"({est / actual:.2f}x). Observed {chars / actual:.2f} chars per token; config uses "
        f"{ctx.estimator.chars_per_token}. The estimate should stay above the count."
    )


# ---------------------------------------------------------------------------- verification


@app.command("verify")
def verify_cmd(
    universe: UniverseOpt = "pilot",
    ticker: TickerOpt = None,
    variant: VariantOpt = "default",
    tier2: Annotated[bool, typer.Option("--tier2/--no-tier2", help="Run escalations.")] = True,
    tier2_variant: Annotated[str, typer.Option(help="Tier 2 settings variant.")] = "default",
    confirm: ConfirmOpt = False,
    dry_run: DryRunOpt = False,
) -> None:
    """Tier 1 judge for every promise (batched), Tier 2 agent for escalations (capped)."""
    ctx = _ctx()
    ciks = list(_ciks_for(ctx, _members(ctx, universe, ticker)).values())
    conn = db.connect(ctx.paths.database)
    try:
        _plan, st = verify_runner.run_verify(
            ctx, conn, ciks, variant=variant, t2_variant=tier2_variant, tier2_on=tier2,
            confirm=confirm, dry_run=dry_run, log=out.print,
        )  # fmt: skip
    except (BudgetError, MissingApiKey, OfflineCacheMiss) as exc:
        _fail(exc)
        return
    finally:
        conn.close()
    if not dry_run:
        t1 = ", ".join(f"{k} {v}" for k, v in sorted(st.tier1.items()))
        stops = ", ".join(f"{k} {v}" for k, v in sorted(st.tier2_stops.items())) or "none"
        out.print(f"{st.clusters} promises. Tier 1: {t1}. Escalated: {st.escalated}; Tier 2 "
                  f"ran {st.tier2_done} ({stops}); left for later (run cap): "
                  f"{st.tier2_skipped_cap}.")  # fmt: skip


@app.command("explain")
def explain_cmd(
    universe: UniverseOpt = "pilot",
    ticker: TickerOpt = None,
    variant: VariantOpt = "default",
    confirm: ConfirmOpt = False,
    dry_run: DryRunOpt = False,
) -> None:
    """Cited 2-4 sentence explanations for statuses that can be published (batched)."""
    ctx = _ctx()
    ciks = list(_ciks_for(ctx, _members(ctx, universe, ticker)).values())
    conn = db.connect(ctx.paths.database)
    try:
        _plan, counts = verify_runner.run_explain(ctx, conn, ciks, variant=variant,
                                                  confirm=confirm, dry_run=dry_run,
                                                  log=out.print)  # fmt: skip
        if not dry_run:
            gate_counts = verify_runner.run_gate(ctx, conn, variant)
    except (BudgetError, MissingApiKey, OfflineCacheMiss) as exc:
        _fail(exc)
        return
    finally:
        conn.close()
    if not dry_run:
        out.print(f"Explanations: {counts.get('ok', 0)} passed citation and wording checks, "
                  f"{counts.get('failed_checks', 0)} did not (those stay pending).")  # fmt: skip
        out.print("Gate: " + ", ".join(f"{k} {v}" for k, v in sorted(gate_counts.items())))


@app.command("gate")
def gate_cmd(variant: VariantOpt = "default") -> None:
    """Decide what can be published and what stays 'Status pending review'. Costs $0."""
    ctx = _ctx()
    conn = db.connect(ctx.paths.database)
    try:
        counts = verify_runner.run_gate(ctx, conn, variant)
    finally:
        conn.close()
    out.print(
        "Gate: " + (", ".join(f"{k} {v}" for k, v in sorted(counts.items())) or "nothing yet")
    )


@app.command("status")
def status_cmd(ticker: TickerOpt = None, variant: VariantOpt = "default") -> None:
    """Show each promise's published status, with the reason when it is pending."""
    ctx = _ctx()
    conn = db.connect(ctx.paths.database)
    try:
        rows = conn.execute(
            "SELECT c.ticker, k.first_stated, p.quote, f.label, f.reason FROM final_status f "
            "JOIN promise_clusters k ON k.cluster_id=f.cluster_id AND k.variant=f.variant "
            "JOIN promises p ON p.promise_id=k.canonical_promise_id "
            "JOIN companies c ON c.cik=k.cik WHERE f.variant=? ORDER BY c.ticker, k.first_stated",
            (variant,),
        ).fetchall()
    finally:
        conn.close()
    wanted = {t.upper() for t in ticker} if ticker else None
    table = Table(title="Promise statuses")
    for col in ("ticker", "first stated", "promise", "status", "why"):
        table.add_column(col)
    for r in rows:
        if wanted and r["ticker"] not in wanted:
            continue
        table.add_row(r["ticker"], r["first_stated"], r["quote"][:90], r["label"],
                      r["reason"] or "")  # fmt: skip
    out.print(table if rows else "No statuses yet (run verify, explain).")


@app.command("status-packets")
def status_packets_cmd(
    n: Annotated[int, typer.Option(help="Promises to label (about 5-8 minutes each).")] = 60,
    force: Annotated[bool, typer.Option("--force", help="Overwrite an existing key.")] = False,
) -> None:
    """Excel packet for Nick to label promise statuses (evidence shown, verdicts hidden)."""
    ctx = _ctx()
    key_dir = ctx.paths.gold_dir / "status_packets" / status_mod.VERSION
    if (key_dir / "key.csv").exists() and not force:
        msg = (f"A status packet key already exists in {key_dir}. Labels are matched "
               "through it; use --force only before labeling starts.")  # fmt: skip
        _fail(FileExistsError(msg))
    conn = db.connect(ctx.paths.database)
    try:
        out_path = ctx.paths.exports_dir / "packets" / f"status_packet_{status_mod.VERSION}.xlsx"
        rows = status_mod.build(conn, out_path, key_dir, n=n)
    finally:
        conn.close()
    if not rows:
        _fail(ValueError("No promise clusters yet: run filter, extract and verify first."))
    out.print(f"Status packet: {rows} promises -> {out_path}. Key: {key_dir / 'key.csv'}")


@app.command("import-statuses")
def import_statuses_cmd(
    path: Annotated[str | None, typer.Option("--file", help="The returned xlsx.")] = None,
) -> None:
    """Check Nick's returned status packet and write evals/gold/statuses.csv. Costs $0."""
    ctx = _ctx()
    key_dir = ctx.paths.gold_dir / "status_packets" / status_mod.VERSION
    returned = Path(path) if path else (
        ctx.paths.gold_dir / "returned" / f"status_packet_{status_mod.VERSION}.xlsx")  # fmt: skip
    if not returned.exists():
        _fail(FileNotFoundError(f"{returned} not found. Put Nick's returned file there."))
    rep = status_mod.import_statuses(returned, key_dir, ctx.paths.gold_dir / "statuses.csv")
    out.print(f"{rep.labeled} of {rep.rows} promises labeled -> evals/gold/statuses.csv")
    for p in rep.problems:
        err.print(f"  {p}")
    if rep.problems:
        raise typer.Exit(code=1)


@app.command("eval-status")
def eval_status_cmd(variant: VariantOpt = "default") -> None:
    """Statuses vs gold: accuracy, per-class recall, published precision vs coverage. $0."""
    ctx = _ctx()
    gold = status_eval_mod.load_gold(ctx.paths.gold_dir / "statuses.csv")
    if not gold:
        _fail(eval_mod.NoGold("No gold statuses yet. Nick labels the status packet, then "
                              "run aipb import-statuses."))  # fmt: skip
    conn = db.connect(ctx.paths.database)
    try:
        result = status_eval_mod.evaluate(
            conn, gold, variant=variant, threshold=verify_runner.gate_threshold(ctx),
            load_verdict=verify_runner.load_verdict,
            errors=verify_runner.open_error_reports(ctx),
        )  # fmt: skip
    finally:
        conn.close()
    sha = _git_sha(ctx.paths.root)
    stamp = f"{eval_mod.timestamp(sha)}_status_{variant}"
    results_dir = ctx.paths.evals_dir / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    result.update(created=utc_now(), git_sha=sha, variant=variant, kind="status")
    (results_dir / f"{stamp}.json").write_text(json.dumps(result, indent=2, default=str) + "\n",
                                               encoding="utf-8", newline="\n")  # fmt: skip
    text = status_eval_mod.render(result)
    (results_dir / f"{stamp}.md").write_text(text, encoding="utf-8", newline="\n")
    out.print(text)


# ---------------------------------------------------------------------------- publish + site


@app.command("publish")
def publish_cmd(variant: VariantOpt = "default") -> None:
    """Export gate-approved results to data/site/ (committed) for the site and newsletter."""
    ctx = _ctx()
    conn = db.connect(ctx.paths.database)
    try:
        verify_runner.run_gate(ctx, conn, variant)
        res = publish_mod.publish(conn, ctx.paths.data / "site", ctx.paths.error_reports, variant)
    finally:
        conn.close()
    out.print(f"Published {res['published']} of {res['promises']} promises with a status (the "
              f"rest show 'Status pending review'); {res['events']} new or changed.")  # fmt: skip


@app.command("site")
def site_cmd() -> None:
    """Render the static site from data/site/site_data.json into site/dist. Costs $0."""
    ctx = _ctx()
    res = site_mod.build_site(
        ctx.paths.config / "site.yaml", ctx.paths.data / "site" / "site_data.json",
        ctx.paths.evals_dir, ctx.paths.root / "site" / "dist",
    )  # fmt: skip
    out.print(f"Built {res['pages']} pages ({res['companies']} companies, {res['promises']} "
              "promises) in site/dist. Open site/dist/index.html to preview.")  # fmt: skip


# ---------------------------------------------------------------------------- newsletter

IssueOpt = Annotated[
    str | None, typer.Option("--issue", help="Issue key, e.g. free-2026-12 (default: this month).")
]


def _newsletter_cfg(ctx: AppContext) -> dict:
    import yaml

    return yaml.safe_load((ctx.paths.config / "newsletter.yaml").read_text(encoding="utf-8"))


def _services(ctx: AppContext):
    """Buttondown and GitHub clients from secrets. Tests replace this function."""
    s = ctx.settings
    bd = nl_services.Buttondown(s.secret(s.buttondown_api_key))
    gh = nl_services.GitHub(s.secret(s.github_token), s.github_repository)
    return bd, gh


def _issue_key(issue: str | None) -> str:
    return issue or f"free-{date.today():%Y-%m}"


def _build_issue(ctx: AppContext, key: str, use_llm: bool):
    cfg = _newsletter_cfg(ctx)
    issue = nl_issue.build_issue(ctx.paths.data / "site", ctx.paths.data / "sends" /
                                 "newsletter_log.jsonl", key, name=cfg["name"],
                                 min_items=int(cfg["min_items"]))  # fmt: skip
    if use_llm:
        conn = db.connect(ctx.paths.database)
        try:
            names = [r[0] for r in conn.execute("SELECT name FROM companies")]
        finally:
            conn.close()
        nl_intro.write_intro(ctx, issue, names, max_usd=Decimal(str(cfg["intro_max_usd"])))
    else:
        issue.intro = nl_issue.template_intro(issue)
    return issue, issue.markdown(cfg["site_url"].rstrip("/")), cfg


@app.command("newsletter-preview")
def newsletter_preview_cmd(
    issue: IssueOpt = None,
    no_llm: Annotated[bool, typer.Option("--no-llm", help="Template intro only.")] = False,
) -> None:
    """Render an issue locally (exports/newsletter/<key>.{md,html}). Sends nothing."""
    ctx = _ctx()
    key = _issue_key(issue)
    try:
        iss, body, _cfg = _build_issue(ctx, key, not no_llm)
    except nl_issue.IssueError as exc:
        _fail(exc)
        return
    outdir = ctx.paths.exports_dir / "newsletter"
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / f"{key}.md").write_text(body, encoding="utf-8", newline="\n")
    (outdir / f"{key}.html").write_text(nl_render.to_html(body, iss.subject), encoding="utf-8")
    out.print(f"{iss.subject}: {len(iss.item_ids)} items, intro from {iss.intro_source}.")
    for n in iss.notes:
        out.print(f"  note: {n}")
    out.print(f"Preview: {outdir / (key + '.html')}")


def _rails(ctx: AppContext, cfg: dict) -> nl_flow.Rails:
    return nl_flow.Rails(
        autosend=ctx.settings.newsletter_autosend,
        ramp_up_test_issues=int(cfg["ramp_up_test_issues"]),
        hold_label=cfg["hold_label"],
        founders=ctx.settings.founders(),
    )


@app.command("newsletter-stage")
def newsletter_stage_cmd(issue: IssueOpt = None) -> None:
    """Build the issue, create the Buttondown draft, email the founders, open the preview
    issue. The send happens 24 hours later unless someone adds the `hold` label."""
    ctx = _ctx()
    key = _issue_key(issue)
    log = ctx.paths.data / "sends" / "newsletter_log.jsonl"
    gh = None
    try:
        bd, gh = _services(ctx)
        iss, body, cfg = _build_issue(ctx, key, True)
        rec = nl_flow.stage(iss, body, log, bd, gh, _rails(ctx, cfg), "the next scheduled run")
    except (nl_issue.IssueError, nl_services.ServiceError, nl_flow.SendBlocked) as exc:
        nl_flow.report_failure(gh, key, str(exc), log)
        _fail(exc)
        return
    out.print(f"Staged {key}: draft {rec['email_id']}, preview issue #{rec['github_issue']}.")


@app.command("newsletter-send")
def newsletter_send_cmd(issue: IssueOpt = None) -> None:
    """Send a staged issue if every rail allows it (idempotent; fails closed)."""
    ctx = _ctx()
    key = _issue_key(issue)
    log = ctx.paths.data / "sends" / "newsletter_log.jsonl"
    gh = None
    try:
        bd, gh = _services(ctx)
        rec = nl_flow.send(key, log, bd, gh, _rails(ctx, _newsletter_cfg(ctx)))
    except nl_flow.SendBlocked as exc:
        if "cancelled" in str(exc):
            out.print(f"Not sent: {exc}")
            return
        nl_flow.report_failure(gh, key, str(exc), log)
        _fail(exc)
        return
    except nl_services.ServiceError as exc:
        nl_flow.report_failure(gh, key, str(exc), log)
        _fail(exc)
        return
    out.print(f"{key}: {rec['event']} ({rec.get('reason', 'to subscribers')}).")
