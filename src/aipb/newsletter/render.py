"""Tiny Markdown -> HTML for local previews (headings, bullets, bold, links). Escapes first."""

from __future__ import annotations

import html
import re


def to_html(markdown: str, title: str) -> str:
    out = [
        f"<!doctype html><meta charset='utf-8'><title>{html.escape(title)}</title>",
        "<body style='font:16px/1.6 system-ui;max-width:680px;margin:24px auto;padding:0 16px'>",
        f"<h1>{html.escape(title)}</h1>",
    ]
    in_list = False
    for raw in markdown.splitlines():
        line = html.escape(raw)
        line = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", line)
        line = re.sub(r"\[(.+?)\]\((https?://[^)\s]+)\)", r"<a href='\2'>\1</a>", line)
        if line.startswith("- "):
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{line[2:]}</li>")
            continue
        if in_list:
            out.append("</ul>")
            in_list = False
        if line.startswith("## "):
            out.append(f"<h2>{line[3:]}</h2>")
        elif line == "---":
            out.append("<hr>")
        elif line.strip():
            out.append(f"<p>{line}</p>")
    if in_list:
        out.append("</ul>")
    return "\n".join(out) + "\n</body>\n"
