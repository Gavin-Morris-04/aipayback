"""HTML -> blocks -> sections -> passages, on the synthetic fixture filings."""

from pathlib import Path

import pytest

from aipb.parse.html import Block, html_to_blocks, text_to_blocks
from aipb.parse.passages import (
    BLOCK_SEP,
    MAX_WORDS,
    build_passages,
    chunk_blocks,
    normalize_for_match,
)
from aipb.parse.sections import split_sections

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "sec"


@pytest.fixture(scope="module")
def tenk_blocks() -> list[Block]:
    return html_to_blocks((FIX / "exm-20241231.htm").read_bytes())


def texts(blocks):
    return [b.text for b in blocks]


def test_hidden_xbrl_and_page_furniture_are_dropped(tenk_blocks):
    joined = "\n".join(texts(tenk_blocks))
    assert "HIDDENXBRLCONTEXT" not in joined
    assert ".x{color" not in joined  # <style>
    assert "Exemplar Industries 2024 Form 10-K" not in joined  # running footer (4 times)
    assert not any(t.strip().isdigit() for t in texts(tenk_blocks))  # page numbers


def test_text_is_kept_verbatim_except_invisible_characters(tenk_blocks):
    joined = "\n".join(texts(tenk_blocks))
    assert "the “company”" in joined  # curly quotes kept
    assert "artiﬁcial intelligence" in joined  # ligature kept as written
    assert "technology improvements" in joined  # soft hyphen removed
    assert "Software & Services" in joined  # entity decoded


def test_tables_layout_vs_data(tenk_blocks):
    tables = [b for b in tenk_blocks if b.kind == "table"]
    toc, data = tables[0], tables[1]
    assert "Item 1A. Risk Factors | 3" in toc.text
    assert "Revenue | $12,345 | $11,022" in data.text  # "$" glued to the number
    assert "Operating margin | 18.2% | 16.7%" in data.text
    assert "$(45)" in data.text
    bullets = [b for b in tenk_blocks if b.text.startswith("We may not realize")]
    assert bullets and bullets[0].kind == "p"  # bullet layout table -> paragraphs


def test_10k_sections(tenk_blocks):
    secs = split_sections(tenk_blocks, "10-K")
    assert [s.name for s in secs] == ["cover", "item1", "item1a", "item7", "item8"]
    mdna = " ".join(b.text for b in secs[3].blocks)
    assert "$150 million in annual run-rate cost savings by the end of 2025" in mdna


def test_10q_paragraph_toc_is_overwritten_by_real_headings():
    blocks = html_to_blocks((FIX / "exm-20250331.htm").read_bytes())
    secs = {s.name: " ".join(b.text for b in s.blocks) for s in split_sections(blocks, "10-Q")}
    assert set(secs) == {"cover", "p1item1", "p1item2", "p2item1a", "p2item6"}
    assert "remains on track" in secs["p1item2"]
    assert "no material changes" in secs["p2item1a"]


def test_exhibits_are_single_sections_and_sgml_wrapper_is_stripped():
    blocks = html_to_blocks((FIX / "exm-ex991.htm").read_bytes())
    assert blocks[0].text == "EXEMPLAR REPORTS FIRST-QUARTER 2025 RESULTS"
    assert not any("<TYPE>" in t or t == "EX-99.1" for t in texts(blocks))
    assert [s.name for s in split_sections(blocks, "8-K", "ex99")] == ["ex99"]
    ex13 = html_to_blocks((FIX / "exm-20241231_ex13.htm").read_bytes())
    assert [s.name for s in split_sections(ex13, "10-K", "ex13")] == ["ex13"]


def test_plain_text_documents():
    blocks = text_to_blocks("ITEM 7. MD&A\n\nWe expect   savings.\n\n\n12\n")
    assert texts(blocks) == ["ITEM 7. MD&A", "We expect savings."]


def test_passages_have_stable_unique_ids_and_consistent_offsets(tenk_blocks):
    secs = split_sections(tenk_blocks, "10-K")
    ps = build_passages(99999999, "9999999999-25-000010", "primary", secs)
    ids = [p.passage_id for p in ps]
    assert len(ids) == len(set(ids))
    assert ids[0] == "99999999-9999999999-25-000010-cover-0001"
    assert all(p.words <= MAX_WORDS for p in ps)
    doc_text = BLOCK_SEP.join(p.text for p in ps)
    for p in ps:
        assert doc_text[p.char_start : p.char_end] == p.text
    # Deterministic: parsing again gives identical passages.
    again = build_passages(99999999, "9999999999-25-000010", "primary", secs)
    assert [(p.passage_id, p.text_sha256) for p in again] == [
        (p.passage_id, p.text_sha256) for p in ps
    ]


def test_item1a_splits_into_more_than_one_passage(tenk_blocks):
    secs = split_sections(tenk_blocks, "10-K")
    ps = [p for p in build_passages(1, "a", "primary", secs) if p.section == "item1a"]
    assert len(ps) >= 2


def test_long_block_is_split_on_sentences():
    sentence = "This sentence has exactly eight words in it. "
    block = Block((sentence * 120).strip(), "p")  # 960 words; real blocks are stripped
    chunks = chunk_blocks([block])
    assert len(chunks) == 3
    for chunk in chunks:
        assert sum(b.words for b in chunk) <= MAX_WORDS
        assert chunk[0].text.endswith("in it.")


def test_short_tail_joins_previous_chunk():
    chunks = chunk_blocks([Block("word " * 390, "p"), Block("tail " * 5, "p")])
    assert len(chunks) == 1


def test_normalize_for_match():
    raw = "Our “AI” plan—artiﬁcial intel­ligence  savings’"
    assert normalize_for_match(raw) == 'Our "AI" plan-artificial intelligence savings\''
