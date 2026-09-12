from __future__ import annotations

from pathlib import Path


def test_v1_audit_names_every_required_market_and_does_not_claim_readiness() -> None:
    document = (
        Path(__file__).resolve().parents[1] / "docs/v1-market-code-audit.md"
    ).read_text()
    required = (
        "MATCH_RESULT / 1X2",
        "OVER_UNDER_1_5",
        "OVER_UNDER_2_5",
        "BTTS",
        "DOUBLE_CHANCE",
        "HOME_TEAM_GOALS O/U 0.5",
        "HOME_TEAM_GOALS O/U 1.5",
        "AWAY_TEAM_GOALS O/U 0.5",
        "AWAY_TEAM_GOALS O/U 1.5",
    )
    assert all(name in document for name in required)
    assert "Mathematical derivability is not treated as production readiness" in document
    assert "READY |" not in document


def test_recommendation_keeps_double_chance_nonexclusive_and_does_not_implement_markets() -> None:
    document = (
        Path(__file__).resolve().parents[1] / "docs/v1-market-code-audit.md"
    ).read_text()
    assert "overlapping selections are not a mutually exclusive book" in document
    assert "It is not a frozen product roadmap" in document
