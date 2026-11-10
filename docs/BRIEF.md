# AIPayback — Project Brief for Claude Code (Plan Mode)

You are in **plan mode**. Read this whole brief, ask clarifying questions, then produce a plan. Do not write code until the plan is approved.

## 0. Who is who

- **You (Claude Code)** do *all* engineering work: architecture, code, tests, evals, data pipelines, the website, payments wiring, integrations, deployment config, and docs. Assume the humans will not write code.
- **CS student (the person running you)** is the operator, approver and **customer-facing lead**. They approve plans and phases, run commands you can't run, create accounts, hold the keys, and do the human-only customer work in §13.2: discovery calls, demos and selling. They're targeting **Forward Deployed Engineer, Solutions Engineer and AI Transformation Engineer** roles, so the customer-facing work is a core deliverable, not a side task.
- **Finance student** is the domain expert. They write the judgment rules, hand-label the gold evaluation data, review results, and co-lead conversations with finance users. They are **not** a programmer: everything you give them must open in Excel or Google Sheets, or read as plain Markdown/HTML, and come with step-by-step instructions (§13.1).
- **Design partners** are 3–5 real early users the CS student recruits: for example a student investment fund, a finance professor, a wealth advisor, a student journalist, or an investor-relations or compliance professional. We build for *their* workflows.

## 1. The project

**AIPayback: "Did the AI promises pay off?"**

Since 2023, public companies have made big claims about AI: cost savings, margin gains, workforce reductions, new revenue, productivity. AIPayback:

1. **Extracts** specific, checkable AI promises from SEC filings.
2. **Verifies** each promise against the company's *later* filings and reported financials.
3. **Assigns a status** (§4), with **citations to both the promise and the evidence**.
4. **Publishes** free public scorecards, and sells paid products on top of them (§9).

**Goals, in priority order:**

1. **Career:** produce real evidence of Forward Deployed / Solutions / AI Transformation engineering skills:
   - discovery with real users;
   - deploying into their workflows (integrations);
   - measuring business impact;
   - demos and technical selling;
   - plus production-grade AI engineering: evals, citations, cost control, observability.
2. **Accuracy:** a wrong verdict about a real company is the worst failure mode.
3. **Revenue:** make *some* money (§9). Small and real beats big and imaginary.
4. **Visibility:** one or two defensible findings for a LinkedIn launch.

## 2. HARD CONSTRAINT: the total API budget is $19

These rules override everything else in this brief.

**2.1 Claude Code must never spend the API credits.**
- The CS student runs Claude Code on their **Claude subscription plan**, not the Console API key. If an `ANTHROPIC_API_KEY` environment variable is set in the shell, Claude Code bills that key instead of the plan.
- So name the app's key **`AIPAYBACK_API_KEY`**: store it only in `.env` and pass it explicitly to the SDK client. Never export `ANTHROPIC_API_KEY`. Remind the CS student of this during setup.

**2.2 Budget guard (build this in Phase 0, before any LLM call).**
- Every LLM call is logged with its exact cost, using a pricing config checked against the official pricing page.
- A hard cap of **$15 for the app** (leaving $4 in reserve) is enforced in code.
- Before any run: estimate the cost (use the token-counting endpoint or a calibrated heuristic) and print it. Refuse if it would exceed the remaining budget. Require `--confirm` for any run estimated above $0.50.
- `make budget` shows spent, remaining, and spend by stage and model.

**2.3 Cost-first model strategy.** Verify current models and prices in the docs.
- **Default every stage to Claude Haiku 5.5** (`claude-haiku-5-5`; about $0.10 per million input tokens and $0.50 per million output tokens for prompts up to 100k tokens, and half that through the Batch API).
- **Keep every prompt under 100k tokens.** Haiku 5.5's per-token prices are 5x higher above that size.
- Use **Claude Sonnet 5.5** only in two places:
  - a **capped** A/B comparison on the dev eval set;
  - **escalations:** the low-confidence cases Haiku flags, and only if the evals show Sonnet materially improves accuracy there.
