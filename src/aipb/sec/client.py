"""Polite, cached HTTP client for SEC EDGAR.

SEC fair-access rules (https://www.sec.gov/os/accessing-edgar-data): at most 10 requests
per second, and a descriptive User-Agent with a contact email. We stay at 8 per second,
back off on 429/5xx, and never download the same immutable file twice.

Two kinds of cache:
- Filing documents never change once filed, so they are cached forever.
- Listings (submissions, company facts, the ticker file) change as companies file, so they
  are cached with a maximum age and refreshed after that.

In offline mode (CI, AIPAYBACK_OFFLINE=true) a cache miss raises instead of calling the SEC.
"""

from __future__ import annotations

import contextlib
import json
import os
import random
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import httpx2

DEFAULT_RATE_PER_SEC = 8.0
RETRY_STATUSES = {429, 500, 502, 503, 504}
APP_NAME = "AIPayback/0.1"


class SecError(RuntimeError):
    """Base class for SEC access problems."""


class SecOffline(SecError):
    """Offline mode is on and the file is not in the local cache."""


class SecNotFound(SecError):
    """The SEC returned 404 for a URL."""


class MissingContactEmail(SecError):
    """SEC requires a contact email in the User-Agent."""


@dataclass
class RateLimiter:
    """Token bucket. `rate` requests per second, bursts of at most `burst`."""

    rate: float = DEFAULT_RATE_PER_SEC
    burst: float = 1.0
    clock: Callable[[], float] = time.monotonic
    sleep: Callable[[float], None] = time.sleep
    _tokens: float = field(default=-1.0, repr=False)
    _last: float = field(default=0.0, repr=False)

    def acquire(self) -> None:
        now = self.clock()
        if self._tokens < 0:  # first call
            self._tokens = self.burst
            self._last = now
        self._tokens = min(self.burst, self._tokens + (now - self._last) * self.rate)
        self._last = now
        if self._tokens < 1.0:
            wait = (1.0 - self._tokens) / self.rate
            self.sleep(wait)
            self._last = self.clock()
            self._tokens = 1.0
        self._tokens -= 1.0


def user_agent(contact_email: str | None) -> str:
    if not contact_email or "@" not in contact_email:
        raise MissingContactEmail(
            "SEC_CONTACT_EMAIL is not set in .env. The SEC requires a contact email in every "
            "request's User-Agent (use the shared project Gmail)."
        )
    return f"{APP_NAME} ({contact_email.strip()})"


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".tmp{os.getpid()}")
    tmp.write_bytes(data)
    tmp.replace(path)


@dataclass
class FetchStats:
    requests: int = 0
    cache_hits: int = 0
    retries: int = 0
    bytes_downloaded: int = 0


class SecClient:
    """All SEC traffic goes through here: rate limit, retries, disk cache, offline guard."""

    def __init__(
        self,
        contact_email: str | None,
        *,
        offline: bool = False,
        rate: float = DEFAULT_RATE_PER_SEC,
        max_retries: int = 5,
        timeout: float = 60.0,
        transport: httpx2.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.offline = offline
        self.max_retries = max_retries
        self._sleep = sleep
        self._clock = clock
        self.stats = FetchStats()
        self.limiter = RateLimiter(rate=rate, clock=clock, sleep=sleep)
        self._contact_email = contact_email
        self._transport = transport
        self._timeout = timeout
        self._http: httpx2.Client | None = None

    # The HTTP client is created lazily, so offline runs never need a contact email.
    def _client(self) -> httpx2.Client:
        if self._http is None:
            self._http = httpx2.Client(
                headers={"User-Agent": user_agent(self._contact_email)},
                timeout=self._timeout,
                follow_redirects=True,
                transport=self._transport,
            )
        return self._http

    def close(self) -> None:
        if self._http is not None:
            self._http.close()
            self._http = None

    def __enter__(self) -> SecClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # ------------------------------------------------------------------ network

    def _download(self, url: str) -> bytes:
        if self.offline:
            raise SecOffline(f"Offline mode: not in the local cache: {url}")
        client = self._client()
        attempt = 0
        while True:
            self.limiter.acquire()
            self.stats.requests += 1
            try:
                resp = client.get(url)
            except httpx2.TransportError as exc:
                if attempt >= self.max_retries:
                    raise SecError(
                        f"Network error after {attempt + 1} tries: {url}: {exc}"
                    ) from exc
                self._backoff(attempt, None)
                attempt += 1
                continue
            if resp.status_code == 404:
                raise SecNotFound(f"404 Not Found: {url}")
            if resp.status_code in RETRY_STATUSES:
                if attempt >= self.max_retries:
                    raise SecError(f"HTTP {resp.status_code} after {attempt + 1} tries: {url}")
                self._backoff(attempt, resp.headers.get("Retry-After"))
                attempt += 1
                continue
            if resp.status_code >= 400:
                raise SecError(f"HTTP {resp.status_code}: {url}")
            data = resp.content
            self.stats.bytes_downloaded += len(data)
            return data

    def _backoff(self, attempt: int, retry_after: str | None) -> None:
        self.stats.retries += 1
        delay = min(60.0, 2.0**attempt) + random.uniform(0, 0.5)
        if retry_after:
            with contextlib.suppress(ValueError):
                delay = max(delay, float(retry_after))
        self._sleep(delay)

    # ------------------------------------------------------------------ cached access

    def get_bytes(self, url: str, cache_path: Path, *, max_age_s: float | None = None) -> bytes:
        """Return the file at `url`, from `cache_path` when it is there and fresh enough.

        max_age_s=None means the file never changes (filing documents): cache forever.
        """
        if cache_path.exists():
            age = time.time() - cache_path.stat().st_mtime
            if max_age_s is None or age <= max_age_s or self.offline:
                self.stats.cache_hits += 1
                return cache_path.read_bytes()
        data = self._download(url)
        _atomic_write(cache_path, data)
        return data

    def get_json(self, url: str, cache_path: Path, *, max_age_s: float | None = None) -> dict:
        raw = self.get_bytes(url, cache_path, max_age_s=max_age_s)
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            cache_path.unlink(missing_ok=True)  # never keep a corrupt cache entry
            raise SecError(f"Invalid JSON from {url}") from exc
