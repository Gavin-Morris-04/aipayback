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

## D10. SEC client: httpx2, 8 requests per second, two kinds of cache (Phase 1, 2026-11-10)
**Context.** The SEC allows at most 10 requests per second with a descriptive User-Agent. This machine's TLS setup needs the OS certificate store. Tests must never touch the network.
**Options.** (a) `requests`. (b) `httpx`. (c) `httpx2`, which the Anthropic SDK already installs.
**Choice.** (c), declared as an explicit dependency. It already uses the OS certificate store (truststore), and its `MockTransport` lets every test run against an in-memory fake SEC.
- A token bucket holds 8 requests per second, with backoff on 429 and 5xx that honors `Retry-After`.
- Filing documents never change, so they're cached forever. Listings (submissions, company facts, the ticker file) are cached for 12–24 hours to a week.
- Offline mode serves the cache and refuses misses.

**Evidence.** The pilot ingest made 467 requests in 72 s with 0 retries and 0 errors. The second run made 44 requests and served 476 from cache.

## D11. Which documents we parse (Phase 1)
**Choice.**
- **10-K and 10-Q:** the primary document. A 10-K also gets its EX-13 when present, because some companies put MD&A in an annual report incorporated by reference.
- **8-K:** only Item 2.02 (results of operations), and only its EX-99.1 press release (falling back to the first EX-99, then the primary document).
- **Amendments** (10-K/A, 10-Q/A) are skipped in v1. They're mostly Part III or exhibit refilings.

**Evidence.** IBM's 2024 10-K main document has 15,871 words. Its EX-13 has 71,662, including all of Management Discussion. Without EX-13, IBM's MD&A would be missing.

## D12. Companies that re-register keep their history (Phase 1)
**Context.** Ticker→CIK lookup returns the *current* registrant. XOM now maps to ExxonMobil Holdings Corp (CIK 2115436, registered in 2026), which had only 4 filings since 2024. The 2024–2025 filings sit under Exxon Mobil Corp (CIK 34088).
**Choice.**
- Universe files get an `extra_ciks` column for predecessor registrants.
- Each manifest row stores the filer CIK (to build the URL) and the company CIK (for identity).
- A filing listed under both CIKs (one joint 10-Q) is de-duplicated by accession number.
- Ingest warns when a company has fewer 10-K/10-Q filings than the window implies (about 4 per year, minus 2), so the S&P 100 run catches other cases.

**Evidence.** XOM went from 4 to 24 filings (3 10-K, 9 10-Q, 12 earnings 8-Ks), in line with the other pilot companies. Without this, every Exxon promise from 2024–2025 would have been invisible.

## D13. Passages: 150–400 words, Item sections, stable IDs (Phase 1)
**Choice.**
- HTML and inline XBRL are converted to blocks. Hidden XBRL, page numbers and repeated running headers or footers are dropped; page numbers are stripped before counting repeats, because footers carry them.
- Section headings come only from short **paragraphs** starting with "Item N". A table of contents laid out as a table is ignored. One laid out as paragraphs creates empty sections that the real headings later overwrite.
- Passages pack whole paragraphs up to 400 words; long paragraphs split at sentence ends.
- ID: `{cik}-{accession}-{section}-{seq}`.

**Evidence.** On the pilot: 236 filings → 18,381 passages. On sample filings the median passage is about 350 words. Parsing is deterministic: a fresh clone rebuilt identical passage IDs and text hashes (see D19).

