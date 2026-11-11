"""Only analyzed companies appear on the site or count in findings (D43).

Every S&P 100 company is ingested, but the pilot analyzes 10. A company the filter never
read must not show "No checkable AI promises found", and must not inflate denominators.
"""

from aipb import db, findings
from aipb.publish import analyzed_ciks, build_site_data


def test_unanalyzed_companies_are_left_out(tmp_path):
    conn = db.connect(tmp_path / "x.sqlite")
    conn.execute("PRAGMA foreign_keys=OFF")
    conn.executemany(
        "INSERT INTO companies (cik, ticker, name, sector, universe) VALUES (?,?,?,?,?)",
        [
            (1, "PILOT", "Pilot Co", "Industrials", "pilot"),
            (2, "OTHER", "Other Co", "Energy", "sp100"),
        ],
    )
    conn.execute(
        "INSERT INTO passages (passage_id, cik, accession, form, filing_date, doc_role, section, "
        "seq, text, text_sha256, char_start, char_end, words) "
        "VALUES ('p1', 1, 'a1', '10-K', '2025-02-01', 'main', 'item7', 1, 'AI', 'h', 0, 2, 1)"
    )
    conn.execute(
        "INSERT INTO classifications VALUES ('p1', 'default', 'none', 'high', 'filter/v1', 'm')"
    )
    conn.commit()
    assert analyzed_ciks(conn) == {1}
    data = build_site_data(conn)
    assert [c["ticker"] for c in data["companies"]] == ["PILOT"]
    assert data["stats"]["companies"] == 1
    assert findings.compute(conn, data)["companies"] == 1
    conn.close()
