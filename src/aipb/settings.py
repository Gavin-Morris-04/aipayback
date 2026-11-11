"""Settings from .env. The app's key is AIPAYBACK_API_KEY, never ANTHROPIC_API_KEY.

Why: Claude Code bills ANTHROPIC_API_KEY instead of the Claude subscription whenever that
variable is set in the shell. Keeping the app's key under a different name means the $19
of API credit is only ever spent by this app, through the budget guard.

pydantic-settings reads .env into this object without exporting anything to os.environ.
"""

from __future__ import annotations

import hashlib
import os
import platform
import re
from collections.abc import Mapping
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_device() -> str:
    digest = hashlib.sha256(platform.node().encode("utf-8")).hexdigest()[:6]
    return f"dev-{digest}"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file_encoding="utf-8", extra="ignore")

    aipayback_api_key: SecretStr | None = None
    sec_contact_email: str | None = None
    aipayback_offline: bool = False
    aipayback_device: str = Field(default_factory=_default_device)
    # Phase 4 services. In GitHub Actions these come from secrets and repo variables.
    buttondown_api_key: SecretStr | None = None
    founder_emails: str = ""
    newsletter_autosend: bool = False
    github_token: SecretStr | None = None
    github_repository: str | None = None

    def founders(self) -> list[str]:
        return [e.strip() for e in self.founder_emails.split(",") if e.strip()]

    @staticmethod
    def secret(value: SecretStr | None) -> str | None:
        return value.get_secret_value().strip() or None if value is not None else None

    @classmethod
    def load(cls, dotenv: Path) -> Settings:
        return cls(_env_file=dotenv if dotenv.exists() else None)  # type: ignore[call-arg]

    def api_key(self) -> str | None:
        if self.aipayback_api_key is None:
            return None
        value = self.aipayback_api_key.get_secret_value().strip()
        return value or None


_DOTENV_ANTHROPIC = re.compile(r"^\s*(export\s+)?ANTHROPIC_API_KEY\s*=", re.MULTILINE)


def anthropic_key_warnings(
    env: Mapping[str, str] | None = None, dotenv: Path | None = None
) -> list[str]:
    """Problems that would make Claude Code (or this app) bill the wrong account."""
    env = os.environ if env is None else env
    warnings: list[str] = []
    if env.get("ANTHROPIC_API_KEY"):
        warnings.append(
            "ANTHROPIC_API_KEY is set in this shell. Claude Code will bill that API key "
            "instead of your Claude subscription. Unset it; the app uses AIPAYBACK_API_KEY."
        )
    dotenv_text = (
        dotenv.read_text(encoding="utf-8", errors="ignore")
        if dotenv is not None and dotenv.exists()
        else ""
    )
    if _DOTENV_ANTHROPIC.search(dotenv_text):
        warnings.append(
            ".env contains ANTHROPIC_API_KEY. Rename it to AIPAYBACK_API_KEY so it can "
            "never be picked up by Claude Code or the SDK's defaults."
        )
    return warnings
