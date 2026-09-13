from __future__ import annotations

import pytest

from pitchvalue.config.settings import ConfigurationError
from pitchvalue.prediction.contracts import MarketFamily
from pitchvalue.providers.contracts import CapabilityAvailability
from pitchvalue.providers.five_dfa.capabilities import (
    FREE_CAPABILITIES,
    FREE_COMPETITION_COVERAGE,
    CompetitionCoverageState,
)
from pitchvalue.providers.five_dfa.config import load_five_dfa_config


def test_free_capability_profile_is_deliberately_bounded() -> None:
    profile = FREE_CAPABILITIES
    assert profile.plan_name == "FREE"
    assert profile.supported_competitions == frozenset(
        {"Premier League", "Ligue 1", "Bundesliga", "La Liga"}
    )
    assert profile.fixtures_available and profile.results_available and profile.stats_available
    assert profile.odds_available
    assert not profile.lineups_available
    assert not profile.injuries_available
    assert not profile.odds_history_available
    assert not profile.market_stability_available
    assert not profile.batch_odds_available
    assert profile.exact_timestamp_available is CapabilityAvailability.UNKNOWN
    assert profile.supported_bookmakers == frozenset({"BET365"})
    assert profile.supported_markets == frozenset(
        {MarketFamily.MATCH_RESULT, MarketFamily.TOTAL_GOALS, MarketFamily.BTTS}
    )
    assert (profile.requests_per_window, profile.request_window_seconds) == (60, 3600)
    assert profile.burst_per_minute == 20


@pytest.mark.parametrize(
    "competition",
    [
        "Süper Lig",
        "Primeira Liga",
        "Scottish Premiership",
        "UEFA Champions League",
        "UEFA Europa League",
        "UEFA Conference League",
    ],
)
def test_unsupported_pitchvalue_competitions_are_absent(competition: str) -> None:
    assert competition not in FREE_CAPABILITIES.supported_competitions


def test_provider_config_is_optional_until_loaded_and_redacts_key() -> None:
    config = load_five_dfa_config({"FIVEDFA_API_KEY": "fake-test-key", "FIVEDFA_PLAN": "FREE"})
    assert config.base_url == "https://api.5dollarfootballapi.com/v1"
    assert "fake-test-key" not in repr(config)
    with pytest.raises(ConfigurationError, match="FREE"):
        load_five_dfa_config({"FIVEDFA_API_KEY": "fake", "FIVEDFA_PLAN": "PRO"})


def test_missing_provider_key_fails_only_when_provider_config_is_requested() -> None:
    with pytest.raises(ConfigurationError, match="FIVEDFA_API_KEY"):
        load_five_dfa_config({})


def test_free_competition_coverage_register_is_complete_and_evidence_bounded() -> None:
    coverage = {item.competition: item for item in FREE_COMPETITION_COVERAGE}
    assert len(coverage) == 10
    assert {
        name for name, item in coverage.items() if item.state is CompetitionCoverageState.AVAILABLE
    } == {"Premier League", "Ligue 1", "Bundesliga", "La Liga"}
    assert all(
        item.state is CompetitionCoverageState.NOT_YET_VERIFIED
        for name, item in coverage.items()
        if name not in FREE_CAPABILITIES.supported_competitions
    )
    assert "Serie A" not in coverage
