# Evidence map (final, November 11, 2026)

**What this is:** for each claim type, where in later filings the evidence usually is, and which reported numbers (XBRL tags) can confirm or refute a promise. Verification (Phase 3) uses this map: code pulls the listed numbers and does the arithmetic, and the model only judges.

**Your job:** correct anything wrong, fill in the **DECIDE** cells, and add what an analyst would check that isn't here. About 1–2 hours. Edit the Google Doc copy in the shared Drive, as with the rubric.

> **How this file was put together (2026-11-11, G8):** the finance lead finalized his Google Doc from the earlier draft, whose "Reported by" columns covered the placeholder companies. Meanwhile the columns were rechecked against his 10 final pilot companies. This file has **his text word for word** and the **rechecked columns**. Notes in [square brackets] are additions from the merge, not his words. The software follows it as evidence map `em3` (`config/evidence_map.yaml`, `docs/DECISIONS.md` D41). The two questions raised by the merge were answered on 2026-11-11 (end of this file).

**About the "Reported by" column:** these are real checks of the 10 final pilot companies' XBRL data for filings since 2024 (AMZN, BLK, CAT, FDX, META, MSFT, NVDA, PEP, PFE, TSLA). Companies use different tags for the same idea, so each row lists tags in the order code should try them.

---

## cost_savings

- **Where to look:** MD&A (10-K Item 7, 10-Q Item 2); earnings releases ("productivity savings", "run-rate savings"); restructuring notes in the financial statements.
- **Numbers (XBRL), tried in this order:**

  | Measure | Tags | Reported by (pilot) |
  |---|---|---|
  | Operating expenses | `OperatingExpenses` | BLK, MSFT, NVDA, TSLA |
  | SG&A | `SellingGeneralAndAdministrativeExpense` | CAT, NVDA, PEP, PFE, TSLA |
  | Bank operating costs | `NoninterestExpense` | none in this pilot (banks such as JPM use it) |
  | Total costs and expenses | `CostsAndExpenses` | AMZN, CAT, FDX, META. [In code, the last fallback: used only for AMZN, FDX and META, which report none of the tags above. Labeled "total costs and expenses (includes cost of sales)" and shown as context only (question 1 below).] |
  | Restructuring and severance | `RestructuringCharges`, `SeveranceCosts1` | restructuring: BLK, CAT, FDX, PEP, PFE, TSLA; severance: AMZN, BLK, META, PFE, TSLA; neither for MSFT or NVDA |

- **Caveat:** most savings targets are company-defined ("run-rate productivity savings"). XBRL rarely reports them directly, so the evidence is usually the company's own later statement of the achieved amount. A drop in total expenses alone does not prove AI savings. **DECIDED:** yes, a company's own statement of savings achieved is enough for "Delivered", quoted verbatim with its filing, but only if it measures the same thing the promise did: the same program, the same kind of savings (run-rate or realized) and a period that ends by the deadline. The explanation says the figure is company-reported. A drop in total expenses alone is never enough for "Delivered", and a rise in total expenses alone never refutes a savings promise. **Also check:** restructuring charges are the cost of getting savings, not savings, so never count them as evidence of savings; the restructuring note's table of charges and remaining liability shows whether a program is still running. Total costs and expenses (`CostsAndExpenses`) and cost of revenue (`CostOfRevenue`) are fallbacks when a promise names those lines (tags not yet checked against the pilot companies). [Checked 2026-11-11: `CostsAndExpenses` is reported by AMZN, CAT, FDX and META; `CostOfRevenue` by CAT, META, NVDA and TSLA.]

## margin

- **Where to look:** MD&A results tables; earnings release highlights.
- **Numbers:** code computes margin = numerator ÷ revenue for the same period.

  | Measure | Numerator tags | Revenue tags |
  |---|---|---|
  | Gross margin | `GrossProfit` (MSFT, NVDA, PEP, TSLA); otherwise revenue minus `CostOfRevenue` (CAT, META, NVDA, TSLA) or `CostOfGoodsAndServicesSold` (AMZN, CAT, MSFT, PEP, PFE). [Code now computes this fallback, labeled as computed. BLK and FDX report neither cost tag, so they have no gross margin.] | `Revenues` (BLK, CAT, NVDA, PEP, PFE, TSLA), `RevenueFromContractWithCustomerExcludingAssessedTax` (AMZN, BLK, FDX, META, MSFT, PFE, TSLA) |
  | Operating margin | `OperatingIncomeLoss` (AMZN, BLK, CAT, FDX, META, MSFT, NVDA, PEP, TSLA); not reported by PFE | same |

