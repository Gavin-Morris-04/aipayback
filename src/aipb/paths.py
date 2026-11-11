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
    def evidence_map(self) -> Path:
        return self.config / "evidence_map.yaml"

    @property
    def error_reports(self) -> Path:
        return self.data / "error_reports.csv"

    @property
    def prompts_dir(self) -> Path:
        return self.root / "prompts"

    @property
    def evals_dir(self) -> Path:
        return self.root / "evals"

    @property
    def raw_dir(self) -> Path:
        """Git-ignored SEC download cache. `aipb restore` refills it from the manifest."""
        return self.data / "raw" / "sec"

    @property
    def manifests_dir(self) -> Path:
        return self.data / "manifests"

    @property
    def filings_manifest(self) -> Path:
        return self.manifests_dir / "filings.jsonl"

    @property
    def universe_dir(self) -> Path:
        return self.config / "universe"

    @property
    def keywords_config(self) -> Path:
        return self.config / "keywords.yaml"

    @property
    def exports_dir(self) -> Path:
        return self.root / "exports"

    @property
    def gold_dir(self) -> Path:
        return self.root / "evals" / "gold"

    @property
    def dotenv(self) -> Path:
        return self.root / ".env"
