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

## Forward Deployed Engineer
*(Phase 1–4: discovery calls, what partners actually asked for, integrations built into their workflows.)*

## Solutions Engineer
*(Phase 4–5: the demo script, objection handling with eval numbers, the solution brief, the pilot proposal.)*

## AI Transformation Engineer
*(Phase 4–6: ROI measurement, partner time before vs after, and cost per verified promise.)*

## Failures the evals caught
*(Phase 2–3: real examples with numbers.)*
