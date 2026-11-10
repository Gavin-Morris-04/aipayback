# Progress

_Last updated: 2026-11-10 (Phase 1, checkpoint 1)_

## Current phase: 1, pilot ingestion, labeling packets, outreach and discovery kit

Phase 0 is complete except the smoke test, which waits on the Console key (see the table below).
Gavin said "continue" on 2026-11-10, so Phase 1 started; it spends $0 of API credit.

### Phase 1 done so far
- `src/aipb/sec/`: SEC client (8 req/s token bucket, backoff on 429/5xx, immutable disk
  cache for filing documents, max-age cache for listings, offline mode), ticker→CIK, filing
  selection (10-K, 10-Q, 8-K Item 2.02 → EX-99.1; 10-K EX-13 when the annual report is
  incorporated by reference, e.g. IBM), XBRL company facts, committed manifest
  `data/manifests/filings.jsonl` (URL + sha256 per document).
- `src/aipb/parse/`: HTML/iXBRL → blocks (hidden XBRL, page numbers and running footers
  dropped; layout tables vs data tables), Item sections (10-K `item7`, 10-Q `p1item2`,
  `ex13`, `ex99`), 150–400-word passages with stable IDs, FTS5 index on NFKC-normalized text.
- `src/aipb/stages/`: `ingest`, `parse` (+ XBRL load), `prefilter` (`config/keywords.yaml`
  v kw1; conservative dedup: near-identical AND same numbers).
- CLI: `aipb ingest | parse | prefilter | stats`, and `aipb restore` now re-downloads from
  the manifest, re-parses and re-filters.
- **Placeholder pilot ingested** (`config/universe/pilot.csv`, 10 S&P 100 names, 7 sectors):
  236 filings (30 10-K, 87 10-Q, 119 earnings 8-Ks), 18,381 passages, 1,396 AI-keyword
  passages, 1,128 after dedup, 99,706 XBRL facts. 555 MB raw download in 72 s, 0 errors.
- Gotcha found: ExxonMobil re-registered in 2026 (new CIK 2115436); its 2024–2025 filings
  are under CIK 34088. Universe files now take `extra_ciks`, and ingest warns when a
  company has too few 10-K/10-Q filings.

### Phase 1 still to do (in order)
1. Tests + small fixture filings (10-K, 10-Q, 8-K) for the SEC client, parser, prefilter,
   manifest and CLI (all offline).
2. `aipb packets` (xlsx per company for the finance student) and `aipb import-labels`.
3. `docs/finance/`: RUBRIC draft, EVIDENCE_MAP draft, LABELING_GUIDE, PILOT_PICKER.
4. `gtm/`: outreach messages, discovery guide + notes template, ROI_PLAN.
5. Fresh-clone `aipb restore` check; README, DECISIONS, INTERVIEW_NOTES; phase report.

## Phase 0 record

### Done
- Plan approved. Brief saved in `docs/BRIEF.md`, plan in `docs/PLAN.md`, working rules in `CLAUDE.md`.
- uv project (Python 3.12.10, `anthropic` 2.8.0, typer, pydantic-settings), ruff, pytest.
- **Budget guard:**
  - `config/budget.yaml`: $15 cap, $4 reserve locked, $0.50 confirm threshold, 100k prompt limit.
  - `config/pricing.yaml`: official prices, verified 2026-11-10.
  - Reserve-then-settle guard (`src/aipb/budget/guard.py`), Decimal pricing, conservative estimator.
  - Append-only ledger committed in git with union merge.
- **LLM gateway** `src/aipb/llm/client.py`: explicit `AIPAYBACK_API_KEY`, output cache (never pay twice), offline mode, refusal and error logging.
- **CLI `aipb`:** `budget`, `cost-report`, `doctor`, `smoke`, `restore`, `release-run`. The Makefile wraps them.
- **Secret protection:** a custom key-pattern hook plus detect-secrets (pre-commit, local hooks); CI runs the same patterns plus a gitleaks full-history scan.
- **CI:** offline ruff + pytest on every push.
- **Tests:** 51 passing (unit + CLI integration), all offline.
- **Repo:** private at https://github.com/Gavin-Morris-04/aipayback. First push on 2026-11-10; CI and the gitleaks secret scan both green.
- **Acceptance checks:**
  - A planted fake Anthropic key was blocked by the pre-commit hook.
  - A force-added `.env` was blocked.
  - Neither reached history.
  - Note: detect-secrets alone did not catch the planted key; the custom pattern hook did.

### In progress / next step
- Waiting on the humans' setup tasks below. Then `uv run aipb smoke --fresh` makes one ~$0.00002 call, checks that its ledger cost matches the Console, and closes Phase 0.
- Phase 1 (after approval) starts with `src/aipb/sec/` (rate-limited client, ticker→CIK, submissions, filing download), then parsing.

### Blocked / waiting on
| Who | Task | Blocks |
|---|---|---|
| ~~CS student~~ | ~~Create the shared project Gmail~~ **Done:** aipayback.team@gmail.com, set as `SEC_CONTACT_EMAIL` in `.env` on the main PC | — |
| CS student | Create a Console API key with a workspace spend limit (suggested $5/month) and put it in `.env` as `AIPAYBACK_API_KEY` | Phase 0 smoke test |
| CS student | Optional: `winget install ezwinports.make` (otherwise use `uv run aipb ...`) | nothing |
| Finance student | Pick the 10 pilot companies (≥5 sectors, ≥4 AI-heavy) | Phase 1 final ingest |

## Budget
| Spent | Reserved | Remaining under the $15 cap | Locked reserve |
|---|---|---|---|
| $0.00 | $0.00 | $15.00 | $4.00 |

## Latest eval numbers
None yet (Phase 2).

## Resume on any device
```bash
git pull                      # or git clone https://github.com/Gavin-Morris-04/aipayback
cp .env.example .env          # first time only; fill it in
uv sync && uv run pre-commit install
uv run aipb doctor && uv run aipb budget && uv run aipb restore
uv run pytest
```
Then tell Claude Code: **"Read CLAUDE.md and docs/PROGRESS.md, then continue."**

## Gotchas
- **Windows TLS:** uv on this machine needs the OS certificate store. It's set in `pyproject.toml` (`[tool.uv] system-certs = true`).
- **No make on Windows:** use `uv run aipb <command>`, or install make.
- **Never set `ANTHROPIC_API_KEY`:** Claude Code would bill it. `aipb doctor` checks for it.
- **Crashed runs:** a run that crashes keeps its reservation (fail closed). Check `aipb budget`, then `aipb release-run <id> --yes`.
- **Haiku 5.5 thinks by default** (effort medium, billed as output). Every stage must set thinking or effort in `config/stages.yaml`.
