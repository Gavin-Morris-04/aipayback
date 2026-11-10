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

**"How do you make a data pipeline reproducible?"** (Phase 1)
The repo commits a manifest with the URL and sha256 of all 239 SEC documents, not the 555 MB of raw files. A fresh clone runs `aipb restore`, re-downloads, verifies the hashes and rebuilds the database. I proved it: the rebuilt database had the same 18,381 passages with identical IDs, hashes, keyword hits and dedup marks, and 0 API calls.

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

## Solutions Engineer
*(Phase 4–5: the demo script, objection handling with eval numbers, the solution brief, the pilot proposal.)*

## AI Transformation Engineer
*(Phase 4–6: ROI measurement, partner time before vs after, and cost per verified promise.)*

## Failures the evals caught
*(Phase 2–3: real examples with numbers.)*
