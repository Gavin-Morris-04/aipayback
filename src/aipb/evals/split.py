"""Dev / held-out test split, grouped by company and frozen in evals/splits.json.

Grouping by company prevents leakage: a promise restated in several filings never ends
up on both sides. Companies are shuffled with a fixed seed within each sector and dealt
alternately, so both sides span sectors. Once written, the split never changes unless
someone passes --force (and that is recorded in the file).
"""

from __future__ import annotations

import json
import random
from collections import defaultdict
from pathlib import Path

from aipb.budget.ledger import utc_now

SEED = 20261110
DEV_SHARE = 0.6


def make_split(
    companies: dict[str, str], *, seed: int = SEED, dev_share: float = DEV_SHARE
) -> dict:
    """companies: ticker -> sector. Returns {"dev": [...], "test": [...]}."""
    rng = random.Random(seed)
    by_sector: dict[str, list[str]] = defaultdict(list)
    for ticker, sector in sorted(companies.items()):
        by_sector[sector].append(ticker)
    order: list[str] = []
    for sector in sorted(by_sector):
        tickers = by_sector[sector]
        rng.shuffle(tickers)
        order += tickers
    # Greedy dealing keeps the running dev share near dev_share, so sectors (which are
    # contiguous in `order`) end up on both sides.
    dev: list[str] = []
    test: list[str] = []
    for t in order:
        if len(dev) + 1 <= round(dev_share * (len(dev) + len(test) + 1)):
            dev.append(t)
        else:
            test.append(t)
    return {"dev": sorted(dev), "test": sorted(test)}


def load_split(path: Path) -> dict | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def freeze_split(path: Path, companies: dict[str, str], *, force: bool = False) -> dict:
    existing = load_split(path)
    if existing is not None and not force:
        return existing
    split = make_split(companies)
    record = {
        **split,
        "seed": SEED,
        "dev_share": DEV_SHARE,
        "sectors": {t: companies[t] for t in sorted(companies)},
        "created": utc_now(),
        "replaced_previous": existing is not None,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8",
                    newline="\n")  # fmt: skip
    return record
