"""SEC HTML / inline-XBRL -> an ordered list of text blocks (paragraphs and tables).

Rules (each one exists because real filings needed it):
- Hidden content (display:none, the <ix:header> XBRL block, scripts, styles) is dropped.
- Block tags (p, div, li, headings, br, ...) start a new block; inline tags (span, font,
  a, ix:nonNumeric, ...) are concatenated as written.
- Tables: a table whose rows are mostly prose (bullets, side headings) is "layout" and each
  row becomes its own paragraph. Any other table is "data" and becomes one block with
  rows on separate lines and cells joined by " | ".
- Page furniture is dropped: page numbers, "Table of Contents" links, and short lines that
  repeat on many pages (running headers and footers).
- Text is kept as written (curly quotes stay curly) so quotes can be checked verbatim.
  Only invisible characters are removed and whitespace is collapsed.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

from lxml import etree
from lxml import html as lxml_html

PARSER_VERSION = "p1"

BLOCK_TAGS = {
    "p", "div", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote",
    "section", "article", "center", "pre", "dl", "dt", "dd", "hr", "br", "body",
    "header", "footer", "address", "figure", "figcaption", "form", "fieldset",
}  # fmt: skip
SKIP_TAGS = {"script", "style", "head", "title", "ix:header", "noscript", "template"}

_INVISIBLE = dict.fromkeys(map(ord, "\u00ad\u200b\u200c\u200d\u2060\ufeff"), None)
_WS = re.compile(r"[\s\u00a0\u2002\u2003\u2009\u202f]+")
_BULLET = re.compile(r"^[\u2022\u25cf\u25e6\u25aa\u25a0\u2023\u2043\u2219\u00b7o\-\u2013\u2014*]$")
_PAGE_NUM = re.compile(r"^(page\s+)?([0-9]{1,3}|[ivxlc]{1,6})$", re.IGNORECASE)
_FURNITURE = re.compile(
    r"^(table of contents|index|back to contents|return to table of contents)$", re.I
)
_DISPLAY_NONE = re.compile(r"display\s*:\s*none", re.IGNORECASE)
_XML_DECL = re.compile(rb"^\s*<\?xml[^>]*\?>", re.IGNORECASE)
_SGML_TEXT = re.compile(rb"<TEXT>(.*?)(</TEXT>|\Z)", re.DOTALL | re.IGNORECASE)


@dataclass(frozen=True)
class Block:
    text: str
    kind: str  # "p" (paragraph or heading) or "table"

    @property
    def words(self) -> int:
        return len(self.text.split())


def clean_text(text: str) -> str:
    return _WS.sub(" ", text.translate(_INVISIBLE)).strip()


def _decode(raw: bytes) -> str:
    if raw.lstrip()[:10].upper().startswith(b"<DOCUMENT>"):
        m = _SGML_TEXT.search(raw)
        if m:
            raw = m.group(1)
    raw = _XML_DECL.sub(b"", raw, count=1)
    for enc in ("utf-8", "cp1252"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1")


def _tag(el) -> str | None:
    tag = el.tag
    return tag.lower() if isinstance(tag, str) else None


def _hidden(el) -> bool:
    return bool(_DISPLAY_NONE.search(el.get("style") or ""))


class _Builder:
    def __init__(self) -> None:
        self.blocks: list[Block] = []
        self._pieces: list[str] = []

    def text(self, s: str | None) -> None:
        if s:
            self._pieces.append(s)

    def flush(self) -> None:
        if self._pieces:
            text = clean_text("".join(self._pieces))
            self._pieces = []
            if text:
                self.blocks.append(Block(text, "p"))

    def add(self, block: Block) -> None:
        self.flush()
        self.blocks.append(block)


def _inline_text(el) -> str:
    """Visible text of an element, ignoring hidden children; blocks inside become spaces."""
    parts: list[str] = []

    def walk(node) -> None:
        tag = _tag(node)
        if tag is None:
            parts.append(node.tail or "")
            return
        if tag in SKIP_TAGS or _hidden(node):
            parts.append(node.tail or "")
            return
        block = tag in BLOCK_TAGS or tag in ("td", "th", "tr", "table")
        if block:
            parts.append(" ")
        parts.append(node.text or "")
        for child in node:
            walk(child)
        if block:
            parts.append(" ")
        parts.append(node.tail or "")

    parts.append(el.text or "")
    for child in el:
        walk(child)
    return clean_text("".join(parts))


def _merge_cells(cells: list[str]) -> list[str]:
    """Drop empties and bullets; glue '$' to the next cell and ')' or '%' to the previous."""
    out: list[str] = []
    pending_prefix = ""
    for cell in cells:
        if not cell or _BULLET.match(cell):
            continue
        if cell in ("$", "\u20ac", "\u00a3", "(", "$(", "($"):
            pending_prefix += cell
            continue
        if out and re.fullmatch(r"[)%]+|\)%", cell):
            out[-1] += cell
            continue
        out.append(pending_prefix + cell)
        pending_prefix = ""
    return out


def _rows(table) -> list[list[str]]:
    rows: list[list[str]] = []
    for tr in table.iter("tr"):
        # Skip rows that belong to a nested table; they are read with that table.
        parent = tr.getparent()
        while parent is not None and _tag(parent) != "table":
            parent = parent.getparent()
        if parent is not table or _hidden(tr):
            continue
        cells = [_inline_text(td) for td in tr if _tag(td) in ("td", "th") and not _hidden(td)]
        cells = _merge_cells(cells)
        if cells:
            rows.append(cells)
    return rows


def _table_blocks(table) -> list[Block]:
    rows = _rows(table)
    if not rows:
        return []
    prose_rows = sum(1 for r in rows if len(r) <= 2 and max(len(c.split()) for c in r) >= 12)
    single_cell = sum(1 for r in rows if len(r) == 1)
    if (len(rows) == 1 and len(rows[0]) <= 2) or prose_rows + single_cell >= max(
        1, len(rows) * 0.6
    ):
        return [Block(" ".join(r), "p") for r in rows]
    return [Block("\n".join(" | ".join(r) for r in rows), "table")]


def _walk(el, b: _Builder) -> None:
    tag = _tag(el)
    if tag is None:  # comment or processing instruction
        b.text(el.tail)
        return
    if tag in SKIP_TAGS or _hidden(el):
        b.text(el.tail)
        return
    if tag == "table":
        b.flush()
        for block in _table_blocks(el):
            b.add(block)
        b.text(el.tail)
        return
    is_block = tag in BLOCK_TAGS
    if is_block:
        b.flush()
    b.text(el.text)
    for child in el:
        _walk(child, b)
    if is_block:
        b.flush()
    b.text(el.tail)


def _furniture_key(text: str) -> str:
    # Running footers carry the page number at either end ("44 Notes ... Companies" and
    # "Notes ... Companies 45"), so numbers are removed before counting repeats.
    return " ".join(re.sub(r"\d+", " ", text.lower()).split())


def _drop_furniture(blocks: list[Block]) -> list[Block]:
    counts = Counter(
        _furniture_key(blk.text) for blk in blocks if blk.kind == "p" and blk.words <= 12
    )
    out = []
    for blk in blocks:
        if blk.kind == "p":
            if _PAGE_NUM.match(blk.text) or _FURNITURE.match(blk.text):
                continue
            if blk.words <= 12 and counts[_furniture_key(blk.text)] >= 4:
                continue
        out.append(blk)
    return out


def html_to_blocks(raw: bytes) -> list[Block]:
    text = _decode(raw)
    if "<" not in text[:2000] and "<html" not in text.lower()[:5000]:
        return text_to_blocks(text)
    try:
        root = lxml_html.document_fromstring(text)
    except (etree.ParserError, ValueError):
        return text_to_blocks(text)
    body = root.find(".//body")
    builder = _Builder()
    _walk(body if body is not None else root, builder)
    builder.flush()
    return _drop_furniture(builder.blocks)


def text_to_blocks(text: str) -> list[Block]:
    """Plain-text filings: paragraphs are separated by blank lines."""
    paras = re.split(r"\n\s*\n", text)
    return _drop_furniture([Block(clean_text(p), "p") for p in paras if clean_text(p)])
