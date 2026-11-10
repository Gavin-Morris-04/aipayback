"""Ticker -> CIK, from the SEC's own company_tickers.json."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from aipb.sec.client import SecClient, SecError

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
TICKERS_MAX_AGE_S = 7 * 24 * 3600


@dataclass(frozen=True)
class CompanyId:
    ticker: str
    cik: int
    name: str


def normalize_ticker(ticker: str) -> str:
    """SEC writes class shares with a dash: BRK.B -> BRK-B."""
    return ticker.strip().upper().replace(".", "-").replace("/", "-")


def load_ticker_map(client: SecClient, raw_dir: Path) -> dict[str, CompanyId]:
    data = client.get_json(
        TICKERS_URL, raw_dir / "tickers" / "company_tickers.json", max_age_s=TICKERS_MAX_AGE_S
    )
    out: dict[str, CompanyId] = {}
    for row in data.values():
        ticker = normalize_ticker(str(row["ticker"]))
        out.setdefault(ticker, CompanyId(ticker, int(row["cik_str"]), str(row["title"])))
    return out


def resolve(ticker: str, ticker_map: dict[str, CompanyId]) -> CompanyId:
    key = normalize_ticker(ticker)
    if key not in ticker_map:
        raise SecError(f"Ticker {ticker!r} is not in the SEC ticker file. Check the spelling.")
    return ticker_map[key]