## D14. Store text verbatim; match on a normalized copy (Phase 1)
**Context.** Quotes must match the source verbatim, but filings contain typographic ligatures ("ﬁled" in IBM's 10-K), curly quotes, soft hyphens and non-breaking spaces, which break naive search and quote checks.
**Choice.** Passage text is stored as written. Keyword search, full-text search and quote checks all use one function, `normalize_for_match`:
- NFKC (folds ligatures and odd spaces)
- straight quotes and plain dashes
- soft hyphens and zero-width characters removed
- whitespace collapsed

The FTS5 index stores the normalized text with Porter stemming.
**Evidence.** Unit tests cover each case. The ligature test confirms "artiﬁcial intelligence" matches the keyword "artificial intelligence".

## D15. Dedup is conservative: near-identical AND the same numbers (Phase 1)
**Context.** 10-Qs repeat 10-K boilerplate, and paying to classify the same paragraph eight times wastes budget. But a restated promise with a *changed* target is exactly what verification must see.
**Options.** (a) Exact duplicates only. (b) Near-duplicates by text similarity. (c) Near-duplicates that also contain identical numbers.
**Choice.** (c) for passages with AI keywords: word 5-gram Jaccard ≥ 0.9 **and** the same multiset of numbers. The earliest filing is canonical. Passages without AI keywords get exact dedup only (cheap, and they're never sent to the LLM).
**Evidence.**
- Dedup removes 19% of AI-keyword passages (1,396 → 1,128), below the plan's 30–50% guess. The lower saving is accepted on purpose.
- Test `test_changed_number_is_never_a_duplicate` proves a change from $3.5 billion to $4.5 billion, or from 2025 to 2026, is never merged away.

## D16. XBRL facts: filed since 2022; key includes period start (Phase 1)
**Context.** The plan's key, (cik, tag, unit, period_end, accession), collides: a 10-Q reports both the three-month and the year-to-date value for the same end date in one filing.
**Choice.** The key is (cik, taxonomy, tag, unit, period_start, period_end, accession). Only facts filed on or after 2022-01-01 are loaded. Baselines for 2024 promises appear as prior-period comparatives in 2024+ filings anyway.
**Evidence.** IBM's Q3 2026 10-Q reports Revenues of $17,103M (2026-07-01 to 09-30) and $50,182M (2026-01-01 to 09-30), same end date, same accession. The pilot has 99,706 facts. The tags differ by company (EVIDENCE_MAP.md): JPM has no SG&A or operating-income tag, and IBM reports no operating income.

## D17. Labeling packets: keyword-sampled, promise-window only, recall check built in (Phase 1)
**Context.** Gold labels must not be biased toward what the model finds, and the finance student has about 6–8 hours.
**Choice.**
- Rows come from the keyword prefilter, never from model output. Only canonical passages from 2024–2025 filings with at least 40 words are sampled.
- **Allocation by water-filling.** Every company gets all its keyword passages up to a common cap. The cap fit 450 rows at 93 per company, so MSFT, CRM, IBM and ACN were capped and the rest got all of theirs.
- About 5% of rows are random passages with **no** keyword, to measure what the keyword filter misses.
- One seeded random stream per company, so changing the company list doesn't reshuffle everyone's rows.
- AI words in red, dropdowns for label and claim type, SEC links, an Instructions tab.
- A committed key per company maps each row to its passage ID, text hash, sampling method and **full text**. Imports and evals never depend on the local database or parser version.
- `aipb packets` refuses to overwrite existing keys without `--force`. After labeling starts, a new round gets a new `PACKET_VERSION` instead.

**Evidence.** Placeholder packets: 450 rows (428 keyword + 22 random). XOM has zero AI-keyword passages in 2024–2025, so its packet is the 2 random rows.

## D18. Label import: plain-English, row-level, verbatim quotes (Phase 1)
**Choice.**
- Every problem names the row, the Row ID and the fix ("Promise 1's quote is not in the passage text. Copy it exactly…"). The report is written to be forwarded as is.
- Good rows import even when other rows need fixing. Gold files are rebuilt from all returned files on every run.
- Quotes must be one continuous piece (no "…"). Capitalization differences are forgiven, but the gold quote is stored in the passage's own (normalized) wording.
- Unsure rows are kept for review but never used as gold promises. Two returned files for one company: the second is skipped, with a message.

**Evidence.** `tests/integration/test_labeling.py` fills packets the way a labeler would, including seven kinds of mistakes, and checks each message and the gold output.

## D19. Reproducibility: committed manifest, fresh-clone restore (Phase 1)
**Choice.** `data/manifests/filings.jsonl` records the URL and sha256 of all 239 documents. `aipb restore` re-downloads them, checks the hashes, re-parses, re-indexes and re-filters. The raw SEC cache (about 555 MB for the pilot) and the SQLite database stay out of git.
**Evidence.** On 2026-11-10, a fresh clone in a temp folder ran `aipb restore` in 2 min 30 s. It rebuilt 18,381 passages whose IDs, text hashes, keyword hits and dedup marks digest to the same value as the original, plus 99,706 XBRL facts, with 0 LLM calls and no ledger entries. The prefilter was sped up from 49 s to 16 s by combining each keyword list into one regex; keep/drop decisions are unchanged.

## D20. Batches by default, with a committed batch log (Phase 2, 2026-11-10)
**Context.** The Batch API halves the price. But a batch is billed even if the process waiting for it dies (a closed laptop, a killed terminal).
**Choice.**
- Every non-interactive stage submits one Message Batch of its uncached requests.
- The batch id and request map go into `data/ledger/batches.jsonl` (committed) **before** waiting.
- If waiting is interrupted, the run's reservation stays held (fail closed) until `aipb batch-collect <id>` settles the real cost, caches the outputs and closes the run.
- `aipb batches` lists anything uncollected.

**Evidence.** `test_interrupted_batch_is_collected_not_paid_twice` simulates the crash. The reservation stays open, collect settles it, and re-running the stage submits nothing.

## D21. Filter requests pack up to 10 passages from the same filing (Phase 2)
**Context.** Packing passages saves the per-request system-prompt overhead. Packing across filings would change every request's contents (and cache key) whenever a new filing arrives, so the monthly update would re-pay for old passages.
**Choice.** Groups of up to `group_size` (10) passages, always from one filing, in document order. New filings create new groups and never touch old ones.
**Evidence.** Pilot dry run (`aipb filter --dry-run`): 688 passages → 129 requests, worst case $0.09 (under the $0.50 confirm threshold).

## D22. Thinking off, effort low, no sampling parameters; variants for the A/B (Phase 2)
**Choice.**
- Filter and extract default to `thinking: disabled` + effort `low` on Haiku 5.5. Disabled thinking is allowed there at effort high or below, and thinking would bill as output.
- `temperature` and similar are never sent: Haiku 5.5 rejects non-default sampling values.
- The A/B variants live in `config/stages.yaml`:
  - `effort_low`: adaptive thinking at effort low.
  - `sonnet`: Sonnet 5.5, adaptive at effort low. Sonnet 5.5 rejects `disabled`.
- Variants are stored separately (the `variant` column), so a comparison never overwrites the default results.

## D23. Structured outputs for filter and extract; quotes checked and mapped back by code (Phase 2)
**Choice.**
- Both stages use `output_config.format` with strict JSON schemas (no numeric or length constraints, which structured outputs don't support).
- Every extracted quote is located in the passage after `normalize_for_match`. The **original** characters at that span are stored, so published quotes are the filing's own text, curly quotes included.
- A response with a failing quote gets one retry that names the failing quotes. Anything still failing is dropped and logged in `extraction_log`.
- Passages go to extraction when the filter says promise, says it's unsure (low confidence), or fails (recall first).

**Evidence.** Tests cover a paraphrased first answer fixed on retry, a quote that never matches being dropped, and refusals not being cached.

## D24. Promise clusters never merge a changed target (Phase 2)
**Choice.** Restatements merge when the claim type matches and either the quotes are similar (word Jaccard ≥ 0.5) or the metric, target and deadline all match. The same metric with a different target or deadline starts a new cluster with `related_cluster_id` set: a raised or lowered target is evidence, not a duplicate. Cluster ids come from the earliest statement, so they're stable; non-default variants get a variant prefix.

## D25. Eval design (Phase 2)
**Choice.**
- **Split:** by company, seeded, frozen in `evals/splits.json` (placeholder pilot: dev ACN, CAT, IBM, UNH, VZ, XOM; test CRM, JPM, MSFT, WMT). It's recomputed once with `--force` when Nick's final list arrives.
- **Matching:** same passage, quote-span IoU ≥ 0.5 in normalized text.
- **Metrics:** precision, recall and F1 with seeded bootstrap 95% intervals over passages (too few companies to resample by company); field accuracy (claim type, target number, deadline year); filter and end-to-end confusion matrices; prefilter miss rate from the random non-keyword rows with a Wilson interval.
- **Rules:** `--split test` refuses without `--milestone "<reason>"`. Each run writes `evals/results/<ts>_<sha>_<split>_<variant>.{json,md}`, a README history row, and a disagreement workbook for Nick ("Model wrong", "Label wrong", "Rubric unclear").
- **A/B:** `aipb compare` reports cost per F1 point against the default.

## D26. Verdict and explanation are two calls: structured, then cited (Phase 3, 2026-11-10)
**Context.** Citations and structured outputs can't be combined: the API returns a 400. That was confirmed in the citations docs on 2026-11-10.
**Choice.** The Tier 1 verdict is a structured call: the status, the evidence and number ids it relies on, a confidence, and one neutral finding. The explanation is a separate batched call. In it, the promise passage, the cited evidence passages and the cited numbers (as sentences) are plain-text `document` blocks with citations enabled.

Code checks every citation: `document.data[start:end]` must equal `cited_text`. The promise must be cited, and any status other than "No evidence yet" must also cite evidence. The neutral-language lint must pass.

## D27. What the judge sees is assembled by code, deterministically (Phase 3)
**Choice.**
- **Evidence:** FTS5 BM25 over the company's later filings (top 8, at most 2 per filing), with ids E1–E8.
- **Numbers:** an XBRL table for the claim type, computed in code (annual values where a restated number wins, year-over-year changes, margins), with ids N1….
- **Code-computed facts:** fiscal-year end (inferred from the XBRL periods), deadline end, whether it has passed, whether results for the deadline period are filed, later 10-K/10-Q count, later mentions.
- **"As of"** is the company's latest filing date, not the wall clock. Otherwise every request would change daily and re-pay.

## D28. Silent walk-backs and negative statuses are gated by code (Phase 3)
**Choice.**
- A "silent" walk-back is accepted only when the code-computed conditions hold (from the rubric draft): deadline passed, at least two 10-K/10-Q filings after it, and no later passage mentioning the promise. Otherwise it's downgraded to "No evidence yet".
- Any "Walked back" needs Tier 1 and Tier 2 to agree, both confident, on status and kind.
- Two confident checks that disagree → pending. A confident check beats an unconfident one, which is the point of escalating.

**Evidence.** Unit tests cover every gate branch. An integration test shows a Tier 1 walk-back staying pending until Tier 2 independently agrees.

## D29. Tier 2 is a manual, capped, cached tool loop (Phase 3)
**Choice.**
- A manual loop, not the SDK tool runner, so every turn goes through the budget-guarded gateway and the output cache.
- Strict tools: `search_company_filings`, `get_passage`, `get_reported_metric`, `calculate` (a safe AST calculator, no `eval`), `submit_verdict`. `tool_choice` is `auto` with an instruction to submit once.
- Caps: 8 turns and 60k tokens per promise. Each run is capped at $0.50 by worst-case estimate; escalations beyond that stay pending.
- No `submit_verdict` → no verdict (never published).
- Thinking blocks are passed back unchanged. A replay of the loop is served entirely from cache.

**Why not an agent for everything:** Tier 1 is one call per promise. The agent runs only on escalations and second checks, which keeps it in the project without letting it use up the budget.

## D30. Status gold labels are independent of the model (Phase 3)
**Choice.** `aipb status-packets` shows Nick each promise with the same code-retrieved evidence and numbers the judge sees, never the verdict. Gold statuses are matched back to clusters by passage and quote overlap, not cluster id, so they survive re-extraction. `aipb eval-status` reports published precision vs coverage at thresholds 0.50–0.95. That curve is how the confidence threshold (default 0.75) gets set.

## D31. The site is built from a committed data file, not the database (Phase 4, 2026-11-10)
**Choice.** `aipb publish` runs the gate and exports `data/site/site_data.json` (committed). `aipb site` renders static HTML from that file alone, so the Pages workflow builds without SEC downloads or API calls.
- Pending items carry the verified quote only.
- Each page has canonical URLs, OpenGraph tags and the disclaimer; the home page has a JSON-LD `Dataset` block; the site has a sitemap.
- The leaderboard is hidden until results exist, so "0 promises" never reads as "we looked and found none".

`data/site/published_log.jsonl` is append-only and records when each promise's shown status first appeared or changed, and why: first publish, status change, or correction after a closed error report. The newsletter's "new", "changed" and "corrections" sections come from it.

## D32. The newsletter is templates plus a fact-checked intro (Phase 4)
**Choice.**
- The items, the one stat and the footer are deterministic templates over published data.
- Haiku writes only a 2–3 sentence intro from a JSON of the issue's facts, capped at $0.05 worst case.
- Code checks every number, ticker-like word, company name and status word against the facts, plus the neutral-language lint. A failed check regenerates once, naming the problems; a second failure (or no key or budget) falls back to the template intro.

## D33. Sending is staged, vetoable, idempotent and fails closed (Phase 4)
**Context.** Buttondown's API, checked against its OpenAPI spec on 2026-11-10: `POST /v1/emails` (status `draft`, `metadata`), `POST /v1/emails/{id}/send-draft` (`recipients`), and `PATCH /v1/emails/{id}` (status `about_to_send`).
**Choice.**
- **Stage** (1st of the month): build the issue, create a Buttondown draft with the issue key and body hash in its metadata, send a test copy to `FOUNDER_EMAILS`, and open a GitHub "Newsletter preview" issue.
- **Send** (24 hours later) refuses unless:
  - the issue was staged and not already sent;
  - the preview issue has no `hold` label (if the labels can't be read, it doesn't send);
  - the draft's metadata and normalized body hash still match the preview;
  - the status is still `draft`.
- Founders-only test mode applies while `NEWSLETTER_AUTOSEND` isn't `true` and for the first two issues.
- Any other failure opens a "Newsletter not sent" issue. Everything is logged in `data/sends/newsletter_log.jsonl` (committed).
- Workflow inputs pass through environment variables and a strict issue-key pattern, never interpolated into shell (script-injection safe).

**Evidence.** Eight integration tests against fake Buttondown and GitHub servers: ramp-up, live send, idempotency, hold label, kill switch, edited draft, never staged, too few items.

## D34. Scheduled jobs are off until a human turns them on (Phase 4)
**Choice.** `deploy-site.yml`, `newsletter.yml` and `monitor.yml` each run only when a repo variable is `true` (`SITE_DEPLOY`, `NEWSLETTER_ENABLED`, `MONITOR_ENABLED`). The monitor job spends API credit through the same guard. It has no `--confirm`, so a monthly run over $0.50 stops and needs a person. Outputs, ledger and manifest are committed back, so the next run never re-pays.

## D35. S&P 100 list: Wikipedia's constituents table, recorded with date (Phase 5)
**Choice.** `config/universe/sp100.csv`: 100 companies parsed from the S&P 100 article's constituents table on 2026-11-10. It has 101 securities; GOOG is folded into GOOGL, since it's the same company and CIK. Exxon carries its predecessor CIK. The `source` column says to cross-check against S&P DJI or the iShares OEF holdings before the paid run, because Wikipedia isn't the index provider.

## D36. Findings only from published data, with denominators (Phase 5)
**Choice.** `aipb findings` writes `docs/FINDINGS.md` from `site_data.json` and the promises table. Every share shows "k of n", groups with fewer than 5 items are labeled "too few to compare", and the caveats sit next to the numbers. LinkedIn drafts (`gtm/linkedin/`) may only quote that file.

## D37. The estimator counts the hidden tool-use system prompt (Phase 5)
**Choice.** I re-checked `config/pricing.yaml` against the pricing page on 2026-11-10 before the S&P 100 estimate, and every Haiku 5.5 and Sonnet 5.5 price matched. The page also lists a hidden system prompt that's billed on any request with `tools`: 286 tokens (tool_choice auto) or 406 (any/tool) on Haiku 5.5. The estimator only added 50 tokens of overhead, so Tier 2 agent turns were slightly under-estimated. Now any request with tools adds `tool_overhead_tokens: 406` (in `config/stages.yaml`), so the estimate stays above the real count. That's about $0.00004 per agent turn: small, but the rule is that estimates never run low.

## D38. S&P 100 re-registrations, spin-offs and a lost-lines guard (Phase 5)
**Choice.**
- **BlackRock** formed a new holding company (CIK 2012383) in 2024. Its 2024 10-K and first two 10-Qs are under the predecessor, CIK 1364742 (now "BlackRock Finance, Inc.", formerly "BlackRock, Inc."), which `extra_ciks` now lists. The count-based warning missed it (9 filings passed), so ingest also warns when a company's first 10-K/10-Q comes more than 120 days after the window start.
- **Sandisk (SNDK)** triggers both warnings, but it was spun off from Western Digital in 2025 and registered as a new company, so there's no predecessor to add. Western Digital's 2024 filings are a different company's promises. SNDK's window starts with its first 10-Q (filed 2025-03-07).
- **Lost manifest lines:** pre-commit's stash rewrote `filings.jsonl` while an ingest was appending to it, and six Cisco documents vanished. Ingest now reloads the manifest from disk after writing (`Manifest.missing_on_disk`/`repair`), re-appends anything missing and prints a warning.

## D39. The final pilot list is Nick's picks (2026-11-11)
**Choice.** `config/universe/pilot.csv` is now the finance lead's list: AMZN, BLK, CAT, FDX, META, MSFT, NVDA, PEP, PFE and TSLA. That's 7 sectors, 8 AI-heavy and 2 low-AI comparisons (CAT, PEP), which meets the PLAN's bar of at least 5 sectors and at least 4 AI-heavy. His reason for each company is in the `notes` column, word for word. BlackRock carries its predecessor CIK 1364742 (D38).

**What was rebuilt ($0, SEC data only; every filing was already downloaded for the S&P 100):** ingest, parse and prefilter; packets with `--force`, which deleted the 8 dropped companies' keys and spreadsheets; and the split with `--force`. The packets still total 450 rows (428 keyword, 22 random), so the labeling estimate is unchanged. Split (seed 20261110, 60% dev): dev BLK, CAT, META, NVDA, PFE, TSLA; test AMZN, FDX, MSFT, PEP.

**Cost effect.** The new list talks more about AI: 868 AI passages in the promise window instead of 688. These figures come from dry runs and from the same estimator used as an upper bound, which reproduces the S&P 100's $2.84:
- filter: 165 requests, $0.11 (was 129 requests, $0.08)
- extract upper bound: $0.63 (was $0.50)
- pilot total: ≤ $1.53 at 300 promises (was $1.37)
- S&P 100 filter requests left after the pilot: 748 (was 784)

**Known issue: the Sonnet A/B can't fit $1.50 as written.** This was already true of the placeholder list. With `max_tokens: 8192`, Sonnet 5.5's worst case is about $0.045 per passage in a batch, so all 569 dev passages reserve $25.67, and $1.50 covers only about 33. The guard stops the run, so nothing can overspend. Before G10, size the test: only labeled dev passages that filter routed, and a `max_tokens` set from the pilot's real Haiku output lengths. That needs a small `extract` option for a list of passage ids.

## D40. Evidence map em2-draft: fallback tags for the final pilot (2026-11-11)
**Context.** I re-ran the evidence map's "Reported by" check against Nick's 10 companies (us-gaap facts filed since 2024). Several report a measure under a different tag than the draft listed, so verification would have found no number for them.

**Choice.** Each new tag is the **last** one tried for its measure, so every company that reports an earlier tag keeps it:
- `operating_expenses` += `CostsAndExpenses` for AMZN, FDX and META. This is total costs, including cost of sales, which the doc flags.
- `capex` += `PaymentsToAcquireProductiveAssets` for AMZN, FDX, NVDA and PEP.
- `rnd` += `ResearchAndDevelopmentExpenseExcludingAcquiredInProcessCost` for PFE.

Version `em1-draft` becomes `em2-draft`. No verify result used em1. `docs/finance/EVIDENCE_MAP.md` now shows the coverage for the final pilot and marks the new tags **(new)**. Nick had already finished his evidence map in the Google Doc (N4, ticked 19:51 UTC), working from the em1 draft. G8 merges his version with these changes, and the new tags and the gross-margin question go to him as follow-ups.

**Gaps that remain (real absences, not missing tags):** *(Update: D41 settled the gross-margin item. Code now computes revenue minus cost of revenue, as Nick's final map says.)*
- **Gross margin** is computed only from `GrossProfit`, which AMZN, BLK, CAT, FDX, META and PFE don't report. The draft doc said "otherwise revenue minus cost of revenue", but the code never did that: `cost_of_revenue` isn't used by any claim type. Until it's built, those companies' gross-margin promises can only be checked from text. The outcome is No evidence yet or Status pending review, never a guessed status.
- Not reported at all: `OperatingIncomeLoss` (PFE), restructuring tags (MSFT, NVDA), an R&D line (AMZN, BLK, FDX) and headcount (every company).

## D41. Nick's final rubric and evidence map are the rules (G8, 2026-11-11)
**Context.** Nick finished both Google Docs (N3, N4), and Gavin brought them in as PDFs before the pilot's verify step. His evidence map was edited from the em1 draft, so it was merged with the em2 coverage check (D40). The repo's `docs/finance/RUBRIC.md` and `EVIDENCE_MAP.md` now carry his text word for word. Merge notes are in [square brackets].

**His decisions, and where code follows them:**
- **Tolerances** (rubric section 5): 95% of a numeric target; 100% if the promise says "at least", "more than" or "exceed"; one-sided 90% for "about"; the low end of a range with no extra tolerance; overshooting is always met; run-rate and realized never mixed; fiscal deadlines (halves and quarters too); a grace period for results filed later, but no credit for progress after the deadline period; same accounting basis; organic figures only when the company reports them. Followed in prompts `verify_t1/v2` and `verify_t2/v2`.
- **Silent walk-backs:** two new conditions. One silent 10-K/10-Q must cover the deadline period, which code checks (`deadline_period_filed`). The program must have been named before, which the judge decides. Specificity-1 promises are never silent (code).
- **Pending review in specific cases:** a vague specificity-1 deliverable, unclear run-rate vs realized, a changed GAAP/non-GAAP basis or metric definition, and a percentage target with an undefined base. Verdicts now carry a `pending_reason`. The gate publishes these as "Status pending review", and Tier 1 doesn't escalate them, because a second check couldn't change the outcome. "vague_deliverable" is accepted only on specificity-1 promises.
- **Reaffirmations** never make a promise On track or Delivered. **Raised targets:** the original promise is judged against its own target.
- **Evidence rules per claim type** (evidence map): total expenses never decide a savings promise; restructuring charges aren't savings; margins change in points; bookings, backlog and run-rate aren't revenue; total headcount can't decide a promise about a group of roles; capex is matched to the guidance's definition; derived ratios count only for promises stated in reported numbers; general availability excludes previews and partial rollouts. All are in the v2 prompts.
- **Numbers (code):** gross profit falls back to revenue minus cost of revenue, labeled as computed (his map kept this line; it was never built before). Margins get year-over-year changes in percentage points. `CostsAndExpenses` is labeled "total costs and expenses". Capex rows include finance-lease payments, capitalized software and asset-sale proceeds. Evidence map version **em3**.
- **Explanations** (`explain/v2`): say when a figure is company-reported or computed by code; state results against targets; quote a reaffirmation and name its filing; mention the other GAAP/non-GAAP figure when the company gives both.
- **Findings:** capex promises are reported in their own table, apart from promises about results (his answer to question 3).
- **Confirmed by his map:** the em2 fallback tags for capex (`PaymentsToAcquireProductiveAssets`) and R&D (`...ExcludingAcquiredInProcessCost`), and the gross-margin fallback. Both D40 follow-ups are settled.

**Not built yet (no pilot effect, or handled by the second check):**
- A margin change against a baseline older than the prior year. Tier 1 can't compute it; the second check can. Prompt v3 will say so explicitly.
- Showing `CostOfRevenue` only when a promise names that line.
- Bank efficiency ratios and adjusted noninterest expense (no bank in the pilot).
- Segment figures from the segment note (text evidence only for now).

**Merge questions, answered in chat by Gavin on 2026-11-11:**
1. Total costs and expenses stay as context for AMZN, FDX and META's cost-savings promises: **yes**. No change to em3.
2. The rubric is final: **yes**. `RUBRIC.md` is titled final.

## D42. AI statements only (extract v2), and results tied to the promise they judged
**Context.** The first pilot verify run showed that extract v1 kept ordinary business guidance from passages that mention AI somewhere:
- 101 of 137 promise clusters had no AI term in the quote itself;
- all 10 of Caterpillar's clusters were sales, tariff, restructuring or capex guidance;
- 10 of the 12 Tier 1 "walked back" verdicts were on such statements.

Nick's rubric excludes "general guidance with no AI link". Explain and publish were held until this was fixed. Gavin approved the fix and the re-runs in chat ("go").

**Choice 1: an AI link checked by code.** Prompt `extract/v2` asks, for each statement, for `ai_link`: the passage's own words that tie the statement's outcome to AI. Code keeps a statement only if the link is:
- verbatim in the passage (the same matching as quotes);
- within 400 characters of the quote, so the model can't point at an unrelated "AI" elsewhere in the passage;
- naming AI, using the prefilter lexicon.

Anything else is dropped and logged as `dropped_unlinked`, with no retry: a retry would only push the model to find some AI word to point at. The link is stored in `promises.ai_link`, so a reviewer can see why each promise counts as an AI promise.

**Choice 2: stored results follow the promise, not the cluster id.** Cluster ids come from the canonical promise's position in its passage (`c-default:<passage>:s1`), so a re-extraction can put a different statement under an old id. Verdicts and explanations were never cleared. The danger: a new low-confidence Tier 1 verdict, with Tier 2 skipped by the run cap, would have been paired with an old confident Tier 2 verdict about a different statement. Now:
- verdicts and explanations store `promise_sha`, a fingerprint of the canonical promise's fields and its restatements;
- `load_verdict` and `load_explanation` ignore any row whose fingerprint doesn't match the promise now under that id, and rows stored before this change have none;
- `aipb verify` purges such rows before it runs. Results for unchanged promises are re-stored from the cache at $0.

Tests cover both choices.

**Result on the pilot (extract v2, $0.03 for 192 passages):**
- 44 promises and 165 hype statements in 40 promise clusters, down from 170, 246 and 137.
- 129 statements dropped with no verified AI link:
  - 76 links named no AI term;
  - 25 were too far from the quote;
  - 18 had no link at all;
  - 5 weren't in the passage.
- Every Caterpillar statement is gone. The 40 clusters are AMZN 10, META 13, MSFT 1, NVDA 11, PFE 4, TSLA 1.

**Link matching ignores case.** The link is a pointer, never published, and the model writes "we expect…" for a sentence that starts "We expect…". This recovered Meta's 2025 capex guidance ("…to support both our generative AI efforts"). It was a $0 re-check of cached answers.

**Known limits for the eval to measure:**
- **Recall:** a link that names only a product (Tesla FSD and robotaxi, Amazon Q, Nvidia Blackwell, DGX, "an AWS agent") fails the lexicon check unless the passage names AI nearby. If Nick's labels show real misses, give the link check its own term list with AI product names, leaving the prefilter lexicon and its packets alone.
- **Precision:** some kept items are past-tense announcements ("Announced…", "Unveiled…") rather than promises.

## D43. Pilot review before anything is public: one hold, and only analyzed companies
**Context.** I read all 14 statuses the gate published from the pilot before committing them. The site is a local preview until Gavin sets `SITE_DEPLOY` (G15).

**Hold R-001 (Meta, "approximately $70 billion to $72 billion" of 2025 capex).** Tier 1 said Delivered at "about 99.5% of the $70 billion low end", which applies the 95% numeric tolerance to a range; Nick's rubric excludes that. Reported purchases of property and equipment were $69.69 billion. Adding finance-lease principal ($2.52 billion) gives $72.2 billion, which would meet the range on Meta's own definition of capex, but the promise quote doesn't state that definition. The explanation said "just below the low end… Delivered". The case is unclear, so per principle 1 it's held as "Status pending review" through an open internal report in `data/error_reports.csv`, the gate's existing hold mechanism.

**Questions for Nick:**
1. Does "approximately $X to $Y" follow the range rule (low end, no tolerance) or the "about" rule (90%)?
2. When a capex promise doesn't say which definition it uses, may the company's usual guidance definition, such as Meta's "including principal payments on finance leases", be applied?

Prompt v3 should then state the answer explicitly.

**Only analyzed companies appear or count.** Every S&P 100 company is ingested, but the pilot analyzed 10. Two bugs came from treating every company in the database as analyzed:
- the findings said statements came from "100 companies' filings";
- the site built pages for 90 unanalyzed companies with the notice "No checkable AI promises found in this company's 2024–2025 filings so far", which would be a false statement about, for example, Apple.

Now a company counts only if the filter stage read its passages (`publish.analyzed_ciks`). Tested.

**Known gap:** a company with zero AI passages in the window has nothing to classify, so for the S&P 100 run it won't appear rather than showing a true "no checkable AI promises" notice. Decide before that run whether to list such companies.

**Pilot result after the hold:** 13 of 40 promises published (5 Delivered, all Meta capex; 8 No evidence yet). 27 are "Status pending review". Total pilot API spend was $0.24.

## D44. Capex on the company's own definition; "approximately" ranges use the range rule (prompt v3, 2026-11-12)
**Context.** The two D43 questions, answered.

**Capex definition (Gavin: yes).** When a capex promise doesn't say which definition it uses, it is judged on the company's usual definition, as the company's own filings state it. This amends Nick's evidence-map answer 3 ("including finance leases only if the guidance did") for the case where the guidance is silent. How it works, all in code:
- `numbers.capex_definition` looks for the company's own phrase "capital expenditures, including principal payments on finance leases" in its filings up to the promise date, and needs it in at least two filings to count as "usual".
- When found, the reported numbers get an extra derived row, "capital expenditures as the company defines them", which is purchases of property and equipment plus principal payments on finance leases, summed by code for years where both cover the same period. The facts block quotes the phrase. When not found, the facts say "none stated; use purchases of property and equipment".
- Deliberately narrow: only phrasings whose parts are both XBRL tags are recognized. In the S&P 100 data only Meta uses this phrase (24 filings). American Tower's "including payments on finance leases" and Microsoft's "capital expenditures including finance leases" are not the same sum and are not recognized.
- Check: Meta's 2025 figure on this definition is $72.22 billion ($69.69 billion + $2.52 billion), the same figure Meta reports.

**"Approximately $X to $Y" (Gavin asked me to decide): the range rule.** Met at the low end, with no extra tolerance. Reasons:
- Nick's rubric already says the low end is "the company's own floor"; "approximately" applies to a range that is already a band.
- Stacking the 90% "about" tolerance on a range would count $63 billion as meeting "approximately $70 billion to $72 billion".
- A wrong Delivered is a wrong verdict about a real company. A near-miss loses nothing in accuracy: under Nick's partial-delivery rule it is "No evidence yet" (or "Walked back" if the company explicitly lowered it), and the explanation states the reported figure against the range.

Nick can overrule this; it is one line in each verify prompt.

**Prompt v3** (verify_t1, verify_t2, explain) states both rules, Nick's partial-delivery rule, and that a margin change against a baseline older than the prior year goes to the second check (it can calculate). The explanation names what a code-computed capex figure combines.

**Result so far (Tier 1 only, $0.018):** the R-001 Meta item is Delivered at confidence 0.8, citing both $69.69 billion and $72.22 billion against $70–72 billion. 22 of 40 items escalate to Tier 2, whose worst case reaches its $0.50 run cap, so the combined run is over $0.50 and waits for Gavin's go-ahead. R-001 stays open until the re-run is published.

## D45. AI product names count as an AI link, if the company's own filings say so (2026-11-12)
**Context.** The first eval against Nick's labels (dev split) found extraction recall of 25%. Of the 24 dev gold promises, 11 were dropped by the ai_link check (D42) because the link named only a product: "Blackwell revenue", "FSD (Supervised)", "Optimus", "purpose-built Robotaxi product". The rubric counts promises about "AI products" as AI promises, so these drops were wrong.

**Decision.**
- `config/ai_products.yaml` (ap1) lists AI product, platform and program names per company. A link that names one of the company's listed products counts as naming AI.
- The safeguard is in code (`aipb.stages.ai_products`). A listed name counts for a company only if that company's own filings put it in the same sentence as a keywords.yaml AI term in at least 2 filings. Of 58 listed names, 41 are confirmed; for example H100, Full Self-Driving and Inferentia are not, and they're ignored. Names match case-sensitively, as whole words, and only for their company.
- The list was built the same way for all 10 pilot companies: capitalized names ranked by how often they share a sentence with an AI term in the company's filings. Only products, platforms and programs were kept; segments ("Data Center", "Power Generation"), markets, places, laws and partner companies were left out. Nick's labels were not used.
- The prefilter lexicon (kw1) is unchanged. The passages Nick labeled are still the passages the pipeline reads, and extraction replayed from cache for $0.
- Not added: generic autonomy words ("autonomous", "level 4"). CAT's "autonomous solutions" and NVIDIA's "level 4-ready mobility network" links still don't count. Nick can say whether self-driving counts as AI in general (N7).

**Result ($0):** 58 promise clusters (was 40). Dev extraction recall rose from 25.0% to 54.2%, and F1 from 36.4% to 59.1% [35.7%, 75.0%]. Precision held at 65.0% (13 matched, 7 extra, 11 missed). Claim type is right for 12 of the 13 matches. The disagreement file for Nick is now 19 rows (`exports/disagreements/20261112T210557_262d836_dev_default.xlsx`); it replaces the 21-row file from before the fix.

**Still missed (dev):** 2 passages the filter labeled "none" (product launches), 2 links that name only autonomy, 1 link too far from its quote, and Nick's CAT Power Generation guidance, which ties to AI only through data-center demand. That last one is a rubric question for Nick.

**For the S&P 100:** extend the list to the other 90 companies by the same procedure, then have Nick review it. `uv run aipb ai-products --universe sp100 --suggest` ranks each company's candidate names and shows which listed names its filings confirm ($0).

## D46. Checking the 58 pilot promises: a Tier 2 fix, two holds, and explanations checked by code (2026-11-12)
**Context.** Gavin OK'd checking all 58 promises (worst case about $0.55). The whole job cost $0.09: Tier 1 $0.007, Tier 2 $0.07 and explanations $0.016. Total spend is now $0.35.

**Tier 2 bug fixed.** Each run sent the first escalations on the list, even ones already finished. Those replayed from the cache for $0 but still used up the run cap, so the 17 escalations past the cap could never be reached. Now finished agent runs replay first, without a reservation, and the cap applies only to escalations not done yet. Regression test: `test_a_second_run_reaches_escalations_the_run_cap_left`. All 33 escalations are done.

**Held as pending (error reports):**
- R-002: NVIDIA "ramp customer shipments of Blackwell in the second half of the fiscal year". It was marked Delivered, but the evidence is a forward statement plus results from after the deadline.
- R-003: NVIDIA "Blackwell production ramp is scheduled to begin in the fourth quarter". It was marked Delivered on a FY2026 statement about Blackwell Ultra.

Both may well be right. The evidence shown doesn't prove them, so they're held until retrieval finds the Q4 FY2025 results.

**R-001 closed.** Under D44, Meta's 2025 capex on its own definition is $72.22 billion, which reaches the $70 billion low end.

**Explanations, which were wrong in ways the statuses weren't.** Reading all 18 publishable explanations from explain v3 found:
- "$37.26 billion falls within $30-37 billion" (it's above);
- "$72.22 billion is within the $70-72 billion range only at the top end";
- the company's voice without quotation marks ("We anticipate…", "we shipped…"), which reads as if AIPayback said it;
- a leak of internal process ("the key finding… is not verified");
- a Delivered reason based on progress after the deadline.

Fixes, all in code where possible:
- `verify/targets.py` places each capex figure for the deadline year against a promised dollar range ("is above the range; it reaches the low end"). The sentence goes into the reported-figures document, so the model cites it instead of comparing numbers itself.
- `verify/neutral.py` adds two wording checks. One catches "we/our/us" outside quotation marks, the other mentions of our checks ("key finding", "the documents", "not verified"). Either one keeps the explanation from publishing, so the item stays "Status pending review".
- A text block that repeats its cited text word for word is shown in quotation marks (it is the company's words).
- Explain prompt v5 adds third person, the company name first, the code's comparison words, and deadline-period evidence as the reason for Delivered. Explain now uses brief thinking (adaptive, effort low, max_tokens 4096). With thinking off, 8 of 17 failed the wording checks; with it on, 5 do.

**Result:** 12 of 58 published: 7 Delivered (all Meta capex) and 5 No evidence yet (Amazon). 46 are "Status pending review", including 5 whose explanations failed the wording checks (Meta $70-72 billion, NVIDIA x3, Tesla Robotaxi).

**For Nick's review before anything is public:**
- 4 of the 5 Amazon items are present-tense product claims or announcements ("DeepFleet… improving robot travel efficiency by 10%", "AI Zones", S3 Vectors, Quick Suite), not forward-looking promises. That's an extraction scope issue: extract v3 should drop them.
- The Meta $66-72 billion explanation describes the capex definition with the free-cash-flow wording; the numbers are right.
- Two explanations repeat a sentence (Amazon "AI Zones", S3 Vectors).

## D47. Sizing the Sonnet A/B (G10), and holding jiter at 0.18 (2026-11-13)

Gavin asked to start G10. As configured, the Sonnet variant (adaptive thinking, `max_tokens` 8192) would reserve about $25 for all dev passages (D39).

**Scope: only the passages Nick labeled.** New option `aipb extract --only-labeled`: it reads only dev-split passages that have a scored gold label, and it refuses test-split companies by name, so the held-out set stays unseen. The eval scores only labeled passages, so extracting the rest would add cost and no information. Of the 257 labeled dev passages, the filter sends 60 to extraction (TSLA 19, META 17, NVDA 10, CAT 6, PFE 4, BLK 4). Haiku read the same 60, so the comparison is like for like.

**Settings: Sonnet with thinking off, at Haiku's cap.** Sonnet 5.5 rejects `thinking: disabled`. Its thinking-off setting is `between_tools`, which means no thinking when the request has no tools (extract uses structured output, not tools). Haiku runs extract with thinking off, so this compares the models and not the thinking. `max_tokens` is 2048, Haiku's own cap; Haiku's longest pilot answer was 1,095 output tokens (median 313).

| Sonnet setting (60 passages) | Worst case |
|---|---|
| adaptive thinking, 8,192 (before) | $2.75 |
| thinking off, 4,096 | $1.52 |
| **thinking off, 2,048 (chosen)** | **$0.91** |

The expected real cost is about $0.15–0.20. The worst case is over $0.50, so the run needs `--confirm` and Gavin's go-ahead in chat.

**jiter held below 0.19.** Windows Smart App Control is now On on Gavin's machine (it was presumably in evaluation mode before), and it blocks jiter 0.19.0's native file. jiter is the Anthropic SDK's JSON parser, so the SDK wouldn't import and no paid call could run. Versions 0.18.0, 0.15.0, 0.11.1 and 0.10.0 all load. `pyproject.toml` adds `constraint-dependencies = ["jiter<0.19"]` (anthropic needs >=0.4,<1). This is safer than turning Smart App Control off. Lift it once 0.19+ loads on this machine (`uv run --with "jiter==0.19.0" python -c "import jiter"`).

**Result (2026-11-13, Gavin's go-ahead in chat): keep Haiku.** The run cost $0.15 (worst case $0.91). Both scored on the corrected dev gold (D48): 253 passages, 22 promises.

| Model | Precision | Recall | F1 (95% interval) | Extraction cost, same 60 passages |
|---|---|---|---|---|
| Haiku 5.5 | 76.2% | 72.7% | **74.4%** [54.1%, 88.9%] | about $0.008 |
| Sonnet 5.5 | 65.2% | 68.2% | 66.7% [46.7%, 81.6%] | $0.14 |

The intervals overlap (the sample is small), but Sonnet shows no gain at about 17 times the cost. Sonnet got the target field right more often (80% vs 60% on 5 matched promises), too few to matter. Revisit only if a later prompt change makes extraction a judgment-heavy task. Saved table: `evals/results/ab_dev.md`.

## D48. Nick's disagreement review (N7) applied (2026-11-13)

Nick reviewed the 21-row disagreement file from before D45. His verdicts: 11 "Model wrong", 1 "Label wrong", 9 "Rubric unclear", and 3 quote fixes. The product-name fix (D45) had already resolved 6 of his "Model wrong" rows (the Blackwell revenue and Q4 ramp items, Robotaxi later this year, FSD in Europe and China, Optimus, Cybercab).

**Gold corrections, applied on top of his labels.** New file `evals/gold/corrections.yaml`, applied by `aipb eval`. His returned workbooks are never edited, every entry names its review row and reason, and every quote is checked verbatim against the passage when the gold set loads.
- Row 11 (Label wrong): the NVIDIA "Copilot+ capabilities anticipated next quarter" passage becomes a promise.
- Row 10 (Rubric unclear, NVIDIA Foxconn supercomputer): the rubric decides it. Section 2's checkable test includes a concrete deliverable with no date or number (specificity 1), so it's a promise, consistent with his row 13. The other announcement rows (MediaTek, Foxconn factory, U.S. factories, RTX PRO 6000) keep his "promise" label for the same reason.
- Rows 15, 16, 22: quotes fixed to the filing's characters (™, curly apostrophes, an en dash). "PROTM" could never match.
- Rows 2–5 (CAT Power Generation): **left out of scoring, pending a decision.** Each passage ties the growth to "data center growth related to cloud computing and generative AI" in CAT's own words, so the literal rubric would count them. But the promise is about a non-AI product, and counting it makes CAT no longer a low-AI comparison. That's a scope call for Nick and Gavin.

**Two extraction rules, both free (cache replay):**
- **A quote that names AI is its own AI link.** Tesla's "In 2025, we intend to begin launching our Robotaxi business" was dropped because the model pointed at "fully autonomous vehicles". Robotaxi is a product Tesla's filings tie to AI (D45), and the quote names it.
- **Risk factors are never extracted.** The rubric says risk factors are not promises, and Nick labeled all 130 risk-factor passages "No forward-looking AI statement". 20 pilot passages are now skipped (no API call), removing 27 statements: 2 "promises" (Meta's "we continue to launch new AI features…" from row 6, and an NVIDIA Blackwell supply line) and 25 hype statements that were inflating the hype count.

**Result (dev, Haiku):** F1 59.1% → **74.4%** [54.1%, 88.9%]; precision 76.2%, recall 72.7% (16 matched, 5 extra, 6 missed). The pilot now has 60 promise clusters (was 58) and 234 AI statements. 12 are still published; the 4 changed items were all pending.

**Still missed (for extract v3, paid):** the NVIDIA announcements (MediaTek and RTX PRO 6000 were filtered out as "none"; the Foxconn factory and U.S. factories were extracted as hype). The NVIDIA Uber 2027 promise was dropped because its link ("level 4-ready mobility network") has no AI word.

**Questions for Nick (via Gavin):**
1. CAT: does AI-driven demand for a non-AI product count as an AI promise? Recommendation: no. Count promises about the company's own AI products, AI investment and results it attributes to its own AI use, and keep CAT as the low-AI comparison.
2. Announcements: keep the rubric as written (a concrete deliverable with no date or number counts, specificity 1), or require a date or number? Today's labels follow the rubric as written.
3. Autonomy: should "level 4", "autonomous driving" and "self-driving" count as AI words for the AI-link check? (The NVIDIA Uber row.)
4. A new 12-row disagreement file from today's eval: `exports/disagreements/20261113T183639_1713cd8_dev_default.xlsx`. It includes rows Nick hasn't seen, such as two NVIDIA Blackwell statements the model found that his labels don't have.

## D49. Site redesign (2026-11-13)

Gavin said the preview "looks cheap and terrible" and asked for an entirely new UI. Same data, same wording rules, new presentation:
- **Look:** editorial data-tracker style. Serif headlines (Source Serif 4), Inter for text, IBM Plex Mono for tickers, tabular figures, warm paper background, navy and gold brand, a check-mark logo. Full dark mode.
- **Status chips:** soft tinted chips replace the solid pills. "Status pending review" is an outlined chip, and a hatched segment in bars, so it reads as "not judged" rather than as a result.
- **Home:** a status-mix bar with a legend for all promises, a stat strip, the leaderboard with a per-company status bar (the sector sits under the company name), the six most recent published statuses as cards, and "How a status is made".
- **Company pages:** a status-mix panel, and status filter buttons (progressive enhancement; without JavaScript every card shows).
- **Promise pages:** two columns with a sticky "Key facts" panel. `[n]` markers in explanations link to their numbered sources, figures tables show the XBRL tag in mono, and the pending box gives the reason.
- **Fonts are self-hosted** (changed the same day). They're in `static/fonts/`: Latin and Latin Extended subsets of Inter, Source Serif 4 and IBM Plex Mono, about 385 KB, under the SIL Open Font License with `OFL.txt`. The site makes no requests to Google, and the offline preview zip shows the right fonts.
- Checked by screenshots in headless Edge at 1280px and in a true 390px frame, in light and dark. `sort.js` became `site.js` (sort plus filter).

## D50. The returned status packet holds AI drafts; the threshold stays at 0.75 (2026-11-13)

Gavin saved the returned status packet (N8) and asked for the G11 steps: import, eval, and set `gate.confidence_threshold` from the precision-coverage curve.

**What came back.** All 58 rows have a status and a note, and **every note starts "Claude draft, Nick to review."** The packet we sent had both columns empty and no such text (our code never writes it). The returned file was last saved in Excel on a Mac. So the labels were drafted with an AI on Nick's side, and nothing in the file says he reviewed them. One note gives a revenue figure "from my own knowledge", which is exactly what the rules forbid: numbers come from filings.

**Why that blocks the threshold.** A threshold set from AI-drafted labels measures one model agreeing with another, not accuracy. The first eval showed 100% precision at every threshold from 0.50 to 0.80 (8–10 items), and the Methodology page lists status-eval results automatically. Publishing that as "published status precision 100%" would be a claim we can't back.

**What changed:**
- `aipb import-statuses` now skips any row whose note still marks it as a draft ("Claude draft", "AI draft", "Nick to review", "to be reviewed"). It says how many it skipped and exits with an error. Today: 0 of 58 imported, so `evals/gold/statuses.csv` is empty.
- The status-eval results from the drafts were deleted, so the Methodology page can't pick them up.
- `gate.confidence_threshold` stays at the 0.75 placeholder.

**For Nick:** check each row against the evidence in the packet, change the status if needed, then delete "Claude draft, Nick to review" from that row's note. The drafts are fine as a starting point, but each status has to be his call. Rows he isn't sure of stay "Unsure". Then Gavin saves the file again as `evals/gold/returned/status_packet_v1.xlsx` and runs `uv run aipb import-statuses` and `uv run aipb eval-status`.

**One useful signal from the drafts (tentative, unreviewed):** the drafts disagreed with 3 of the pipeline's "Delivered" verdicts (NVIDIA customer samples in Q2, NVIDIA second-half shipments, Pfizer R&D savings). The gate held all three: one for a failed explanation check, one on confidence (0.60), one by a rubric rule. If Nick confirms them, that's evidence the gate is doing its job.

## D51. Extract v3 tried on dev, not promoted (2026-11-13)

`prompts/extract/v3.md` spells out that product claims ("helps turn month-long projects into days", "improving travel efficiency by 10%") and highlight bullets reporting past actions ("Announced…", "Unveiled…") are not promises. It also says such a bullet still counts when it states something still to come, and that "on track… by June" counts. It was aimed at the 4 Amazon items in D46.

It ran as the `v3` variant on the 51 labeled dev passages ($0.004; worst case $0.04). **Dev F1 68.1% vs 74.4% for v2:** same recall (16 matched), but 9 extra promises instead of 5. v3 moved quote boundaries (a fragment where Nick's gold has the full sentence) and added new extras (Volvo SUV, HUMAIN, Pfizer program text). v2 stays the default; v3 stays in the repo as a recorded experiment.

A code rule requiring a forward-looking cue in a promise's sentence was considered and not built. The prefilter's cue list misses phrasings in Nick's confirmed promises ("scheduled for… starting in 2026", "is coming to…", "starting in 2027"), so it would drop real promises unless tuned on the same 22 dev promises it's scored on. The Amazon items stay with Nick (D46); nothing is public.

## D52. Evidence from the deadline period gets reserved slots (2026-11-13)

R-002 and R-003 (NVIDIA Blackwell, deadline FY2025 ending 2025-01-26) were held because the evidence cited only post-deadline filings. The cause was retrieval: Tier 1 gets the top 8 keyword-ranked passages from any later filing, and nothing favored the filings that report the deadline period. NVIDIA's Q4 FY2025 release and 10-K (both filed 2025-02-26) are in the corpus with 13 Blackwell passages, including "We've successfully ramped up the massive-scale production of Blackwell…".

Change (`verify/context.py`): once a promise's deadline has passed, up to 3 of the 8 evidence slots go to passages from filings released within 100 days after the deadline period ends, the rubric's grace period. Per-filing caps and de-duplication apply across both lists. 30 of the 60 pilot promises got new evidence; Tier 1 re-ran on them for about $0.01 (worst case $0.03) and sent 32 promises to Tier 2, which waits for Gavin's OK.

**R-002 and R-003 stay open:**
- **R-002:** its evidence now includes three passages from the 2025-02-26 filings, and Tier 1 says Delivered at 0.8. But it reasons by inference (GB200 systems "coming to cloud regions… indicating" shipments began). The direct sentence in the Q4 FY2025 release ("We've successfully ramped up the massive-scale production of Blackwell AI supercomputers, achieving billions of dollars in sales…") wasn't among the passages picked. The FTS index doesn't stem words, so "ramp" in the promise doesn't match "ramped".
- **R-003:** the promise is two-part ("begin in the fourth quarter and continue into fiscal year 2026"), and its deadline was read as FY2026. So the reserved slots went to 2026 filings, not the Q4 FY2025 results.

Next retrieval fixes, not built yet: a stemming tokenizer for the passage index (a rebuild, $0), and taking the earliest deadline when a promise names a start date and a continuation.

## D53. One retry for explanations that fail their checks (2026-11-13)

Five publishable statuses were pending only because their explanation failed the wording checks (D46). `aipb explain` now retries each failing explanation once: the same request, plus a note listing the failed checks. It's a fresh request (no earlier answer or thinking replayed), so it caches on its own and re-runs cost $0. A retry that still fails stays pending. Explain worst case for the pilot: $0.01.

## D54. S&P 100 run prepared; waiting on cost approval (2026-11-13)

Gavin said "just do everything". Everything on his list that doesn't need his accounts, his cost approval or Nick is done:
- **Prices re-checked** against the pricing page: all unchanged (Haiku 5.5 $0.10/$0.50 per MTok and $0.50/$2.50 over 100k tokens; Sonnet 5.5 $2/$10; batch 50% off; tool overhead 286/406 tokens). `verified_on` is now 2026-11-13.
- **Company list:** our 100 tickers match Wikipedia's current S&P 100 table. Its 101st row is GOOG, Alphabet's second share class, which we track once as GOOGL. The iShares OEF holdings file couldn't be downloaded automatically (the page loads it with JavaScript), so the independent check stays with Gavin (G16 step 1).
- **Filter dry run:** 913 requests, 165 cached from the pilot, 748 to send. Worst case $0.44. With extract (at most $2.84 if every AI passage were routed; fewer now that risk factors are skipped), verify and explain (about $0.001 per promise) and the Tier 2 cap ($0.50), the run stays under $5. $14.48 remained under the cap before today's Tier 2 run.
- **Not done, and why:** enabling GitHub Pages was blocked by this session's permission rules (it changes repo settings), so G14 stays with Gavin. Buttondown (G12), the GitHub secrets (G15) and outreach (G5) need his accounts. The S&P 100 run needs his explicit cost approval, e.g. "I approve the S&P 100 run up to $5".

## D55. AIPayback is free; everything about people paying us is removed (2026-11-23)

Gavin, 2026-11-23: "get rid of anything that has to do with people paying us. For now this will be completely free."

**Removed:**
- **Site:** the Pricing page (`pricing.html`) and its nav and footer links, the "Pro (waitlist)" and "Reports and pilots" tiers in `config/site.yaml`, and the pricing styles. The About page now says the project is free and there's nothing to buy.
- **Go-to-market kit:** the price in `gtm/PILOT_PROPOSAL.md` (pilots are now free; the Stripe Payment Link is gone), the Pricing section of `gtm/SOLUTION_BRIEF.md` (now "Cost: free"), the willingness-to-pay question and notes section in `gtm/discovery/`, and "paying audience" and "buyer" wording in the outreach and demo drafts.
- **Plans:** the Pro tier, Stripe Checkout and Payment Links, paid reports and pilots, sponsor slots and "cost per paying user" in `docs/BRIEF.md` §9 and `docs/PLAN.md` Phase 6. Revenue is no longer a project goal; the goals are now career evidence, accuracy and LinkedIn findings.
- **Accounts:** no Stripe account is needed. Buttondown stays on its free tier.

**Kept:** API-cost wording ("paid stages", "never pay twice"), which is about our own API spend, and the secret scanner's Stripe-key pattern, which only blocks keys from being committed. D4's note that Vercel bans commercial use is history; GitHub Pages stays either way.

**Phase 6** is now free partner integrations only (alerts, exports, an MCP server, pilot benchmarks), built only when a design partner asks.

## D56. The S&P 100 run: $0.39, 49 statuses published after review (2026-11-23)

Gavin approved the run "up to $5" on 2026-11-23. Before it: prices re-checked against the pricing page (all unchanged; `verified_on` 2026-11-23), and `config/universe/sp100.csv` matched the iShares OEF holdings as of 2026-11-20 (the fund's 101st line is GOOG, Alphabet's second share class, tracked once as GOOGL). That closes G16 step 1.

| Stage | Worst case | Actual | Notes |
|---|---|---|---|
| filter | $0.44 | $0.14 | 913 requests, 748 new; 340 promise, 397 hype, 3,201 none |
| extract | $0.30 | $0.05 | 572 passages (79 risk-factor passages skipped), 400 new requests |
| verify Tier 1 | $0.11 | | 171 promises, 111 new |
| verify Tier 2 | $0.50 per run | $0.18 with Tier 1 | 85 escalations, 68 new, over four runs at the $0.50 run cap |
| explain | $0.08 | $0.02 | 59 passed the checks (10 after one retry); 6 failed and stay pending |
| **Total** | **$4.84 planned** | **$0.39** | |

**AI product names ap2.** The extract dropped 109 statements outside the pilot for having no verified AI link. Most were right to drop (fab construction, acquisitions, cloud capacity). Added the AI products the drops named: AMD Instinct and ROCm, Adobe Firefly and GenStudio, ServiceNow Now Assist (each confirmed in 7–15 of the company's own filings). Extract replayed from cache at $0: 171 promise clusters, up from 167. Left out on purpose: AI demand for non-AI products (Micron HBM, Oracle OCI, Intel Core Ultra), the same question as Nick's open Caterpillar call (D48).

**Review of the 41 new published statuses.** Every one was read against its evidence. Ten are held with open error reports (R-004 to R-013), so 49 of 171 are published (32 Delivered, 15 No evidence yet, 2 On track):
- **Wrong verdicts (2):** Oracle "double-digit revenue growth" in FY2025 marked Delivered against 8.4% growth (R-004); ServiceNow "available in November" marked Delivered though the later filing moved it to March 2025 (R-005).
- **Evidence doesn't support the status (2):** AMD MI325X "available in Q4 2024" Delivered on an "unveiled" announcement with no availability date (R-006); Micron's second Idaho fab "On track" on a restated plan alone (R-007).
- **Not the company's promise (6):** two Qualcomm analyst forecasts (R-008, R-009), AT&T's Open RAN plan in an Intel release (R-010), two market-size estimates from AMD and Intel (R-011, R-012), and IBM's fund that was already set up (R-013).

**What this says about the pipeline.** _(Corrected in D57: only Tier 1 checked the Oracle promise. Its confidence was 0.85, so it wasn't escalated, and its own finding said 8.4% was "short of the 10% double-digit growth target" while its status said Delivered.)_ Nothing compared the growth figure with "double-digit" in code. Next fixes (built in D57): a code check that compares "double-digit" and percentage targets with the computed growth figure (as D46 did for ranges), and an extract rule that drops third-party forecasts and market-size statements. Both are $0 to build; re-checking the affected promises costs cents.

Not public: `SITE_DEPLOY` is off, and Nick reads the published statuses before it goes on.

## D57. Two $0 checks from the S&P 100 review, and the 10 held items re-checked (2026-11-23)

Gavin said "Yes, build them" on 2026-11-23. Both checks are code; the re-check cost $0.0017 (spend still $0.95).

**Correction to D56.** D56 said Tier 1 and Tier 2 agreed on the Oracle error. They didn't: only Tier 1 checked it (confidence 0.85, so no escalation), and its own key finding said FY2025 revenue growth of 8.4% was "short of the 10% double-digit growth target" while its status said Delivered. The lesson is the same (a confident model can contradict itself; arithmetic belongs in code), but the claim was wrong.

**1. Growth targets checked in code (`aipb.verify.targets`, applied by the gate).** For a total-revenue growth target in percent, code takes the deadline year's reported revenue change from the promise's whole number table and holds any status it contradicts: below the target but Delivered or On track, or meeting it but anything other than Delivered. It uses the rubric's tolerances (section 5): "double-digit" is a 10% target and "triple-digit" 100%, met at 95%; "at least / more than / exceed X%" at 100%; "about X%" at 90%; "X% to Y%" at the low end. Narrow on purpose: segments ("cloud revenue", "ISG net revenue"), quarters ("Q3 2025 revenue growth") and other measures (ARR, RPO) aren't the annual total and aren't compared. On the S&P 100 data it applies to two promises: Oracle (8.4% against a 9.5% floor, held) and Intuit (15.6%, Delivered, consistent). The public hold reason names no figure, draft status or direction ("the reported revenue growth for the deadline year and the draft status disagree"), since "8.4%, below the target" would be an unreviewed finding.

Tried and not kept: handing the comparison sentence to the explainer, as D46 does for capex ranges. The Intuit explanation copied it ("meets the target; the lowest figure that meets it is 9.5%"), and the D46 auto-quoting put it in quotation marks as if a filing said it. Restricting the auto-quoting to filing text instead turned the figure sentences other explanations copy ("Capex for the fiscal year ended 2025-12-31 was $91.45 billion…") into run-on prose, so that was reverted too. The gate check alone carries the safety property: no published status contradicts a computed growth figure.

**2. Statements that aren't the company's own commitment are dropped at extract (`aipb.stages.extract.not_own_statement`).** A forecast its sentence attributes to analysts or research firms ("analysts estimate", "according to IDC"), and a target that is a market's size ("TAM", "addressable market", "market opportunity", "market size") rather than the company's result. Logged as `dropped_not_own`; replayed from cache at $0. Over all 887 stored statements it drops exactly 4, all from the review, and none of Nick's 31 gold promises. The rubric (section 2) doesn't name these cases, so this is a rule for Nick to confirm: a promise is about what AI will deliver *for the company*, as the company states it. A company's own market share is still its result and is kept.

**Re-check of the 10 held items (R-004 to R-013).**

| Report | Item | Now |
|---|---|---|
| R-004 | Oracle double-digit growth vs 8.4% | Held by the growth check; report closed |
| R-008, R-009 | Qualcomm analyst estimates | Dropped at extract; reports closed |
| R-011, R-012 | AMD and Intel market sizes | Dropped at extract; reports closed |
| R-005 | ServiceNow November availability moved to March | Still open: a moved date needs reading, not arithmetic |
| R-006 | AMD MI325X "unveiled", not shown available | Still open |
| R-007 | Micron Idaho fab "On track" on a restated plan | Still open (rubric 4: a reaffirmation is "No evidence yet") |
| R-010 | AT&T's plan in an Intel release | Still open: whose plan it is isn't safe to decide by pattern |
| R-013 | IBM's fund already set up (past action) | Still open: extract v3's past-action rule targets it, but v3 isn't promoted |

Result: 167 promises (from 171), 49 published (unchanged: 32 Delivered, 15 No evidence yet, 2 On track), 118 pending. The published set is identical to D56's. Nick still reads the 49 statuses and the five open items before `SITE_DEPLOY`.

## Upcoming decisions (recorded when made)
- The CAT scope question and the announcement rule (D48 questions 1–2), from Nick.
- `gate.confidence_threshold`, once Nick has reviewed the status packet himself (D50).
- The confidence threshold, from the precision-coverage curve (Phase 3, once Nick labels statuses).
