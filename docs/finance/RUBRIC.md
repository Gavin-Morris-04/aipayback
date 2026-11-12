# AIPayback rubric (final, November 11, 2026)

**Status:** decisions recorded November 11, 2026. Every DECIDE item is now marked DECIDED and section 7 is answered; ready to copy back into the repo after a final read-through. **You own this document.** Every rule marked DECIDE is a proposal; change it, approve it, or replace it. The software and the labels follow whatever this file says once you approve it.

> Copied into the repo from the finance lead's Google Doc on 2026-11-11 (G8) and confirmed final the same day. The software follows it from verify prompt v2 on (`docs/DECISIONS.md` D41). Later changes come back the same way: edit the Doc, then the CS student brings them into the repo.

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

**DECIDED:** specificity-1 promises get a status only when the deliverable is unambiguous: a named product, feature or program with a defined scope (e.g. a named AI assistant reaching general availability). If the deliverable is vague ("AI agents for customers", "more AI features"), the promise is counted but published as "Status pending review". Because specificity-1 promises have no deadline, they can be "Delivered" or "Walked back" (explicitly dropped) but never "Walked back (silent)".

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

**DECIDED: silent walk-backs.** Keep the strict rule. Flag "Walked back (silent)" only if all of these hold: (a) the deadline has passed; (b) at least two later periodic filings (10-K or 10-Q) are silent about the program, and one of them is the filing that covers the deadline period; (c) no earnings release in the same window mentions it; and (d) the program was named in at least one filing before it went silent (so we know what we are searching for). Otherwise it is "No evidence yet". The two-independent-checks safeguard still applies on top of this.

**DECIDED: reaffirmation without numbers.** Approved as proposed: a later filing that says "we remain on track" (or similar) with no progress figure gets "No evidence yet", and the explanation quotes the reaffirmation and names the filing. "On track" always needs a measurable number. If the deadline passes and the only evidence is reaffirmations, it stays "No evidence yet"; a reaffirmation never counts as "Delivered".

**DECIDED: raised targets.** Approved with one clarification: the original promise keeps its original target and is judged against it ("On track" while progress is reported, "Delivered" if the original target is met by its deadline). The raised target becomes a new promise, linked to the original, dated from the filing that announced the raise, and the raise is noted on both. If a raised target is later cut back, only the new promise can be "Walked back"; the original is still judged against its own target.

## 5. Tolerances (decided)

| Situation | Proposal |
|---|---|
| Numeric target met? | Delivered if the reported outcome is at least 95% of the target (companies round). Exception: if the promise says "at least", "more than" or "exceed", the outcome must reach 100% of the target. Overshooting a target always counts as met. |
| "About" or "approximately" targets | Delivered if the outcome is at least 90% of the target. The tolerance is one-sided: overshooting is still met, and the explanation reports the actual figure. For spending and capex targets, an outcome more than 10% above the target is still Delivered, but the explanation states the difference factually. |
| Range targets ("$100–150 million") | Delivered if the reported outcome reaches the low end of the range. No extra 95% tolerance on top: the low end is already the company's own floor. **Added 2026-11-12 (D44):** this includes "approximately $X to $Y"; the word "approximately" does not add the 90% tolerance to a range. |
| Run-rate vs realized | A run-rate target is met by a reported run-rate. A realized target needs realized savings in the period. Never mix them. If the promise doesn't say which it is and the context doesn't make it clear, mark "Status pending review". |
| Deadline "by 2025" or "by end of 2025" | The company's fiscal year 2025 as the company itself labels it, unless it says "calendar". Half-year and quarter deadlines ("first half of 2025", "Q3") also use the company's fiscal periods. |
| Grace period | Results for the deadline period count even if filed after it (e.g. a FY2025 10-K filed in February 2026). A later filing also counts if it explicitly states the outcome as of the deadline period. Progress achieved after the deadline period does not make a promise "Delivered"; it is reported factually in the explanation. |
| GAAP vs non-GAAP, constant currency | Judge on the same basis the promise used (GAAP or non-GAAP, reported or constant currency, and the currency the target was stated in). If the company switches basis, mark "Status pending review". |
| Acquisitions or divestitures make the metric incomparable | "No evidence yet", with a note. Never adjust numbers ourselves. Exception: if the company itself reports a like-for-like or organic figure for the same metric, use that figure (it is reported, not adjusted by us) and say so in the explanation. |
| Partial delivery (e.g. 70% of target at the deadline) | Anything below the Delivered threshold above is not "Delivered". If the company explicitly lowered the target, "Walked back"; if it's silent, "No evidence yet". Either way the explanation reports the achieved share factually ("Later filings report X against a target of Y, 70% of the target"). |

