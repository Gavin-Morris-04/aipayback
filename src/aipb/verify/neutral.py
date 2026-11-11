"""Neutral-language lint for every piece of generated text (verdicts, explanations, issues).

We report what filings say. Words that judge management are banned in generated text;
quotes from filings are exempt (they're the company's own words, shown as quotes).
"""

from __future__ import annotations

import re

BANNED = (
    "failed",
    "fails",
    "failure",
    "failing",
    "missed",
    "misses",
    "broke",
    "broken",
    "misled",
    "misleading",
    "mislead",
    "backtracked",
    "backtracking",
    "overpromised",
    "overpromise",
    "abandoned",
    "gave up",
    "lied",
    "lies",
    "false promise",
    "reneged",
    "underdelivered",
    "disappointing",
    "disappointed",
    "succeeded",
    "crushed",
    "beat",
    "debacle",
    "flop",
    "empty promise",
    "hype",
)
_PATTERN = re.compile(r"\b(" + "|".join(re.escape(w) for w in BANNED) + r")\b", re.IGNORECASE)


def banned_words(text: str) -> list[str]:
    """Banned words found in generated text, ignoring anything inside quotation marks."""
    unquoted = re.sub(r"[\"“][^\"”]*[\"”]", " ", text or "")
    return sorted({m.group(0).lower() for m in _PATTERN.finditer(unquoted)})
