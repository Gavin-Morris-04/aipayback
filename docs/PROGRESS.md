# Progress

_Last updated: 2026-11-12 (AI product names fix: dev recall 25% → 54% at $0; checking the 58 promises waits for Gavin's OK)_

## Where things stand

On 2026-11-10 Gavin said: "Do all the phases until you absolutely cannot proceed without me and Nick's help." So the code for **Phases 0–5 is built, tested (196 offline tests, CI green) and pushed**. Phase 6 is discovery-driven and waits on partner calls.

**2026-11-11:**
- Gavin put the API key in `.env` and ran the smoke test (G3, G4). It cost $0.0000102 for 27 input and 15 output tokens on Haiku 5.5.
- Nick's 10 pilot picks are final (N2, D39). Ingest, parse, prefilter, packets and split were rebuilt for them, all at $0.
- The evidence map's coverage was redone for his companies, and fallback tags were added (em2-draft, D40).
- Checklist ticks: Gavin G1–G4; Nick N1–N5. Nick finished the rubric (N3) and the evidence map (N4) in the Google Docs **before** the em2 update, so G8 had to merge the two.
- **G8 done:** Nick's final rubric and evidence map are in the repo and in the code (D41): verify/explain prompts v2, `pending_reason` on verdicts, stricter silent walk-backs, the gross-profit fallback, margin changes in points, evidence map em3, and capex reported apart in findings. Gavin answered the two merge questions the same day: total costs stay as context for AMZN, FDX and META, and the rubric is final.

- **Pilot run (G7) complete: $0.24 in total.** 40 AI promise clusters from 10 companies. 13 have a published status (5 Delivered, all Meta capex; 8 No evidence yet), and 27 are "Status pending review". The site preview (`site/dist/index.html`, 54 pages) and `docs/FINDINGS.md` are built. Nothing is public: `SITE_DEPLOY` is off.
- **Pilot review (D43):**
  - Meta's "approximately $70–72 billion" capex promise is held pending (R-001 in `data/error_reports.csv`), because Tier 1 applied a 95% tolerance to a range.
  - The site and findings now count only analyzed companies. They had said "100 companies", and would have shown unanalyzed companies like Apple as having "no checkable AI promises".
- **Extract v2 (D42).** Extract v1 kept ordinary business guidance from passages that mention AI: 101 of 137 clusters had no AI term in the quote, including all of Caterpillar's. v2 keeps a statement only if code verifies the filing's own words tying it to AI. That leaves 40 AI promise clusters. Stored verdicts and explanations now carry a promise fingerprint, so a reused cluster id can never inherit another promise's result.
- **Status packet (G11)** rebuilt from the 40 AI promises: `exports/packets/status_packet_v1.xlsx` (key committed). The packet built before extract v2 was never sent.
- Checklist ticks (2026-11-12): Gavin G1–G4 and G6–G9 (Claude Code ticked G9 after the import and eval); Nick N1–N6. The checklist page now opens with a "What's left, in order" box for both people.

**2026-11-12:**
- Gavin answered the two D43 questions (D44):
  - **Capex definition: yes.** A capex promise that doesn't state its definition is judged on the company's usual one, as its own filings state it. Code detects Meta's "capital expenditures, including principal payments on finance leases" and adds a summed row, $72.22 billion for 2025, the figure Meta reports.
  - **"Approximately $X to $Y": Gavin asked me to decide.** It follows the range rule (the low end, no tolerance). A near-miss is "No evidence yet" under Nick's partial-delivery rule, with the figure stated. Nick can overrule.
- Prompt v3 (verify_t1, verify_t2, explain) carries both rules, plus the older-baseline margin rule.
- **Tier 1 v3 re-run done ($0.018).** The R-001 Meta item is now Delivered at 0.8, citing $69.69 billion and $72.22 billion against $70–72 billion. 22 of 40 escalate to Tier 2.
- **Waiting on Gavin's go-ahead:** Tier 2 + explain (superseded below: the run now covers all 58 promises). Until it runs, don't publish: the stored Tier 2 verdicts are still v2.
- `evals/gold/returned/` now exists with a README; it hadn't been created before.
- **Nick's passage labels are in (N6, G9).** All 10 pilot packets came back fully labeled: 450 rows (368 none, 46 hype, 25 checkable promise, 11 unsure), 30 with notes, and 31 promises written out. The import found no problems. Nick also returned a labeled IBM packet (95 rows) from the packet list before his picks. Its row IDs match no current key, so it's kept in `evals/gold/returned/not_in_pilot/` and not scored.
- **First eval (dev split: BLK, CAT, META, NVDA, PFE, TSLA; 257 passages, 24 promises):**
  - Extraction: precision 66.7%, recall 25.0%, F1 36.4% [8.7%, 60.0%] (6 matched, 3 extra, 18 missed). For matched promises, claim type and deadline year are 100% right, and the target is 60% right (5).
  - Filter accuracy 83.2%; 89.5% of gold-promise passages go on to extraction. Quotes are 100% verbatim. The prefilter missed none of the 13 random non-keyword passages.
  - Disagreement file for Nick (N7): `exports/disagreements/20261112T201200_8d8e263_dev_default.xlsx` (21 rows; `exports/` is git-ignored, so Gavin uploads it).
- **Why recall is low (dev only):** of the 24 gold promises, **11 are dropped by the ai_link check**, because the link to AI is only a product name (Blackwell, Robotaxi, FSD, Optimus, Cybercab) or, for CAT, Power Generation growth. 2 more were classed "none" by the filter, 2 "hype", and 9 were extracted. This is the known product-name gap (D42). Next fix: an AI product-name list for the ai_link check (and the filter), built from dev rows and company product names, then re-run extract and verify on the pilot after showing the worst case. Nick's CAT Power Generation promises need his note: the rubric excludes general guidance unless the passage ties it to AI.
- **AI product names fix (D45, $0).** Gavin asked for it on 2026-11-12.
  - `config/ai_products.yaml` (ap1) lists product names per company. A link naming one counts only if the company's own filings tie that name to AI in at least 2 filings (41 of 58 names confirmed).
  - Extraction replayed from cache: 58 promise clusters (was 40).
  - Dev eval: recall 25.0% → 54.2%, F1 36.4% → 59.1%, precision 65.0%.
  - New command: `aipb ai-products [--suggest]`.
  - Nick's disagreement file is now `exports/disagreements/20261112T210557_262d836_dev_default.xlsx` (19 rows). It replaces the 21-row file, which Gavin should not send.
- **Waiting on Gavin's OK: check the 58 promises.**
  - Worst case is about $0.55: Tier 1 $0.02 for 18 new promises (40 are cached), Tier 2 at its $0.50 run cap, and explain at about $0.03 for up to 58 statuses.
  - Expected real cost is about $0.10 (the last Tier 2 run was $0.07).
  - Commands: `uv run aipb verify --confirm`, `uv run aipb explain`, then `publish`, `site`, `findings`. Read every published status, close R-001 if the Meta item is right, and commit with the ledger and outputs.
- Gotcha: the first trace of the missed promises also printed the 7 test-split (AMZN) gold promises. Nothing was tuned on them. Build the product-name list from dev rows only, so the test split stays usable for milestones.

**API spend so far: $0.26** (smoke test + pilot + Tier 1 v3). Run `uv run aipb budget` for the exact figure.

The money rules are unchanged: runs over $0.50 need `--confirm` plus Gavin's go-ahead in chat, and the S&P 100 run needs explicit cost approval.

| Phase | Built | Waiting on |
|---|---|---|
| 0 Setup, billing safety | ✅ budget guard, ledger, cache, secret hooks, CI; smoke test passed 2026-11-11 | **Gavin:** check the Console Usage page shows about $0.00001 |
| 1 Ingest, packets, kits | ✅ final pilot (Nick's picks) ingested; packets sent (G6); Nick's rubric and evidence map merged (G8, D41) | — |
| 2 Filter, extract, evals | ✅ pilot filter + extract v2 run (D42); Nick's 450 labels imported; first eval: extraction F1 36.4% (recall 25%) | AI product names fix done (D45): dev F1 59.1%, recall 54.2%. **Nick:** 19 disagreements (N7). A/B after the fix, sized first (D39) |
| 3 Verification, citations | ✅ pilot verify run on Nick's rules; status packet of 40 AI promises built | **Gavin:** upload the status packet (G11); **Nick:** 40 status labels (N8) |
| 4 Site, newsletter | ✅ site, publish, newsletter with rails, 3 workflows (all off) | **Gavin:** Buttondown, Pages, secrets/variables; demos |
| 5 S&P 100, findings, launch kit | ✅ sp100 list, findings, solution brief, demo, pilot, objections, LinkedIn drafts | cost approval; real results; launch |
| 6 Monetization, integrations | ⏸ only what partners ask for (Pro alerts, exports, MCP server, paid report) | discovery calls → `gtm/discovery/SYNTHESIS.md` |

## Blocked: who does what

**Step-by-step checklist for Gavin and Nick:** https://claude.ai/artifact/QqmDKJPxRPfprggV99eEJY (private; share it with Nick as an Editor so his ticks sync). It has 17 Gavin steps (G1–G17) and 9 Nick steps (N1–N9), each with exact instructions, plus a pilot company picker that shows AI-mention counts for all 100 companies. Ticks are stored in the page's shared database, so Claude Code can read progress with `ArtifactData list` on collection `steps`.

**Next session:** `git pull`, read this file, then check the checklist's ticks. If Gavin has given the go-ahead for the prompt v3 Tier 2 run, do it first: `uv run aipb verify --confirm` (Tier 1 is cached, so only Tier 2 is paid), then `uv run aipb explain`, `uv run aipb publish`, `uv run aipb site`, `uv run aipb findings`, read every published status, close R-001 in `data/error_reports.csv` if the Meta item is right, and commit with the ledger and outputs.

| Who | Task | Unblocks |
|---|---|---|
| Gavin | Upload `exports/packets/status_packet_v1.xlsx` (40 AI promises, built after extract v2) to Drive `packets/` and tell Nick (G11) | status eval; confidence threshold |
| Gavin | OK in chat to check the 58 promises: Tier 1 for 18 new, Tier 2, explain (worst case about $0.55; expected about $0.10) | updated pilot statuses; R-001 closed |
| Gavin | Put `exports/disagreements/20261112T210557_262d836_dev_default.xlsx` (19 rows) in Drive for Nick (N7) | label fixes; prompt changes |
| Gavin | Share the checklist page with Nick as Editor: on 2026-11-11 it was still private to Gavin | Nick's own ticks |
| Nick | Review the 19 disagreements (N7), then label the status packet (~40 promises, N8) | label fixes; confidence threshold |
| Nick (FYI, via Gavin) | D44 decided both D43 questions: "approximately" ranges use the range rule, and capex uses the company's usual definition when the promise is silent. Both are noted in Nick's rubric and evidence map; Nick can overrule either | — |
| Nick | Before `SITE_DEPLOY` is switched on: read the 13 published pilot statuses in the site preview | first public results |
| Gavin | Outreach (`gtm/outreach/`, ~25 messages) → discovery calls → notes | Phase 6, ROI numbers, demos |
| Gavin | Buttondown account (free tier) → API key as GitHub secret `BUTTONDOWN_API_KEY`; username into `config/site.yaml` | newsletter, signup box |
| Gavin | GitHub secrets `FOUNDER_EMAILS`, `AIPAYBACK_API_KEY`, `SEC_CONTACT_EMAIL`; Pages (GitHub Pro via the Student Pack, or a public deploy repo); LinkedIn URLs and Nick's display name in `config/site.yaml` | site, newsletter, monitor |
| Gavin | Approve the S&P 100 cost (table below) | Phase 5 run |

## Pilot run order (each step prints its worst case first)

The key is in `.env`, and the smoke test passed on 2026-11-11 ($0.0000102, ledger committed).

**Pilot run (2026-11-11, complete):**
- `calibrate`: the estimator reads 1.26x the real input-token count (130,842 vs 103,628), so worst cases stay high.
- `filter` done: **$0.04** against a $0.11 worst case (batch msgbatch_01MJuiSQd95RiLxTeHCgXLks, committed). 868 passages: promise 120 (58 high, 62 low confidence), hype 83 (60 low), none 665 (12 low).
- Promises by company: META 39, TSLA 35, NVDA 20, AMZN 7, MSFT 6, PFE 4, CAT 4, FDX 3, BLK 2, PEP 0.
- `extract` v1: $0.03 for 192 passages; 170 promises and 246 hype in 137 clusters. Then verify on Nick's rules: $0.10. **That run exposed the non-AI extraction (D42).**
- `extract` v2: $0.03; 44 promises and 165 hype in **40 clusters** (AMZN 10, META 13, MSFT 1, NVDA 11, PFE 4, TSLA 1); 129 statements dropped with no verified AI link.
- `verify` on the 40: $0.05. Stale results for the 137 old cluster ids were purged.
  - Tier 1: delivered 11, no evidence 20, on track 8, walked back 1. That one is Meta's raised 2025 capex guidance, which Tier 2 didn't confirm, so it stays pending.
  - Tier 1 held 21 as pending by rubric rule: 18 vague deliverables, 2 changed basis, 1 undefined base.
  - Tier 2 ran 17 of 19 escalations; 2 wait for the next run (run cap).
- `explain`: $0.004 for 14 statuses; all 14 passed the citation and wording checks.
- `publish`, `site` and `findings`: 13 published after the R-001 hold, 27 pending.

```bash
uv run aipb doctor                 # must be all OK
uv run aipb calibrate              # free count_tokens check of the estimator (1.26x on filter)
uv run aipb filter --dry-run       # pilot: 868 passages, 165 requests, worst case $0.11
uv run aipb filter
uv run aipb extract --dry-run      # upper bound $0.63 if filter routed everything; over $0.50 needs --confirm + Gavin's go-ahead
uv run aipb extract
uv run aipb verify --dry-run && uv run aipb verify
uv run aipb explain --dry-run && uv run aipb explain
uv run aipb publish && uv run aipb site && uv run aipb findings
git add -A && git commit -m "pilot run" && git push   # outputs + ledger: never pay twice
```

Nick's picks: **done 2026-11-11** (D39). `pilot.csv` is final, and packets and split were rebuilt with `--force`. Never use `--force` on either again once Nick starts labeling; bump the packet version instead.

After labels return: `aipb import-labels` → `aipb eval` → send `exports/disagreements/*.xlsx` to Nick → the Sonnet A/B (`aipb extract --variant sonnet` on dev passages, capped at $1.50; **size it first, see Known issues**) → `aipb eval --variant sonnet` → `aipb compare` → record the Sonnet decision in DECISIONS.

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

- The 10 pilot companies are all in the S&P 100, and filter requests are grouped per filing. Once the pilot has run, the S&P 100 run reuses its 165 cached filter requests and sends only 748 new ones ($0.44 worst case). That's checked: all 165 pilot request hashes appear among the S&P 100's 913.
- Budget plan:
  - pilot: ≤ $1.53 (filter $0.11 + extract ≤ $0.63 + verify/explain $0.29 at 300 promises + agent cap $0.50)
  - Sonnet A/B: ≤ $1.50
  - S&P 100: ≤ $4.84
  - total: ≤ $7.87 of the $11
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
| $0.24 (smoke test + pilot) | $0.00 | $14.76 | $4.00 |

## Known issues (to fix before the step that needs them)
- **Sonnet A/B sizing (before G10, D39).** Sonnet 5.5's worst case is about $0.045 per passage (`max_tokens: 8192`), so all 569 dev passages reserve $25.67, and $1.50 covers only about 33. The guard stops the run, so nothing overspends. Fix: an `extract` option that takes a list of passage ids (`run_extract` already accepts `passage_ids`). Then run only on labeled dev passages that filter routed, with Sonnet's `max_tokens` set from the pilot's real Haiku output lengths.
- ~~Gross margin fallback~~: **fixed** (D41). Nick's map kept "revenue minus cost of revenue", and code computes it now.
- **Zero-AI companies in the S&P 100 run (D43):** a company with no AI passages in the window isn't listed on the site. Decide whether to list it with a true "no AI passages found" notice.
- **Extract recall (D42):** links that name only a product (FSD, Amazon Q, Blackwell) are dropped. If Nick's labels show misses, give the link check its own AI-product term list.
- **Prompt v3 (D44) is built:** the "approximately" range rule, capex on the company's definition, the partial-delivery rule and the older-baseline margin rule. Not built yet: showing `CostOfRevenue` only when a promise names it; bank efficiency ratios; segment-note figures.

## Latest eval numbers
None yet: they need real outputs (the pilot run) and Nick's labels (gold).

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
- **The split is final** (2026-11-11, D39): dev BLK, CAT, META, NVDA, PFE, TSLA; test AMZN, FDX, MSFT, PEP. Never `split --force` again: test companies must stay unseen.
- **Commit outputs with the ledger:** after any paid call, commit `data/ledger` **and** `data/outputs` (or `git add -A`). The checklist's G4 commands left out `data/outputs` once; the smoke output was committed later with the final pilot list.
- **Commit after background jobs finish:** a running ingest writes the manifest, and pre-commit's stash can drop its new lines (it lost six Cisco documents once). Ingest now re-checks the file on disk and re-appends anything missing, but don't commit mid-ingest.
- **Tool escapes (Claude Code on this machine):** in bash heredocs `\\` collapses to `\`, and the Write tool turns `\u` escapes into literal characters. Check with `grep -nP '[^\x00-\x7F]' src/`, and use the Edit tool for strings containing backslashes.