- **Caveat:** companies often promise non-GAAP margins, which XBRL doesn't contain. Then the evidence is the earnings release's own non-GAAP figure. **DECIDED:** the definition the promise used wins. If the promise names GAAP or non-GAAP ("adjusted", "non-GAAP", "excluding"), use that one. If it doesn't, use the basis of the document it appeared in: a promise in an earnings-release outlook stated on a non-GAAP basis is judged non-GAAP; one in a 10-K or 10-Q is judged GAAP. Report the other figure in the explanation if the company gives it, and never pick whichever looks better. If the company changes its non-GAAP definition along the way, mark "Status pending review". **Also check:** margin promises are usually in points ("expand by 1 point"), so code computes the change in percentage points against the baseline period the promise names, not a percent change. [Code computes it against the prior year. A promise with an older baseline year needs the second check, which can calculate; prompt v3 will say so explicitly.] Segment margin promises use segment operating profit and segment revenue from the segment note. Where operating income isn't reported (IBM, JPM, XOM), use pre-tax margin only if that is what the promise named. [In this pilot: PFE.] A bank efficiency-ratio promise uses `NoninterestExpense` divided by total net revenue, or the ratio the bank itself reports.

## revenue

- **Where to look:** earnings releases (AI "book of business" or AI revenue run-rate metrics); MD&A segment discussion.
- **Numbers:** `Revenues` or `RevenueFromContractWithCustomerExcludingAssessedTax` for totals; segment revenue from the segment note.
- **Caveat:** AI-specific revenue is almost never a separate XBRL figure. Expect the evidence to be the company's own later statement of the metric it promised, on the same definition. **Also check:** bookings, backlog and run-rate metrics are not revenue. A bookings promise is judged on reported bookings, and remaining performance obligations (`RevenueRemainingPerformanceObligation`) are only context. A run-rate promise is met only by a reported run-rate, never by recognized revenue, and the reverse. The revenue-disaggregation note sometimes isolates the line an AI product sits in, but use it only if the company itself says that line is the AI product. "Double" or "grow N%" promises are computed by code against the baseline period the promise names.

## workforce

- **Where to look:** 10-K Item 1 "Human Capital" (total employees, usually once a year); restructuring notes (positions eliminated); MD&A.
- **Numbers:** headcount is not in XBRL for any placeholder company. [Or for any of the 10 pilot companies.] Evidence is text: "As of December 31, 2025, we had approximately N employees."
- **Caveat:** headcount changes have many causes. **DECIDED:** no. A change in total headcount cannot make a promise about one group of roles "Delivered", and cannot refute it either; the status stays "No evidence yet" unless a filing reports the group or program the promise named. Total headcount can appear in the explanation as context, and counts as evidence only for promises about total headcount. **Also check:** the restructuring note for positions eliminated under a named program, and the date of the headcount figure (Item 1 counts are usually as of fiscal year end and include staff from acquisitions). Contractors and outsourced roles are usually not in employee counts, so roles moved to vendors may not show up in headcount at all; say so rather than treating it as delivered.

## capex_investment

- **Where to look:** cash-flow statement; MD&A liquidity section; earnings-release outlook.
- **Numbers:**
  - Capex: `PaymentsToAcquirePropertyPlantAndEquipment` (BLK, CAT, META, MSFT, PFE, TSLA).
  - R&D promises: `ResearchAndDevelopmentExpense` (CAT, META, MSFT, NVDA, PEP, TSLA). [No R&D line for AMZN, BLK or FDX.]
  - [Shown next to capex so a guidance definition can be matched: `FinanceLeasePrincipalPayments` (AMZN, FDX, META, MSFT, TSLA), `PaymentsToDevelopSoftware` (none in the pilot), `ProceedsFromSaleOfPropertyPlantAndEquipment` (CAT, FDX, META).]
