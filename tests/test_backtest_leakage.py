from datetime import UTC, datetime, timedelta

import pytest

from pitchvalue.evaluation import (
    EvaluationProvenance,
    EvaluationStatus,
    EvaluationTarget,
    EvaluationValidationError,
    LeakageCode,
    ObservationKind,
    OddsUse,
    PredictionEvaluationRecord,
    TemporalObservation,
    validate_as_of,
    validate_evaluation_record,
    validate_prediction_history,
)

BASE = datetime(2026, 1, 1, tzinfo=UTC)
TARGET_KICKOFF = BASE + timedelta(days=2)
AS_OF = TARGET_KICKOFF - timedelta(hours=6)


def _target() -> EvaluationTarget:
    return EvaluationTarget("target", "comp", "season", TARGET_KICKOFF, AS_OF)


def _row(**changes: object) -> TemporalObservation:
    values: dict[str, object] = {
        "observation_id": "obs",
        "match_id": "past-match",
        "competition_id": "comp",
        "season_id": "season",
        "kickoff": BASE,
        "available_at": BASE + timedelta(hours=2),
    }
    values.update(changes)
    return TemporalObservation(**values)  # type: ignore[arg-type]


def _codes(*rows: TemporalObservation) -> set[LeakageCode]:
    return {item.code for item in validate_prediction_history(_target(), rows).diagnostics}


def test_clean_past_history_is_ready() -> None:
    assert validate_prediction_history(_target(), [_row()]).status is EvaluationStatus.READY


def test_target_self_inclusion_is_detected() -> None:
    assert LeakageCode.TARGET_SELF_LEAKAGE in _codes(_row(match_id="target"))


def test_target_result_in_feature_material_is_detected() -> None:
    assert LeakageCode.TARGET_RESULT_IN_FEATURES in _codes(
        _row(kind=ObservationKind.FEATURE, contains_target_outcome=True)
    )


def test_future_observation_is_detected() -> None:
    assert LeakageCode.FUTURE_OBSERVATION in _codes(_row(kickoff=AS_OF + timedelta(minutes=1)))


def test_same_target_kickoff_is_detected() -> None:
    assert LeakageCode.SAME_TIME_OBSERVATION in _codes(_row(kickoff=TARGET_KICKOFF))


def test_other_match_at_as_of_is_not_historical() -> None:
    assert LeakageCode.FUTURE_OBSERVATION in _codes(_row(kickoff=AS_OF))


def test_feature_calculated_after_as_of_is_detected() -> None:
    assert LeakageCode.FEATURE_AVAILABLE_AFTER_AS_OF in _codes(
        _row(kind=ObservationKind.FEATURE, available_at=AS_OF + timedelta(seconds=1))
    )


@pytest.mark.parametrize(
    "use",
    [OddsUse.PREDICTION_FEATURE, OddsUse.EVALUATION_REFERENCE, OddsUse.CLOSING_REFERENCE],
)
def test_odds_observed_after_as_of_are_detected(use: OddsUse) -> None:
    assert LeakageCode.ODDS_AVAILABLE_AFTER_AS_OF in _codes(
        _row(
            kind=ObservationKind.ODDS,
            odds_use=use,
            available_at=AS_OF + timedelta(minutes=1),
        )
    )


def test_later_closing_odds_are_illegal_as_prediction_input() -> None:
    closing = _row(
        kind=ObservationKind.ODDS,
        odds_use=OddsUse.CLOSING_REFERENCE,
        available_at=TARGET_KICKOFF - timedelta(minutes=15),
    )
    assert LeakageCode.ODDS_AVAILABLE_AFTER_AS_OF in _codes(closing)


def test_odds_available_exactly_at_as_of_are_legal() -> None:
    odds = _row(kind=ObservationKind.ODDS, odds_use=OddsUse.PREDICTION_FEATURE, available_at=AS_OF)
    assert LeakageCode.ODDS_AVAILABLE_AFTER_AS_OF not in _codes(odds)


