# Progress

_Last updated: 2026-11-10 (end of Phase 1; waiting for approval)_

## Current phase: 1 complete, waiting for Gavin's approval before Phase 2

Phase 1 (pilot ingestion, labeling packets, outreach and discovery kit) is built, tested and pushed. It spent **$0.00** of API credit. Two items carry over and need the humans (table below): the Phase 0 smoke test, which needs the Console key, and the final pilot list, which needs the finance student.

### Phase 1 done
- **SEC pipeline** (`src/aipb/sec/`, `src/aipb/stages/`):
  - Rate-limited, cached EDGAR client (D10).
  - Filing selection: 10-K + EX-13, 10-Q, 8-K Item 2.02 → EX-99.1 (D11).
  - Predecessor CIKs, for ExxonMobil's 2026 re-registration (D12).
  - Committed manifest `data/manifests/filings.jsonl` (239 documents, URL + sha256).
- **Parsing** (`src/aipb/parse/`):
  - iXBRL/HTML → blocks → Item sections → 150–400-word passages with stable IDs; FTS5 on normalized text (D13, D14).
  - XBRL facts filed since 2022 (D16).
- **Prefilter:** AI keywords + forward-looking cues (`config/keywords.yaml`, version kw1). Conservative dedup: near-identical AND the same numbers (D15).
- **Labeling:**
  - `aipb packets`: 450 rows (428 keyword + 22 random), one xlsx per company in `exports/packets/`; keys committed in `evals/gold/packets/v1/` (D17).
  - `aipb import-labels`: plain-English row-level checks; writes `evals/gold/{passages,promises}.csv` and `import_report.md` (D18).
- **Finance docs** (`docs/finance/`): PILOT_PICKER (with real AI-mention counts), RUBRIC draft (with DECIDE proposals and tolerances), EVIDENCE_MAP draft (which XBRL tags each pilot company reports), LABELING_GUIDE (with fictional worked examples).
- **GTM kit** (`gtm/`): outreach for 5 partner types (LinkedIn note, follow-up, email), `outreach/tracker.csv`, a 30-minute discovery guide, a notes template, ROI_PLAN.
- **CLI:** `ingest`, `parse`, `prefilter`, `stats`, `packets`, `import-labels`; `restore` now rebuilds everything. All wrapped in the Makefile (`U=pilot`).
- **Tests:** 106 passing, all offline (a fake SEC on fixture filings for a fictional company). CI conditions (`AIPAYBACK_OFFLINE=true`) also pass.

### Acceptance checks (Phase 1)
| Check | Result |
|---|---|
| All 10 pilot companies ingested, with a counts table | ✅ on the **placeholder** list: 236 filings, 18,381 passages, 1,396 AI-keyword passages (1,128 after dedup, 19% removed), 99,706 XBRL facts, 0 errors. `uv run aipb stats` prints the per-company table. |
| Parser and rate-limit tests pass | ✅ 106 tests |
| Fresh-clone restore rebuilds with zero API calls | ✅ 2026-11-10, temp-folder clone: 2 min 30 s; identical digest of passage IDs, hashes, keywords and dedup marks; 0 LLM calls |
| Packets open correctly in Excel and Google Sheets | ⏳ **Gavin to check** (files in `exports/packets/`) |
| Final pilot list from the finance student | ⏳ placeholder list in use |

### Per-company corpus (placeholder pilot)
| Ticker | Sector | Filings | Passages | AI kw | Unique AI | Unique AI, 2024–25 | XBRL facts |
|---|---|---|---|---|---|---|---|
| IBM | Info Tech | 25 | 1,895 | 257 | 242 | 170 | 10,911 |
| MSFT | Info Tech | 24 | 1,469 | 418 | 309 | 187 | 9,971 |
| CRM | Info Tech | 22 | 1,910 | 423 | 301 | 178 | 7,953 |
| ACN | Info Tech | 22 | 1,161 | 142 | 135 | 97 | 9,744 |
| JPM | Financials | 24 | 4,529 | 28 | 26 | 12 | 20,002 |
| WMT | Cons. Staples | 22 | 1,272 | 35 | 31 | 12 | 6,981 |
| UNH | Health Care | 24 | 1,077 | 31 | 26 | 10 | 8,730 |
| CAT | Industrials | 25 | 1,992 | 10 | 10 | 6 | 10,599 |
| XOM | Energy | 24 | 1,359 | 7 | 7 | 0 | 6,183 |
| VZ | Comm. Services | 24 | 1,717 | 45 | 41 | 16 | 8,632 |
| **Total** | | **236** | **18,381** | **1,396** | **1,128** | **688** | **99,706** |

