"""Where things live on disk. AIPAYBACK_ROOT overrides the repo root (used by tests)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def repo_root() -> Path:
    override = os.environ.get("AIPAYBACK_ROOT")
    if override:
        return Path(override).resolve()
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").is_file() and (parent / "config").is_dir():
            return parent
    return Path.cwd().resolve()


@dataclass(frozen=True)
class Paths:
    root: Path

    @classmethod
    def default(cls) -> Paths:
        return cls(repo_root())

    @property
    def config(self) -> Path:
        return self.root / "config"

    @property
    def budget_config(self) -> Path:
        return self.config / "budget.yaml"

    @property
    def pricing_config(self) -> Path:
        return self.config / "pricing.yaml"

    @property
    def stages_config(self) -> Path:
        return self.config / "stages.yaml"

    @property
    def data(self) -> Path:
        return self.root / "data"

    @property
    def ledger_dir(self) -> Path:
        return self.data / "ledger"

    @property
    def outputs_dir(self) -> Path:
        return self.data / "outputs"

    @property
    def database(self) -> Path:
        return self.data / "aipb.sqlite"

    @property
    def dotenv(self) -> Path:
        return self.root / ".env"
