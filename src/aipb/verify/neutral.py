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


def _unquoted(text: str) -> str:
    return re.sub(r"[\"“][^\"”]*[\"”]", " ", text or "")


# The company's voice belongs inside quotation marks; outside them "we" reads as if
# AIPayback made the promise (D46).
_FIRST_PERSON = re.compile(r"\b(?:[Ww]e|[Oo]urs?|[Uu]s)\b")
# A published explanation talks about the company and its filings, never about our checks.
_PROCESS = re.compile(
    r"\b(?:key finding|documents provided|the documents|first check|second check|not verified)\b",
    re.IGNORECASE,
)


def first_person(text: str) -> list[str]:
    """ "we", "our" or "us" outside quotation marks."""
    return sorted({m.group(0).lower() for m in _FIRST_PERSON.finditer(_unquoted(text))})


def process_words(text: str) -> list[str]:
    """Words about our own checks, outside quotation marks."""
    return sorted({m.group(0).lower() for m in _PROCESS.finditer(_unquoted(text))})
