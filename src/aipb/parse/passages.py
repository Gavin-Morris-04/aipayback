"""Sections -> passages of about 150-400 words, split on paragraph boundaries.

passage_id = {cik}-{accession}-{section}-{seq:04d}. IDs are stable as long as the parser
version (aipb.parse.html.PARSER_VERSION) and the source document do not change. Gold labels
also store the passage text hash and the quote, so they can be re-mapped if the parser ever
changes after labeling.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass

from aipb.parse.html import Block
from aipb.parse.sections import Section

MIN_WORDS = 150
MAX_WORDS = 400
BLOCK_SEP = "\n\n"
_INVISIBLE_CHARS = frozenset(map(chr, (0x00AD, 0x200B, 0x200C, 0x200D, 0x2060, 0xFEFF)))

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?\u201d])\s+(?=[A-Z\u201c\"(\u2022])")


@dataclass(frozen=True)
class Passage:
    passage_id: str
    cik: int
    accession: str
    doc_role: str
    section: str
    seq: int
    text: str
    char_start: int
    char_end: int

    @property
    def words(self) -> int:
        return len(self.text.split())

    @property
    def text_sha256(self) -> str:
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()


def normalize_for_match(text: str) -> str:
    """The one normalization used for keyword search, FTS and verbatim quote checks.

    NFKC folds ligatures ("ﬁ" -> "fi") and odd spaces; quotes and dashes are made plain;
    soft hyphens are removed; whitespace is collapsed. Documented in docs/DECISIONS.md.
    """
    text = unicodedata.normalize("NFKC", text)
    text = text.translate(
        {
            0x2018: "'", 0x2019: "'", 0x201A: "'", 0x201B: "'", 0x2032: "'",
            0x201C: '"', 0x201D: '"', 0x201E: '"', 0x201F: '"', 0x2033: '"',
            0x2013: "-", 0x2014: "-", 0x2012: "-", 0x2212: "-", 0x2010: "-", 0x2011: "-",
            0x00AD: None, 0x200B: None, 0x200C: None, 0x200D: None, 0xFEFF: None,
        }
    )  # fmt: skip
    return " ".join(text.split())


def passage_id(cik: int, accession: str, section: str, seq: int) -> str:
    return f"{cik}-{accession}-{section}-{seq:04d}"


def _split_long(block: Block) -> list[Block]:
    """Break one oversized block into pieces of at most MAX_WORDS words."""
    if block.words <= MAX_WORDS:
        return [block]
    units = block.text.split("\n") if block.kind == "table" else _SENTENCE_SPLIT.split(block.text)
    joiner = "\n" if block.kind == "table" else " "
    pieces: list[Block] = []
    buf: list[str] = []
    count = 0
    for unit in units:
        n = len(unit.split())
        if buf and count + n > MAX_WORDS:
            pieces.append(Block(joiner.join(buf), block.kind))
            buf, count = [], 0
        if n > MAX_WORDS:  # a single run-on sentence or row: hard split on words
            words = unit.split()
            for i in range(0, len(words), MAX_WORDS):
                pieces.append(Block(" ".join(words[i : i + MAX_WORDS]), block.kind))
            continue
        buf.append(unit)
        count += n
    if buf:
        pieces.append(Block(joiner.join(buf), block.kind))
    return pieces


def chunk_blocks(blocks: list[Block]) -> list[list[Block]]:
    """Greedy packing on paragraph boundaries: a chunk closes when the next paragraph would
    push it past MAX_WORDS. A short tail joins the previous chunk when that still fits."""
    chunks: list[list[Block]] = []
    cur: list[Block] = []
    count = 0
    for block in (piece for b in blocks for piece in _split_long(b)):
        n = block.words
        if cur and count + n > MAX_WORDS:
            chunks.append(cur)
            cur, count = [], 0
        cur.append(block)
        count += n
    if cur:
        tail_words = sum(b.words for b in cur)
        if (
            chunks
            and tail_words < MIN_WORDS // 3
            and (sum(b.words for b in chunks[-1]) + tail_words <= MAX_WORDS)
        ):
            chunks[-1].extend(cur)
        else:
            chunks.append(cur)
    return chunks


def build_passages(
    cik: int, accession: str, doc_role: str, sections: list[Section], *, offset: int = 0
) -> list[Passage]:
    """Passages for one document. char_start/char_end index into the document's clean text,
    which is every block joined with a blank line, in order."""
    out: list[Passage] = []
    pos = offset
    for sec in sections:
        for seq, chunk in enumerate(chunk_blocks(sec.blocks), start=1):
            text = BLOCK_SEP.join(b.text for b in chunk)
            out.append(
                Passage(
                    passage_id=passage_id(cik, accession, sec.name, seq),
                    cik=cik,
                    accession=accession,
                    doc_role=doc_role,
                    section=sec.name,
                    seq=seq,
                    text=text,
                    char_start=pos,
                    char_end=pos + len(text),
                )
            )
            pos += len(text) + len(BLOCK_SEP)
    return out


def _normalize_with_map(text: str) -> tuple[str, list[int]]:
    """normalize_for_match(text) plus, for each output character, its index in `text`."""
    out: list[str] = []
    where: list[int] = []
    pending_space = False
    for i, ch in enumerate(text):
        piece = normalize_for_match_char(ch)
        if piece is None:
            continue
        if piece == " ":
            pending_space = bool(out)
            continue
        if pending_space:
            out.append(" ")
            where.append(i)
            pending_space = False
        for c in piece:
            out.append(c)
            where.append(i)
    return "".join(out), where


def normalize_for_match_char(ch: str) -> str | None:
    """One character's contribution to normalize_for_match: None (dropped), " " or text."""
    if ch.isspace():
        return " "
    norm = normalize_for_match(ch) if ch.strip() else ""
    if not norm:
        return None if ch in _INVISIBLE_CHARS else " "
    return norm


def locate_quote(passage_text: str, quote: str) -> tuple[int, int] | None:
    """(start, end) of `quote` in the ORIGINAL passage text, matched after normalization.

    Returns None unless the quote appears verbatim (case-sensitive, after the documented
    normalization). The returned span lets us publish the filing's own characters.
    """
    target = normalize_for_match(quote)
    if not target:
        return None
    norm, where = _normalize_with_map(passage_text)
    i = norm.find(target)
    if i < 0:
        return None
    start, end = where[i], where[i + len(target) - 1] + 1
    if normalize_for_match(passage_text[start:end]) != target:
        return None
    return start, end
