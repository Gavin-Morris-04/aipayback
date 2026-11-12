"""Wires settings, budget, cache and LLM client together for the CLI and the stages."""

from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property

import yaml

from aipb.budget.estimator import Estimator
from aipb.budget.guard import BudgetConfig, BudgetGuard
from aipb.budget.ledger import Ledger
from aipb.budget.pricing import PricingTable
from aipb.llm.cache import OutputCache
from aipb.llm.client import LLMClient, SdkFactory, default_sdk_factory
from aipb.paths import Paths
from aipb.sec.client import SecClient
from aipb.sec.manifest import Manifest
from aipb.settings import Settings
from aipb.stages.ai_products import AIProducts
from aipb.stages.prefilter import Lexicon


@dataclass
class AppContext:
    paths: Paths
    settings: Settings
    sdk_factory: SdkFactory = default_sdk_factory

    @classmethod
    def create(cls, paths: Paths | None = None, sdk_factory: SdkFactory | None = None):
        paths = paths or Paths.default()
        settings = Settings.load(paths.dotenv)
        return cls(paths=paths, settings=settings, sdk_factory=sdk_factory or default_sdk_factory)

    @cached_property
    def pricing(self) -> PricingTable:
        return PricingTable.load(self.paths.pricing_config)

    @cached_property
    def ledger(self) -> Ledger:
        return Ledger(self.paths.ledger_dir)

    @cached_property
    def guard(self) -> BudgetGuard:
        return BudgetGuard(
            BudgetConfig.load(self.paths.budget_config),
            self.ledger,
            self.pricing,
            device=self.settings.aipayback_device,
            repo_dir=self.paths.root,
        )

    @cached_property
    def estimator(self) -> Estimator:
        return Estimator.load(self.paths.stages_config)

    @cached_property
    def stages(self) -> dict:
        raw = yaml.safe_load(self.paths.stages_config.read_text(encoding="utf-8")) or {}
        return raw.get("stages", {})

    @cached_property
    def cache(self) -> OutputCache:
        return OutputCache(self.paths.outputs_dir)

    @cached_property
    def sec(self) -> SecClient:
        """SEC EDGAR client. Offline mode never touches the network (cache only)."""
        return SecClient(self.settings.sec_contact_email, offline=self.settings.aipayback_offline)

    @cached_property
    def manifest(self) -> Manifest:
        return Manifest(self.paths.filings_manifest)

    @cached_property
    def lexicon(self) -> Lexicon:
        return Lexicon.load(self.paths.keywords_config)

    @cached_property
    def ai_products(self) -> AIProducts:
        return AIProducts.load(self.paths.ai_products_config)

    @cached_property
    def llm(self) -> LLMClient:
        return LLMClient(
            guard=self.guard,
            cache=self.cache,
            estimator=self.estimator,
            api_key=self.settings.api_key(),
            offline=self.settings.aipayback_offline,
            device=self.settings.aipayback_device,
            sdk_factory=self.sdk_factory,
        )
