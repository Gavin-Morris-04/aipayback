# Progress

_Last updated: 2026-11-10 (Phase 0)_

## Current phase: 0, setup, billing safety, budget guard

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
| CS student | Create the shared project Gmail; put it in `.env` as `SEC_CONTACT_EMAIL` | Phase 1 ingest |
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
