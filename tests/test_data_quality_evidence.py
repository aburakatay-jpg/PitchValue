from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime

import pytest

from pitchvalue.quality import (
    DataQualityEvaluation,
    EvidenceAvailability,
    EvidenceFamily,
    EvidenceProfile,
    QualityEvidence,
)


def _item(
    family: EvidenceFamily,
    availability: EvidenceAvailability = EvidenceAvailability.AVAILABLE,
) -> QualityEvidence:
    return QualityEvidence(
        family,
        availability,
        availability is EvidenceAvailability.HARD_FAIL,
        () if availability is EvidenceAvailability.AVAILABLE else ("EVIDENCE_MISSING",),
        {"source": "canonical_history"},
        datetime(2026, 9, 12, tzinfo=UTC),
    )


def _evaluation() -> DataQualityEvaluation:
    at = datetime(2026, 9, 12, tzinfo=UTC)
    profile = EvidenceProfile.HISTORICAL_RECONSTRUCTED
    version = "dq_evidence_v1"
    evidence = (
        _item(EvidenceFamily.HISTORICAL_DEPTH),
        _item(EvidenceFamily.MATCH_STATISTICS_COMPLETENESS),
        _item(EvidenceFamily.CURRENT_SEASON_FRESHNESS, EvidenceAvailability.UNAVAILABLE),
        _item(EvidenceFamily.FIXTURE_INTEGRITY),
        _item(EvidenceFamily.ENTITY_MAPPING_INTEGRITY),
        _item(EvidenceFamily.SOURCE_PROVIDER_HEALTH, EvidenceAvailability.UNAVAILABLE),
    )
    return DataQualityEvaluation(
        DataQualityEvaluation.deterministic_id(1, at, profile, version),
        1,
        None,
        at,
        profile,
        version,
        evidence,
    )


def test_historical_reconstructed_is_distinct_and_score_remains_null() -> None:
    evaluation = _evaluation()
    assert evaluation.profile is EvidenceProfile.HISTORICAL_RECONSTRUCTED
    assert evaluation.quality_score is None
    assert not evaluation.hard_failed
    with pytest.raises(FrozenInstanceError):
        evaluation.quality_score = None  # type: ignore[misc]


def test_historical_profile_cannot_claim_live_freshness_or_provider_health() -> None:
    evidence = list(_evaluation().evidence)
    evidence[2] = _item(EvidenceFamily.CURRENT_SEASON_FRESHNESS)
    with pytest.raises(ValueError, match="cannot claim live evidence"):
        replace(_evaluation(), evidence=tuple(evidence))


def test_unavailable_is_not_zero_and_requires_reason() -> None:
    item = _item(EvidenceFamily.SOURCE_PROVIDER_HEALTH, EvidenceAvailability.UNAVAILABLE)
    assert item.availability is EvidenceAvailability.UNAVAILABLE
    with pytest.raises(ValueError, match="requires a reason"):
        replace(item, reason_codes=())


def test_hard_failure_is_independent_of_future_numeric_score() -> None:
    failure = _item(EvidenceFamily.FIXTURE_INTEGRITY, EvidenceAvailability.HARD_FAIL)
    evaluation = replace(
        _evaluation(),
        evidence=tuple(
            failure if item.family is EvidenceFamily.FIXTURE_INTEGRITY else item
            for item in _evaluation().evidence
        ),
    )
    assert evaluation.hard_failed
    assert evaluation.quality_score is None


def test_duplicate_evidence_family_and_naive_time_are_rejected() -> None:
    with pytest.raises(ValueError, match="unique"):
        replace(_evaluation(), evidence=(_evaluation().evidence[0],) * 2)
    with pytest.raises(ValueError, match="timezone-aware"):
        replace(_evaluation(), evaluated_at=datetime(2026, 9, 12))
