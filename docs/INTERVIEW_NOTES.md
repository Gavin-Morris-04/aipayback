# Interview notes

Likely questions, with answers grounded in AIPayback's real numbers. Every number here must come from the repo (ledger, eval results, cost report). Each phase adds to this file.

## Common to all three roles

**"Tell me about a project you're proud of."**
AIPayback checks whether the AI promises companies made in their SEC filings in 2024–25 actually paid off, using their later filings. It publishes cited, neutral scorecards. The constraint that shaped everything: $19 of API credit in total. *(Phase 5: add the S&P 100 cost, eval accuracy and partner count.)*

**"How did you keep costs under control?"** (Phase 0 answer; add real numbers as phases complete)
- I built the budget guard before writing a single LLM call.
- Every run reserves its worst case before it starts: estimated input plus the full `max_tokens` output on every request. Runs above $0.50 need an explicit `--confirm`, and nothing can push total spend past $15.
- Every call's exact cost comes from the API's usage numbers and the official per-token prices, stored as Decimals.
- Those costs go into an append-only ledger in git. All my devices and the cron job share one budget, and git's union merge means two machines appending at once never conflict.
- Outputs are cached by request hash, prompt version and model, so nothing is ever paid for twice. CI runs fully offline against that cache.

**"What was a surprising detail?"**
- **Haiku 5.5 thinks by default.** It runs adaptive thinking at medium effort, and thinking tokens bill as output, so a yes/no classifier can quietly cost about 10× more than it should. Every stage now sets thinking explicitly.
- **The 100k tier counts cached tokens.** Haiku's long-prompt price tier counts cache reads, so a mostly cached 110k prompt still pays the 5× rate. The guard refuses anything over 100k.
- **Vercel's free plan bans commercial use.** That ruled it out for a site with a paid tier.

**"How do you handle messy real-world data?"** (Phase 1)
Every surprise in the SEC data became a rule and a test:
- **IBM puts its MD&A in Exhibit 13.** The 10-K main document is 15,871 words; the annual report exhibit is 71,662. Parsing only the main document would have missed IBM's management discussion entirely.
- **ExxonMobil re-registered in 2026.** The ticker now points to a new holding company with 4 filings. The 2024–2025 history is under the old CIK. I added predecessor CIKs plus a warning when a company has too few filings, so the S&P 100 run catches the next case automatically.
- **Tables of contents look like headings.** Headings are taken only from paragraphs, never from tables.
- **Ligatures break search.** "ﬁled" isn't "filed". Text is stored verbatim but searched in a normalized form.
- **BlackRock re-registered too, and my warning missed it.** Its new holding company still had 9 periodic filings, enough to pass the count check, but none before November 2024. Ingest now also warns when a company's first 10-K/10-Q comes more than 120 days into the window, and BlackRock's predecessor CIK is listed. Sandisk triggers the same warning for a different reason: it was spun off in 2025, so there is no predecessor, and the decision log says so.
- **Wikipedia isn't a data source you can trust blindly.** Berkshire's ticker cell held a hidden editor comment ("DO NOT CHANGE THIS TICKER…"), which broke the CIK lookup. The list is cleaned, and the run plan says to cross-check it against the index provider before the paid run.

**"How do you make a data pipeline reproducible?"** (Phase 1)
The repo commits a manifest with the URL and sha256 of all 239 SEC documents, not the 555 MB of raw files. A fresh clone runs `aipb restore`, re-downloads, verifies the hashes and rebuilds the database. I proved it: the rebuilt database had the same 18,381 passages with identical IDs, hashes, keyword hits and dedup marks, and 0 API calls.

**"How big did it get, and what would the full run cost?"** (Phase 5)
For the S&P 100, ingest pulled 2,407 SEC documents for $0: 179,348 passages and 905,926 XBRL facts. Plain code then cut that to 3,938 unique AI passages in the 2024–25 promise window. The worst case for the whole paid pipeline is under $4.84 at 1,000 promises:
- filter: $0.54, exact
- extract: at most $2.84
- verification: about $0.001 per promise
- the agent: capped at $0.50

That worst case assumes every response uses its full token limit. The pilot's 129 filter requests are reused from cache, so the S&P 100 run only sends 784 new ones.

**"What did Phase 1 cost?"** $0.00 of API credit. 236 filings, 18,381 passages and about 100,000 XBRL facts were processed with plain code: rate-limited downloads, parsing, full-text search and keyword filters. The LLM only starts in Phase 2, and only on the 688 unique AI-keyword passages from 2024–2025 filings: under 4% of the corpus. Later filings are searched as evidence, not classified.

## Forward Deployed Engineer
*(Phase 1–4: discovery calls, what partners actually asked for, integrations built into their workflows.)*

**"How did you work with a non-technical domain expert?"** (Phase 1)
- The finance student never touches Git or code. They get one Excel file per company: AI words highlighted in red, dropdowns for every label, a link to the SEC filing, and an Instructions tab.
- The worked examples in the labeling guide use a fictional company, so my examples can't bias their labels on real rows.
- When they return a file, the importer writes a plain-English list of fixes ("Row 12 (IBM-011): Promise 1's quote is not in the passage text…") that the CS student can forward unchanged. Good rows import even when others need fixing, so nobody redoes work.

