"""Market-isolated calibration-confidence research evidence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from pitchvalue.evaluation.metrics.contracts import (
    CalibrationBucket,
    MetricStatus,
    MulticlassCalibrationResult,
)

CALIBRATION_CONFIDENCE_VERSION = "calibration_confidence_research_v1"


class ConfidenceEvidenceStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True)
class CalibrationEvidenceScope:
    market: str
    model_version: str
    competition_id: str | None = None
    window_start: datetime | None = None
    window_end: datetime | None = None

    def __post_init__(self) -> None:
        if not self.market.strip() or not self.model_version.strip():
            raise ValueError("market and model_version must be nonblank")
        if (self.window_start is None) != (self.window_end is None):
            raise ValueError("calibration window boundaries must be supplied together")
        if self.window_start is not None and self.window_end is not None:
            if any(
                item.tzinfo is None or item.utcoffset() is None
                for item in (self.window_start, self.window_end)
            ):
                raise ValueError("calibration window must be timezone-aware")
            if self.window_end <= self.window_start:
                raise ValueError("calibration window must be increasing")


@dataclass(frozen=True)
class CalibrationEvidenceCandidate:
    scope: CalibrationEvidenceScope
    result: MulticlassCalibrationResult


@dataclass(frozen=True)
class CalibrationConfidenceEvidence:
    status: ConfidenceEvidenceStatus
    version: str
    requested_scope: CalibrationEvidenceScope
    selected_scope: CalibrationEvidenceScope | None
    support_count: int
    ece_like: Decimal | None
    reliability_buckets: tuple[CalibrationBucket, ...]
    confidence_score: None
    diagnostics: tuple[str, ...]


def select_calibration_evidence(
    requested_scope: CalibrationEvidenceScope,
    candidates: tuple[CalibrationEvidenceCandidate, ...],
    fallback_hierarchy: tuple[CalibrationEvidenceScope, ...],
) -> CalibrationConfidenceEvidence:
    """Select prior OOS evidence from an explicit hierarchy; never map it to a score."""
    if any(
        scope.market != requested_scope.market
        or scope.model_version != requested_scope.model_version
        for scope in fallback_hierarchy
    ):
        raise ValueError("fallback hierarchy cannot cross market or model version")
    by_scope = {candidate.scope: candidate for candidate in candidates}
    for scope in fallback_hierarchy:
        candidate = by_scope.get(scope)
        if candidate is None or candidate.result.status is not MetricStatus.READY:
            continue
        buckets = tuple(
            bucket
            for class_result in candidate.result.classes
            for bucket in class_result.calibration.buckets
        )
        return CalibrationConfidenceEvidence(
            ConfidenceEvidenceStatus.AVAILABLE,
            CALIBRATION_CONFIDENCE_VERSION,
            requested_scope,
            scope,
            candidate.result.usable_count,
            candidate.result.macro_ece,
            buckets,
            None,
            (),
        )
    return CalibrationConfidenceEvidence(
        ConfidenceEvidenceStatus.UNAVAILABLE,
        CALIBRATION_CONFIDENCE_VERSION,
        requested_scope,
        None,
        0,
        None,
        (),
        None,
        ("INSUFFICIENT_MARKET_SPECIFIC_OOS_EVIDENCE",),
    )
