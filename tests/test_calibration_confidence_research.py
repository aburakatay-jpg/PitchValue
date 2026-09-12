from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from pitchvalue.evaluation.calibration_confidence import (
    CalibrationEvidenceCandidate,
    CalibrationEvidenceScope,
    ConfidenceEvidenceStatus,
    select_calibration_evidence,
)
from pitchvalue.evaluation.metrics.calibration import multiclass_calibration
from pitchvalue.evaluation.metrics.config import MetricConfig
from pitchvalue.evaluation.metrics.contracts import ClassProbability, MulticlassPrediction

D = Decimal


def _scope(market: str, competition: str | None = None) -> CalibrationEvidenceScope:
    return CalibrationEvidenceScope(market, "raw_ml_v1", competition)


def _ready_result():  # type: ignore[no-untyped-def]
    rows = tuple(
        MulticlassPrediction(
            f"row-{index}",
            (
                ClassProbability("HOME", D("0.50")),
                ClassProbability("DRAW", D("0.30")),
                ClassProbability("AWAY", D("0.20")),
            ),
            "HOME" if index % 2 == 0 else "AWAY",
        )
        for index in range(6)
    )
    return multiclass_calibration(
        rows,
        MetricConfig(minimum_total_samples=1, minimum_bucket_samples=1),
    )


def test_explicit_fallback_selects_first_ready_same_market_scope() -> None:
    requested = _scope("MATCH_RESULT", "EPL")
    global_scope = _scope("MATCH_RESULT")
    result = select_calibration_evidence(
        requested,
        (CalibrationEvidenceCandidate(global_scope, _ready_result()),),
        (requested, global_scope),
    )
    assert result.status is ConfidenceEvidenceStatus.AVAILABLE
    assert result.selected_scope == global_scope
    assert result.support_count == 6
    assert result.ece_like is not None
    assert result.confidence_score is None


@pytest.mark.parametrize("market", ["BTTS", "TOTAL_GOALS", "DOUBLE_CHANCE", "TEAM_TOTAL"])
def test_match_result_evidence_cannot_transfer_to_other_market(market: str) -> None:
    requested = _scope(market)
    with pytest.raises(ValueError, match="cannot cross market"):
        select_calibration_evidence(
            requested,
            (CalibrationEvidenceCandidate(_scope("MATCH_RESULT"), _ready_result()),),
            (_scope("MATCH_RESULT"),),
        )


def test_no_market_specific_evidence_is_explicitly_unavailable() -> None:
    requested = _scope("BTTS")
    result = select_calibration_evidence(requested, (), (requested,))
    assert result.status is ConfidenceEvidenceStatus.UNAVAILABLE
    assert result.support_count == 0
    assert result.ece_like is None
    assert result.confidence_score is None


def test_model_version_isolation_and_timezone_window_validation() -> None:
    requested = _scope("MATCH_RESULT")
    wrong_model = CalibrationEvidenceScope("MATCH_RESULT", "other_model")
    with pytest.raises(ValueError, match="model version"):
        select_calibration_evidence(requested, (), (wrong_model,))
    with pytest.raises(ValueError, match="timezone-aware"):
        CalibrationEvidenceScope(
            "MATCH_RESULT",
            "raw_ml_v1",
            window_start=datetime(2026, 1, 1),
            window_end=datetime(2026, 2, 1, tzinfo=UTC),
        )
