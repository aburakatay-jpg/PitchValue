"""Provider-neutral capability contracts used at external-data boundaries."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from pitchvalue.prediction.contracts import MarketFamily


class CapabilityAvailability(StrEnum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    UNKNOWN = "UNKNOWN"


class CapabilityOutcome(StrEnum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    EXCLUDED = "EXCLUDED"
    QUARANTINED = "QUARANTINED"


@dataclass(frozen=True)
class ProviderCapabilityProfile:
    provider_name: str
    plan_name: str
    fixtures_available: bool
    results_available: bool
    stats_available: bool
    lineups_available: bool
    injuries_available: bool
    odds_available: bool
    odds_history_available: bool
    exact_timestamp_available: CapabilityAvailability
    market_stability_available: bool
    batch_odds_available: bool
    supported_competitions: frozenset[str]
    supported_markets: frozenset[MarketFamily]
    supported_bookmakers: frozenset[str]
    historical_depth: str
    requests_per_window: int
    request_window_seconds: int
    burst_per_minute: int | None
    capability_version: str

    def __post_init__(self) -> None:
        for name in ("provider_name", "plan_name", "historical_depth", "capability_version"):
            if not getattr(self, name).strip():
                raise ValueError(f"{name} must be nonblank")
        if self.requests_per_window <= 0 or self.request_window_seconds <= 0:
            raise ValueError("request limit metadata must be positive")
        if self.burst_per_minute is not None and self.burst_per_minute <= 0:
            raise ValueError("burst_per_minute must be positive")


@dataclass(frozen=True)
class CapabilityDecision:
    component: str
    outcome: CapabilityOutcome
    reason_code: str | None = None
    quarantine_scope: str | None = None

    def __post_init__(self) -> None:
        if not self.component.strip():
            raise ValueError("component must be nonblank")
        if self.outcome is not CapabilityOutcome.AVAILABLE and not self.reason_code:
            raise ValueError("unavailable outcomes require a reason_code")