## 6. Neutral wording

| Use | Don't use |
|---|---|
| "Later filings report…", "The 2025 10-K states…" | "failed", "missed", "broke a promise" |
| "The company lowered its target from X to Y" | "misled", "backtracked", "overpromised" |
| "No later filing reports progress on this target" | "abandoned", "gave up" (unless quoting the company) |
| "Delivered: reported X against a target of Y" | "succeeded", "beat", "crushed" |

Code checks every generated sentence against a banned-word list built from the right-hand column.

## 7. Questions for you

1. Are the 95% and ±10% tolerances right for how companies report these numbers? **ANSWER:** Yes, with two changes now in section 5: "about" targets use a one-sided 90% floor (overshooting is met), and "at least" or "more than" targets need 100%. Companies usually report savings and revenue rounded to the nearest 5 or 10 million, so 95% absorbs rounding without rewarding real shortfalls.
2. Is the silent walk-back rule strict enough, or too strict? **ANSWER:** Strict enough; keep it. Silence is weak evidence and a wrong negative is the worst failure, so I added two conditions (section 4): one of the silent filings must cover the deadline period, and the program must have been named in an earlier filing.
3. Should capex guidance ("80 billion of capital spending, primarily for AI") count as an AI promise? **ANSWER:** Yes, as `capex_investment`, but only when the guidance itself ties the spending to AI ("primarily for AI", "AI infrastructure", "data centers for AI"). General capex guidance with no AI link does not count. Check it against reported capital expenditures (purchases of property and equipment in the cash flow statement) on the same definition the guidance used, e.g. including finance leases only if the guidance did. **Added 2026-11-12 (D44, approved by Gavin):** if the guidance doesn't say which definition it uses, use the company's usual definition as its own filings state it (e.g. Meta's "capital expenditures, including principal payments on finance leases"). Report capex promises separately from payoff promises (savings, revenue, margin) in the findings, since spending money is an input, not a return.
4. For banks, which expense line should cost-savings promises be checked against? (Banks report "noninterest expense", not SG&A.) **ANSWER:** Total noninterest expense by default. If the promise names a narrower line (technology and communications, compensation and benefits, operations), use that line. If the bank guides on an adjusted noninterest expense (e.g. excluding an FDIC special assessment or litigation charges) and the promise used that basis, use the same adjusted figure as the bank reports it. A promise stated as an efficiency ratio is a margin claim and is checked against the efficiency ratio the bank reports. Insurers: use the operating expense or expense ratio the company reports.
5. Anything you've seen in filings that this rubric doesn't cover? **ANSWER:** Five additions. (a) Repeated promises: the same target restated in later filings is one promise, sourced to the earliest filing; a restatement with a changed number or date is a raise or a walk-back. (b) Promises made only on earnings calls or at investor days are out of scope unless repeated in a 10-K, 10-Q or earnings release. (c) Attribution: if the company later reports results for the same named program but no longer credits AI, the program's figure still counts, and the explanation notes the change in wording. (d) Percentage targets with an undefined base ("cut costs 20%" without saying which costs or from which year) get "Status pending review". (e) Restated prior-period figures: use the latest reported figure for the deadline period and note the restatement.
