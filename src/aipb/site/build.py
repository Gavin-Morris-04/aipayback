"""`aipb site`: render the static site from data/site/site_data.json. No database needed.

Output goes to site/dist (git-ignored). CI builds the same way and deploys to GitHub
Pages, so the site only ever shows what `aipb publish` exported (and the gate allowed).
"""

from __future__ import annotations

import json
import shutil
from datetime import date
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape

from aipb.verify.gate import PENDING

HERE = Path(__file__).parent
BADGES = {
    "Delivered": "delivered",
    "On track": "ontrack",
    "No evidence yet": "noevidence",
    "Walked back": "walked",
    "Walked back (silent)": "walked",
    PENDING: "pending",
}


def empty_data() -> dict:
    return {
        "as_of": None,
        "stats": {"companies": 0, "promises": 0, "published": 0, "checkable_share": None},
        "companies": [],
        "promises": [],
        "status_order": list(BADGES),
    }


def eval_rows(evals_dir: Path) -> list[dict]:
    """Rows for the Methodology page: held-out test results only (dev is for tuning)."""
    rows = []
    for path in sorted((evals_dir / "results").glob("*.json")):
        try:
            r = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if r.get("kind") == "status" and r.get("at_threshold"):
            a = r["at_threshold"]
            if a.get("precision") is not None:
                rows.append(
                    {
                        "date": r["created"][:10],
                        "name": "Published status precision",
                        "result": f"{100 * a['precision']:.0f}% of {a['published']} "
                        f"(coverage {100 * (a['coverage'] or 0):.0f}%)",
                    }
                )
        elif r.get("split") == "test" and r.get("extraction", {}).get("f1") is not None:
            e = r["extraction"]
            ci = e["ci95"]["f1"]
            ci_text = f" (95% interval {100 * ci[0]:.0f}-{100 * ci[1]:.0f}%)" if ci else ""
            rows.append(
                {
                    "date": r["created"][:10],
                    "name": "Promise extraction F1",
                    "result": f"{100 * e['f1']:.0f}%{ci_text}",
                }
            )
    return rows[-6:]


def build_site(site_cfg: Path, data_path: Path, evals_dir: Path, out: Path) -> dict[str, int]:
    site = yaml.safe_load(site_cfg.read_text(encoding="utf-8"))
    site["site_url"] = site["site_url"].rstrip("/")
    data = json.loads(data_path.read_text(encoding="utf-8")) if data_path.exists() else empty_data()
    env = Environment(
        loader=FileSystemLoader(HERE / "templates"),
        autoescape=select_autoescape(["html"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["badge"] = lambda s: BADGES.get(s, "pending")
    if out.exists():
        shutil.rmtree(out)
    (out / "companies").mkdir(parents=True)
    (out / "promises").mkdir()
    shutil.copytree(HERE / "static", out / "static")
    pages: list[str] = []

    def render(template: str, path: str, title: str, description: str, **ctx) -> None:
        root = "../" * path.count("/")
        html = env.get_template(template).render(
            site=site,
            data=data,
            path=path,
            root=root,
            page_title=title,
            page_description=description,
            **ctx,
        )
        (out / path).write_text(html, encoding="utf-8", newline="\n")
        pages.append(path)

    dataset = {
        "@context": "https://schema.org",
        "@type": "Dataset",
        "name": f"{site['title']} scorecards",
        "description": site["description"].strip(),
        "url": f"{site['site_url']}/",
        "creator": {"@type": "Organization", "name": site["title"]},
        "isAccessibleForFree": True,
        "dateModified": data.get("as_of") or str(date.today()),
    }
    render(
        "home.html",
        "index.html",
        site["title"],
        site["description"].strip(),
        json_ld=json.dumps(dataset),
    )
    by_ticker: dict[str, list] = {}
    for p in data["promises"]:
        by_ticker.setdefault(p["ticker"], []).append(p)
        render(
            "promise.html",
            f"promises/{p['id']}.html",
            f"{p['company']}: {p['metric'] or p['claim_type'].replace('_', ' ')}",
            f"{p['status']}. AI promise from {p['company']}'s {p['form']} filed "
            f"{p['first_stated']}, with sources.",
            p=p,
        )
    for c in data["companies"]:
        render(
            "company.html",
            f"companies/{c['ticker'].lower()}.html",
            f"{c['name']} AI promises scorecard",
            f"{c['promises']} AI promises from {c['name']}'s SEC filings and what later "
            "filings report.",
            company=c,
            items=by_ticker.get(c["ticker"], []),
        )
    render(
        "methodology.html",
        "methodology.html",
        "Methodology",
        "How AIPayback finds, checks and explains AI promises in SEC filings.",
        evals=eval_rows(evals_dir),
    )
    render("pricing.html", "pricing.html", "Pricing", "Free scorecards; Pro alerts and reports.")
    render("about.html", "about.html", "About", "Who builds AIPayback.")
    urls = "".join(f"<url><loc>{site['site_url']}/{p}</loc></url>" for p in pages)
    (out / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>\n',
        encoding="utf-8",
        newline="\n",
    )
    (out / "robots.txt").write_text(
        f"User-agent: *\nAllow: /\nSitemap: {site['site_url']}/sitemap.xml\n",
        encoding="utf-8",
        newline="\n",
    )
    (out / ".nojekyll").write_text("", encoding="utf-8")
    return {
        "pages": len(pages),
        "promises": len(data["promises"]),
        "companies": len(data["companies"]),
    }