- Use the **Message Batches API** (50% off) for every non-interactive run, and **prompt caching** for stable prefixes: system prompts, tool definitions, few-shot examples.
- **Never pay twice:** cache every LLM output keyed by (input hash, prompt version, model), and commit the outputs as JSONL (§16).
- Cheap deterministic code comes first: keyword filters, full-text search, XBRL numbers, arithmetic. The LLM only does what code can't.
- Include a budget table in the plan (dev, evals, pilot, S&P 100 run, monthly updates, reserve) and recompute it with real numbers after the pilot.

**2.4 Free infrastructure only.** Static hosting on a free tier (e.g., Vercel or Cloudflare Pages); scheduled jobs on GitHub Actions; SQLite. Paid services need explicit approval. The one expected exception is the newsletter platform (§9.1): verify its current pricing, use the free tier for as long as possible, and propose upgrading only when Pro revenue covers the cost.

## 3. Scope

- **Pilot:** 10 companies chosen by the finance student. Build and evaluate everything on the pilot first.
- **v1 universe:** S&P 100, but only after the cost is approved. Fetch the constituent list from a reliable source and record the source and date.
- **Promise window:** filings dated 2024-01-01 through 2025-12-31.
- **Evidence window:** all later filings up to the present.
- **Data: SEC EDGAR only.**
  - 10-K and 10-Q filings.
  - 8-K earnings releases (Item 2.02, usually Exhibit 99.1).
  - XBRL company facts.
  - Verify the endpoints and fair-access rules in SEC documentation: a descriptive User-Agent with a contact email (ask the CS student), and staying under the published rate limit (currently 10 requests per second).
- **Out of scope for v1:** earnings call transcripts, news articles, LLM calls triggered by public visitors, and buy/sell recommendations of any kind.

## 4. Core concepts (DRAFTS — the finance student finalizes these)

**Promise.** A forward-looking statement about what AI will deliver, specific enough that a later filing could confirm or refute it. Count vague hype separately; the ratio of hype to checkable promises is a finding in itself.

**Claim types:** `cost_savings`, `margin`, `revenue`, `workforce`, `capex_investment`, `productivity`, `product_or_timeline`, `other`.

**Statuses:**
- **Delivered:** later filings confirm the outcome met the promise, within a defined tolerance.
- **On track:** the deadline hasn't passed and later filings show measurable progress.
- **No evidence yet:** nothing later confirms or refutes it.
- **Walked back:** the company explicitly lowered, delayed or dropped the commitment, or silently abandoned it after the deadline (flag the silent case separately).

Use neutral language only. Every status links to its sources.

## 5. Pipeline (Python; stages must be idempotent, resumable and cached)

1. **Ingest:** ticker→CIK; download filings; cache raw files; respect SEC rate limits.
2. **Parse:** clean HTML into text; split into sections and passages with stable IDs; store them in SQLite with an FTS5 full-text index. No vector database unless evals prove retrieval misses.
3. **Filter:** a high-recall keyword prefilter, then a Haiku batch classification of passages as forward-looking AI claims.
4. **Extract:** Haiku with **structured outputs** produces Promise records (exact quote, passage ID, claim type, metric, target, unit, deadline, specificity, promise vs hype, confidence).
5. **Deduplicate:** merge restatements of the same promise.
6. **Verify, in two tiers to control cost:**
   - **Tier 1 (all promises):** deterministic retrieval (FTS search of later filings, plus the relevant XBRL metrics) feeds **one** Haiku judge call, which uses a strict-schema verdict tool. All arithmetic is done in code.
   - **Tier 2 (escalations only, capped):** a **tool-using agent** with `search_company_filings`, `get_passage`, `get_reported_metric`, `calculate` and `submit_verdict`, with iteration and token caps. It runs only on low-confidence Tier 1 cases and on Pro "deep check" requests. This keeps an agent in the project without letting it consume the budget.
