"""Cluster ids are reused after a re-extraction; stored results must follow the promise (D42).

A cluster id comes from its canonical promise's position in the passage ("s1"). When
extraction changes, "s1" can be a different statement, so a verdict or explanation stored
for the old one must never be read as if it judged the new one.
"""

from aipb import db
from aipb.stages import verify_runner as vr
from aipb.verify.tier1 import Verdict

CID = "c-default:p1:s1"


def _promise(conn, quote: str) -> None:
    conn.execute("DELETE FROM promises")
    conn.execute(
        "INSERT INTO promises (promise_id, variant, passage_id, cik, accession, filing_date, "
        "seq, quote, quote_start, quote_end, kind, claim_type, prompt_version, model, "
        "cluster_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        ("default:p1:s1", "default", "p1", 1, "a1", "2025-02-01", 1, quote, 0, len(quote),
         "promise", "cost_savings", "extract/v1", "m", CID),
    )  # fmt: skip
    conn.execute(
        "INSERT OR REPLACE INTO promise_clusters VALUES (?,?,?,?,?,?,?,?,?)",
        (CID, "default", 1, "cost_savings", "default:p1:s1", "2025-02-01", "2025-02-01", 1, None),
    )
    conn.commit()


def test_results_for_a_replaced_promise_are_ignored_then_purged(tmp_path):
    conn = db.connect(tmp_path / "x.sqlite")
    conn.execute("PRAGMA foreign_keys=OFF")
    _promise(conn, "We expect equipment sales to decline in 2025")
    v = Verdict("2", "delivered", "none", 0.95, ["E1"], [], "The 10-K reports it.")
    vr._store_verdict(conn, CID, "default", v, tier="2", stop="submitted", prompt_id="p", model="m")
    with conn:
        conn.execute(
            "INSERT INTO explanations (cluster_id, variant, status, text, citations, "
            "citations_valid, lint_ok, problems, prompt_version, model, promise_sha) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (CID, "default", "delivered", "t", "[]", 1, 1, "[]", "p", "m",
             vr.promise_sha(conn, CID, "default")),
        )  # fmt: skip
    assert vr.load_verdict(conn, CID, "default", "2").status == "delivered"
    assert vr.load_explanation(conn, CID, "default") is not None

    # Re-extraction: a different statement now sits under the same cluster id.
    _promise(conn, "We expect AI to deliver $150 million of savings by 2025")
    assert vr.load_verdict(conn, CID, "default", "2") is None
    assert vr.load_explanation(conn, CID, "default") is None
    assert vr.purge_stale(conn, "default") == 1
    assert conn.execute("SELECT COUNT(*) FROM verdicts").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM explanations").fetchone()[0] == 0
    conn.close()


def test_results_without_a_fingerprint_are_never_trusted(tmp_path):
    conn = db.connect(tmp_path / "x.sqlite")
    conn.execute("PRAGMA foreign_keys=OFF")
    _promise(conn, "We expect AI to deliver $150 million of savings by 2025")
    v = Verdict("1", "on_track", "none", 0.9, ["E1"], [], "x")
    vr._store_verdict(conn, CID, "default", v, tier="1", stop="", prompt_id="p", model="m")
    with conn:
        conn.execute("UPDATE verdicts SET promise_sha=NULL")  # a row stored before D42
    assert vr.load_verdict(conn, CID, "default", "1") is None
    conn.close()
