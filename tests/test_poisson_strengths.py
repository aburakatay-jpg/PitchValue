from dataclasses import replace
from decimal import Decimal

import pytest

from pitchvalue.features.contracts import FeatureAvailability
from pitchvalue.models.poisson.config import (
    DEFAULT_POISSON_CONFIG,
    PartialHistoryPolicy,
    PoissonValidationError,
)
from pitchvalue.models.poisson.contracts import (
    PoissonModelInput,
    PoissonModelStatus,
    PoissonStrengths,
)
from pitchvalue.models.poisson.model import analyze_poisson
from pitchvalue.models.poisson.strengths import calculate_strengths

D = Decimal


def model_input(**overrides: object) -> PoissonModelInput:
    values: dict[str, object] = {
        "match_id": "target",
        "home_team_home_goals_for_per_match": D("1.5"),
        "home_team_home_goals_against_per_match": D("1.2"),
        "away_team_away_goals_for_per_match": D("1.2"),
        "away_team_away_goals_against_per_match": D("1.5"),
        "league_home_goals_per_match": D("1.5"),
        "league_away_goals_per_match": D("1.2"),
    }
    values.update(overrides)
    return PoissonModelInput(**values)  # type: ignore[arg-type]


def strengths(value: PoissonModelInput | None = None) -> PoissonStrengths:
    result = calculate_strengths(value or model_input(), DEFAULT_POISSON_CONFIG)
    assert result is not None
    return result


def test_default_config_is_valid_serializable_and_provisional() -> None:
    assert DEFAULT_POISSON_CONFIG.max_goals == 10
    assert DEFAULT_POISSON_CONFIG.partial_history_policy is PartialHistoryPolicy.ALLOW_PARTIAL
    assert DEFAULT_POISSON_CONFIG.probability_tolerance == D("1e-12")
    assert DEFAULT_POISSON_CONFIG.as_dict()["max_goals"] == 10


@pytest.mark.parametrize(
    "overrides",
    [
        {"max_goals": -1},
        {"max_goals": 1},
        {"max_goals": True},
        {"partial_history_policy": "ALLOW_PARTIAL"},
        {"probability_tolerance": D("0")},
        {"probability_tolerance": D("1")},
        {"probability_tolerance": D("NaN")},
        {"maximum_lambda": D("0")},
        {"maximum_lambda": D("Infinity")},
    ],
)
def test_invalid_config_is_rejected(overrides: dict[str, object]) -> None:
    with pytest.raises(PoissonValidationError):
        replace(DEFAULT_POISSON_CONFIG, **overrides)  # type: ignore[arg-type]


def test_config_override_does_not_mutate_default() -> None:
    override = replace(DEFAULT_POISSON_CONFIG, max_goals=15)
    assert override.max_goals == 15
    assert DEFAULT_POISSON_CONFIG.max_goals == 10


def test_league_identical_rates_produce_identity_strengths_and_baseline_lambdas() -> None:
    result = strengths()
    assert result.home_attack_strength == 1
    assert result.home_defensive_weakness == 1
    assert result.away_attack_strength == 1
    assert result.away_defensive_weakness == 1
    assert result.lambda_home == D("1.5")
    assert result.lambda_away == D("1.2")


def test_stronger_home_attack_and_weaker_away_defense_raise_home_lambda() -> None:
    base = strengths()
    stronger_attack = strengths(model_input(home_team_home_goals_for_per_match=D("2.0")))
    weaker_defense = strengths(model_input(away_team_away_goals_against_per_match=D("2.0")))
    assert stronger_attack.lambda_home > base.lambda_home
    assert weaker_defense.lambda_home > base.lambda_home


def test_stronger_away_attack_and_weaker_home_defense_raise_away_lambda() -> None:
    base = strengths()
    stronger_attack = strengths(model_input(away_team_away_goals_for_per_match=D("2.0")))
    weaker_defense = strengths(model_input(home_team_home_goals_against_per_match=D("2.0")))
    assert stronger_attack.lambda_away > base.lambda_away
    assert weaker_defense.lambda_away > base.lambda_away


def test_true_zero_team_attack_rate_is_valid() -> None:
    result = strengths(model_input(home_team_home_goals_for_per_match=D("0")))
    assert result.home_attack_strength == 0
    assert result.lambda_home == 0


def test_missing_required_rate_produces_input_insufficient_not_a_prior() -> None:
    value = model_input(home_team_home_goals_for_per_match=None)
    assert calculate_strengths(value, DEFAULT_POISSON_CONFIG) is None
    analysis = analyze_poisson(value)
    assert analysis.status is PoissonModelStatus.INPUT_INSUFFICIENT
    assert analysis.strengths is None
    assert analysis.markets is None
    assert "home_team_home_goals_for_per_match" in analysis.reasons


@pytest.mark.parametrize(
    "overrides",
    [
        {"league_home_goals_per_match": D("0")},
        {"league_away_goals_per_match": D("-1")},
        {"home_team_home_goals_for_per_match": D("-0.1")},
        {"away_team_away_goals_against_per_match": D("NaN")},
        {"home_team_home_goals_against_per_match": 1.2},
    ],
)
def test_invalid_rates_are_rejected(overrides: dict[str, object]) -> None:
    with pytest.raises(PoissonValidationError):
        model_input(**overrides)


def test_unavailable_coverage_cannot_claim_numeric_rates() -> None:
    with pytest.raises(PoissonValidationError, match="unavailable home coverage"):
        model_input(home_venue_availability=FeatureAvailability.UNAVAILABLE)


def test_combined_lambda_above_explicit_ceiling_is_rejected() -> None:
    config = replace(DEFAULT_POISSON_CONFIG, maximum_lambda=D("2"))
    with pytest.raises(PoissonValidationError, match="combined lambda"):
        calculate_strengths(model_input(), config)
