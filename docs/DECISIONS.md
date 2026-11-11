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

**Gaps that remain (real absences, not missing tags):**
- **Gross margin** is computed only from `GrossProfit`, which AMZN, BLK, CAT, FDX, META and PFE don't report. The draft doc said "otherwise revenue minus cost of revenue", but the code never did that: `cost_of_revenue` isn't used by any claim type. Until it's built, those companies' gross-margin promises can only be checked from text. The outcome is No evidence yet or Status pending review, never a guessed status.
- Not reported at all: `OperatingIncomeLoss` (PFE), restructuring tags (MSFT, NVDA), an R&D line (AMZN, BLK, FDX) and headcount (every company).

## Upcoming decisions (recorded when made)
- Sonnet use, decided by the capped A/B test (Phase 2, once there's a key and labels). Size it first (D39).
- Whether to compute gross profit as revenue minus cost of revenue when `GrossProfit` isn't reported (D40). Ideally before the pilot's verify step.
- The confidence threshold, from the precision-coverage curve (Phase 3, once Nick labels statuses).
