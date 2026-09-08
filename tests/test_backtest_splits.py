from datetime import UTC, datetime, timedelta

import pytest

from pitchvalue.evaluation import (
    EvaluationStatus,
    EvaluationValidationError,
    SplitStrategy,
    TemporalObservation,
    WalkForwardConfig,
    canonical_observations,
    plan_walk_forward,
    summarize_walk_forward,
)

BASE = datetime(2026, 1, 1, tzinfo=UTC)


def _row(
    day: int, identifier: str | None = None, *, available_delay_hours: int = 1
) -> TemporalObservation:
    kickoff = BASE + timedelta(days=day)
    return TemporalObservation(
        identifier or f"obs-{day:02d}",
        f"match-{day:02d}",
        "comp-a" if day % 2 == 0 else "comp-b",
        "season-1" if day < 7 else "season-2",
        kickoff,
        kickoff + timedelta(hours=available_delay_hours),
    )


def _config(
    strategy: SplitStrategy = SplitStrategy.EXPANDING, **changes: object
) -> WalkForwardConfig:
    values: dict[str, object] = {
        "strategy": strategy,
        "training_window": timedelta(days=3),
        "test_window": timedelta(days=2),
        "step_size": timedelta(days=2),
    }
    values.update(changes)
    return WalkForwardConfig(**values)  # type: ignore[arg-type]


def test_expanding_fold_boundaries_and_counts() -> None:
    folds = plan_walk_forward([_row(day) for day in range(10)], _config())
    assert len(folds) == 4
    assert folds[0].fold.train_start == BASE
    assert folds[0].fold.train_end == BASE + timedelta(days=3)
    assert folds[0].fold.test_start == BASE + timedelta(days=3)
    assert folds[0].fold.test_end == BASE + timedelta(days=5)
    assert folds[0].fold.training_observation_count == 3
    assert folds[0].fold.test_observation_count == 2


def test_expanding_train_start_stays_fixed_and_end_advances() -> None:
    folds = plan_walk_forward([_row(day) for day in range(10)], _config())
    assert {fold.fold.train_start for fold in folds} == {BASE}
    assert [fold.fold.train_end.day for fold in folds] == [4, 6, 8, 10]


def test_rolling_boundaries_advance_and_span_stays_bounded() -> None:
    folds = plan_walk_forward([_row(day) for day in range(10)], _config(SplitStrategy.ROLLING))
    assert [fold.fold.train_start.day for fold in folds] == [1, 3, 5, 7]
    assert all(fold.fold.train_end - fold.fold.train_start == timedelta(days=3) for fold in folds)


@pytest.mark.parametrize("strategy", list(SplitStrategy))
def test_test_window_follows_training_without_overlap(strategy: SplitStrategy) -> None:
    for execution in plan_walk_forward([_row(day) for day in range(10)], _config(strategy)):
        assert execution.fold.train_end <= execution.fold.test_start
        assert not set(execution.fold.training_observation_ids) & set(
            execution.fold.test_observation_ids
        )


@pytest.mark.parametrize("strategy", list(SplitStrategy))
def test_embargo_creates_explicit_gap(strategy: SplitStrategy) -> None:
    config = _config(strategy, embargo=timedelta(days=1))
    first = plan_walk_forward([_row(day) for day in range(10)], config)[0].fold
    assert first.test_start - first.train_end == timedelta(days=1)


@pytest.mark.parametrize("strategy", list(SplitStrategy))
def test_shuffled_input_produces_identical_folds(strategy: SplitStrategy) -> None:
    rows = [_row(day) for day in range(10)]
    ordered = plan_walk_forward(rows, _config(strategy))
    shuffled = plan_walk_forward(
        [rows[8], rows[1], rows[6], *rows[2:6], rows[0], rows[7], rows[9]], _config(strategy)
    )
    assert [item.fold.to_dict() for item in ordered] == [item.fold.to_dict() for item in shuffled]