def test_feature_available_exactly_at_as_of_is_legal() -> None:
    feature = _row(kind=ObservationKind.FEATURE, available_at=AS_OF)
    assert LeakageCode.FEATURE_AVAILABLE_AFTER_AS_OF not in _codes(feature)


def test_outcome_claimed_available_before_its_match_is_detected() -> None:
    outcome = _row(kind=ObservationKind.OUTCOME, available_at=BASE - timedelta(seconds=1))
    assert LeakageCode.OUTCOME_AVAILABLE_TOO_EARLY in _codes(outcome)


def test_evaluation_truth_before_target_resolution_is_detected() -> None:
    record = PredictionEvaluationRecord(
        "record",
        _target(),
        "fold-0001",
        EvaluationProvenance("model", "v1"),
        "prediction",
        "outcome",
        TARGET_KICKOFF - timedelta(seconds=1),
    )
    result = validate_evaluation_record(record)
    assert result.status is EvaluationStatus.LEAKAGE_DETECTED
    assert result.diagnostics[0].code is LeakageCode.OUTCOME_AVAILABLE_TOO_EARLY


def test_evaluation_truth_after_target_resolution_is_valid() -> None:
    record = PredictionEvaluationRecord(
        "record",
        _target(),
        "fold-0001",
        EvaluationProvenance("model", "v1"),
        "prediction",
        "outcome",
        TARGET_KICKOFF + timedelta(hours=2),
    )
    assert validate_evaluation_record(record).status is EvaluationStatus.READY


@pytest.mark.parametrize(
    ("as_of", "kickoff", "expected"),
    [
        (BASE, BASE + timedelta(seconds=1), EvaluationStatus.READY),
        (BASE, BASE, EvaluationStatus.INVALID_TEMPORAL_ORDER),
        (BASE + timedelta(seconds=1), BASE, EvaluationStatus.INVALID_TEMPORAL_ORDER),
        (BASE.replace(tzinfo=None), BASE, EvaluationStatus.INVALID_TEMPORAL_ORDER),
    ],
)
def test_raw_as_of_validation(
    as_of: datetime, kickoff: datetime, expected: EvaluationStatus
) -> None:
    result = validate_as_of(as_of, kickoff)
    assert result.status is expected
    if expected is not EvaluationStatus.READY:
        assert result.diagnostics[0].code is LeakageCode.INVALID_AS_OF


def test_multiple_diagnostics_have_deterministic_order() -> None:
    rows = [
        _row(observation_id="z", match_id="target", kickoff=TARGET_KICKOFF),
        _row(
            observation_id="a",
            kind=ObservationKind.FEATURE,
            available_at=TARGET_KICKOFF,
        ),
    ]
    one = validate_prediction_history(_target(), rows).to_dict()
    two = validate_prediction_history(_target(), reversed(rows)).to_dict()
    assert one == two


def test_duplicate_history_is_rejected_not_silently_deduplicated() -> None:
    with pytest.raises(EvaluationValidationError, match="duplicate observation_id"):
        validate_prediction_history(_target(), [_row(), _row(match_id="other")])


def test_validator_does_not_mutate_or_correct_timestamps() -> None:
    row = _row(kind=ObservationKind.FEATURE, available_at=TARGET_KICKOFF)
    before = row.to_dict()
    validate_prediction_history(_target(), [row])
    assert row.to_dict() == before


def test_recalculated_feature_uses_its_actual_availability_time() -> None:
    recalculated = _row(
        kickoff=BASE - timedelta(days=30),
        kind=ObservationKind.FEATURE,
        available_at=AS_OF + timedelta(days=1),
    )
    assert LeakageCode.FEATURE_AVAILABLE_AFTER_AS_OF in _codes(recalculated)


def test_result_serialization_is_deterministic() -> None:
    result = validate_prediction_history(_target(), [_row()])
    assert result.to_dict() == result.to_dict()
