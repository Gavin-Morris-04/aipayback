from decimal import Decimal

from aipb.budget.estimator import Estimator
from aipb.llm.cache import CacheKey, OutputCache, input_hash
from aipb.settings import Settings, anthropic_key_warnings

# ---------------------------------------------------------------------------- cache


def test_input_hash_ignores_key_order():
    a = {"model": "m", "max_tokens": 5, "messages": [{"role": "user", "content": "x"}]}
    b = {"messages": [{"content": "x", "role": "user"}], "max_tokens": 5, "model": "m"}
    assert input_hash(a) == input_hash(b)
    assert input_hash(a) != input_hash({**a, "max_tokens": 6})


def test_cache_persists_across_instances(cache):
    key = CacheKey("h1", "v1", "claude-haiku-5-5")
    cache.put("extract", "0000320193", key, {"content": []}, "call-1")
    reloaded = OutputCache(cache.directory)
    assert reloaded.get("extract", key)["call_id"] == "call-1"
    assert reloaded.get("extract", CacheKey("h1", "v2", "claude-haiku-5-5")) is None
    assert b"\r\n" not in (cache.directory / "extract" / "0000320193.jsonl").read_bytes()


# ---------------------------------------------------------------------------- estimator


def test_estimate_is_conservative_and_includes_max_tokens(pricing):
    est = Estimator()
    text = "word " * 4000  # 20,000 chars ~ 5,000 real tokens
    params = {
        "model": "claude-haiku-5-5",
        "max_tokens": 1000,
        "messages": [{"role": "user", "content": text}],
    }
    tokens = est.input_tokens(params)
    assert tokens > 20_000 / 4  # never below the usual English ratio
    cost = est.worst_case_cost(pricing, params, batch=False)
    floor = (Decimal(tokens) * Decimal("0.10") + 1000 * Decimal("0.50")) / 1_000_000
    assert cost == floor


def test_estimate_prices_cached_prefixes_at_write_rates(pricing):
    est = Estimator()
    base = {
        "model": "claude-haiku-5-5",
        "max_tokens": 10,
        "system": [{"type": "text", "text": "x" * 3000}],
        "messages": [{"role": "user", "content": "hi"}],
    }
    plain = est.worst_case_cost(pricing, base, batch=False)
    cached = {**base, "system": [{**base["system"][0], "cache_control": {"type": "ephemeral"}}]}
    assert est.worst_case_cost(pricing, cached, batch=False) > plain
    assert est.worst_case_cost(pricing, cached, batch=True) < est.worst_case_cost(
        pricing, cached, batch=False
    )


# ---------------------------------------------------------------------------- settings


def test_settings_read_app_key_not_anthropic_key(tmp_path, monkeypatch):
    dotenv = tmp_path / ".env"
    dotenv.write_text("AIPAYBACK_API_KEY=app-key\nSEC_CONTACT_EMAIL=x@example.com\n")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "wrong-key")
    s = Settings.load(dotenv)
    assert s.api_key() == "app-key"
    assert s.sec_contact_email == "x@example.com"


def test_blank_app_key_counts_as_missing(tmp_path):
    dotenv = tmp_path / ".env"
    dotenv.write_text("AIPAYBACK_API_KEY=\n")
    assert Settings.load(dotenv).api_key() is None


def test_warnings(tmp_path):
    assert anthropic_key_warnings(env={}) == []
    assert len(anthropic_key_warnings(env={"ANTHROPIC_API_KEY": "x"})) == 1
    dotenv = tmp_path / ".env"
    dotenv.write_text("ANTHROPIC_API_KEY=oops\n")
    assert len(anthropic_key_warnings(env={}, dotenv=dotenv)) == 1
