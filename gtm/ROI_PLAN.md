# ROI measurement plan

**Question:** does AIPayback save design partners time on AI-claims research, and by how much? This is the AI Transformation story: we measure whether *our* AI pays off, the same way we measure companies' AI.

**Rule:** report only measured numbers, with the sample size. If only two partners are measured, say "two partners", and never extrapolate to "users".

## What we measure

| Metric | How | When |
|---|---|---|
| **Baseline minutes per check** | The partner does one standard task (below) their usual way while timing it, or reports the time from their last real check (marked "self-reported") | Discovery call, or a short session after it |
| **Minutes per check with AIPayback** | The same task type on a **different** company, using AIPayback | After the Phase 4 demo |
| **Answer quality** | The finance student scores both answers against the filings: correct / partly correct / wrong | After each task |
| **Checks per month** | From the discovery notes | Discovery call |
| **Time saved per month** | (baseline − with AIPayback) × checks per month | Computed |
| **Would keep using?** | Yes / no, and why | After the second task |

## The standard task

> "For [company], find one specific AI-related target the company set in a 2024 or 2025 SEC filing. Then find what its later filings say about that target. Write down the target, the evidence, and your conclusion, with where you found each."

- Use a **different company** for the baseline and the AIPayback run, so the second run isn't faster just because they've seen it.
- Pick both companies from those with a published scorecard, matched roughly on how much AI they discuss.
- The partner chooses their own tools for the baseline: filings, search, ChatGPT, anything.
- Time starts when they read the task and stops when they've written the conclusion.

## Recording

Add one row per task to `gtm/roi/roi_log.csv` (created at the first measurement):

```
partner_id,partner_type,date,condition,company,minutes,self_reported,answer_quality,notes
```

- `condition` is `baseline` or `aipayback`.
- `partner_id` is a code (P1, P2…), never a name. Names stay in the discovery notes.

## Reporting (README, solution brief, interviews)

- Per partner: baseline minutes → AIPayback minutes, plus answer quality.
- Overall: the **median** time saved with n, and how many partners would keep using it.
- Include anything that went worse: slower runs, wrong answers, confusing screens. Those findings drive Phase 6.

## Ethics

- Partners know they're being timed and why.
- No partner's employer, holdings or clients are named in anything we publish without written permission.
