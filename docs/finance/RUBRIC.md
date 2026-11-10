# AIPayback rubric (DRAFT for the finance student to finalize)

**Status:** draft written by Claude Code from the project brief (section 4). **You own this document.** Every rule marked **DECIDE** is a proposal; change it, approve it, or replace it. The software and the labels follow whatever this file says once you approve it.

**How to edit:** the CS student puts a copy of this file in the shared Drive as a Google Doc. Change the text directly or leave comments there, and tell the CS student when it's final; they copy your changes back into the repo. Nothing here needs code.

---

## 1. Principles (fixed; these come from the brief)

1. **A wrong verdict about a real company is the worst failure.** When the evidence is unclear, the published status is **"Status pending review"**, never a guess.
2. **Neutral language only.** We report what the filings say, not whether management did a good job. See section 6.
3. **Every status cites both sides:** the exact promise quote (with its filing) and the exact evidence (a quote, a reported number, or both).
4. **Numbers are never invented, rounded up or cherry-picked.** Arithmetic is done by code from reported figures.
5. **Not investment or legal advice.**

## 2. What counts as a promise

A **promise** is a forward-looking statement, in a 10-K, 10-Q or earnings release, about **what AI will deliver**, that is **specific enough for a later filing to confirm or refute**.

All three must hold:

