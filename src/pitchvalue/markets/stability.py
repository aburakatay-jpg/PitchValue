"""Provider-neutral market stability evidence without score normalization."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from enum import StrEnum

from pitchvalue.markets.odds import raw_implied_probability, validate_decimal_odds
from pitchvalue.prediction.contracts import MarketFamily, Selection

MARKET_STABILITY_VERSION = "market_stability_evidence_v1"


class StabilityStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    HARD_INVALID = "HARD_INVALID"


class ContinuityState(StrEnum):
    CONTINUOUS = "CONTINUOUS"
    GAPPED = "GAPPED"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True)
class StabilityObservation:
    match_id: str
    bookmaker: str
    market: MarketFamily
    selection: Selection
    line: Decimal | None
    normalization_version: str
    decimal_odds: Decimal
    observed_at: datetime
    market_family_complete: bool

    def __post_init__(self) -> None:
        for name in ("match_id", "bookmaker", "normalization_version"):
            if not getattr(self, name).strip():
                raise ValueError(f"{name} must be nonblank")
        validate_decimal_odds(self.decimal_odds)
        if self.line is not None and (
            not isinstance(self.line, Decimal) or not self.line.is_finite()
        ):
            raise ValueError("line must be a finite Decimal")
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("observed_at must be timezone-aware")


@dataclass(frozen=True)
class MarketStabilityEvidence:
    status: StabilityStatus
    version: str
    observation_count: int
    first_observed_at: datetime | None
    last_observed_at: datetime | None
    absolute_implied_probability_movement: Decimal | None
    maximum_single_step_movement: Decimal | None
    directional_reversal_count: int | None
    maximum_observation_gap: timedelta | None
    market_family_complete: bool
    continuity: ContinuityState
    freshness: timedelta | None
    diagnostics: tuple[str, ...]


def calculate_market_stability(
    observations: tuple[StabilityObservation, ...],
    *,
    as_of: datetime,
    maximum_expected_gap: timedelta,
) -> MarketStabilityEvidence:
    """Calculate evidence for one exact semantic series; never produce a score."""
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError("as_of must be timezone-aware")
    if maximum_expected_gap <= timedelta(0):
        raise ValueError("maximum_expected_gap must be positive")
    if not observations:
        return _unavailable("NO_OBSERVATIONS")
    ordered = tuple(sorted(observations, key=lambda item: item.observed_at))
    identity = _identity(ordered[0])
    if any(_identity(item) != identity for item in ordered[1:]):
        return _invalid(ordered, "INCOMPARABLE_SERIES")
    if len({item.observed_at for item in ordered}) != len(ordered):
        return _invalid(ordered, "CONFLICTING_OBSERVATION_TIME")
    if any(not item.market_family_complete for item in ordered):
        return _invalid(ordered, "MARKET_FAMILY_INCOMPLETE")
    if ordered[-1].observed_at > as_of:
        return _invalid(ordered, "FUTURE_OBSERVATION")
    freshness = as_of - ordered[-1].observed_at
    if len(ordered) == 1:
        return MarketStabilityEvidence(
            StabilityStatus.UNAVAILABLE,
            MARKET_STABILITY_VERSION,
            1,
            ordered[0].observed_at,
            ordered[0].observed_at,
            None,
            None,
            None,
            None,
            True,
            ContinuityState.UNAVAILABLE,
            freshness,
            ("ONE_OBSERVATION_CANNOT_ESTABLISH_STABILITY",),
        )
    probabilities = tuple(raw_implied_probability(item.decimal_odds) for item in ordered)
    movements = tuple(
        current - previous
        for previous, current in zip(probabilities, probabilities[1:], strict=False)
    )
    gaps = tuple(
        current.observed_at - previous.observed_at
        for previous, current in zip(ordered, ordered[1:], strict=False)
    )
    signs = tuple(1 if value > 0 else -1 if value < 0 else 0 for value in movements)
    directional = tuple(value for value in signs if value)
    reversals = sum(a != b for a, b in zip(directional, directional[1:], strict=False))
    largest_gap = max(gaps)
    return MarketStabilityEvidence(
        StabilityStatus.AVAILABLE,
        MARKET_STABILITY_VERSION,
        len(ordered),
        ordered[0].observed_at,
        ordered[-1].observed_at,
        abs(probabilities[-1] - probabilities[0]),
        max(abs(value) for value in movements),
        reversals,
        largest_gap,
        True,
        (
            ContinuityState.GAPPED
            if largest_gap > maximum_expected_gap
            else ContinuityState.CONTINUOUS
        ),
        freshness,
        (),
    )


def _identity(observation: StabilityObservation) -> tuple[object, ...]:
    return (
        observation.match_id,
        observation.bookmaker,
        observation.market,
        observation.selection,
        observation.line,
        observation.normalization_version,
    )


def _unavailable(reason: str) -> MarketStabilityEvidence:
    return MarketStabilityEvidence(
        StabilityStatus.UNAVAILABLE,
        MARKET_STABILITY_VERSION,
        0,
        None,
        None,
        None,
        None,
        None,
        None,
        False,
        ContinuityState.UNAVAILABLE,
        None,
        (reason,),
    )


def _invalid(
    observations: tuple[StabilityObservation, ...], reason: str
) -> MarketStabilityEvidence:
    return MarketStabilityEvidence(
        StabilityStatus.HARD_INVALID,
        MARKET_STABILITY_VERSION,
        len(observations),
        observations[0].observed_at,
        observations[-1].observed_at,
        None,
        None,
        None,
        None,
        all(item.market_family_complete for item in observations),
        ContinuityState.UNAVAILABLE,
        None,
        (reason,),
    )
