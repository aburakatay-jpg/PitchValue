"""Provider-neutral, immutable data-quality evidence contracts."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType


class EvidenceProfile(StrEnum):
    HISTORICAL_RECONSTRUCTED = "HISTORICAL_RECONSTRUCTED"
    LIVE_OPERATIONAL = "LIVE_OPERATIONAL"


class EvidenceFamily(StrEnum):
    HISTORICAL_DEPTH = "HISTORICAL_DEPTH"
    MATCH_STATISTICS_COMPLETENESS = "MATCH_STATISTICS_COMPLETENESS"
    CURRENT_SEASON_FRESHNESS = "CURRENT_SEASON_FRESHNESS"
    FIXTURE_INTEGRITY = "FIXTURE_INTEGRITY"
    ENTITY_MAPPING_INTEGRITY = "ENTITY_MAPPING_INTEGRITY"
    SOURCE_PROVIDER_HEALTH = "SOURCE_PROVIDER_HEALTH"


class EvidenceAvailability(StrEnum):
    AVAILABLE = "AVAILABLE"
    PARTIAL = "PARTIAL"
    UNAVAILABLE = "UNAVAILABLE"
    HARD_FAIL = "HARD_FAIL"


def _mapping(value: Mapping[str, str]) -> Mapping[str, str]:
    normalized = dict(sorted(value.items()))
    if any(not key.strip() or not item.strip() for key, item in normalized.items()):
        raise ValueError("provenance keys and values must be nonblank")
    return MappingProxyType(normalized)


@dataclass(frozen=True)
class QualityEvidence:
    family: EvidenceFamily
    availability: EvidenceAvailability
    hard_fail: bool
    reason_codes: tuple[str, ...]
    provenance: Mapping[str, str]
    observed_at: datetime | None

    def __post_init__(self) -> None:
        if self.observed_at is not None and (
            self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None
        ):
            raise ValueError("observed_at must be timezone-aware")
        if tuple(sorted(set(self.reason_codes))) != self.reason_codes:
            raise ValueError("reason_codes must be unique and sorted")
        if any(not reason.strip() for reason in self.reason_codes):
            raise ValueError("reason_codes must be nonblank")
        if self.hard_fail != (self.availability is EvidenceAvailability.HARD_FAIL):
            raise ValueError("hard_fail must agree with availability")
        if self.availability is not EvidenceAvailability.AVAILABLE and not self.reason_codes:
            raise ValueError("non-available evidence requires a reason")
        object.__setattr__(self, "provenance", _mapping(self.provenance))


@dataclass(frozen=True)
class DataQualityEvaluation:
    evaluation_id: str
    match_id: int
    run_id: str | None
    evaluated_at: datetime
    profile: EvidenceProfile
    evidence_version: str
    evidence: tuple[QualityEvidence, ...]
    quality_score: None = None

    def __post_init__(self) -> None:
        if not self.evaluation_id.strip() or not self.evidence_version.strip():
            raise ValueError("evaluation identity and version must be nonblank")
        if self.match_id <= 0:
            raise ValueError("match_id must be positive")
        if self.evaluated_at.tzinfo is None or self.evaluated_at.utcoffset() is None:
            raise ValueError("evaluated_at must be timezone-aware")
        families = tuple(item.family for item in self.evidence)
        if not families or len(set(families)) != len(families):
            raise ValueError("evidence families must be nonempty and unique")
        if self.profile is EvidenceProfile.HISTORICAL_RECONSTRUCTED:
            forbidden = {
                EvidenceFamily.CURRENT_SEASON_FRESHNESS,
                EvidenceFamily.SOURCE_PROVIDER_HEALTH,
            }
            if any(
                item.family in forbidden and item.availability is EvidenceAvailability.AVAILABLE
                for item in self.evidence
            ):
                raise ValueError("historical reconstruction cannot claim live evidence")

    @property
    def hard_failed(self) -> bool:
        return any(item.hard_fail for item in self.evidence)

    @staticmethod
    def deterministic_id(
        match_id: int, evaluated_at: datetime, profile: EvidenceProfile, evidence_version: str
    ) -> str:
        payload = json.dumps(
            [match_id, evaluated_at.isoformat(), profile.value, evidence_version],
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode()).hexdigest()
