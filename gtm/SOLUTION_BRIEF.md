# AIPayback: solution brief

> Fill every `[[...]]` from the repo before sending: eval numbers from the latest `evals/results/*_test_*.md` and `aipb eval-status`, cost from `aipb cost-report`, coverage from `aipb stats -u sp100`. Never round up, and never send a version with a placeholder left in.

## The problem

Since 2023, public companies have promised a great deal from AI: cost savings, margin gains, leaner workforces, new revenue. Analysts, journalists and compliance teams increasingly need to know which of those claims were specific, and what the company's own later filings say about them. Today that means reading years of 10-Ks, 10-Qs and earnings releases by hand, about `[[baseline minutes per check from gtm/roi]]` minutes per claim for our design partners.

## What AIPayback does

For every company in the S&P 100:
1. **Finds** each forward-looking AI statement in its 2024–2025 SEC filings, and separates checkable promises (a number, a deadline or a deliverable) from general AI language.
2. **Checks** each promise against the company's later filings and reported XBRL numbers.
3. **Publishes** a neutral status (Delivered, On track, No evidence yet, Walked back) with citations to both the promise and the evidence, linked to SEC.gov.

## How it works

- **Sources:** SEC EDGAR only. 10-K, 10-Q, 8-K earnings releases and XBRL company facts. No scraping of news or social media.
- **Code first:** downloads, parsing, full-text search and all arithmetic are plain code. The language model only classifies, extracts and judges, and only from the material code gives it.
- **Verbatim quotes:** every quote is checked by code against the filing text. A quote that doesn't match is never stored.
- **Two checks for negative statuses:** "Walked back" is published only when two independent checks agree. Uncertain items show "Status pending review" with the verified quote, never a guess.
- **Cited explanations:** every explanation cites the exact sentences it relies on, and code verifies each citation.

## Proof

| Measure | Result |
|---|---|
| Promise extraction F1, held-out companies | `[[F1]]` (95% interval `[[CI]]`) |
| Published status precision | `[[precision]]` at `[[coverage]]` coverage |
| Quotes verbatim | `[[100%]]` (checked by code) |
| Cost to process the S&P 100 | `[[$X]]` total API cost |
| Time per claim for design partners | `[[baseline]]` min by hand → `[[with AIPayback]]` min |

Labels come from a finance student who hand-labeled `[[N]]` passages and `[[M]]` statuses. Methodology and limitations: `[[site_url]]/methodology.html`.

## Security and data

- Public SEC data only. We store no customer data beyond the email addresses partners give us.
- API keys live in GitHub secrets and a git-ignored `.env`. Pre-commit hooks and CI block key patterns, and a full-history secret scan runs on every push.
- Static site: nothing runs on the server, and visitors never trigger model calls.

## Cost

Free. Every scorecard, the monthly newsletter and the methodology are free, and there are no paid tiers. Design partners can also ask for a free pilot: an **AI Disclosure Benchmark** of one company's AI claims and their support against its peers, reviewed by both founders before delivery (`gtm/PILOT_PROPOSAL.md`).

Data and benchmarking only: never investment or legal advice.

**Contact:** aipayback.team@gmail.com