- **Caveat:** total capex includes non-AI spending. If the promise is "capex of about $X, mostly for AI", code checks total capex against $X; the "mostly AI" part needs a text statement. **Also check:** match the capex definition the guidance used. Some companies guide capex including finance leases (`FinanceLeasePrincipalPayments`, or the lease figure given in the release) or including capitalized software (`PaymentsToDevelopSoftware`), and some state it net of asset-sale proceeds; code must add or subtract the same pieces. Where `PaymentsToAcquirePropertyPlantAndEquipment` isn't reported (VZ), try `PaymentsToAcquireProductiveAssets` (not yet checked against the pilot companies). [Checked 2026-11-11: AMZN, FDX, NVDA and PEP report it instead. It can also include other long-lived assets such as software or intangibles.] For R&D promises, `ResearchAndDevelopmentExpenseExcludingAcquiredInProcessCost` is the fallback tag. [PFE reports it.] Future lease commitments for data centers in the leases note are not capex. [Added 2026-11-12 (D44): when the guidance doesn't state a definition, code uses the company's usual one if its filings state it. Recognized so far: "capital expenditures, including principal payments on finance leases" (Meta), shown as an extra row "capital expenditures as the company defines them" = `PaymentsToAcquirePropertyPlantAndEquipment` + `FinanceLeasePrincipalPayments`, summed by code.]

## productivity

- **Where to look:** MD&A and earnings releases (e.g. "AI now handles N% of inquiries").
- **Numbers:** usually text only. Revenue per employee = revenue ÷ the headcount from the text (code computes it; flagged as derived).
- **DECIDED:** a derived ratio is enough for "Delivered" only when the promise is itself stated in reported numbers ("revenue per employee will rise 10%") and code computes it from figures the company reported for matching periods; the explanation labels it as derived. When the promise uses a company-defined measure ("AI will handle half of customer inquiries", "30% of new code written with AI"), only the company's own later statement of that measure counts, and a derived ratio can appear only as context. **Also check:** headcount is a point-in-time figure while revenue covers a period, so use the same convention in the baseline and later years (year-end headcount both times), and note acquisitions or divestitures that change either number.

## product_or_timeline

- **Where to look:** earnings releases and MD&A announcing launches or general availability.
- **Numbers:** none. Evidence is a later statement that the product launched (or was delayed), with its date. **Also check:** "general availability" means available to all eligible customers; a preview, beta, pilot or limited release does not meet a general-availability promise unless the promise itself said preview or pilot. The launch date is the date the company says the product became available, not the filing date. A launch in only some regions, tiers or customer groups is reported factually and does not meet a promise of a broader launch. A later statement that the launch was delayed is "Walked back" evidence and is quoted.

## other

Decide case by case. Write a note in the labeling sheet and we'll add a row here. Likely cases: adoption metrics (number of customers or users of an AI product) and usage metrics (queries, transactions, tokens). These are text only and are judged on the company's own later statement of the same metric on the same definition; if the company changes the definition, "Status pending review".

---

### Rules for all claim types (fixed)

- Evidence must come from a filing **dated after** the promise.
- Use the **same period definition** as the promise (fiscal vs calendar year; quarter vs year to date). Code matches XBRL periods by their start and end dates.
- If a later filing **restates** an earlier number, the restated number wins, with a note.

---

### Questions from the merge (answered 2026-11-11)

1. **Total costs as a fallback.** Your map says `CostsAndExpenses` and `CostOfRevenue` are fallbacks *when a promise names those lines*. AMZN, FDX and META report no operating-expense or SG&A line, so code shows their total costs and expenses (labeled as such) for every cost-savings promise, as context only. Keep it as context for those three? **Answer: yes.** Total expenses still never decide a savings promise on their own. (Showing a line only when a promise names it, such as cost of revenue, isn't built yet.)
2. **Rubric title.** The rubric Doc still said "DRAFT" and mentioned a final read-through. Is it final? **Answer: yes.** The repo copy is titled final.
