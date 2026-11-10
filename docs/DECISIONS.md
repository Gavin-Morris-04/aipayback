# Decisions

Each entry: context, options considered, choice, evidence. Newest last. Plain English.

---

## D1. Separate API key name so Claude Code can't spend the app's credit (Phase 0, 2026-11-10)
**Context.** The project has $19 of API credit in total. Claude Code bills `ANTHROPIC_API_KEY` instead of the subscription plan whenever that variable is set, so one stray `export` could silently spend the app's money on coding sessions.
**Options.** (a) Use `ANTHROPIC_API_KEY` and be careful. (b) Give the app its own variable name and pass it explicitly.
**Choice.** (b) The app reads `AIPAYBACK_API_KEY` from `.env` and passes it as `Anthropic(api_key=...)`. If it's missing, the client refuses instead of falling back to the SDK's defaults. `aipb doctor` and every CLI command warn if `ANTHROPIC_API_KEY` is set, and the secret hook blocks committing an `ANTHROPIC_API_KEY=` line.
**Evidence.** Checked on 2026-11-10: `ANTHROPIC_API_KEY` is unset at the process, user and machine levels. Tests prove the app key is passed explicitly even when `ANTHROPIC_API_KEY` is set (`tests/unit/test_llm_client.py`).

## D2. Reserve-then-settle budget guard with a committed ledger (Phase 0)
**Context.** The $15 app cap must hold across several devices, a GitHub Actions cron job, crashes and asynchronous batches.
**Options.** (a) Check spend after each call. (b) Rely on the Console's spend limit. (c) Reserve the worst case before a run, then settle the actual cost.
**Choice.** (c) plus (b) as a second, independent layer.
- Before a run, the guard reserves input estimate + `max_tokens` for every request, and refuses if spent + open reservations + estimate would pass $15.
- Runs over $0.50 need `--confirm`.
- A crashed run keeps its reservation until a human releases it (fail closed).
- The ledger is append-only JSONL in git with `merge=union`, so every device sees the same spend.
- Money is `Decimal`, never float.
**Evidence.** 16 guard and ledger unit tests (12 in `test_guard.py`, 4 in `test_ledger.py`): cap, confirm threshold, reservation lifecycle, crash, union-merge duplicates, corrupt-line refusal.

## D3. Exact prices in config, verified against the official page (Phase 0)
**Context.** The brief quoted approximate prices. The real Haiku 5.5 pricing has a 100k-token tier and separate prices for 5-minute and 1-hour cache writes.
**Choice.** `config/pricing.yaml` stores the official per-MTok prices, dated 2026-11-10:
- Haiku 5.5, prompts ≤100k: $0.10 input / $0.125 5-minute cache write / $0.20 1-hour cache write / $0.01 cache read / $0.50 output.
- Haiku 5.5, prompts >100k: $0.50 / $0.625 / $1.00 / $0.05 / $2.50.
- Sonnet 5.5: $2 / $2.50 / $4 / $0.10 / $10.
- Batch: ×0.5, stacking with the cache prices.

The 100k threshold counts cache reads and writes as part of the prompt (per the pricing page), so the guard refuses any prompt over 100,000 tokens.
**Evidence.** `tests/unit/test_pricing.py` checks the tier boundary (100,000 vs 100,001) and the case where cached tokens push a prompt over 100k.

## D4. Thinking is set explicitly on every stage (Phase 0)
**Context.** Haiku 5.5 runs adaptive thinking at effort `medium` by default, and thinking tokens bill as output. A classifier that thinks for 300 tokens before answering "no" would cost about 10× what it should.
**Choice.** `config/stages.yaml` sets thinking or effort per stage. Classification starts with thinking `disabled`. Extraction and judging get an A/B test in Phase 2: thinking off vs effort `low`, measured on the dev set.

## D5. Never pay twice: a content-addressed output cache in git (Phase 0)
**Choice.** Each output is keyed by (sha256 of the canonical request JSON, prompt version, model) and stored in `data/outputs/<stage>/<shard>.jsonl`, which is committed. Offline mode (used in CI) raises on a cache miss instead of calling the API. Refusals are logged and billed but not cached, so a retry is possible.

## D6. Hosting on GitHub Pages; private repo until launch (planning, 2026-11-10)
**Context.** The brief suggested Vercel or Cloudflare Pages. Vercel's free Hobby plan forbids commercial use, which rules it out for a site with paid tiers. The CS student chose GitHub Pages.
**Choice.** GitHub Pages. Pages from a private repo needs GitHub Pro (free with the Student Developer Pack). Without Pro, an Action pushes only the built site to a small public repo. Cloudflare Pages stays a one-workflow fallback if GitHub Pages' commercial-use terms ever become an issue. The source repo goes public at the Phase 5 launch, after a full-history secret scan and the finance student's consent to publish the gold labels.

## D7. Local-only pre-commit hooks (Phase 0)
**Context.** This machine needs the OS certificate store for TLS (`uv --system-certs`), which tends to break pre-commit's own environment downloads.
**Choice.** All hooks are `language: system` and run inside the project's uv environment: a custom key-pattern blocker, `detect-secrets` with a baseline, and ruff. CI adds a gitleaks scan of the full history.

## D8. Makefile wraps the CLI; make is optional (Phase 0)
**Context.** The brief specifies a Makefile, but `make` isn't installed on the main Windows machine.
**Choice.** All logic lives in the `aipb` typer CLI, and each Makefile target is one line (`uv run aipb ...`). On Windows you can run the CLI directly or install make with winget. CI and cloud sessions run on Linux, where make exists.

## D9. Finance-student files go through Google Drive (planning, 2026-11-10)
**Choice.** Labeling packets are `.xlsx` files with dropdowns, frozen headers and SEC links, shared in a Drive folder. The CS student copies the returned files into `evals/gold/returned/`, and `aipb import-labels` validates them and writes the canonical CSVs. The finance student never needs Git.

## Upcoming decisions (recorded when made)
- Citations vs structured outputs. They can't be combined in one call (the API returns a 400), so the cited explanation is a separate step after the structured verdict (Phase 3).
- Tier 2 agent as a manual loop, so every turn is logged and capped (Phase 3).
- Sonnet use, decided by the capped A/B test (Phase 2).
