from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from pitchvalue.shadow import ShadowValidationRecord

D = Decimal


def _record() -> ShadowValidationRecord:
    return ShadowValidationRecord(
        run_id="run-1",
        match_id=1,
        prediction_as_of=datetime(2026, 9, 12, 8, tzinfo=UTC),
        generated_at=datetime(2026, 9, 12, 8, 1, tzinfo=UTC),
        model_version="raw_ml_v1",
        feature_profile="FOOTBALL_PERFORMANCE_ONLY",
        market_family="MATCH_RESULT",
        selection="HOME",
        model_probability=D("0.50"),
        bookmaker=None,
        decimal_odds=None,
        market_observed_at=None,
        no_vig_market_probability=None,
        edge=None,
        dq_evidence_reference=None,
        dq_status="UNAVAILABLE",
        market_stability_reference=None,
        market_stability_status="UNAVAILABLE",
        calibration_confidence_reference=None,
        calibration_confidence_status="UNAVAILABLE",
        agreement=D("0.75"),
        policy_decision="NO_BET",
        publication_eligible=False,
        public_disabled_reason="MODEL_READINESS_GATE_PENDING",
        closing_reference=None,
        result=None,
        settlement_status=None,
    )


def test_shadow_contract_is_deterministic_immutable_and_provider_optional() -> None:
    record = _record()
    assert record.bookmaker is None
    assert record.market_observed_at is None
    assert record.to_dict()["model_probability"] == "0.50"
    with pytest.raises(FrozenInstanceError):
        record.run_id = "changed"  # type: ignore[misc]


def test_shadow_contract_never_synthesizes_market_timestamp_or_publication() -> None:
    record = _record()
    assert record.market_observed_at is None
    with pytest.raises(ValueError, match="cannot be publication eligible"):
        replace(record, publication_eligible=True)


def test_shadow_contract_requires_explicit_public_disabled_reason() -> None:
    with pytest.raises(ValueError, match="public-disabled reason"):
        replace(_record(), public_disabled_reason=None)


def test_shadow_contract_preserves_nullable_result_and_settlement() -> None:
    serialized = _record().to_dict()
    assert serialized["result"] is None
    assert serialized["settlement_status"] is None
    assert serialized["closing_reference"] is None
