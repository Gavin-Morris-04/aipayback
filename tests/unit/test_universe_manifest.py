"""Universe files, the filings manifest and the JSONL helper."""

from datetime import date

import pytest

from aipb import jsonl
from aipb.sec.manifest import Manifest, ManifestEntry
from aipb.stages.ingest import expected_periodic
from aipb.universe import UniverseError, load_universe


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_load_universe_with_extra_ciks_and_comments(tmp_path):
    write(
        tmp_path / "u.csv",
        "ticker,name,sector,extra_ciks\n"
        "xom,Exxon Mobil,Energy,34088\n"
        "#SKIP,ignored,x,\n"
        "ABC,Abc,Tech,1; 2\n"
        ",blank,x,\n",
    )
    members = load_universe(tmp_path, "u")
    assert [m.ticker for m in members] == ["XOM", "ABC"]
    assert members[0].extra_ciks == (34088,)
    assert members[1].extra_ciks == (1, 2)


def test_real_pilot_file_loads():
    from tests.conftest import REPO

    members = load_universe(REPO / "config" / "universe", "pilot")
    assert len(members) == 10
    assert len({m.sector for m in members}) >= 5


@pytest.mark.parametrize(
    "text, message",
    [
        ("ticker,name\nA,a\n", "missing columns: sector"),
        ("ticker,name,sector\nA,a,x\nA,a2,y\n", "twice: A"),
        ("ticker,name,sector,extra_ciks\nA,a,x,12ab\n", "must be numbers"),
    ],
)
def test_universe_errors(tmp_path, text, message):
    write(tmp_path / "u.csv", text)
    with pytest.raises(UniverseError, match=message):
        load_universe(tmp_path, "u")


def entry(acc="0001-25-000001", doc="a.htm", cik=1, company_cik=1, ticker="ABC"):
    return ManifestEntry(
        cik=cik, company_cik=company_cik, ticker=ticker, accession=acc, form="10-K",
        filing_date="2025-02-01", report_date="2024-12-31", items="", primary_doc=doc,
        role="primary", doc=doc, url=f"https://www.sec.gov/{doc}", sha256="0" * 64, bytes=10,
        fetched="2026-11-10T00:00:00Z",
    )  # fmt: skip


def test_manifest_add_is_idempotent_and_survives_union_merge(tmp_path):
    path = tmp_path / "filings.jsonl"
    m = Manifest(path)
    assert m.add([entry(), entry(doc="b.htm")]) == 2
    assert m.add([entry()]) == 0
    # A union merge can duplicate lines; reading still gives unique entries.
    lines = path.read_text(encoding="utf-8")
    path.write_text(lines + lines, encoding="utf-8", newline="\n")
    again = Manifest(path)
    assert len(again) == 2
    assert b"\r\n" not in path.read_bytes()


def test_manifest_tracks_predecessor_filers(tmp_path):
    m = Manifest(tmp_path / "f.jsonl")
    m.add([entry(acc="a", cik=34088, company_cik=2115436, ticker="XOM"),
           entry(acc="b", cik=2115436, company_cik=2115436, ticker="XOM")])  # fmt: skip
    assert m.ciks() == {"XOM": 2115436}
    assert m.filer_ciks(2115436) == {34088, 2115436}
    assert m.accessions(2115436) == {"a", "b"}
    assert [e.accession for e in m.entries(2115436)] == ["a", "b"]


def test_jsonl_rejects_corrupt_lines(tmp_path):
    path = tmp_path / "x.jsonl"
    path.write_text('{"a": 1}\n<<<<<<< HEAD\n', encoding="utf-8")
    with pytest.raises(ValueError, match="merge conflict"):
        list(jsonl.read(path))


def test_expected_periodic():
    assert expected_periodic(date(2024, 1, 1), today=date(2026, 11, 10)) == 9
    assert expected_periodic(date(2026, 10, 1), today=date(2026, 11, 10)) == 0
