"""Block commits that contain API keys or .env files.

Used by the pre-commit hook and by CI (`python scripts/check_secrets.py $(git ls-files)`).
Exit code 1 means a secret-looking value was found; nothing is printed beyond the file,
line and rule, so the secret itself never lands in a log.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

RULES: list[tuple[str, re.Pattern[str]]] = [
    ("Anthropic API key", re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}")),
    ("Stripe live secret key", re.compile(r"\b[sr]k_live_[A-Za-z0-9]{16,}")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}")),
    (
        "Buttondown-style API token assignment",
        re.compile(r"(?i)\bBUTTONDOWN_API_KEY\s*=\s*['\"]?[A-Za-z0-9\-]{20,}"),
    ),
    ("AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    (
        "ANTHROPIC_API_KEY assignment",
        re.compile(r"(?m)^\s*(?:export\s+)?ANTHROPIC_API_KEY\s*=\s*\S+"),
    ),
    (
        "AIPAYBACK_API_KEY with a value",
        re.compile(r"(?m)^\s*(?:export\s+)?AIPAYBACK_API_KEY\s*=\s*['\"]?[A-Za-z0-9]"),
    ),
]


def is_env_file(path: Path) -> bool:
    name = path.name
    return (name == ".env" or name.startswith(".env.")) and name != ".env.example"


def scan(paths: list[str]) -> list[str]:
    problems: list[str] = []
    for raw in paths:
        path = Path(raw)
        if is_env_file(path):
            problems.append(f"{raw}: .env files must never be committed")
            continue
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue  # binary or unreadable: skip
        for lineno, line in enumerate(text.splitlines(), start=1):
            for rule, pattern in RULES:
                if pattern.search(line):
                    problems.append(f"{raw}:{lineno}: looks like a {rule}")
    return problems


def main(argv: list[str]) -> int:
    problems = scan(argv)
    for p in problems:
        print(p)
    if problems:
        print("Commit blocked: remove the secret (keys belong only in .env or GitHub secrets).")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
