# Progress

_Last updated: 2026-11-11 (Phases 0–5 built; blocked on humans)_

## Where things stand

On 2026-11-10 Gavin said: "Do all the phases until you absolutely cannot proceed without me and Nick's help." So the code for **Phases 0–5 is built, tested (176 offline tests, CI green) and pushed**. Phase 6 is discovery-driven and waits on partner calls.

**API spend so far: $0.00.** No paid run has happened, because there's no API key yet. Every paid stage has been exercised end to end against a fake model.

The money rules are unchanged: runs over $0.50 need `--confirm` plus Gavin's go-ahead in chat, and the S&P 100 run needs explicit cost approval.

| Phase | Built | Waiting on |
|---|---|---|
| 0 Setup, billing safety | ✅ budget guard, ledger, cache, secret hooks, CI | **Gavin:** API key → `aipb smoke --fresh` |
| 1 Ingest, packets, kits | ✅ pilot ingested (placeholder list), packets, finance docs, outreach kit | **Nick:** pilot picks; **Gavin:** check packets in Excel/Sheets |
| 2 Filter, extract, evals | ✅ stages, batches, eval harness, A/B, compare | **Gavin:** key (pilot run ≈ cents); **Nick:** labels |
| 3 Verification, citations | ✅ Tier 1 + Tier 2, explain, gate, status packets + eval | key; **Nick:** ~60 status labels |
| 4 Site, newsletter | ✅ site, publish, newsletter with rails, 3 workflows (all off) | **Gavin:** Buttondown, Pages, secrets/variables; demos |
| 5 S&P 100, findings, launch kit | ✅ sp100 list, findings, solution brief, demo, pilot, objections, LinkedIn drafts | cost approval; real results; launch |
| 6 Monetization, integrations | ⏸ only what partners ask for (Pro alerts, exports, MCP server, paid report) | discovery calls → `gtm/discovery/SYNTHESIS.md` |

## Blocked: who does what

| Who | Task | Unblocks |
|---|---|---|
| Gavin | Console API key with a workspace spend limit (suggested $5/month) → `.env` as `AIPAYBACK_API_KEY` | every paid stage |
| Gavin | Open 2–3 `exports/packets/*.xlsx` in Excel **and** Google Sheets (red words, dropdowns, links) | Phase 1 acceptance |
| Gavin | Drive folder with `packets/` and `returned/`; Google Doc copies of `docs/finance/RUBRIC.md` and `EVIDENCE_MAP.md` | Nick's work |
| Nick | Pick the 10 pilot companies (`docs/finance/PILOT_PICKER.md`) | final packets and split |
| Nick | Decide the RUBRIC DECIDE items; correct EVIDENCE_MAP | labels; `config/evidence_map.yaml` |
| Nick | Label the passage packets (~6–8 h), then the status packet (~60 promises) | evals; confidence threshold |
| Gavin | Outreach (`gtm/outreach/`, ~25 messages) → discovery calls → notes | Phase 6, ROI numbers, demos |
| Gavin | Buttondown account (free tier) → API key as GitHub secret `BUTTONDOWN_API_KEY`; username into `config/site.yaml` | newsletter, signup box |
| Gavin | GitHub secrets `FOUNDER_EMAILS`, `AIPAYBACK_API_KEY`, `SEC_CONTACT_EMAIL`; Pages (GitHub Pro via the Student Pack, or a public deploy repo); LinkedIn URLs and Nick's display name in `config/site.yaml` | site, newsletter, monitor |
| Gavin | Approve the S&P 100 cost (table below) | Phase 5 run |

## When the key arrives: run order (each step prints its worst case first)

```bash
uv run aipb doctor                 # must be all OK
uv run aipb smoke --fresh          # ~$0.00002; compare the ledger cost with the Console usage page
uv run aipb calibrate              # free count_tokens check of the estimator
uv run aipb filter --dry-run       # pilot: 688 passages, 129 requests, worst case $0.08
uv run aipb filter
uv run aipb extract --dry-run && uv run aipb extract
uv run aipb verify --dry-run && uv run aipb verify
uv run aipb explain --dry-run && uv run aipb explain
uv run aipb publish && uv run aipb site && uv run aipb findings
git add -A && git commit -m "pilot run" && git push   # outputs + ledger: never pay twice
```

After Nick's picks: edit `config/universe/pilot.csv`, then `aipb ingest && aipb parse && aipb prefilter && aipb packets --force && aipb split --force` (before any labeling).

After labels return: `aipb import-labels` → `aipb eval` → send `exports/disagreements/*.xlsx` to Nick → the Sonnet A/B (`aipb extract --variant sonnet` on dev passages, capped at $1.50) → `aipb eval --variant sonnet` → `aipb compare` → record the Sonnet decision in DECISIONS.

After the status packet: `aipb status-packets` (after verify) → Nick labels → `aipb import-statuses` → `aipb eval-status` → set `gate.confidence_threshold` in `config/stages.yaml` from the precision-coverage curve.

## S&P 100 (needs explicit cost approval)

**Corpus (ingested, parsed and pre-filtered on 2026-11-10; $0, SEC only):**
- 100 of 100 companies
- 2,407 documents: 293 10-K, 882 10-Q and 1,220 earnings 8-K exhibits
- 179,348 passages and 905,926 XBRL facts; about 4.8 GB of raw files including the pilot, git-ignored
- **3,938 unique AI passages in the 2024–2025 promise window.** These are what the paid stages read.

