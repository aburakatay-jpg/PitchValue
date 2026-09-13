"""Truthful 5DFA Free-plan capabilities; no paid-plan feature is implied."""

from dataclasses import dataclass
from enum import StrEnum

from pitchvalue.prediction.contracts import MarketFamily
from pitchvalue.providers.contracts import CapabilityAvailability, ProviderCapabilityProfile

PROVIDER_NAME = "5DollarFootballAPI"
FREE_PLAN = "FREE"
CAPABILITY_VERSION = "five_dfa_free_capabilities_v1"

SUPPORTED_COMPETITIONS = frozenset({"Premier League", "Ligue 1", "Bundesliga", "La Liga"})


class CompetitionCoverageState(StrEnum):
    AVAILABLE = "AVAILABLE"
    NOT_CURRENTLY_AVAILABLE = "NOT_CURRENTLY_AVAILABLE"
    NOT_YET_VERIFIED = "NOT_YET_VERIFIED"


@dataclass(frozen=True)
class CompetitionCoverage:
    competition: str
    state: CompetitionCoverageState
    evidence: str


_CANONICAL_COMPETITIONS = (
    "Premier League",
    "Ligue 1",
    "Bundesliga",
    "Süper Lig",
    "Primeira Liga",
    "La Liga",
    "Scottish Premiership",
    "UEFA Champions League",
    "UEFA Europa League",
    "UEFA Conference League",
)

FREE_COMPETITION_COVERAGE = tuple(
    CompetitionCoverage(
        competition,
        (
            CompetitionCoverageState.AVAILABLE
            if competition in SUPPORTED_COMPETITIONS
            else CompetitionCoverageState.NOT_YET_VERIFIED
        ),
        (
            "authenticated_free_runtime_evidence_2026_09"
            if competition in SUPPORTED_COMPETITIONS
            else "no_authenticated_free_runtime_evidence"
        ),
    )
    for competition in _CANONICAL_COMPETITIONS
)

FREE_CAPABILITIES = ProviderCapabilityProfile(
    provider_name=PROVIDER_NAME,
    plan_name=FREE_PLAN,
    fixtures_available=True,
    results_available=True,
    stats_available=True,
    lineups_available=False,
    injuries_available=False,
    odds_available=True,
    odds_history_available=False,
    exact_timestamp_available=CapabilityAvailability.UNKNOWN,
    market_stability_available=False,
    batch_odds_available=False,
    supported_competitions=SUPPORTED_COMPETITIONS,
    supported_markets=frozenset(
        {MarketFamily.MATCH_RESULT, MarketFamily.TOTAL_GOALS, MarketFamily.BTTS}
    ),
    supported_bookmakers=frozenset({"BET365"}),
    historical_depth="LAST_3_MONTHS",
    requests_per_window=60,
    request_window_seconds=3600,
    burst_per_minute=20,
    capability_version=CAPABILITY_VERSION,
)
