"""The labeling vocabulary shared by `aipb packets` and `aipb import-labels`.

Changing any value here changes what the finance student sees in the dropdowns, so it must
match docs/finance/RUBRIC.md and docs/finance/LABELING_GUIDE.md.
"""

from __future__ import annotations

PACKET_VERSION = "v1"
SAMPLE_SEED = 20261110
PROMISE_WINDOW = ("2024-01-01", "2025-12-31")

LABEL_PROMISE = "Checkable promise"
LABEL_HYPE = "Vague AI talk (hype)"
LABEL_NONE = "No forward-looking AI statement"
LABEL_UNSURE = "Unsure"
LABELS = (LABEL_PROMISE, LABEL_HYPE, LABEL_NONE, LABEL_UNSURE)

CLAIM_TYPES = (
    "cost_savings",
    "margin",
    "revenue",
    "workforce",
    "capex_investment",
    "productivity",
    "product_or_timeline",
    "other",
)

PROMISE_FIELDS = ("quote", "claim_type", "metric", "target", "deadline")
N_PROMISE_SLOTS = 2

# Column order in the "Passages" sheet. The importer finds columns by header text, so a
# labeler who moves or hides a column does not break the import.
COLUMNS = (
    ("row_id", "Row ID", 10),
    ("ticker", "Company", 9),
    ("form", "Form", 7),
    ("filing_date", "Filed", 11),
    ("section", "Section", 22),
    ("link", "SEC link", 10),
    ("text", "Passage (AI words in red)", 100),
    ("label", "Your label", 24),
    *(
        (f"p{n}_{field}", f"Promise {n}: {field.replace('_', ' ')}", 40 if field == "quote" else 16)
        for n in range(1, N_PROMISE_SLOTS + 1)
        for field in PROMISE_FIELDS
    ),
    ("notes", "Notes", 30),
)
HEADER = {key: title for key, title, _ in COLUMNS}

SECTION_NAMES = {
    "cover": "Cover / front matter",
    "item1": "Business (Item 1)",
    "item1a": "Risk factors (Item 1A)",
    "item1c": "Cybersecurity (Item 1C)",
    "item2": "Properties (Item 2)",
    "item3": "Legal proceedings (Item 3)",
    "item5": "Market for equity (Item 5)",
    "item7": "MD&A (Item 7)",
    "item7a": "Market risk (Item 7A)",
    "item8": "Financial statements (Item 8)",
    "item9a": "Controls (Item 9A)",
    "p1item1": "Financial statements (10-Q Item 1)",
    "p1item2": "MD&A (10-Q Item 2)",
    "p1item3": "Market risk (10-Q Item 3)",
    "p1item4": "Controls (10-Q Item 4)",
    "p2item1": "Legal proceedings (10-Q Part II)",
    "p2item1a": "Risk factors (10-Q Part II)",
    "ex13": "Annual report (Exhibit 13)",
    "ex99": "Earnings release (Exhibit 99.1)",
}


def section_name(section: str) -> str:
    if section in SECTION_NAMES:
        return SECTION_NAMES[section]
    if section.startswith("p2item"):
        return f"10-Q Part II, Item {section[6:].upper()}"
    if section.startswith("p1item"):
        return f"10-Q Part I, Item {section[6:].upper()}"
    if section.startswith("item"):
        return f"Item {section[4:].upper()}"
    return section
