"""SEC client, filing selection, index parsing and XBRL. All offline (MockTransport)."""

from datetime import date

import httpx2
import pytest

from aipb.sec import ciks
from aipb.sec import filings as F
from aipb.sec.client import (
    MissingContactEmail,
    RateLimiter,
    SecClient,
    SecError,
    SecNotFound,
    SecOffline,
)
from aipb.sec.xbrl import iter_facts
from tests.fake_sec import CIK, IN_WINDOW, PAGE_NAME, FakeSec, companyfacts, index_page


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0
        self.slept: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, s: float) -> None:
        self.slept.append(s)
        self.now += s


def make_client(fake: FakeSec, **kw) -> SecClient:
    return SecClient("ops@example.com", transport=fake.transport(), sleep=lambda s: None, **kw)


def test_rate_limiter_holds_eight_per_second():
    clock = FakeClock()
    limiter = RateLimiter(rate=8.0, clock=clock, sleep=clock.sleep)
    for _ in range(17):
        limiter.acquire()
    # The first request is free; the next 16 need 16/8 = 2 seconds.
    assert clock.now == pytest.approx(2.0)
    assert max(clock.slept) <= 1 / 8 + 1e-9


def test_user_agent_requires_contact_email(tmp_path):
    client = SecClient(None, transport=FakeSec().transport())
    with pytest.raises(MissingContactEmail):
        client.get_bytes("https://www.sec.gov/files/company_tickers.json", tmp_path / "t.json")


def test_user_agent_carries_contact_email_and_cache_avoids_refetch(tmp_path):
    fake = FakeSec()
    client = make_client(fake)
    url = "https://www.sec.gov/files/company_tickers.json"
    first = client.get_bytes(url, tmp_path / "t.json")
    second = client.get_bytes(url, tmp_path / "t.json")
    assert first == second
    assert fake.requests == ["/files/company_tickers.json"]
    assert fake.user_agents == {"AIPayback/0.1 (ops@example.com)"}
    assert client.stats.cache_hits == 1


def test_max_age_refreshes_stale_listing(tmp_path):
    fake = FakeSec()
    client = make_client(fake)
    url = "https://www.sec.gov/files/company_tickers.json"
    path = tmp_path / "t.json"
    client.get_bytes(url, path, max_age_s=3600)
    import os

    os.utime(path, (0, 0))  # pretend it is from 1970
    client.get_bytes(url, path, max_age_s=3600)
    assert len(fake.requests) == 2


def test_retries_on_429_then_succeeds(tmp_path):
    fake = FakeSec(fail_once={"/files/company_tickers.json"})
    client = make_client(fake)
    client.get_bytes("https://www.sec.gov/files/company_tickers.json", tmp_path / "t.json")
    assert len(fake.requests) == 2
    assert client.stats.retries == 1


def test_gives_up_after_max_retries(tmp_path):
    fake = FakeSec(status_overrides={"/files/company_tickers.json": 503})
    client = make_client(fake, max_retries=2)
    with pytest.raises(SecError, match="503 after 3 tries"):
        client.get_bytes("https://www.sec.gov/files/company_tickers.json", tmp_path / "t.json")
    assert not (tmp_path / "t.json").exists()


def test_404_raises_not_found(tmp_path):
    client = make_client(FakeSec())
    with pytest.raises(SecNotFound):
        client.get_bytes("https://www.sec.gov/nothing-here", tmp_path / "x")


def test_offline_serves_cache_and_refuses_misses(tmp_path):
    fake = FakeSec()
    path = tmp_path / "t.json"
    path.write_text('{"cached": true}', encoding="utf-8")
    import os

    os.utime(path, (0, 0))  # stale, but offline mode still serves it
    client = make_client(fake, offline=True)
    url = "https://www.sec.gov/files/company_tickers.json"
    assert client.get_json(url, path, max_age_s=1) == {"cached": True}
    with pytest.raises(SecOffline):
        client.get_bytes("https://www.sec.gov/other", tmp_path / "other")
    assert fake.requests == []