7. **Explain with citations:** a separate call with the promise and evidence passages passed as documents with **Citations** enabled. Citations can't be combined with structured outputs, which is why this is a separate step. Record that tradeoff in DECISIONS.md.
8. **Publish:** export to the static site's data files.
9. **Monitor (monthly or daily cron on GitHub Actions):** detect new filings for tracked companies and process only new passages, which should cost pennies. This feeds the fully automatic newsletter and alerts (§9.1).

Check all Claude API details against the current docs (https://platform.claude.com/llms.txt). Prompts live in versioned files, and every result records its prompt version and model.

## 6. Evaluation (the centerpiece)

- Gold data comes from the finance student. Split it into **dev** (tune on it) and **held-out test** (report only), using a fixed seed.
- **Metrics:**
  - Extraction: precision, recall and F1, plus field-level accuracy.
  - Status: accuracy, per-class recall, and a confusion matrix.
  - Quote fidelity: 100% of quotes appear verbatim in their source, checked by code.
  - Cost and latency per promise.
- **Evals must be cheap.** Cached outputs mean re-runs only pay for items whose prompt or model changed. Cap each eval run with the budget guard.
- `make eval` writes timestamped results, and the eval history goes in the README. CI runs a tiny subset against cached outputs, with zero API calls.
- **Production monitoring:** each month, a random sample of *published* items (site and newsletter) goes to the finance student for a quick accuracy check. Track the production accuracy rate over time, alongside the offline eval numbers.
- Never invent, round up or cherry-pick numbers.

## 7. Observability, reliability, security

- An `llm_calls` table records: run_id, stage, model, prompt_version, tokens (input, output, cache read, cache write), batch flag, latency and cost. `make cost-report` summarizes it.
- Measure before/after numbers for every optimization (routing, caching, batching, escalation). These go in the README and on the resumes.
- Retries with backoff and rate limits for the SEC and the API. Handle malformed filings gracefully.
- `.env` is git-ignored and `.env.example` is committed. Add a secret-scanning pre-commit hook. API keys never reach the frontend.

## 8. Website (static, precomputed, free to host)

- **Pages:**
  - Home: headline stats, a leaderboard, and a newsletter signup.
  - Company scorecard.
  - Promise detail: quotes, evidence, cited explanation, and SEC links.
  - Methodology: rubric, eval results, limitations, and how to report errors.
  - Pricing: the free and paid tiers.
  - About: both founders, with LinkedIn links.
- The footer carries a disclaimer: informational only, not investment advice.
- Credible, fast and SEO-friendly: one page per company and per promise.

## 9. Business model (keep the engineering cheap; validate before building)

Build in this order, and only build a paid feature after a design partner or user asks for it:

1. **Free public site.** This drives traffic, search rankings and credibility.
2. **Free newsletter, "AI Promise Watch," sent fully automatically every month** (§9.1).
3. **Pro tier**, at a price for the humans to test (suggested starting point: $8–15 per month). Start as a **paid newsletter tier** on the same platform (zero auth code), sent fully automatically and offering:
   - watchlist alerts when a tracked company adds or changes an AI promise;
   - monthly CSV/Excel exports;
   - full history.

   Only later, if demand exists, add accounts (e.g., Supabase auth) and Stripe Checkout for in-site Pro features.
4. **Paid reports and pilots (B2B), the most realistic real money.** For example, an "AI Disclosure Benchmark" comparing one company's AI claims and their support against its peers. Possible buyers: investor-relations and compliance teams, securities lawyers, consultants, and journalists. The SEC is actively scrutinizing companies' AI disclosures in 2026, which creates demand. Sell with a Stripe Payment Link and deliver a generated report that the humans review before sending. **Data and benchmarking only; never legal or investment advice.**
5. **Ads:** no display ad networks; they pay very little at low traffic and undermine trust. At most one clearly labeled **sponsor slot** in the newsletter or site, once there's an audience.

**Integrations for design partners** (the Forward Deployed Engineer evidence; build only what partners ask for):
- a Google Sheets/Excel export;
- Slack or email alerts;
- an **MCP server** (`search_promises`, `get_company_scorecard`) so partners can query AIPayback from their own Claude app.

**Unit economics:** the public pages cost nothing per visitor (precomputed). Alerts and monthly updates should cost cents. Track API cost per paying user in `make cost-report`. **Revenue buys more API credits first**, for example to expand to the S&P 500.

### 9.1 Fully automatic newsletter and alerts (no human editing or sending)

The newsletter must write, check and send itself on a schedule. Automated safeguards replace human review, and a wrong claim about a real company must never go out.

**Platform.** Use a newsletter platform whose API can create *and send* issues and that supports paid subscriptions.
- **Default: Buttondown.** Its API covers the draft, schedule and send lifecycle, and it supports paid subscriptions through Stripe.
- **Avoid beehiiv for this.** Its API post creation is limited to its Max and Enterprise plans.
- Verify the current API capabilities and pricing before committing. Ask before enabling anything paid.

**Schedule (GitHub Actions cron):**
- **Free issue:** monthly. New AI promises, status changes, one data-backed stat, and links to the site.
- **Pro:**
  - a weekly digest;
  - alerts when a watched company files something that adds or changes an AI promise. Implement watchlists with platform subscriber tags if supported; otherwise use a full-coverage weekly digest.
  - a monthly CSV export link.

**How each issue is built:**
- **Mostly templates.** Structured data from the database fills deterministic templates. Haiku writes only the short intro and summaries, and only from the structured data it is given.
- **Automatic fact check.** Every number, company name, ticker, date and status in the LLM-written text must match the source data, checked by code. On a mismatch, regenerate once; if it still fails, fall back to template-only text.
- **Inclusion gate.** An item appears only if:
  - its quotes are verified verbatim and its citations are valid;
  - its verdict confidence is at or above the threshold;
  - there's no open error report against it;
  - if its status is negative ("Walked back"), two independent checks agree (Tier 1 judge + Tier 2 agent, or a capped second-model check). Otherwise hold it as "pending" and leave it out.
- **Corrections.** A corrections section is included automatically whenever a previously published status changed because of an error fix.
- **Footer.** Not investment advice, plus a plain statement that the issue was generated automatically from SEC filings and checked by automated tests. The platform handles unsubscribe links.

**Safety rails:**
- **Preview and veto window (no action needed).** 24 hours before a send, the job posts the full issue as a GitHub issue and emails a test copy to both founders. If anyone adds a `hold` label, the send is cancelled. If nobody does anything, it sends.
- **Kill switch:** a repo variable `NEWSLETTER_AUTOSEND` (true/false).
- **Fail closed.** If any check fails, the pipeline errors, the budget guard trips, or there are too few items, **send nothing** and open a GitHub issue explaining why. Never send a partial or broken issue.
- **Idempotent sends.** Each issue has a unique key (e.g., `free-2026-12`), so retries never double-send. Log every send (issue key, items, platform email ID) and commit the log.
- **Budget.** Cap each issue's LLM cost (e.g., $0.05). If the API budget runs out, send template-only issues; they need no LLM.
- **Ramp-up.** The first two issues go only to the founders (test mode). After that, flip `NEWSLETTER_AUTOSEND` to true and the schedule takes over.
- **Commands and tests:** `make newsletter-preview` (dry run, renders HTML locally) and `make newsletter-send` (what the cron calls). Snapshot tests for the templates; unit tests for the fact checker and the inclusion gate.

## 10. Customer-facing artifacts (you draft them; the humans use them)

Store these under `gtm/` (go-to-market):

- `gtm/outreach/`: short outreach messages for each design-partner type (LinkedIn DM, email).
- `gtm/discovery/`: a 30-minute discovery call guide and a notes template (problem, current workflow, time spent, tools used, what "useful" means, willingness to pay).
- `gtm/discovery/SYNTHESIS.md`: after the calls, synthesize the findings into requirements with priorities, and propose plan changes.
- `gtm/SOLUTION_BRIEF.md`: a one-page solution brief (problem, solution, how it works, proof from the evals, security and data sources, pricing).
- `gtm/DEMO_SCRIPT.md`: a 5-minute demo script and a shot list for a recorded demo video.
- `gtm/PILOT_PROPOSAL.md`: a paid pilot proposal template (scope, success metrics, timeline, price).
- `gtm/OBJECTIONS.md`: an objection-handling sheet (accuracy, hallucinations, data freshness, "why not just ask ChatGPT", security).
- An **ROI measurement plan:** for each design partner, time spent on manual AI-claims research before AIPayback versus after. This is the AI Transformation story: measuring whether *our* AI pays off.

## 11. Engineering conventions

- Python 3.12 managed with uv, ruff, pytest, and a typer CLI. A Makefile wraps common commands. GitHub Actions runs CI and the scheduled jobs.
- Unit tests for parsers, tools, scoring and the budget guard. Integration tests use cached fixture filings, so CI never calls the SEC or the Claude API.
- README with: the pitch, a Mermaid architecture diagram, the eval table, cost numbers ("the full S&P 100 run cost $X"), a quickstart, and the limitations.

## 12. Interview-readiness docs (required)

- **`docs/DECISIONS.md`:** context, options considered, choice, and evidence for each significant decision, in plain English.
- **`docs/INTERVIEW_NOTES.md`:** likely questions, with answers grounded in our real numbers. Cover the AI engineering, the budget constraint, design-partner learnings, and failures the evals caught. Tailor sections to Forward Deployed, Solutions and AI Transformation interviews.
- At the end of each phase, give a 5-bullet "what you should understand" summary for the CS student.

## 13. Human task lists (put these in the plan, with the phase each one blocks)

### 13.1 Finance student (about 20–30 hours; create every template and guide for them)

1. Choose the 10 pilot companies across at least 5 sectors. Blocks Phase 1.
2. Finalize `docs/finance/RUBRIC.md`, which you draft from §4. Blocks Phase 2.
3. Fill in `docs/finance/EVIDENCE_MAP.md`: for each claim type, where to look in the filings and which metrics prove or disprove it. Blocks verification.
4. **Label passages.** You build labeling packets per company from the *keyword* filter, not model output, so the labels aren't biased toward what the model finds. The finance student fills in `evals/gold/promises.csv`. Size the work to about 6–8 hours.
5. Label statuses for 40–60 promises in `evals/gold/statuses.csv`.
6. Review disagreements after each eval run, marking each row as model wrong, label wrong, or rubric unclear.
7. Join the discovery calls with finance users (wealth advisors, the student fund). Help define the paid report product.
8. Spot-check the top company pages before launch. Write the interpretation in `docs/FINDINGS.md` and the methodology section.
9. **Monthly, about 30 minutes:** check the random sample of published items (§6, production monitoring). The newsletter itself is fully automatic: no editing or sending.

Also write `docs/finance/LABELING_GUIDE.md`: how to open the files, worked examples, how to mark rows "unsure," and how to return files.

### 13.2 CS student (human-only; this is the Forward Deployed / Solutions Engineer work)

**Setup:**
1. Create a **private** GitHub repo and run `gh auth login` on each device.
2. Run Claude Code on the Claude subscription plan (§2.1).
3. Create the Console API key with a **spend limit**. Store it as `AIPAYBACK_API_KEY` in `.env`.
4. Provide the SEC contact email.
5. Create the free hosting, newsletter (Buttondown) and Stripe accounts when the plan reaches them, and add their API keys as GitHub Actions secrets as instructed.

**Customers:**
6. Recruit 3–5 design partners, using the outreach drafts.
7. Run the discovery calls and fill in the notes.
8. Demo the product to partners and collect feedback.
9. Measure each partner's before/after time.
10. Pitch at least one paid pilot or report.

**Every phase:**
11. Approve the phase, commit the finance student's files, and read DECISIONS.md and INTERVIEW_NOTES.md.

## 14. Findings for LinkedIn

`make findings` computes aggregate stats from published results (for example, the share of AI statements that were checkable, and the status breakdown by claim type and sector) and writes `docs/FINDINGS.md` with sample sizes and caveats. No claim may go beyond the data.

## 15. What I want from you now (plan mode)

1. **Ask clarifying questions first**, at most 5, and only ones that change the plan. Examples: whether the CS student has a Claude subscription plan for Claude Code, hosting preference, newsletter platform, team names.
2. **Then produce the plan:**
   - the architecture and a Mermaid diagram;
   - the data model;
   - the repo structure;
   - the **budget table** (§2.3);
   - **phases with acceptance criteria.** Suggested arc for about 5–6 weeks of part-time work:
     - Phase 0: setup, billing safety, and the budget guard;
     - Phase 1: pilot ingestion, labeling packets, and the outreach and discovery kit. Discovery calls start now, in parallel.
     - Phase 2: extraction and evals, ending with a baseline and a capped Haiku-vs-Sonnet comparison;
     - Phase 3: two-tier verification and cited explanations;
     - Phase 4: free website launch, plus the automatic newsletter in founders-only test mode for two issues before auto-send is enabled; design-partner demos;
     - Phase 5: the S&P 100 run after cost approval, findings, the LinkedIn launch, and the solution brief and demo video;
     - Phase 6: monetization and partner integrations, driven by what discovery found (Pro alerts, exports, MCP server, paid report and pilot).
   - the human tasks each phase depends on;
   - the top risks and their mitigations, including running out of budget, low promise counts, ambiguous verdicts, no paying customers, and legal wording;
   - a definition of done.
3. **After approval:**
   - save this brief as `docs/BRIEF.md` and the plan as `docs/PLAN.md`;
   - create `CLAUDE.md` and `docs/PROGRESS.md`;
   - set up the GitHub remote and make the first push;
   - execute one phase at a time.
4. **At the end of every phase:**
   - run the tests and evals;
   - show the budget spent and remaining;
   - update the README, DECISIONS, INTERVIEW_NOTES and PROGRESS;
   - commit and push;
   - report what was built, the key numbers, and the next steps for each human;
   - then **stop and wait for approval.**

## 16. Saving progress and switching devices (usage limits)

GitHub is the source of truth. Any device, including Claude Code on the web, should be able to resume exactly where the last one stopped.

**When to commit and push to the private repo:**
- **Often:** after every working chunk (passing tests, a finished stage, an eval run). Never leave more than about 30–45 minutes of work unpushed.
- **Immediately when usage is getting high:** the context is getting long or a compaction is coming, a session has run long, or the CS student says usage is high or types **"checkpoint"**. You may not see the usage meter, so treat any of these as the signal, and push before starting anything new.
- **At the end of every phase.**

**Every checkpoint updates `docs/PROGRESS.md` first:** current phase, what's done, what's in progress (exact file and next step), what's blocked and on whom, the resume commands, any gotchas, the latest eval numbers, and the **budget spent and remaining**.

Never leave main broken without a note.

**What goes in Git, and what doesn't:**
- **Commit:** code, prompts, tests, docs, gold CSVs, eval results, `gtm/` files, and **all LLM outputs as JSONL**, so no device ever re-pays for them.
- **Git-ignore:** `.env`, the raw SEC cache, and the SQLite database.
- `make restore` rebuilds the database from the JSONL and re-downloads filings, **with zero API calls**.
- Propose Git LFS or splitting for any file over a few MB.

**Resuming on a new device:**
1. `git clone` (or `git pull`), then `gh auth login` if this device is new.
2. Copy `.env.example` to `.env` and fill it in.
3. `make setup && make restore`.
4. Start Claude Code and say: **"Read CLAUDE.md and docs/PROGRESS.md, then continue."**

Always `git pull` and read PROGRESS.md before working. If there are conflicts, stop and explain them instead of resolving them silently.
