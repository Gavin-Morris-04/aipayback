# Pick the 10 pilot companies

> **Done on 2026-11-11.** Your picks are the final pilot: AMZN, BLK, CAT, FDX, META, MSFT, NVDA, PEP, PFE and TSLA. Your labeling packets have been rebuilt for these 10 companies (450 rows in total). Start labeling when Gavin tells you the packets are in the Drive **packets** folder. This page is kept as a record of how the list was chosen.

**Who:** the finance student. **Time:** about 1 hour. **Blocks:** the final Phase 1 ingest and your labeling packets. Please do this first.

## What we need from you

Ten companies from the **S&P 100**:
- **At least 5 sectors.**
- **At least 4 that talk about AI a lot** in their filings (cost savings, productivity, new AI revenue, headcount).
- At least 2 that **don't** talk about AI much, so we can compare how much AI talk is checkable in different industries.

Your judgment matters more than any rule here. Pick companies whose AI claims you would want to check as an analyst.

## What we already know (real numbers from our data)

We ran the tools on a **placeholder** list so the software could be built and tested. The table counts passages (chunks of about 150–400 words) in each company's 2024–2025 filings that mention AI at least once, after removing repeated boilerplate. These are counts of *mentions*, not promises.

| Ticker | Sector | AI-mentioning passages, 2024–2025 filings |
|---|---|---|
| MSFT | Information Technology | 187 |
| CRM | Information Technology | 178 |
| IBM | Information Technology | 170 |
| ACN | Information Technology | 97 |
| VZ | Communication Services | 16 |
| WMT | Consumer Staples | 12 |
| JPM | Financials | 12 |
| UNH | Health Care | 10 |
| CAT | Industrials | 6 |
| XOM | Energy | 0 |

**Things to notice:**
- Four of the placeholder picks are technology companies. That's probably too many. Your list should spread the AI-heavy picks across sectors (for example a bank, a retailer or a health company with big AI claims).
- Filings are 10-Ks, 10-Qs and earnings press releases (8-K Exhibit 99.1) **only**. Earnings-call transcripts and news are out of scope. So a company that talks about AI only on calls will show few mentions here.
- You can keep any placeholder company. Its data is already downloaded.

## How to send your picks

1. Open the shared Google Drive folder.
2. Create a Google Sheet called **pilot_picks** with these columns:

   | ticker | company | sector | AI-heavy? (yes/no) | why you picked it |
   |---|---|---|---|---|

3. Fill in 10 rows and tell the CS student it's ready.

The CS student copies it into `config/universe/pilot.csv` and runs the download. It takes a few minutes and costs nothing. Your labeling packets are then rebuilt for your companies.

> **Please don't start labeling the current packets yet.** They're built from the placeholder list and will be replaced once your picks are in. Even for a company you keep, some rows may change, because the roughly 450 rows are re-divided across your 10 companies.
