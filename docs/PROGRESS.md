# Progress

_Last updated: 2026-11-11 (final pilot list in; smoke test passed; blocked on humans)_

## Where things stand

On 2026-11-10 Gavin said: "Do all the phases until you absolutely cannot proceed without me and Nick's help." So the code for **Phases 0–5 is built, tested (176 offline tests, CI green) and pushed**. Phase 6 is discovery-driven and waits on partner calls.

**2026-11-11:**
- Gavin put the API key in `.env` and ran the smoke test (G3, G4). It cost $0.0000102 for 27 input and 15 output tokens on Haiku 5.5.
- Nick's 10 pilot picks are final (N2, D39). Ingest, parse, prefilter, packets and split were rebuilt for them, all at $0.
- The evidence map's coverage was redone for his companies, and fallback tags were added (em2-draft, D40).
- Checklist ticks: Gavin G1–G4; Nick N1–N5. Nick finished the rubric (N3) and the evidence map (N4) in the Google Docs **before** the em2 update, so G8 must merge the two.

**API spend so far: $0.0000102** (the smoke test). Every other paid stage has only been exercised against a fake model.

The money rules are unchanged: runs over $0.50 need `--confirm` plus Gavin's go-ahead in chat, and the S&P 100 run needs explicit cost approval.

| Phase | Built | Waiting on |
|---|---|---|
| 0 Setup, billing safety | ✅ budget guard, ledger, cache, secret hooks, CI; smoke test passed 2026-11-11 | **Gavin:** check the Console Usage page shows about $0.00001 |
| 1 Ingest, packets, kits | ✅ final pilot (Nick's picks) ingested; packets and split rebuilt; finance docs, outreach kit | **Gavin:** upload the packets, tell Nick (G6); bring in Nick's rubric and evidence map (G8) |
| 2 Filter, extract, evals | ✅ stages, batches, eval harness, A/B, compare | **Gavin:** pilot run (G7, ≤ $1.53); **Nick:** labels. A/B needs sizing first (D39) |
| 3 Verification, citations | ✅ Tier 1 + Tier 2, explain, gate, status packets + eval | key; **Nick:** ~60 status labels |
| 4 Site, newsletter | ✅ site, publish, newsletter with rails, 3 workflows (all off) | **Gavin:** Buttondown, Pages, secrets/variables; demos |
| 5 S&P 100, findings, launch kit | ✅ sp100 list, findings, solution brief, demo, pilot, objections, LinkedIn drafts | cost approval; real results; launch |
| 6 Monetization, integrations | ⏸ only what partners ask for (Pro alerts, exports, MCP server, paid report) | discovery calls → `gtm/discovery/SYNTHESIS.md` |

## Blocked: who does what

**Step-by-step checklist for Gavin and Nick:** https://claude.ai/artifact/QqmDKJPxRPfprggV99eEJY (private; share it with Nick as an Editor so his ticks sync). It has 17 Gavin steps (G1–G17) and 9 Nick steps (N1–N9), each with exact instructions, plus a pilot company picker that shows AI-mention counts for all 100 companies. Ticks are stored in the page's shared database, so Claude Code can read progress with `ArtifactData list` on collection `steps`.

**Next session:** `git pull`, read this file, then check the checklist's ticks and continue from the first unticked step. The key is in `.env`, so the next paid step is the pilot run (G7, worst case ≤ $1.53). Do it after the packets are out to Nick (G6).

| Who | Task | Unblocks |
|---|---|---|
| Gavin | Upload the 10 final `exports/packets/*_packet_v1.xlsx` to Drive `packets/`, then tell Nick "the packets are final" (rest of G6). G2 was checked on the placeholder packets; the code is the same, so the format carries over | Nick's labeling |
| Gavin | G8: download Nick's final rubric and evidence-map Docs as `.md` and give them to Claude Code. **Don't re-copy the repo docs over his Docs.** Claude merges his version with em2 (D40), then lists two follow-ups for Nick: the (new) tags and the gross-margin fallback | verify follows Nick's rules |
| Gavin | Run the pilot (G7), ideally after G8. Filter $0.11; extract ≤ $0.63, which is over $0.50, so it may need `--confirm` and a go-ahead in chat | status packet, first real results |
| Gavin | Share the checklist page with Nick as Editor: on 2026-11-11 it was still private to Gavin | Nick's own ticks |
| Nick | Label the passage packets (~6–8 h), then the status packet (~60 promises) | evals; confidence threshold |
| Gavin | Outreach (`gtm/outreach/`, ~25 messages) → discovery calls → notes | Phase 6, ROI numbers, demos |
| Gavin | Buttondown account (free tier) → API key as GitHub secret `BUTTONDOWN_API_KEY`; username into `config/site.yaml` | newsletter, signup box |
| Gavin | GitHub secrets `FOUNDER_EMAILS`, `AIPAYBACK_API_KEY`, `SEC_CONTACT_EMAIL`; Pages (GitHub Pro via the Student Pack, or a public deploy repo); LinkedIn URLs and Nick's display name in `config/site.yaml` | site, newsletter, monitor |
| Gavin | Approve the S&P 100 cost (table below) | Phase 5 run |

## Pilot run order (each step prints its worst case first)

The key is in `.env`, and the smoke test passed on 2026-11-11 ($0.0000102, ledger committed).

**Pilot in progress (2026-11-11):**
- `calibrate`: the estimator reads 1.26x the real input-token count (130,842 vs 103,628), so worst cases stay high.
- `filter` done: **$0.04** against a $0.11 worst case (batch msgbatch_01MJuiSQd95RiLxTeHCgXLks, committed). 868 passages: promise 120 (58 high, 62 low confidence), hype 83 (60 low), none 665 (12 low).
- Promises by company: META 39, TSLA 35, NVDA 20, AMZN 7, MSFT 6, PFE 4, CAT 4, FDX 3, BLK 2, PEP 0.
- **Next: `extract`.** 192 passages go on (all promises, plus every low-confidence hype or none). The dry-run worst case is $0.14. Waiting on Gavin: run it now, and hold verify until G8 brings in Nick's rubric and evidence map?

```bash
uv run aipb doctor                 # must be all OK
uv run aipb calibrate              # free count_tokens check of the estimator (not run yet)
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
| $0.04 (smoke test + pilot filter) | $0.00 | $14.96 | $4.00 |

## Known issues (to fix before the step that needs them)
- **Sonnet A/B sizing (before G10, D39).** Sonnet 5.5's worst case is about $0.045 per passage (`max_tokens: 8192`), so all 569 dev passages reserve $25.67, and $1.50 covers only about 33. The guard stops the run, so nothing overspends. Fix: an `extract` option that takes a list of passage ids (`run_extract` already accepts `passage_ids`). Then run only on labeled dev passages that filter routed, with Sonnet's `max_tokens` set from the pilot's real Haiku output lengths.
- **Gross margin fallback (ideally before the pilot's verify, D40).** Gross margin uses only `GrossProfit`, which AMZN, BLK, CAT, FDX, META and PFE don't report. Computing revenue minus cost of revenue is a small change in `src/aipb/verify/numbers.py`, but it's a methodology choice, so ask Nick as a follow-up to his evidence map (G8). Until then, those promises fall back to text evidence or "Status pending review".

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
