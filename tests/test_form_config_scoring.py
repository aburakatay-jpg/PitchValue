from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from pitchvalue.features.contracts import (
    Coverage,
    FeatureAvailability,
    ScheduleDensity,
    TeamForm,
    TeamSchedule,
)
from pitchvalue.models.form.config import (
    ComponentWeights,
    FormModelConfig,
    FormValidationError,
    InnerWeights,
    PartialCoveragePolicy,
)
from pitchvalue.models.form.contracts import FormComponent
from pitchvalue.models.form.scoring import (
    normalize_attack_ratio,
    normalize_defense_ratio,
    normalize_goal_difference,
    normalize_ppg,
    score_form_component,
    score_schedule_component,
)

D = Decimal
NEUTRAL_PPG = D("1.5")
NEUTRAL_GOAL_DIFFERENCE = D("0")


def team_form(
    *,
    ppg: Decimal | None = NEUTRAL_PPG,
    gd: Decimal | None = NEUTRAL_GOAL_DIFFERENCE,
    availability: FeatureAvailability = FeatureAvailability.COMPLETE,
) -> TeamForm:
    return TeamForm(
        coverage=Coverage(2, 2, 1, availability),
        matches_played=2,
        wins=1,
        draws=0,
        losses=1,
        points=3,
        points_per_game=ppg,
        goals_for=2,
        goals_against=2,
        goals_for_per_game=D("1"),
        goals_against_per_game=D("1"),
        goal_difference=0,
        goal_difference_per_game=gd,
        clean_sheets=1,
        clean_sheet_rate=D("0.5"),
        failed_to_score=1,
        failed_to_score_rate=D("0.5"),
        btts=0,
        btts_rate=D("0"),
        over_1_5=1,
        over_1_5_rate=D("0.5"),
        over_2_5=0,
        over_2_5_rate=D("0"),
        match_ids=("m1", "m2"),
    )


def schedule(rest: str | None, seven: int = 1, fourteen: int = 2) -> TeamSchedule:
    return TeamSchedule(
        previous_match_kickoff=datetime(2026, 1, 1, tzinfo=UTC) if rest else None,
        days_since_previous_match=D(rest) if rest else None,
        density=(ScheduleDensity(7, seven), ScheduleDensity(14, fourteen)),
    )


def test_default_config_is_valid_and_weights_total_one() -> None:
    config = FormModelConfig()
    assert sum(config.component_weights.__dict__.values(), D(0)) == D(1)
    assert config.as_dict()["partial_coverage_policy"] == "USE_PARTIAL"


def test_invalid_component_weight_total_rejected() -> None:
    with pytest.raises(FormValidationError, match="total 1"):
        ComponentWeights(recent_form=D("0.21"), extended_form=D("0.20"))


def test_negative_component_weight_rejected() -> None:
    with pytest.raises(FormValidationError, match="between 0 and 1"):
        ComponentWeights(recent_form=D("-0.01"), extended_form=D("0.26"))


def test_invalid_inner_weights_rejected() -> None:
    with pytest.raises(FormValidationError, match="total 1"):
        InnerWeights(D("0.8"), D("0.3"))


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"goal_difference_minimum": D("0")}, "surround zero"),
        ({"attack_ratio_maximum": D("1")}, "must exceed 1"),
        ({"defense_ratio_maximum": D("0.5")}, "must exceed 1"),
        ({"short_rest_days": D("8")}, "ordered"),
        ({"schedule_score_minimum": D("55")}, "contain neutral"),
        ({"minimum_scored_components": 0}, "within 1 and 6"),
    ],
)
def test_invalid_config_bounds_rejected(override: dict[str, object], message: str) -> None:
    with pytest.raises(FormValidationError, match=message):
        FormModelConfig(**override)  # type: ignore[arg-type]


def test_invalid_policy_types_rejected() -> None:
    with pytest.raises(FormValidationError, match="partial coverage"):
        FormModelConfig(partial_coverage_policy="USE_PARTIAL")  # type: ignore[arg-type]
    with pytest.raises(FormValidationError, match="missing component"):
        FormModelConfig(missing_component_policy="EXCLUDE")  # type: ignore[arg-type]


def test_config_is_immutable_and_override_does_not_mutate_default() -> None:
    original = FormModelConfig()
    overridden = replace(original, short_rest_days=D("3"))
    assert original.short_rest_days == D("4")
    assert overridden.short_rest_days == D("3")
    with pytest.raises(FrozenInstanceError):
        original.short_rest_days = D("2")  # type: ignore[misc]


