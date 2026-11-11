# LinkedIn launch drafts

> Every number must come from `docs/FINDINGS.md` or the eval results, with its denominator. Pick one or two findings that survive the caveats in FINDINGS.md. If a finding has fewer than 5 items, don't post it. Nick reviews any post that interprets results.

## Post 1: launch (Gavin)

> Since 2023, companies have promised a lot from AI. Did it pay off?
>
> Over `[[weeks]]` weeks, [Nick] and I built AIPayback. It reads every 10-K, 10-Q and earnings release from the S&P 100 since 2024, pulls out the specific AI promises (`[[N]]` of them), and checks each against what the company's later filings report, with citations to both.
>
> One finding: `[[finding 1, with its denominator, e.g. "X of Y forward-looking AI statements were specific enough to check"]]`.
>
> How we kept it honest:
> • Every quote checked word for word against the filing by code
> • "Walked back" only when two independent checks agree; otherwise "pending review"
> • Accuracy measured on held-out companies: `[[F1]]` / `[[precision]]`
> • The whole S&P 100 run cost `[[$X]]` in API credit
>
> Scorecards: `[[site_url]]`. Informational only, not investment advice. Feedback welcome, especially if you find an error.

## Post 2: the engineering story (Gavin, a week later)

> How do you build an LLM pipeline on a `[[$19]]` budget without it lying about real companies?
>
> `[[3–5 bullets from docs/INTERVIEW_NOTES.md with real numbers: the budget guard, code-first filtering (under 4% of passages reach the model), batches + caching, verbatim quote checks, the eval that caught [[a real failure]]]]`

## Post 3: the finance view (Nick)

> `[[Nick's interpretation of one finding, within the caveats: what an analyst should take from it and what they shouldn't.]]`
