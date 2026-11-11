"""Findings rendering: capex promises are reported apart from payoff promises (rubric Q3)."""

from aipb import findings


def test_capex_promises_get_their_own_table():
    f = {
        "generated": "2026-11-11T00:00:00+00:00",
        "as_of": "2026-11-01",
        "companies": 10,
        "statements": {"promise": 3, "hype": 5},
        "kinds_by_sector": {"Information Technology": {"promise": 3, "hype": 5}},
        "promises": 3,
        "published": 2,
        "status_by_claim_type": {
            "cost_savings": {"Delivered": 1},
            "capex_investment": {"On track": 1, findings.PENDING: 1},
        },
        "status_by_sector": {},
    }
    text = findings.render(f)
    results, spending = text.split("**Promises about spending on AI**")
    assert "| cost savings | 1 |" in results and "capex investment" not in results
    assert "| capex investment | 2 | 0 | 1 |" in spending
    no_capex = {**f, "status_by_claim_type": {"cost_savings": {"Delivered": 1}}}
    assert "spending on AI" not in findings.render(no_capex)
