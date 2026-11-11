# Evidence map (DRAFT for the finance student to correct)

**What this is:** for each claim type, where in later filings the evidence usually is, and which reported numbers (XBRL tags) can confirm or refute a promise. Verification (Phase 3) uses this map: code pulls the listed numbers and does the arithmetic, and the model only judges.

**Your job:** correct anything wrong, fill in the **DECIDE** cells, and add what an analyst would check that isn't here. About 1–2 hours. Edit the Google Doc copy in the shared Drive, as with the rubric.

**About the "Reported by" column:** these are real checks of your 10 pilot companies' XBRL data for filings since 2024, redone on 2026-11-11 after your picks. Companies use different tags for the same idea, so each row lists tags in the order code should try them. Tags marked **(new)** were added because some of your companies use them instead of the usual tag. Please confirm they measure the right thing.

---

## cost_savings

- **Where to look:** MD&A (10-K Item 7, 10-Q Item 2); earnings releases ("productivity savings", "run-rate savings"); restructuring notes in the financial statements.
- **Numbers (XBRL), tried in this order:**

  | Measure | Tags | Reported by (your pilot) |
  |---|---|---|
  | Operating expenses | `OperatingExpenses` | BLK, MSFT, NVDA, TSLA |
  | SG&A | `SellingGeneralAndAdministrativeExpense` | CAT, NVDA, PEP, PFE, TSLA |
  | Bank operating costs | `NoninterestExpense` | none in this pilot (banks such as JPM use it) |
  | Total costs and expenses **(new)** | `CostsAndExpenses` | AMZN, FDX, META. It's used only when none of the tags above is reported. It **includes cost of sales**, so it's broader than operating expenses. |
  | Restructuring and severance | `RestructuringCharges`, `SeveranceCosts1` | restructuring: BLK, CAT, FDX, PEP, PFE, TSLA; severance: AMZN, BLK, META, PFE, TSLA; **neither for MSFT or NVDA** |

- **Caveat:** most savings targets are company-defined ("run-rate productivity savings"). XBRL rarely reports them directly, so the evidence is usually the company's own later statement of the achieved amount. A drop in total expenses alone does **not** prove AI savings. **DECIDE:** is a company's own statement of achieved savings enough for "Delivered"? *Proposal:* yes, quoted verbatim, because we report what the filings say.

## margin

- **Where to look:** MD&A results tables; earnings release highlights.
- **Numbers:** code computes margin = numerator ÷ revenue for the same period.

  | Measure | Numerator tags | Revenue tags |
  |---|---|---|
  | Gross margin | `GrossProfit` (MSFT, NVDA, PEP, TSLA). Proposed fallback: revenue minus `CostOfRevenue` (CAT, META, NVDA, TSLA) or `CostOfGoodsAndServicesSold` (AMZN, CAT, MSFT, PEP, PFE). **The code doesn't compute that fallback yet**, so today gross margin is missing for AMZN, BLK, CAT, FDX, META and PFE, and their gross-margin promises can only be checked from text. | `Revenues` (BLK, CAT, NVDA, PEP, PFE, TSLA), `RevenueFromContractWithCustomerExcludingAssessedTax` (AMZN, BLK, FDX, META, MSFT, PFE, TSLA) |
  | Operating margin | `OperatingIncomeLoss` (AMZN, BLK, CAT, FDX, META, MSFT, NVDA, PEP, TSLA); **not reported by PFE** | same |

- **Caveat:** companies often promise **non-GAAP** margins, which XBRL doesn't contain. Then the evidence is the earnings release's own non-GAAP figure. **DECIDE:** which margin definition should win when a company reports both?

## revenue

- **Where to look:** earnings releases (AI "book of business" or AI revenue run-rate metrics); MD&A segment discussion.
- **Numbers:** `Revenues` or `RevenueFromContractWithCustomerExcludingAssessedTax` for totals; segment revenue from the segment note.
- **Caveat:** AI-specific revenue is almost never a separate XBRL figure. Expect the evidence to be the company's own later statement of the metric it promised, on the same definition.

## workforce

- **Where to look:** 10-K Item 1 "Human Capital" (total employees, usually once a year); restructuring notes (positions eliminated); MD&A.
- **Numbers:** **headcount is not in XBRL** for any of your pilot companies. Evidence is text: "As of December 31, 2025, we had approximately N employees."
- **Caveat:** headcount changes have many causes. **DECIDE:** should a workforce promise ("reduce support roles by 10%") count as Delivered from total-headcount changes? *Proposal:* no. Only when the filing reports the specific group or program the promise named.

## capex_investment

- **Where to look:** cash-flow statement; MD&A liquidity section; earnings-release outlook.
- **Numbers:**
  - Capex: `PaymentsToAcquirePropertyPlantAndEquipment` (BLK, CAT, META, MSFT, PFE, TSLA), otherwise **(new)** `PaymentsToAcquireProductiveAssets` (AMZN, FDX, NVDA, PEP). The second tag can also include other long-lived assets, such as software or intangibles; it's the capex figure these four companies report.
  - R&D promises: `ResearchAndDevelopmentExpense` (CAT, META, MSFT, NVDA, PEP, TSLA), otherwise **(new)** `ResearchAndDevelopmentExpenseExcludingAcquiredInProcessCost` (PFE). **No R&D line for AMZN, BLK or FDX.**
- **Caveat:** total capex includes non-AI spending. If the promise is "capex of about $X, mostly for AI", code checks total capex against $X; the "mostly AI" part needs a text statement.

## productivity

- **Where to look:** MD&A and earnings releases (e.g. "AI now handles N% of inquiries").
- **Numbers:** usually text only. Revenue per employee = revenue ÷ the headcount from the text (code computes it; flagged as derived).
- **DECIDE:** should derived ratios ever be enough for "Delivered", or only the company's own statement?

## product_or_timeline

- **Where to look:** earnings releases and MD&A announcing launches or general availability.
- **Numbers:** none. Evidence is a later statement that the product launched (or was delayed), with its date.

## other

Decide case by case. Write a note in the labeling sheet and we'll add a row here.

---

### Rules for all claim types (fixed)

- Evidence must come from a filing **dated after** the promise.
- Use the **same period definition** as the promise (fiscal vs calendar year; quarter vs year to date). Code matches XBRL periods by their start and end dates.
- If a later filing **restates** an earlier number, the restated number wins, with a note.