| Test | Passes | Fails |
|---|---|---|
| **Forward-looking** | "we expect", "will", "plan to", "target", "by 2026" | Past results: "AI generated $50 million of savings in 2024" (that's *evidence*) |
| **About AI** | The outcome is tied to AI, machine learning, generative AI, AI products or AI investment | General guidance with no AI link: "we expect 8% revenue growth" |
| **Checkable** | Has at least one of: a **number** (amount, %, count), a **deadline**, or a **concrete deliverable** | "AI will transform how we work" |

**Hype** is forward-looking AI talk that fails the checkable test: "we are well positioned to lead in AI", "AI is a generational opportunity". We count hype separately. The ratio of hype to checkable promises is one of the project's findings.

**Not promises (label "No forward-looking AI statement"):**
- risk factors ("AI investments may not deliver the expected benefits"): these describe risks, not commitments
- descriptions of current products or past results
- the standard forward-looking-statements legal disclaimer

### Specificity score (the model assigns it; you check it)

| Score | Meaning | Fictional example |
|---|---|---|
| 3 | Metric + target + deadline | "We expect AI to deliver $150 million in annual run-rate savings by the end of 2025." |
| 2 | Two of the three | "We expect AI tools to cut support costs by 20 percent." (no deadline) |
| 1 | A concrete deliverable only | "We will launch AI agents for all enterprise customers." |

**DECIDE:** should specificity-1 promises get a status, or only be counted? *Proposal:* they get a status only when the deliverable is unambiguous (a named product or program); otherwise they're counted as promises but published as "Status pending review".

## 3. Claim types

| Code | Use when the promise is about… | Fictional example |
|---|---|---|
| `cost_savings` | lower costs or expenses (absolute or run-rate) | "$150 million in annual run-rate cost savings by 2025" |
| `margin` | gross, operating or segment margin | "AI efficiencies will expand operating margin by 1 point in 2025" |
| `revenue` | revenue, bookings or sales from AI products | "AI software revenue will double in 2025" |
| `workforce` | headcount, hiring, attrition, roles automated | "reduce support headcount by about 10 percent through attrition" |
| `capex_investment` | spending on AI: capex, data centers, R&D amounts | "capital expenditures of about $5 billion in fiscal 2025, mostly AI infrastructure" |
| `productivity` | output per employee, time saved, % of work automated | "AI will handle half of customer inquiries by 2026" |
| `product_or_timeline` | launching or delivering a specific AI product by a date | "general availability of our AI assistant in the first half of 2025" |
| `other` | anything checkable that doesn't fit above | |

If two types fit, pick the one the **target number** measures.

## 4. Statuses

Each promise gets exactly one status, decided from filings **after** the promise was made.

| Status | Rule | Needs |
|---|---|---|
| **Delivered** | A later filing reports an outcome that meets the target (within the tolerance in section 5) by the deadline. | The evidence quote or reported number, and the arithmetic |
| **On track** | The deadline hasn't passed, and a later filing reports **measurable progress** toward the target. | A progress number ("$60 million of the $150 million achieved") |
| **No evidence yet** | Nothing later confirms or refutes it. | A note on what was searched |
| **Walked back** | The company **explicitly** lowered, delayed or dropped the commitment. | The quote where it lowered, delayed or dropped it |
| **Walked back (silent)** | Flag, shown separately: the deadline passed and later filings stopped mentioning it. | See the safeguards below |
| **Status pending review** | Confidence is below the threshold, or the two checks disagree. Published with the verified quote only. | Nothing: this is the safe default |

**Safeguards for negative statuses** (from the brief; fixed): "Walked back" and "Walked back (silent)" are published only when **two independent checks agree**. Otherwise the item is held as pending.

**DECIDE: silent walk-backs.** *Proposal:* flag "Walked back (silent)" only if (a) the deadline has passed, (b) at least **two** later periodic filings (10-K or 10-Q) are silent about the program, and (c) no earnings release mentions it either. Otherwise it's "No evidence yet". Silence is weak evidence, so this proposal is deliberately strict.

**DECIDE: reaffirmation without numbers.** A later filing says "we remain on track" but gives no progress figure. *Proposal:* "No evidence yet", with the reaffirmation quoted in the explanation. ("On track" needs a measurable number.)

**DECIDE: raised targets.** A company raises a target before the deadline ("now expect $200 million, up from $150 million"). *Proposal:* the original promise is "On track" if progress is reported. The raised target becomes a new promise linked to the original, and the raise is noted.

## 5. Tolerances (all DECIDE; proposals shown)

| Situation | Proposal |
|---|---|
| Numeric target met? | Delivered if the reported outcome is **≥ 95% of the target**. Within 95% is fine because companies round. |
| "About" or "approximately" targets | Delivered if within **±10%** of the target. |
| Range targets ("$100–150 million") | Delivered if the reported outcome reaches the **low end** of the range. |
| Run-rate vs realized | A **run-rate** target is met by a reported run-rate. A **realized** target needs realized savings in the period. Never mix them. |
| Deadline "by 2025" or "by end of 2025" | The company's **fiscal** year 2025, unless it says "calendar". |
| Grace period | Results for the deadline period count even if filed after it (e.g. a FY2025 10-K filed in February 2026). |
| GAAP vs non-GAAP, constant currency | Judge on the **same basis the promise used**. If the company switches basis, mark "Status pending review". |
| Acquisitions or divestitures make the metric incomparable | "No evidence yet", with a note. Never adjust numbers ourselves. |
| Partial delivery (e.g. 70% of target at the deadline) | **DECIDE.** Proposal: not "Delivered". If the company explicitly lowered the target, "Walked back"; if it's silent, "No evidence yet", and the explanation reports the 70% factually. |

## 6. Neutral wording

| Use | Don't use |
|---|---|
| "Later filings report…", "The 2025 10-K states…" | "failed", "missed", "broke a promise" |
| "The company lowered its target from X to Y" | "misled", "backtracked", "overpromised" |
| "No later filing reports progress on this target" | "abandoned", "gave up" (unless quoting the company) |
| "Delivered: reported X against a target of Y" | "succeeded", "beat", "crushed" |

Code checks every generated sentence against a banned-word list built from the right-hand column.

## 7. Questions for you

1. Are the 95% and ±10% tolerances right for how companies report these numbers?
2. Is the silent walk-back rule strict enough, or too strict?
3. Should capex guidance ("$80 billion of capital spending, primarily for AI") count as an AI promise? *Proposal:* yes, as `capex_investment`, because the outcome (actual capex) is reported.
4. For banks, which expense line should cost-savings promises be checked against? (Banks report "noninterest expense", not SG&A.)
5. Anything you've seen in filings that this rubric doesn't cover?