def test_invalid_json_is_not_cached(tmp_path):
    def handler(request):
        return httpx2.Response(200, content=b"<html>not json")

    client = SecClient("ops@example.com", transport=httpx2.MockTransport(handler))
    with pytest.raises(SecError, match="Invalid JSON"):
        client.get_json("https://data.sec.gov/x.json", tmp_path / "x.json")
    assert not (tmp_path / "x.json").exists()


def test_ticker_normalization_and_resolve(tmp_path):
    client = make_client(FakeSec())
    tmap = ciks.load_ticker_map(client, tmp_path)
    assert ciks.resolve("exmp", tmap).cik == CIK
    assert ciks.normalize_ticker("brk.b") == "BRK-B"
    with pytest.raises(SecError, match="not in the SEC ticker file"):
        ciks.resolve("NOPE", tmap)


def test_submission_rows_follow_pages_and_select_window(tmp_path):
    fake = FakeSec()
    client = make_client(fake)
    rows = F.submission_rows(client, tmp_path, CIK, date(2024, 1, 1))
    assert f"/submissions/{PAGE_NAME}" in fake.requests  # the older page overlaps the window
    refs = F.select_filings(rows, CIK, date(2024, 1, 1))
    assert {r.accession for r in refs} == IN_WINDOW
    assert [r.filing_date for r in refs] == sorted(r.filing_date for r in refs)
    # No 10-K/A, no Item 5.02 8-K, nothing before 2024.
    assert {r.form for r in refs} == {"10-K", "10-Q", "8-K"}


def test_old_pages_are_skipped_when_outside_window(tmp_path):
    fake = FakeSec()
    F.submission_rows(make_client(fake), tmp_path, CIK, date(2025, 1, 1))
    assert f"/submissions/{PAGE_NAME}" not in fake.requests


def test_select_filings_end_date():
    rows = [
        {"accessionNumber": "a", "form": "10-Q", "filingDate": "2024-05-01"},
        {"accessionNumber": "b", "form": "10-Q", "filingDate": "2026-05-01"},
    ]
    refs = F.select_filings(rows, 1, date(2024, 1, 1), end=date(2025, 12, 31))
    assert [r.accession for r in refs] == ["a"]


def test_parse_index_and_documents_to_parse():
    tenk = F.FilingRef(CIK, "9999999999-25-000010", "10-K", "2025-02-20", "", "", "exm.htm")
    idx = F.parse_index(
        index_page(
            tenk.accession,
            [("exm.htm", "10-K"), ("ex13.htm", "EX-13"), ("g.jpg", "GRAPHIC"), ("x.htm", "EX-21")],
        ).encode()
    )
    assert [d.doc_type for d in idx] == ["10-K", "EX-13", "GRAPHIC", "EX-21"]
    assert F.documents_to_parse(tenk, idx) == [("primary", "exm.htm"), ("ex13", "ex13.htm")]

    eightk = F.FilingRef(CIK, "acc", "8-K", "2025-04-29", "", "2.02", "8k.htm")
    idx8 = F.parse_index(
        index_page("acc", [("8k.htm", "8-K"), ("b.htm", "EX-99.2"), ("a.htm", "EX-99.1")]).encode()
    )
    assert F.documents_to_parse(eightk, idx8) == [("ex99", "a.htm")]
    only_99 = F.parse_index(index_page("acc", [("8k.htm", "8-K"), ("p.htm", "EX-99")]).encode())
    assert F.documents_to_parse(eightk, only_99) == [("ex99", "p.htm")]
    no_exhibit = F.parse_index(index_page("acc", [("8k.htm", "8-K")]).encode())
    assert F.documents_to_parse(eightk, no_exhibit) == [("primary", "8k.htm")]


def test_iter_facts_skips_old_filings():
    facts = list(iter_facts(companyfacts()))
    assert {f.tag for f in facts} == {"Revenues", "EntityCommonStockSharesOutstanding"}
    assert all(f.filed >= "2022-01-01" for f in facts)
    rev = [f for f in facts if f.tag == "Revenues"]
    assert len(rev) == 3 and rev[0].cik == CIK and rev[0].unit == "USD"