@pytest.mark.parametrize(
    ("ppg", "expected"),
    [(D("0"), D("0")), (D("1.5"), D("50.0")), (D("3"), D("100"))],
)
def test_ppg_normalization(ppg: Decimal, expected: Decimal) -> None:
    assert normalize_ppg(ppg) == expected


def test_ppg_rejects_out_of_range_value() -> None:
    with pytest.raises(FormValidationError):
        normalize_ppg(D("3.01"))


@pytest.mark.parametrize(
    ("goal_difference", "expected"),
    [(D("-2"), D("0")), (D("0"), D("50")), (D("2"), D("100"))],
)
def test_goal_difference_normalization(goal_difference: Decimal, expected: Decimal) -> None:
    assert normalize_goal_difference(goal_difference, FormModelConfig()) == expected


def test_goal_difference_mapping_is_bounded_and_monotonic() -> None:
    config = FormModelConfig()
    assert normalize_goal_difference(D("-99"), config) == 0
    assert normalize_goal_difference(D("1"), config) > normalize_goal_difference(D("-1"), config)
    assert normalize_goal_difference(D("99"), config) == 100


@pytest.mark.parametrize(
    ("ratio", "expected"),
    [(D("0"), D("0")), (D("1"), D("50")), (D("2"), D("100"))],
)
def test_attack_normalization(ratio: Decimal, expected: Decimal) -> None:
    assert normalize_attack_ratio(ratio, FormModelConfig()) == expected


@pytest.mark.parametrize(
    ("ratio", "expected"),
    [(D("0"), D("100")), (D("1"), D("50")), (D("2"), D("0"))],
)
def test_defense_normalization(ratio: Decimal, expected: Decimal) -> None:
    assert normalize_defense_ratio(ratio, FormModelConfig()) == expected


def test_attack_and_defense_reject_negative_ratio() -> None:
    with pytest.raises(FormValidationError):
        normalize_attack_ratio(D("-0.1"), FormModelConfig())
    with pytest.raises(FormValidationError):
        normalize_defense_ratio(D("-0.1"), FormModelConfig())


def test_form_component_combines_ppg_and_goal_difference() -> None:
    result = score_form_component(
        team_form(ppg=D("3"), gd=D("2")), FormComponent.RECENT_FORM, FormModelConfig()
    )
    assert result.score == D("100")
    assert result.used is True
    assert [item.name for item in result.normalized_inputs] == [
        "normalized_ppg",
        "normalized_goal_difference",
    ]


def test_partial_form_is_used_by_default_and_can_be_excluded() -> None:
    partial = team_form(availability=FeatureAvailability.PARTIAL)
    assert score_form_component(partial, FormComponent.RECENT_FORM, FormModelConfig()).score == D(
        "50.0"
    )
    config = FormModelConfig(partial_coverage_policy=PartialCoveragePolicy.EXCLUDE_PARTIAL)
    result = score_form_component(partial, FormComponent.RECENT_FORM, config)
    assert result.score is None
    assert result.reason == "COVERAGE_EXCLUDED"


def test_missing_form_rate_is_not_fabricated() -> None:
    result = score_form_component(team_form(ppg=None), FormComponent.RECENT_FORM, FormModelConfig())
    assert result.score is None
    assert result.reason == "FORM_INPUT_MISSING"


def test_schedule_neutral_short_rest_and_adequate_rest() -> None:
    config = FormModelConfig()
    assert score_schedule_component(schedule("5"), config).score == D("50")
    assert score_schedule_component(schedule("3"), config).score == D("35")
    assert score_schedule_component(schedule("7"), config).score == D("55")


def test_schedule_congestion_penalty_is_bounded() -> None:
    config = FormModelConfig()
    normal = score_schedule_component(schedule("5"), config)
    congested = score_schedule_component(schedule("5", 3, 6), config)
    extreme = score_schedule_component(schedule("2", 99, 99), config)
    assert (
        congested.score is not None and normal.score is not None and congested.score < normal.score
    )
    assert extreme.score == config.schedule_score_minimum


def test_missing_rest_is_unavailable_not_neutral() -> None:
    result = score_schedule_component(schedule(None), FormModelConfig())
    assert result.score is None
    assert result.coverage is FeatureAvailability.UNAVAILABLE
    assert result.reason == "REST_MISSING"
