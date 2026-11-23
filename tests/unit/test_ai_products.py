"""AI product names let an ai_link count as AI, if the company's own filings say so (D45)."""

from pathlib import Path

from aipb import db
from aipb.stages.ai_products import AIProducts, ConfirmedProduct, name_pattern, names_ai_for
from aipb.stages.extract import check_ai_link, verify
from aipb.stages.prefilter import Lexicon

LEX = Lexicon.load(Path(__file__).resolve().parents[2] / "config" / "keywords.yaml")


def test_names_match_whole_and_case_sensitively():
    blackwell = name_pattern("Blackwell")
    assert blackwell.search("demand for Blackwell is expected to exceed supply")
    assert blackwell.search("the NVIDIA BlackwellTM platform")  # trademark mark after the name
    assert not blackwell.search("Blackwells") and not blackwell.search("blackwell")
    assert not name_pattern("Rubin").search("Rubinstein")
    assert name_pattern("Grace Blackwell").search("Grace\nBlackwell systems")
    assert name_pattern("Alexa+").search("the new Alexa+ experience")


def _passage(conn, pid: str, cik: int, accession: str, text: str) -> None:
    conn.execute(
        "INSERT INTO passages (passage_id, cik, accession, form, filing_date, doc_role, section, "
        "seq, text, text_sha256, char_start, char_end, words) "
        "VALUES (?, ?, ?, '10-Q', '2025-01-01', 'main', 'item2', 1, ?, 'h', 0, 1, 1)",
        (pid, cik, accession, text),
    )


def test_a_name_counts_only_where_the_company_ties_it_to_ai(tmp_path):
    conn = db.connect(tmp_path / "x.sqlite")
    conn.execute("PRAGMA foreign_keys=OFF")
    tied = "Blackwell is our AI platform. Gaming was flat."
    _passage(conn, "p1", 1, "a1", tied)
    _passage(conn, "p2", 1, "a2", "Revenue grew. Blackwell, our new AI architecture, ramped.")
    # Optimus is in two filings, but never in the same sentence as an AI term.
    _passage(conn, "p3", 1, "a1", "Optimus builds began. Separately, AI spending rose.")
    _passage(conn, "p4", 1, "a2", "Optimus builds continued.")
    # Rubin is tied to AI in only one filing.
    _passage(conn, "p5", 1, "a1", "Rubin is our next AI platform.")
    products = AIProducts("t", 2, {"NVDA": ["Blackwell", "Optimus", "Rubin"]})
    confirmed = products.confirmed(conn, 1, "NVDA", LEX)
    assert [(p.name, p.filings, p.example_passage) for p in confirmed] == [("Blackwell", 2, "p1")]
    assert products.confirmed(conn, 1, "TSLA", LEX) == []  # names are per company
    conn.close()


def test_a_link_naming_a_confirmed_product_is_kept():
    passage = "Blackwell production shipments are scheduled to begin in the fourth quarter of 2025."
    said = {"quote": passage[:-1], "ai_link": "Blackwell", "kind": "promise"}
    good, bad = verify(passage, [said])
    assert not bad
    plain = names_ai_for(LEX, [])
    assert check_ai_link(passage, good[0], plain) == "ai_link names no AI term: 'Blackwell'"
    with_products = names_ai_for(LEX, [ConfirmedProduct("Blackwell", 2, "p1")])
    assert check_ai_link(passage, good[0], with_products) is None
    assert with_products("generative AI tools") and not with_products("equipment sales")


def test_a_quote_naming_a_confirmed_product_is_its_own_link():
    # N7: the model pointed at "fully autonomous vehicles", but the quote names Robotaxi.
    passage = (
        "We are building toward fully autonomous vehicles. "
        "In 2025, we intend to begin launching our Robotaxi business."
    )
    said = {
        "quote": "In 2025, we intend to begin launching our Robotaxi business",
        "ai_link": "fully autonomous vehicles",
        "kind": "promise",
    }
    good, _ = verify(passage, [said])
    plain = names_ai_for(LEX, [])
    assert "names no AI term" in check_ai_link(passage, good[0], plain)
    robotaxi = names_ai_for(LEX, [ConfirmedProduct("Robotaxi", 2, "p1")])
    assert check_ai_link(passage, good[0], robotaxi) is None
    assert good[0].ai_link == good[0].quote


def test_the_repo_list_loads():
    products = AIProducts.load(Path(__file__).resolve().parents[2] / "config" / "ai_products.yaml")
    assert products.version == "ap2" and products.min_filings == 2
    assert "Blackwell" in products.by_ticker["NVDA"] and "Robotaxi" in products.by_ticker["TSLA"]
    assert "Instinct" in products.by_ticker["AMD"]  # ap2, from the S&P 100 run (D56)


def test_suggest_ranks_names_that_share_a_sentence_with_ai(tmp_path):
    from aipb.stages.ai_products import suggest

    conn = db.connect(tmp_path / "x.sqlite")
    conn.execute("PRAGMA foreign_keys=OFF")
    _passage(conn, "p1", 1, "a1", "Blackwell is our AI platform. Gaming grew.")
    _passage(conn, "p2", 1, "a2", "We expect Blackwell AI demand to rise. Gaming grew.")
    _passage(conn, "p3", 1, "a2", "Hopper AI systems shipped.")
    assert suggest(conn, 1, LEX) == [("Blackwell", 2), ("Hopper", 1)]
    conn.close()
