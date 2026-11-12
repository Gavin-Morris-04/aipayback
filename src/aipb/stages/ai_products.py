"""AI product names that let an extracted statement's ai_link count as AI (D45).

The rubric counts promises about AI products as AI promises, but a link such as
"Blackwell revenue" names no term from the keyword lexicon. `config/ai_products.yaml`
lists product names per company. A name counts for a company only if that company's own
filings put it in the same sentence as a lexicon AI term in at least `min_filings`
filings, so a non-AI product listed by mistake can't widen what counts as AI.
"""

from __future__ import annotations

import re
import sqlite3
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import yaml

from aipb.parse.passages import normalize_for_match
from aipb.stages.prefilter import Lexicon

_SENTENCE = re.compile(r"(?<=[.!?])\s+")


def name_pattern(name: str) -> re.Pattern:
    """Case-sensitive whole-name match. A trademark mark right after the name is allowed
    ("OmniverseTM" after normalization), a longer word is not ("Rubinstein")."""
    body = r"\s+".join(re.escape(part) for part in name.split())
    return re.compile(rf"(?<![A-Za-z0-9]){body}(?![a-z0-9])")


@dataclass(frozen=True)
class ConfirmedProduct:
    name: str
    filings: int  # filings where the company ties it to AI in one sentence
    example_passage: str  # one such passage, for the audit


@dataclass
class AIProducts:
    version: str
    min_filings: int
    by_ticker: dict[str, list[str]]

    @classmethod
    def load(cls, path: Path) -> AIProducts:
        if not path.exists():
            return cls("none", 2, {})
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        listed = raw.get("companies") or {}
        companies = {str(k): [str(n) for n in (v or [])] for k, v in listed.items()}
        return cls(str(raw.get("version", "ap?")), int(raw.get("min_filings", 2)), companies)

    def confirmed(
        self, conn: sqlite3.Connection, cik: int, ticker: str, lexicon: Lexicon
    ) -> list[ConfirmedProduct]:
        """The listed names this company's own filings tie to AI."""
        out = []
        for name in self.by_ticker.get(ticker, []):
            pat = name_pattern(name)
            filings: dict[str, str] = {}
            rows = conn.execute(
                "SELECT passage_id, accession, text FROM passages WHERE cik=? AND instr(text, ?) "
                "ORDER BY filing_date, passage_id",
                (cik, name.split()[0]),
            )
            for r in rows:
                if r["accession"] in filings:
                    continue
                for sentence in _SENTENCE.split(normalize_for_match(r["text"])):
                    if pat.search(sentence) and lexicon.scan(sentence)[0]:
                        filings[r["accession"]] = r["passage_id"]
                        break
            if len(filings) >= self.min_filings:
                out.append(ConfirmedProduct(name, len(filings), next(iter(filings.values()))))
        return out


def names_ai_for(lexicon: Lexicon, products: list[ConfirmedProduct]) -> Callable[[str], bool]:
    """True if the text names a lexicon AI term or one of the company's confirmed products."""
    patterns = [name_pattern(p.name) for p in products]

    def names_ai(text: str) -> bool:
        if lexicon.scan(text)[0]:
            return True
        norm = normalize_for_match(text)
        return any(p.search(norm) for p in patterns)

    return names_ai


# Capitalized names (one or more words, acronyms, model numbers) for the suggestion list.
_NAME = re.compile(
    r"\b(?:[A-Z][A-Za-z0-9+\-]*[A-Z0-9][A-Za-z0-9+\-]*|[A-Z][a-z]+[A-Za-z0-9]*)"
    r"(?:\s+(?:[A-Z][A-Za-z0-9+\-]+|\d+))*\b"
)
_NOT_NAMES = frozenset(
    [
        "We",
        "Our",
        "The",
        "In",
        "For",
        "This",
        "These",
        "Such",
        "As",
        "On",
        "With",
        "Company",
        "Inc",
        "Corporation",
        "Form",
        "Item",
        "Part",
        "Annual",
        "Report",
        "Quarterly",
        "Fiscal",
        "Year",
        "Q1",
        "Q2",
        "Q3",
        "Q4",
        "January",
        "February",
        "March",
        "April",
        "May",
        "June",
        "July",
        "August",
        "September",
        "October",
        "November",
        "December",
        "AI",
        "GenAI",
        "LLM",
        "LLMs",
        "GPT",
    ]
)


def suggest(
    conn: sqlite3.Connection, cik: int, lexicon: Lexicon, limit: int = 40
) -> list[tuple[str, int]]:
    """Capitalized names that share a sentence with an AI term, ranked by how many of the
    company's filings do that. A starting point for a person to pick products from: it
    also returns segments, places, laws and partners, which are not products."""
    seen: dict[str, set[str]] = defaultdict(set)
    for r in conn.execute("SELECT accession, text FROM passages WHERE cik=?", (cik,)):
        for sentence in _SENTENCE.split(normalize_for_match(r["text"])):
            if not lexicon.scan(sentence)[0]:
                continue
            for m in _NAME.finditer(sentence):
                words = m.group(0).split()
                while words and words[-1] in _NOT_NAMES:  # "Hopper AI" -> "Hopper"
                    words.pop()
                name = " ".join(words)
                if len(name) >= 3 and words[0] not in _NOT_NAMES:
                    seen[name].add(r["accession"])
    ranked = sorted(seen.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    return [(name, len(acc)) for name, acc in ranked[:limit]]
