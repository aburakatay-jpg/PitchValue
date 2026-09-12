"""Capability-driven degradation and non-public shadow plumbing."""

from __future__ import annotations

from dataclasses import dataclass

from pitchvalue.prediction.contracts import MarketFamily
from pitchvalue.providers.contracts import CapabilityDecision, CapabilityOutcome
from pitchvalue.providers.five_dfa.capabilities import FREE_CAPABILITIES
from pitchvalue.providers.five_dfa.fixtures import ProviderFixture
from pitchvalue.providers.five_dfa.odds import OddsNormalizationResult


def capability_decisions(
    *, competition: str, market: MarketFamily, stats_present: bool, odds_present: bool
) -> tuple[CapabilityDecision, ...]:
    decisions: list[CapabilityDecision] = []
    if competition not in FREE_CAPABILITIES.supported_competitions:
        decisions.append(
            CapabilityDecision(
                "competition",
                CapabilityOutcome.EXCLUDED,
                "UNSUPPORTED_COMPETITION",
                "MATCH",
            )
        )
    if market not in FREE_CAPABILITIES.supported_markets:
        decisions.append(
            CapabilityDecision(
                "market_family",
                CapabilityOutcome.UNAVAILABLE,
                "UNSUPPORTED_MARKET",
                "MARKET_FAMILY",
            )
        )
    decisions.extend(
        (
            _availability("statistics", stats_present, "STATISTICS_UNAVAILABLE"),
            _availability("market_probability_edge", odds_present, "ODDS_UNAVAILABLE"),
            CapabilityDecision(
                "market_stability",
                CapabilityOutcome.UNAVAILABLE,
                "ODDS_HISTORY_UNAVAILABLE",
                "MARKET_FAMILY",
            ),
            CapabilityDecision(
                "final_check",
                CapabilityOutcome.UNAVAILABLE,
                "LINEUPS_UNAVAILABLE",
                "MATCH",
            ),
            CapabilityDecision(
                "injury_evidence",
                CapabilityOutcome.UNAVAILABLE,
                "INJURIES_UNAVAILABLE",
                "MATCH",
            ),
        )
    )
    return tuple(decisions)


def _availability(component: str, available: bool, reason: str) -> CapabilityDecision:
    if available:
        return CapabilityDecision(component, CapabilityOutcome.AVAILABLE)
    return CapabilityDecision(component, CapabilityOutcome.UNAVAILABLE, reason)


@dataclass(frozen=True)
class ProviderShadowInput:
    fixture: ProviderFixture
    odds: OddsNormalizationResult | None
    publication_eligible: bool = False
    publication_blocker: str = "MODEL_READINESS_GATE_PENDING"

    def __post_init__(self) -> None:
        if self.publication_eligible:
            raise ValueError("5DFA Free shadow input cannot be publication eligible")
