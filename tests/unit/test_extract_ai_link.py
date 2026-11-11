"""Extract v2: a statement is kept only if the passage itself ties its outcome to AI (D42)."""

from pathlib import Path

from aipb.stages.extract import Verified, check_ai_link, split_linked, verify
from aipb.stages.prefilter import Lexicon

LEX = Lexicon.load(Path(__file__).resolve().parents[2] / "config" / "keywords.yaml")


def names_ai(text: str) -> bool:
    return bool(LEX.scan(text)[0])


PASSAGE = (
    "We launched a productivity program built on generative AI tools. We expect the program "
    "to deliver $150 million in annual run-rate cost savings by the end of 2025. "
    + "Other operating matters were in line with prior periods. " * 12
    + "We expect equipment sales to decline modestly in 2025."
)


def statement(quote: str, link: str) -> Verified:
    good, bad = verify(PASSAGE, [{"quote": quote, "ai_link": link, "kind": "promise"}])
    assert not bad
    return good[0]


def test_a_nearby_verbatim_link_that_names_ai_is_kept():
    v = statement(
        "We expect the program to deliver $150 million in annual run-rate cost savings",
        "program built on generative AI tools",
    )
    assert check_ai_link(PASSAGE, v, names_ai) is None
    assert v.ai_link == "program built on generative AI tools"


def test_general_guidance_without_a_real_link_is_dropped():
    sales = "We expect equipment sales to decline modestly in 2025"
    # pointing at AI words far away in the passage doesn't count
    far = statement(sales, "generative AI tools")
    assert check_ai_link(PASSAGE, far, names_ai) == "ai_link too far from the quote"
    # a link that names no AI term doesn't count
    plain = statement(sales, "equipment sales")
    assert "names no AI term" in check_ai_link(PASSAGE, plain, names_ai)
    # a paraphrased link, or none at all, doesn't count
    assert check_ai_link(PASSAGE, statement(sales, "AI-driven sales"), names_ai) == (
        "ai_link not in the passage"
    )
    assert check_ai_link(PASSAGE, statement(sales, ""), names_ai) == "no ai_link"


def test_link_match_ignores_case_but_stores_the_filings_characters():
    v = statement(
        "We expect the program to deliver $150 million", "PROGRAM BUILT ON GENERATIVE AI TOOLS"
    )
    assert check_ai_link(PASSAGE, v, names_ai) is None
    assert v.ai_link == "program built on generative AI tools"


def test_split_linked_keeps_order_and_reasons():
    keep = statement(
        "We expect the program to deliver $150 million", "program built on generative AI tools"
    )
    drop = statement("We expect equipment sales to decline modestly in 2025", "")
    linked, unlinked = split_linked(PASSAGE, [keep, drop], names_ai)
    assert linked == [keep] and [why for _, why in unlinked] == ["no ai_link"]