### Blocked / waiting on
| Who | Task | Blocks |
|---|---|---|
| CS student | Create a Console API key with a workspace spend limit (suggested $5/month); put it in `.env` as `AIPAYBACK_API_KEY` | Phase 0 smoke test → Phase 2 |
| CS student | Open 2–3 files from `exports/packets/` in Excel **and** Google Sheets: red AI words, dropdowns and links all work? | Phase 1 acceptance |
| CS student | Create the shared Drive folder with `packets/` and `returned/` subfolders. Add Google Doc copies of `docs/finance/RUBRIC.md` and `EVIDENCE_MAP.md` | Finance student's work |
| CS student | Start outreach (`gtm/outreach/`): about 25 messages → 5–8 calls | Phase 2–4 discovery |
| Finance student | Pick the 10 pilot companies (`docs/finance/PILOT_PICKER.md`) | Final ingest + final packets |
| Finance student | Review the RUBRIC draft (DECIDE items) and the EVIDENCE_MAP draft | Phase 2 labeling (rubric), Phase 3 (evidence map) |
| Finance student | Label the packets **after** the final list (about 6–8 hours) | Phase 2 evals |
| CS student | Optional: `winget install ezwinports.make` | nothing |

### Next steps (in order)
1. **When the finance student sends picks:** edit `config/universe/pilot.csv` (add `extra_ciks` if `aipb ingest` warns about too few filings), then run `uv run aipb ingest && uv run aipb parse && uv run aipb prefilter && uv run aipb stats && uv run aipb packets --force`. Upload `exports/packets/*.xlsx` to Drive and commit `evals/gold/packets/` and the manifest.
2. **When the key is in `.env`:** `uv run aipb doctor`, then `uv run aipb smoke --fresh`. Check that the ledger cost matches the Console usage page. That closes Phase 0.
3. **Phase 2 (after approval):** the filter (classify) and extract stages, prompts v1, the eval harness and split, then the dev baseline. It can start on the placeholder corpus while labels are in progress.

## Budget
| Spent | Reserved | Remaining under the $15 cap | Locked reserve |
|---|---|---|---|
| $0.00 | $0.00 | $15.00 | $4.00 |

## Latest eval numbers
None yet (Phase 2).

## Resume on any device
```bash
git pull                      # or git clone https://github.com/Gavin-Morris-04/aipayback
cp .env.example .env          # first time only; fill in SEC_CONTACT_EMAIL (and the key when you have it)
uv sync && uv run pre-commit install
uv run aipb doctor && uv run aipb budget
uv run aipb restore           # re-downloads ~555 MB of SEC filings, rebuilds the DB (~2.5 min, $0)
uv run pytest
```
Then tell Claude Code: **"Read CLAUDE.md and docs/PROGRESS.md, then continue."**

## Gotchas
- **Windows TLS:** uv on this machine needs the OS certificate store. It's set in `pyproject.toml` (`[tool.uv] system-certs = true`). The SEC client uses httpx2, which uses the OS store too.
- **No make on Windows:** use `uv run aipb <command>`, or install make.
- **Never set `ANTHROPIC_API_KEY`:** Claude Code would bill it. `aipb doctor` checks for it.
- **Crashed runs:** a run that crashes keeps its reservation (fail closed). Check `aipb budget`, then `aipb release-run <id> --yes`.
- **Haiku 5.5 thinks by default** (effort medium, billed as output). Every stage must set thinking or effort in `config/stages.yaml`.
- **Raw SEC data is big:** about 555 MB for the 10-company pilot, so expect about 5–6 GB for the S&P 100. It's git-ignored under `data/raw/`; the manifest is what's committed.
- **Re-registered companies:** a ticker resolves to the *current* registrant only. If `aipb ingest` warns about too few 10-K/10-Q filings, find the predecessor CIK on EDGAR and add it to the `extra_ciks` column (XOM → 34088).
- **Packets are tied to their key:** never edit `evals/gold/packets/v1/*_key.csv` by hand. `aipb packets` refuses to overwrite existing keys unless you pass `--force`. Use `--force` only before labeling starts (e.g. for the final pilot list); after that, bump `PACKET_VERSION` in `src/aipb/labeling/schema.py`.
- **Tool escapes:** when Claude Code writes `\u` escapes, they can land in files as literal characters. Check with `grep -nP '[^\x00-\x7F]' src/`.

## Phase 0 record (complete except the smoke test)
- uv project (Python 3.12.10, anthropic 2.8.0), ruff, pytest, typer CLI, Makefile.
- Budget guard: $15 cap, $4 locked reserve, $0.50 confirm threshold, 100k prompt limit, reserve-then-settle, Decimal pricing, a committed append-only ledger (union merge).
- LLM gateway with explicit `AIPAYBACK_API_KEY`, output cache, offline mode.
- Secret protection: a custom key-pattern hook, detect-secrets, and gitleaks in CI. A planted fake key and a force-added `.env` were both blocked.
- Private repo https://github.com/Gavin-Morris-04/aipayback; CI green.
- Project Gmail aipayback.team@gmail.com is `SEC_CONTACT_EMAIL` on the main PC.
