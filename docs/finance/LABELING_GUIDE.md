# Labeling guide

**For:** the finance student. **Time:** about 6–8 hours in total for about 450 rows, in as many sittings as you like. Most rows take under a minute.

**Why this matters:** your labels are the answer key. Every accuracy number we publish ("the system finds X% of promises") is measured against them, so the system is only as trustworthy as these labels. When in doubt, mark **Unsure** and say why. That's far better than guessing.

---

## 1. Get your files

1. Open the shared Google Drive folder. In **packets/** there's one file per company, e.g. `IBM_packet_v1.xlsx`.
2. Start with any company. Each file is independent.

**Excel:** download the file and open it.
**Google Sheets:** double-click the file in Drive, then **Open with → Google Sheets**. The dropdowns and red highlighting carry over.

Wait for the CS student to say the packets are final (after your pilot picks) before you start.

## 2. What you'll see

Two tabs. **Instructions** is a one-page summary of this guide. **Passages** is where you work. One row is one passage of about 150–400 words from a filing.

| Column | What it is | Do you edit it? |
|---|---|---|
| Row ID | e.g. MSFT-017. Ties your label to the passage. | **Never** |
| Company, Form, Filed, Section | Where the passage comes from | No |
| SEC link | Opens the full filing, if you need context | No |
| Passage (AI words in red) | The text to read. AI words are **red and bold** so you can jump to them. | **Never** |
| **Your label** (yellow) | Pick one from the dropdown | **Yes, every row** |
| Promise 1: quote, claim type, metric, target, deadline | Only for checkable promises | Yes, when needed |
| Promise 2: … | A second promise in the same passage | Yes, when needed |
| Notes | Anything worth saying, especially for Unsure | Optional |

A few rows have **no red words**. That's on purpose: they're a random sample used to check whether our keyword search misses AI promises. Read them like any other row.

## 3. Choosing a label

Ask three questions, in order:

1. **Does the passage say something about the future that involves AI?** If not, choose **No forward-looking AI statement**.
2. **Could a later filing prove it true or false?** It needs a number, a date, or a concrete deliverable. If yes, choose **Checkable promise**.
3. **Otherwise** (future AI talk with nothing checkable), choose **Vague AI talk (hype)**.

If you can't decide, choose **Unsure** and write a few words in Notes. Unsure rows are reviewed together later and never count against anyone.

The full definitions are in `docs/finance/RUBRIC.md`, sections 2 and 3.

## 4. Filling in a promise

When you pick **Checkable promise**:

1. **Quote:** copy the promise's exact words from the Passage cell and paste them into **Promise 1: quote**.
   - In Excel: double-click the passage cell, select the words with the mouse, Ctrl+C, Esc, click the quote cell, Ctrl+V.
   - Part of a sentence is fine. Keep it short: just the promise.
   - **One continuous piece.** No "…" to skip words, and no retyping or paraphrasing. The import checks that your quote appears in the passage word for word.
2. **Claim type:** pick from the dropdown (rubric section 3). If two fit, choose the one the target number measures.
3. **Metric:** what's measured, in a few words: "annual run-rate cost savings", "operating margin".
4. **Target:** the number as written: "$150 million", "1 point", "20 percent". Leave it blank if there's none.
5. **Deadline:** as written: "end of 2025", "fiscal 2026", "first half of 2025". Leave it blank if there's none.

**Two promises in one passage:** use the Promise 2 columns.
**Three or more:** add a row next to it (Excel: right-click the row number → **Insert**; Google Sheets: right-click → **Insert 1 row below**). Copy the **Row ID** into the new row, fill in the extra promise in its Promise 1 columns, and leave its label blank. Where the new row sits doesn't matter; the Row ID links it.

## 5. Worked examples (fictional company, so they don't bias your real labels)

**Example A: a checkable promise**
> "In 2024 we launched a company-wide productivity program built on generative AI tools. We expect the program to deliver $150 million in annual run-rate cost savings by the end of 2025, and we plan to reduce support headcount by about 10 percent through attrition over the same period."

| Field | Promise 1 | Promise 2 |
|---|---|---|
| Label | Checkable promise | |
| Quote | We expect the program to deliver $150 million in annual run-rate cost savings by the end of 2025 | we plan to reduce support headcount by about 10 percent through attrition over the same period |
| Claim type | cost_savings | workforce |
| Metric | annual run-rate cost savings | support headcount |
| Target | $150 million | about 10 percent |
| Deadline | end of 2025 | end of 2025 |

**Example B: hype**
> "We believe AI is a generational opportunity and we are well positioned to lead."

Label: **Vague AI talk (hype)**. It's about the future and about AI, but nothing could prove it true or false.

**Example C: a risk factor, not a promise**
> "We may not realize the expected benefits of our generative AI investments, which could reduce our margins."

Label: **No forward-looking AI statement**. It describes a risk, not a commitment.

**Example D: past results (evidence, not a promise)**
> "Our AI productivity program delivered $60 million of run-rate savings in 2024."

Label: **No forward-looking AI statement**. This is what *later* filings say. It's exactly what we'll use as evidence in Phase 3, but it isn't a promise.

**Example E: capex**
> "We expect capital expenditures of about $5 billion in fiscal 2025, primarily for AI infrastructure."

Label: **Checkable promise**, claim type `capex_investment` (rubric question 3 asks you to confirm this treatment).

**Example F: progress update with a number**
> "We remain on track and now expect $200 million of run-rate savings by the end of 2025, up from $150 million."

Label: **Checkable promise** (the new $200 million target), with a note: "raised from $150 million".

## 6. Saving and returning

1. **Excel:** File → Save (keep the `.xlsx` format and the file name).
   **Google Sheets:** File → Download → **Microsoft Excel (.xlsx)**.
2. Put the file in the Drive folder **returned/**. Keep the name, e.g. `IBM_packet_v1.xlsx`.
3. Tell the CS student. They run a check that prints a plain-English list of anything to fix ("Row 12 (MSFT-011): Promise 1's quote is not in the passage text…"). Fix those rows and return the file again. Everything else is already saved.

You can return partly finished files. Blank rows simply count as "not labeled yet".

## 7. Please don't

- edit the Row ID or Passage columns
- rename the tabs or column headers
- sort or filter only some columns (sorting the whole sheet is fine; the Row ID travels with each row)
- paraphrase quotes or use "…"

## 8. FAQ

**The passage is cut off mid-thought.** Click **SEC link** to read the surrounding text in the filing. Label only what's in this passage.

**The same promise appears in several filings.** Label it every time it appears. Repeated statements are useful: they show when a promise is restated, raised or lowered.

**It's a promise, but not really about AI** (e.g. general cost cuts). Use **No forward-looking AI statement**, unless the passage ties the outcome to AI.

**How long should this take?** About a minute a row on average. If you're spending much longer, choose Unsure, write a note and move on.