**"How did you avoid biased evaluation data?"** (Phase 1)
- Labeling rows come from the keyword filter, not from the model, so the answer key doesn't inherit the model's blind spots.
- 5% of rows are random passages with no AI keyword, so we can measure what the keyword filter itself misses.
- Rows are sampled with a fixed seed per company, from deduplicated 2024–2025 filings only.

**"How do you stop an LLM from saying something false about a real company?"** (Phases 2–4)
Layered so that no single model output can publish a claim:
1. **Quotes:** code locates every quote in the filing text after normalization and stores the filing's own characters. A misquote gets one retry, then it's dropped.
2. **Numbers:** they come from XBRL and are computed in code. The judge can only cite ids (E1, N3) from a table code built, and code rejects any id it didn't provide.
3. **Negative statuses:** "Walked back" needs two independent checks (a one-call judge and a separate tool-using agent) that agree. "Silent" walk-backs need conditions code verifies (deadline passed, at least two later 10-K/10-Qs, no later mention).
4. **Explanations:** a separate Citations call; code checks every cited span against its source, and a lint blocks judgment words.
5. **The gate:** anything that misses a check is published as "Status pending review" with the quote only.

**"Why not use an agent for everything?"**
- Tier 1 is one structured call per promise, with deterministic retrieval in front of it, so it's cheap and replayable.
- The agent (Tier 2) only runs on low-confidence cases and as the second check on walk-backs. It's a manual loop through the same cached, budget-guarded gateway: 8 turns and 60k tokens per promise, $0.50 per run, and no verdict unless it calls `submit_verdict`.
- A replayed agent run costs $0 because every turn's request is deterministic and cached.

**"How do you never pay twice in an LLM pipeline?"**
- Every output is cached by (request hash, prompt version, model) and committed to git.
- Filter requests pack passages **within one filing only**, so next month's new filings never change (and never re-pay for) last month's requests. A cross-filing packing would have re-paid the whole corpus every month.
- "As of" in the verification prompt is the company's latest filing date, not the wall clock, which would change every request every day.
- Batches that outlive their process are logged before waiting, then collected later instead of resubmitted.

## Solutions Engineer
**"Walk me through your demo."** See `gtm/DEMO_SCRIPT.md`: one real promise traced from the filing's exact sentence to its status, with a click-through citation; a "pending review" item to show what happens when we're unsure; then the accuracy table. *(Numbers fill in after the first evals.)*

**"How do you handle objections like 'LLMs hallucinate'?"** Mechanism first, then the measured number (`gtm/OBJECTIONS.md`). Quotes, numbers and citations are verified by code; uncertainty is shown, not hidden.

## AI Transformation Engineer
**"How would you measure whether an AI tool pays off?"** The same way AIPayback measures companies: a baseline, a target, and evidence. For design partners, `gtm/ROI_PLAN.md` times a standard task their usual way and then with AIPayback, on different companies so learning doesn't count as savings. The finance lead scores answer quality, and we report the median with n. *(Partner numbers pending discovery calls.)*

## Failures the tests and evals caught
*(Eval failures get added after the first labeled runs. These are real bugs the test suite caught while building, each before it reached real data.)*
- **Interrupted batch under-counted spend.** A batch is billed even if the process dies while waiting, but the run's reservation was being released anyway. Now an interrupted batch holds its reservation until `batch-collect` settles the real cost (D20).
- **A low-confidence check vetoed a confident one.** The gate treated an unsure Tier 1 answer that disagreed with a confident Tier 2 answer as a "disagreement", which made escalation pointless. Now a confident check beats an unconfident one; two confident checks that disagree still stay pending (D28).
- **Silent walk-backs were rejected for citing nothing.** Silence has nothing to cite; the validation rule ran in the wrong order (D28).
- **A/B runs overwrote each other.** Cluster ids and eval result files didn't include the variant, so a Sonnet run collided with the default run's results.
- **Six Cisco filings silently vanished from the manifest.** I committed while a background ingest was appending to `filings.jsonl`, and pre-commit's stash-and-restore rewrote the file mid-run. This wasn't caught by a test: I found it by cross-checking the raw files on disk against the manifest when Cisco showed only two 10-Ks. Ingest now reloads the manifest from disk after writing, re-appends anything missing and says so, and a unit test simulates the lost lines.
- **The estimator ignored a hidden tool-use prompt.** Re-checking prices before the S&P 100 estimate, I found that any request with tools also bills a 286–406 token system prompt that the estimator didn't count. Now it does, so the worst case stays above the real count (D37).
- **Ligatures would break keyword matching.** IBM's 10-K writes "ﬁled" with a single ﬁ ligature character, so a word like "artiﬁcial" written the same way wouldn't match "artificial". All matching runs on NFKC-normalized text, and a fixture test covers it (D14).
