"""`aipb findings`: aggregate stats for docs/FINDINGS.md and the LinkedIn launch. $0.

Rules (brief section 14): every number comes from the published data, every share shows
its count and denominator, groups with fewer than MIN_N items are labeled "too few to
compare", and the caveats are written next to the numbers, not in a footnote.
"""

from __future__ import annotations

import json
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

from aipb.budget.ledger import utc_now
from aipb.verify.gate import PENDING

MIN_N = 5


def _share(k: int, n: int) -> str:
    if n == 0:
        return "n/a (0 items)"
    if n < MIN_N:
        return f"{k} of {n} (too few to compare)"
    return f"{100 * k / n:.0f}% ({k} of {n})"


def compute(conn: sqlite3.Connection, site_data: dict, variant: str = "default") -> dict:
    sector = {
        r["ticker"]: r["sector"] for r in conn.execute("SELECT ticker, sector FROM companies")
    }
    kinds: dict[str, Counter] = defaultdict(Counter)
    for r in conn.execute(
        "SELECT c.ticker, p.kind FROM promises p JOIN companies c ON c.cik=p.cik WHERE p.variant=?",
        (variant,),
    ):
        kinds[sector.get(r["ticker"], "?")][r["kind"]] += 1
    promises = site_data.get("promises", [])
    by_type: dict[str, Counter] = defaultdict(Counter)
    by_sector: dict[str, Counter] = defaultdict(Counter)
    for p in promises:
        by_type[p["claim_type"]][p["status"]] += 1
        by_sector[sector.get(p["ticker"], "?")][p["status"]] += 1
    total_kinds = Counter()
    for c in kinds.values():
        total_kinds.update(c)
    return {
        "generated": utc_now(),
        "as_of": site_data.get("as_of"),
        "companies": len(sector),
        "statements": dict(total_kinds),
        "kinds_by_sector": {k: dict(v) for k, v in kinds.items()},
        "promises": len(promises),
        "published": sum(p["publishable"] for p in promises),
        "status_by_claim_type": {k: dict(v) for k, v in by_type.items()},
        "status_by_sector": {k: dict(v) for k, v in by_sector.items()},
    }


def render(f: dict) -> str:
    st = f["statements"]
    checkable, hype = st.get("promise", 0), st.get("hype", 0)
    lines = [
        "# Findings",
        "",
        f"_Generated {f['generated'][:10]} by `aipb findings` from published results "
        f"(SEC filings through {f['as_of'] or 'n/a'}). Every number below is computed from "
        "the data; nothing is rounded up or selected by hand._",
        "",
    ]
    if not f["promises"]:
        lines += [
            "No published results yet. This file fills in after the pipeline runs and the "
            "statuses pass the gate.",
            "",
        ]
    lines += [
        "## How much AI talk is checkable?",
        "",
        f"Of {checkable + hype} forward-looking AI statements extracted from {f['companies']} "
        f"companies' 2024-2025 filings, {_share(checkable, checkable + hype)} were specific "
        "enough to check later (a number, a deadline or a concrete deliverable); the rest were "
        "general AI language.",
        "",
        "| Sector | Checkable promises | General AI language | Checkable share |",
        "|---|---|---|---|",
    ]
    for sector, c in sorted(f["kinds_by_sector"].items()):
        k, h = c.get("promise", 0), c.get("hype", 0)
        lines.append(f"| {sector} | {k} | {h} | {_share(k, k + h)} |")
    lines += [
        "",
        "## What later filings report",
        "",
        f"{f['published']} of {f['promises']} promises have a published status; the rest are "
        f'"{PENDING}" because the evidence did not pass our checks.',
        "",
        "| Claim type | Promises | "
        + " | ".join(["Delivered", "On track", "No evidence yet", "Walked back", PENDING])
        + " |",
        "|---|---|---|---|---|---|---|",
    ]
    for t, c in sorted(f["status_by_claim_type"].items()):
        n = sum(c.values())
        cells = [str(c.get(s, 0)) for s in ("Delivered", "On track", "No evidence yet")]
        cells.append(str(c.get("Walked back", 0) + c.get("Walked back (silent)", 0)))
        cells.append(str(c.get(PENDING, 0)))
        lines.append(f"| {t.replace('_', ' ')} | {n} | " + " | ".join(cells) + " |")
    lines += [
        "",
        "## Caveats (read these before quoting any number)",
        "",
        "- SEC filings only (10-K, 10-Q, earnings releases). Promises made only on earnings "
        "calls or in the press are not included.",
        "- Promises from late 2025 have had little time to show results; many read "
        '"No evidence yet" for that reason alone.',
        "- A status describes what later filings report. It is not a judgment of management, "
        "and none of this is investment advice.",
        f'- Groups with fewer than {MIN_N} items are marked "too few to compare"; small '
        "differences between sectors are not meaningful at these sample sizes.",
        "- Accuracy of the underlying labels: see the evaluation table in the README and the "
        "Methodology page.",
    ]
    return "\n".join(lines) + "\n"


def write(conn: sqlite3.Connection, site_dir: Path, out: Path) -> dict:
    path = site_dir / "site_data.json"
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"promises": []}
    f = compute(conn, data)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(f), encoding="utf-8", newline="\n")
    return f
