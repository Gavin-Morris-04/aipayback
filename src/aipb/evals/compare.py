"""`aipb compare`: the A/B table (Haiku settings vs Sonnet) from saved eval results. $0.

For each variant, the latest dev result: precision, recall, F1 with its interval, the
ledger cost of the calls behind it, and the cost per F1 point relative to the default.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

from aipb.evals.run import fmt, fmt_ci


def latest_results(results_dir: Path, split: str) -> dict[str, dict]:
    latest: dict[str, dict] = {}
    for path in sorted(results_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if data.get("split") != split or "extraction" not in data:
            continue
        data["_file"] = path.name
        latest[data["variant"]] = data  # files sort by timestamp, so the last one wins
    return latest


def total_cost(result: dict) -> Decimal:
    return sum((Decimal(v) for v in (result.get("cost_usd") or {}).values()), Decimal(0))


def table(results: dict[str, dict]) -> str:
    base = results.get("default")
    lines = [
        "| Variant | Models | Precision | Recall | F1 (95% CI) | Cost | Extra cost per F1 point |",
        "|---|---|---|---|---|---|---|",
    ]
    for name in sorted(results, key=lambda n: (n != "default", n)):
        r = results[name]
        e = r["extraction"]
        cost = total_cost(r)
        per = "baseline" if name == "default" else "n/a"
        if base and name != "default" and e["f1"] is not None and base["extraction"]["f1"]:
            gain = 100 * (e["f1"] - base["extraction"]["f1"])
            extra = cost - total_cost(base)
            per = f"${extra / Decimal(str(gain)):.4f}" if gain > 0 else "no F1 gain"
        lines.append(
            f"| {name} | {', '.join(r.get('models', []))} | {fmt(e['precision'])} | "
            f"{fmt(e['recall'])} | {fmt(e['f1'])} {fmt_ci(e['ci95']['f1'])} | ${cost:.4f} | "
            f"{per} |"
        )
    return "\n".join(lines)
