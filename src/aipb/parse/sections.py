"""Split a filing's blocks into SEC Items (sections).

Section names are short tokens that go into passage IDs:
- 10-K: item1, item1a, item7, ... (text before the first Item is "cover").
- 10-Q: p1item2 (Part I, Item 2 = MD&A), p2item1a, ... (before the first Item: "cover").
- Exhibits have one section each: ex13 (annual report), ex99 (earnings release).

Headings are only taken from short paragraph blocks that start with "Item N", never from
tables, so a table of contents laid out as a table is ignored. A table of contents laid
out as paragraphs creates empty sections that the real headings later overwrite.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from aipb.parse.html import Block

ITEM_RE = re.compile(r"^item\s*(\d{1,2})\s*([a-c])?\b\s*[.:\-\u2013\u2014]?", re.IGNORECASE)
PART_RE = re.compile(r"^part\s+(iv|iii|ii|i)\b", re.IGNORECASE)
MAX_HEADING_WORDS = 25

TEN_K_ITEMS = {
    "1", "1a", "1b", "1c", "2", "3", "4", "5", "6", "7", "7a", "8", "9", "9a", "9b", "9c",
    "10", "11", "12", "13", "14", "15", "16",
}  # fmt: skip
TEN_Q_ITEMS = {"1": {"1", "2", "3", "4"}, "2": {"1", "1a", "2", "3", "4", "5", "6"}}
ROMAN = {"i": "1", "ii": "2", "iii": "3", "iv": "4"}


@dataclass(frozen=True)
class Section:
    name: str
    blocks: list[Block]


def _heading(block: Block) -> tuple[str, str] | None:
    """('part', '2') or ('item', '1a') when the block is a heading, else None."""
    if block.kind != "p" or block.words > MAX_HEADING_WORDS:
        return None
    m = ITEM_RE.match(block.text)
    if m:
        return "item", (m.group(1) + (m.group(2) or "")).lower()
    m = PART_RE.match(block.text)
    if m:
        return "part", ROMAN[m.group(1).lower()]
    return None


def split_sections(blocks: list[Block], form: str, role: str = "primary") -> list[Section]:
    if role != "primary":
        return [Section(role, blocks)] if blocks else []
    if form == "8-K":
        return [Section("ex99", blocks)] if blocks else []

    sections: list[Section] = []
    current = "cover"
    current_blocks: list[Block] = []
    part = "1"

    def close() -> None:
        if current_blocks:
            sections.append(Section(current, list(current_blocks)))

    for block in blocks:
        head = _heading(block)
        new_name = None
        if head and head[0] == "part":
            part = head[1]
        elif head and head[0] == "item":
            item = head[1]
            if form == "10-K" and item in TEN_K_ITEMS:
                new_name = f"item{item}"
            elif form == "10-Q" and item in TEN_Q_ITEMS.get(part, set()):
                new_name = f"p{part}item{item}"
        if new_name is not None:
            close()
            current, current_blocks = new_name, []
        current_blocks.append(block)
    close()

    # A paragraph-style table of contents can make the same section appear twice. Merge
    # repeats so passage numbering stays unique within (filing, section).
    merged: dict[str, list[Block]] = {}
    order: list[str] = []
    for sec in sections:
        if sec.name not in merged:
            merged[sec.name] = []
            order.append(sec.name)
        merged[sec.name].extend(sec.blocks)
    return [Section(name, merged[name]) for name in order]
