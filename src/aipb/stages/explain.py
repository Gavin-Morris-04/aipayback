"""Stage 7: a short neutral explanation with Citations, in a separate call.

Citations can't be combined with structured outputs (the API returns a 400), which is why
the verdict (structured) and the explanation (cited) are two calls. Documents:
  0: the promise passage;
  1..k: the evidence passages the verdict cited;
  last: the reported numbers the verdict cited, written as sentences.
Code checks every citation: its cited_text must equal the document text at its character
span; the promise document must be cited; any status other than "No evidence yet" must
also cite evidence; and the wording must pass the neutral-language lint.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from aipb.llm.client import LLMResult
from aipb.llm.params import Prompt, thinking_params
from aipb.verify.context import EvidencePassage
from aipb.verify.neutral import banned_words, first_person, process_words
from aipb.verify.numbers import NumberRow
from aipb.verify.tier1 import DISPLAY, Verdict

STAGE = "explain"


@dataclass
class Explanation:
    text: str
    citations: list[dict]
    citations_valid: bool
    lint_ok: bool
    problems: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.citations_valid and self.lint_ok and bool(self.text)


def documents(
    promise_quote: str,
    promise_meta: str,
    promise_text: str,
    evidence: list[EvidencePassage],
    numbers: list[NumberRow],
    comparisons: list[str] | None = None,
) -> list[dict]:
    docs = [
        _doc(
            f"Promise: {promise_meta}", promise_text, f"The promise is this quote: {promise_quote}"
        )
    ]
    for e in evidence:
        docs.append(_doc(f"Evidence {e.eid}: {e.form} filed {e.filing_date}", e.text))
    if numbers:
        sentences = " ".join(
            f"{n.label[0].upper()}{n.label[1:]} was {n.display()} ({n.tag}, filed {n.filed})."
            for n in numbers
        )
        if comparisons:  # computed in code (D46): the model never compares numbers itself
            sentences += " " + " ".join(comparisons)
        docs.append(_doc("Reported figures (XBRL, arithmetic by code)", sentences))
    return docs


def _doc(title: str, text: str, context: str | None = None) -> dict:
    d = {
        "type": "document",
        "source": {"type": "text", "media_type": "text/plain", "data": text},
        "title": title,
        "citations": {"enabled": True},
    }
    if context:
        d["context"] = context
    return d


def build_params(
    cfg: dict, prompt: Prompt, docs: list[dict], verdict: Verdict, company: str
) -> dict:
    status = DISPLAY[verdict.status] + (" (silent)" if verdict.walked_back_kind == "silent" else "")
    ask = (
        f"Company: {company}. Status decided by our checks: {status}. "
        f"Key finding: {verdict.key_finding}\n\n"
        "Write the explanation now: 2 to 4 sentences, citing the promise document for what "
        "was promised and the evidence documents for what later filings report."
    )
    return {
        "model": cfg["model"],
        "max_tokens": int(cfg["max_tokens"]),
        "system": [{"type": "text", "text": prompt.text, "cache_control": {"type": "ephemeral"}}],
        "messages": [{"role": "user", "content": [*docs, {"type": "text", "text": ask}]}],
        **thinking_params(cfg),
    }


_QUOTES = '"“”'
_MIN_QUOTE = 20  # shorter cited fragments ("Blackwell") read fine without quotation marks


def _quote_if_verbatim(text: str, citations: list[dict]) -> str:
    """A text block that repeats its cited text word for word is the company's own words:
    show it in quotation marks (D46). With Citations the model often copies the cited
    sentence ("We expect to ship...") without marking it as a quote."""
    core = text.strip()
    if len(core) < _MIN_QUOTE or core[0] in _QUOTES or core[-1] in _QUOTES:
        return text
    cited = " ".join(" ".join(str(c.get("cited_text", "")).split()) for c in citations)
    if " ".join(core.rstrip(".").split()) not in cited:
        return text
    lead = text[: len(text) - len(text.lstrip())]
    trail = text[len(text.rstrip()) :]
    return f"{lead}“{core}”{trail}"


def check(result: LLMResult, docs: list[dict], status: str) -> Explanation:
    if result.status != "ok" or result.stop_reason in ("refusal", "max_tokens"):
        why = result.status if result.status != "ok" else result.stop_reason
        return Explanation("", [], False, False, [f"no usable explanation ({why})"])
    parts: list[str] = []
    cites: list[dict] = []
    problems: list[str] = []
    for block in result.response.get("content", []):
        if block.get("type") != "text":
            continue
        parts.append(_quote_if_verbatim(block.get("text", ""), block.get("citations") or []))
        for c in block.get("citations") or []:
            idx = c.get("document_index")
            if (
                c.get("type") != "char_location"
                or not isinstance(idx, int)
                or not (0 <= idx < len(docs))
            ):
                problems.append(f"citation to an unknown document: {c}")
                continue
            data = docs[idx]["source"]["data"]
            start, end = c.get("start_char_index", -1), c.get("end_char_index", -1)
            if data[start:end] != c.get("cited_text"):
                problems.append(f"cited text does not match document {idx} at {start}:{end}")
                continue
            cites.append(
                {
                    "document_index": idx,
                    "title": docs[idx]["title"],
                    "start": start,
                    "end": end,
                    "cited_text": c["cited_text"],
                    "after_char": len("".join(parts)),
                }
            )
    text = "".join(parts).strip()
    cited = {c["document_index"] for c in cites}
    if 0 not in cited:
        problems.append("the promise document is not cited")
    if status != "no_evidence_yet" and not cited - {0}:
        problems.append("no evidence document is cited")
    lint = banned_words(text)
    if lint:
        problems.append(f"non-neutral wording: {lint}")
    if voice := first_person(text):
        problems.append(f"wording: the company's voice outside quotation marks: {voice}")
    if process := process_words(text):
        problems.append(f"wording: mentions our checks: {process}")
    citations_valid = not [p for p in problems if "wording" not in p]
    return Explanation(text, cites, citations_valid, not (lint or voice or process), problems)