**Worst case.** It assumes every output uses its full `max_tokens`, so real spend should come in well below it.

| Stage | Worst case | How it's computed |
|---|---|---|
| filter | **$0.54** | exact: 913 batched requests (`aipb filter --dry-run -u sp100`) |
| extract | **≤ $2.84** | upper bound: as if all 3,938 passages were routed on (the real run only extracts what filter routes) |
| verify Tier 1 + explain | **≈ $0.001 per promise** | $0.29 for 300 promises, $0.58 for 600, $0.96 for 1,000 |
| verify Tier 2 (agent) | **≤ $0.50** | hard per-run cap in `config/stages.yaml` |
| **Total** | **≤ $4.84** at 1,000 promises | inside the $11 available ($15 cap minus the $4 locked reserve) |

- The 10 pilot companies are all in the S&P 100, and filter requests are grouped per filing. Once the pilot has run, the S&P 100 run reuses its cached outputs and sends only 784 new filter requests.
- Budget plan:
  - pilot: ≤ $1.37
  - Sonnet A/B: ≤ $1.50
  - S&P 100: ≤ $4.84
  - total: ≤ $7.71 of the $11
- Before the paid run, cross-check the list against S&P DJI or the iShares OEF holdings (D35), and re-check `config/pricing.yaml` (last verified 2026-11-10: all prices matched, D37).

**Data fixes found while ingesting (D37–D38):**
- **BlackRock** moved to a new holding company in 2024. Its early 2024 filings are under predecessor CIK 1364742, now in `extra_ciks`. Ingest now also warns when a company's first 10-K/10-Q comes more than 120 days into the window; the count check alone missed BlackRock.
- **Sandisk** was spun off in 2025 and has no predecessor. Its window starts with its first 10-Q (filed 2025-03-07).
- **Berkshire:** the Wikipedia ticker cell held an HTML comment. The CSV is fixed and BRK-B is ingested.
- **Cisco:** six manifest lines vanished when a commit's pre-commit stash rewrote `filings.jsonl` mid-ingest. Ingest now reloads the manifest from disk after writing, re-appends anything missing and says so.

**To run (after the pilot, and only with Gavin's explicit cost approval):**
```bash
uv run aipb filter -u sp100 --dry-run && uv run aipb filter -u sp100 --confirm
uv run aipb extract -u sp100 --dry-run && uv run aipb extract -u sp100 --confirm
uv run aipb verify -u sp100 --dry-run && uv run aipb verify -u sp100 --confirm
uv run aipb explain -u sp100 --dry-run && uv run aipb explain -u sp100 --confirm
uv run aipb publish && uv run aipb site && uv run aipb findings
git add -A && git commit -m "S&P 100 run" && git push
```

## Budget
| Spent | Reserved | Remaining under the $15 cap | Locked reserve |
|---|---|---|---|
| $0.00 | $0.00 | $15.00 | $4.00 |

## Latest eval numbers
None yet: they need the key (outputs) and Nick's labels (gold).

## Resume on any device
```bash
git pull                      # or git clone https://github.com/Gavin-Morris-04/aipayback
cp .env.example .env          # first time only; SEC_CONTACT_EMAIL (+ the key when you have it)
uv sync && uv run pre-commit install
uv run aipb doctor && uv run aipb budget
uv run aipb restore           # re-downloads SEC filings from the manifest, rebuilds the DB, replays cached LLM outputs ($0)
uv run pytest
```
Then tell Claude Code: **"Read CLAUDE.md and docs/PROGRESS.md, then continue."**

## Gotchas
- **Never set `ANTHROPIC_API_KEY`:** Claude Code would bill it. `aipb doctor` checks for it.
- **Windows TLS:** uv needs the OS certificate store (`[tool.uv] system-certs = true`). httpx2 uses it too.
- **No make on Windows:** use `uv run aipb <command>`.
- **Crashed runs and batches:** a crashed run, or one whose batch outlived its process, keeps its reservation. Check `aipb batches`, then `aipb batch-collect <id>`. Only after checking, `aipb release-run <id> --yes`.
- **Haiku 5.5 thinks by default:** every stage sets thinking or effort in `config/stages.yaml`. Sonnet 5.5 rejects `thinking: disabled`.
- **Raw SEC data is big:** about 555 MB for the pilot and 4.8 GB with the S&P 100. It's git-ignored; the manifest is committed.
- **Re-registered companies:** if `aipb ingest` warns about too few filings or a late first filing, add the predecessor CIK to `extra_ciks` (XOM → 34088, BLK → 1364742). Spin-offs (SNDK, GEV) have no predecessor.
- **Packets and keys:** `aipb packets` and `aipb status-packets` refuse to overwrite keys without `--force`. After labeling starts, bump the packet version instead.
- **Placeholder split:** `evals/splits.json` is for the placeholder list. Run `aipb split --force` once, when the final list arrives.
- **Commit after background jobs finish:** a running ingest writes the manifest, and pre-commit's stash can drop its new lines (it lost six Cisco documents once). Ingest now re-checks the file on disk and re-appends anything missing, but don't commit mid-ingest.
- **Tool escapes (Claude Code on this machine):** in bash heredocs `\\` collapses to `\`, and the Write tool turns `\u` escapes into literal characters. Check with `grep -nP '[^\x00-\x7F]' src/`, and use the Edit tool for strings containing backslashes.
