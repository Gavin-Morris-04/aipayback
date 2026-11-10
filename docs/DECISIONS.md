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

## Upcoming decisions (recorded when made)
- Citations vs structured outputs. They can't be combined in one call (the API returns a 400), so the cited explanation is a separate step after the structured verdict (Phase 3).
- Tier 2 agent as a manual loop, so every turn is logged and capped (Phase 3).
- Sonnet use, decided by the capped A/B test (Phase 2).
