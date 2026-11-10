"""Company lists: config/universe/<name>.csv (pilot, later sp100)."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

REQUIRED = ("ticker", "name", "sector")


@dataclass(frozen=True)
class Member:
    ticker: str
    name: str
    sector: str
    ai_heavy: str = ""
    notes: str = ""
    source: str = ""
    source_date: str = ""
    # Predecessor registrants whose filings belong to this company (see sec/manifest.py).
    extra_ciks: tuple[int, ...] = ()


class UniverseError(ValueError):
    pass


def _parse_ciks(value: str, file: str, ticker: str) -> tuple[int, ...]:
    out = []
    for part in value.replace(",", ";").split(";"):
        part = part.strip()
        if not part:
            continue
        if not part.isdigit():
            raise UniverseError(f"{file}: extra_ciks for {ticker} must be numbers, got {part!r}")
        out.append(int(part))
    return tuple(out)


def load_universe(universe_dir: Path, name: str) -> list[Member]:
    path = universe_dir / f"{name}.csv"
    if not path.exists():
        raise UniverseError(f"No universe file at {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        missing = [c for c in REQUIRED if c not in (reader.fieldnames or [])]
        if missing:
            raise UniverseError(f"{path.name} is missing columns: {', '.join(missing)}")
        members = []
        for row in reader:
            ticker = (row.get("ticker") or "").strip().upper()
            if not ticker or ticker.startswith("#"):
                continue
            members.append(
                Member(
                    ticker=ticker,
                    name=(row.get("name") or "").strip(),
                    sector=(row.get("sector") or "").strip(),
                    ai_heavy=(row.get("ai_heavy") or "").strip(),
                    notes=(row.get("notes") or "").strip(),
                    source=(row.get("source") or "").strip(),
                    source_date=(row.get("source_date") or "").strip(),
                    extra_ciks=_parse_ciks(row.get("extra_ciks") or "", path.name, ticker),
                )
            )
    tickers = [m.ticker for m in members]
    dupes = sorted({t for t in tickers if tickers.count(t) > 1})
    if dupes:
        raise UniverseError(f"{path.name} lists these tickers twice: {', '.join(dupes)}")
    return members