def test_duplicate_observation_id_is_rejected() -> None:
    with pytest.raises(EvaluationValidationError, match="duplicate observation_id"):
        plan_walk_forward([_row(0, "same"), _row(1, "same")], _config())


def test_identical_timestamp_uses_stable_identifier_order() -> None:
    rows = [_row(0, "z"), _row(0, "a"), _row(0, "m")]
    assert [row.observation_id for row in canonical_observations(rows)] == ["a", "m", "z"]


def test_input_collection_is_not_mutated() -> None:
    rows = [_row(3), _row(0), _row(5), _row(1)]
    before = list(rows)
    plan_walk_forward(rows, _config())
    assert rows == before


def test_availability_after_train_boundary_is_not_in_training() -> None:
    rows = [_row(0), _row(1), _row(2, available_delay_hours=30), _row(3), _row(4)]
    first = plan_walk_forward(rows, _config())[0]
    assert "obs-02" not in first.fold.training_observation_ids


def test_half_open_boundary_places_train_end_row_in_test() -> None:
    first = plan_walk_forward([_row(day) for day in range(6)], _config())[0]
    assert "obs-03" not in first.fold.training_observation_ids
    assert "obs-03" in first.fold.test_observation_ids


@pytest.mark.parametrize(
    ("minimum_train", "minimum_test", "expected"),
    [
        (1, 1, EvaluationStatus.READY),
        (4, 1, EvaluationStatus.INSUFFICIENT_TRAINING_SAMPLE),
        (1, 3, EvaluationStatus.INSUFFICIENT_TEST_SAMPLE),
    ],
)
def test_sample_sufficiency_statuses(
    minimum_train: int, minimum_test: int, expected: EvaluationStatus
) -> None:
    config = _config(minimum_training_samples=minimum_train, minimum_test_samples=minimum_test)
    assert plan_walk_forward([_row(day) for day in range(6)], config)[0].fold.status is expected


def test_empty_training_window_is_explicit() -> None:
    rows = [_row(0, available_delay_hours=100), _row(3), _row(4)]
    assert plan_walk_forward(rows, _config())[0].fold.status is EvaluationStatus.EMPTY_WINDOW


def test_empty_test_window_is_explicit() -> None:
    rows = [_row(0), _row(1), _row(2), _row(5)]
    assert plan_walk_forward(rows, _config())[0].fold.status is EvaluationStatus.EMPTY_WINDOW


def test_empty_dataset_produces_no_folds() -> None:
    assert plan_walk_forward([], _config()) == ()


def test_fold_ids_are_deterministic() -> None:
    folds = plan_walk_forward([_row(day) for day in range(10)], _config())
    assert [item.fold.fold_id for item in folds] == [
        "fold-0001",
        "fold-0002",
        "fold-0003",
        "fold-0004",
    ]


def test_fold_serialization_exposes_sample_counts() -> None:
    fold = plan_walk_forward([_row(day) for day in range(6)], _config())[0].fold
    assert fold.to_dict()["training_observation_count"] == 3
    assert fold.to_dict()["test_observation_count"] == 2


def test_summary_preserves_counts_and_statuses() -> None:
    summary = summarize_walk_forward([_row(day) for day in range(6)], _config())
    assert summary.fold_count == 2
    assert summary.valid_fold_count == 2
    assert summary.total_training_observations == 8
    assert summary.total_evaluation_observations == 3
    assert summary.to_dict() == summary.to_dict()


def test_competition_and_season_identity_are_preserved() -> None:
    first = plan_walk_forward([_row(day) for day in range(6)], _config())[0]
    assert {row.competition_id for row in first.training_observations} == {"comp-a", "comp-b"}
    assert {row.season_id for row in first.training_observations} == {"season-1"}


def test_repeated_computation_is_exactly_equal() -> None:
    rows = [_row(day) for day in range(10)]
    assert plan_walk_forward(rows, _config()) == plan_walk_forward(rows, _config())
