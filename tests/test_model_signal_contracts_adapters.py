from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from pitchvalue.models.elo.contracts import EloSnapshot
from pitchvalue.models.form.contracts import (
    FormModelAnalysis,
    FormModelDiagnostics,
    FormModelStatus,
    TeamFormSignal,
    TeamSignalCoverage,
)
from pitchvalue.models.poisson.contracts import (
    MarketProbabilities,
    MarketProbability,
    PoissonAnalysis,
    PoissonDiagnostics,
    PoissonModelStatus,
)
from pitchvalue.models.signals.adapters import (
    adapt_elo_signal,
    adapt_form_signal,
    adapt_poisson_signal,
)
from pitchvalue.models.signals.config import (
    CANONICAL_MODEL_FAMILY_ORDER,
    ModelFamily,
    SignalAgreementConfig,
    SignalValidationError,
)
from pitchvalue.models.signals.contracts import (
    DirectionalPreference,
    ModelSignal,
    SignalStatus,
)
from pitchvalue.prediction.contracts import MarketFamily, Selection

D = Decimal


def signal(**overrides: object) -> ModelSignal:
    values: dict[str, object] = {
        "model_family": ModelFamily.POISSON,
        "model_name": "test-v1",
        "match_id": "match",
        "market": MarketFamily.MATCH_RESULT,
        "selection": Selection.HOME,
        "direction": DirectionalPreference.HOME,
        "signal_status": SignalStatus.READY,
        "normalized_strength": D("0.7"),
    }
    values.update(overrides)
    return ModelSignal(**values)  # type: ignore[arg-type]


def poisson(
    home: str = "0.50",
    draw: str = "0.25",
    away: str = "0.2499",
    *,
    status: PoissonModelStatus = PoissonModelStatus.READY,
    represented: str = "0.9999",
    extra_values: tuple[MarketProbability, ...] = (),
) -> PoissonAnalysis:
    values = (
        MarketProbability(MarketFamily.MATCH_RESULT, Selection.HOME, None, D(home)),
        MarketProbability(MarketFamily.MATCH_RESULT, Selection.DRAW, None, D(draw)),
        MarketProbability(MarketFamily.MATCH_RESULT, Selection.AWAY, None, D(away)),
    ) + extra_values
    diagnostics = PoissonDiagnostics(
        max_goals=10,
        probability_tolerance=D("0.0001"),
        matrix_represented_mass=D(represented),
        matrix_residual_mass=D(1) - D(represented),
        one_x_two_represented_mass=D(represented),
        partial_history_used=False,
    )
    return PoissonAnalysis(
        match_id="match",
        status=status,
        strengths=None,
        score_matrix=None,
        markets=MarketProbabilities(values) if status is PoissonModelStatus.READY else None,
        diagnostics=diagnostics if status is PoissonModelStatus.READY else None,
        reasons=(),
    )


def elo(expected_home: str) -> EloSnapshot:
    expected = D(expected_home)
    return EloSnapshot(
        target_match_id="match",
        competition_id="league",
        season_id="s1",
        home_team_id="A",
        away_team_id="B",
        home_pre_match_rating=D("1500"),
        away_pre_match_rating=D("1500"),
        raw_rating_difference=D("0"),
        effective_home_rating=D("1600"),
        home_adjusted_rating_difference=D("100"),
        expected_home_score=expected,
        expected_away_score=D(1) - expected,
        home_prior_match_count=5,
        away_prior_match_count=5,
        as_of=datetime(2026, 9, 1, tzinfo=UTC),
    )


def team_signal(team_id: str) -> TeamFormSignal:
    return TeamFormSignal(
        team_id=team_id,
        ready=True,
        recent_form_score=D("50"),
        extended_form_score=D("50"),
        venue_form_score=D("50"),
        attack_score=D("50"),
        defense_score=D("50"),
        schedule_score=D("50"),
        weighted_form_score=D("50"),
        coverage=TeamSignalCoverage(6, 0, 0, (), D(1)),
        components=(),
        reasons=(),
    )


def form(
    relative: str | None,
    *,
    status: FormModelStatus = FormModelStatus.READY,
) -> FormModelAnalysis:
    value = D(relative) if relative is not None else None
    return FormModelAnalysis(
        match_id="match",
        home_team_id="A",
        away_team_id="B",
        status=status,
        home_team=team_signal("A"),
        away_team=team_signal("B"),
        home_form_score=D("50") if value is not None else None,
        away_form_score=D("50") if value is not None else None,
        raw_form_difference=value * D(100) if value is not None else None,
        home_relative_form_signal=value,
        away_relative_form_signal=-value if value is not None else None,
        diagnostics=FormModelDiagnostics(D(1), D(1), 0, 0, "EXCLUDE", "USE_PARTIAL"),
        reasons=(),
    )


def test_valid_signal_contract_and_optional_probability() -> None:
    value = signal(probability=None)
    assert value.signal_status is SignalStatus.READY
    assert value.probability is None


@pytest.mark.parametrize("strength", [D("-0.001"), D("1.001")])
def test_invalid_normalized_strength_rejected(strength: Decimal) -> None:
    with pytest.raises(SignalValidationError, match="normalized_strength"):
        signal(normalized_strength=strength)


@pytest.mark.parametrize("probability", [D("-0.001"), D("1.001")])
def test_invalid_probability_rejected(probability: Decimal) -> None:
    with pytest.raises(SignalValidationError, match="probability"):
        signal(probability=probability)


def test_signal_serialization_is_deterministic() -> None:
    value = signal(probability=D("0.7"))
    assert value.to_dict() == value.to_dict()
    assert value.to_dict()["model_family"] == "POISSON"
    assert value.to_dict()["normalized_strength"] == "0.7"


def test_non_ready_signal_cannot_claim_selection() -> None:
    with pytest.raises(SignalValidationError, match="non-READY"):
        signal(signal_status=SignalStatus.AMBIGUOUS)


def test_signal_enforces_canonical_market_selection_and_line() -> None:
    with pytest.raises(SignalValidationError, match="selection is not valid"):
        signal(market=MarketFamily.BTTS)
    totals = signal(
        market=MarketFamily.TOTAL_GOALS,
        selection=Selection.OVER,
        direction=None,
        line=D("2.5"),
    )
    assert totals.line == D("2.5")


def test_neutral_signal_has_no_selection() -> None:
    value = signal(
        model_family=ModelFamily.ELO,
        selection=None,
        direction=DirectionalPreference.NEUTRAL,
        probability=None,
    )
    assert value.selection is None
    assert value.direction is DirectionalPreference.NEUTRAL


@pytest.mark.parametrize(
    ("probabilities", "expected"),
    [
        (("0.50", "0.25", "0.2499"), Selection.HOME),
        (("0.25", "0.50", "0.2499"), Selection.DRAW),
        (("0.25", "0.2499", "0.50"), Selection.AWAY),
    ],
)
def test_poisson_adapter_selects_highest_probability(
    probabilities: tuple[str, str, str], expected: Selection
) -> None:
    result = adapt_poisson_signal(poisson(*probabilities))
    assert result.signal_status is SignalStatus.READY
    assert result.selection is expected
    assert result.probability == D("0.50")
    assert result.normalized_strength == D("0.50")


def test_poisson_probability_is_preserved_without_renormalization() -> None:
    result = adapt_poisson_signal(poisson("0.4000", "0.3000", "0.2999"))
    assert result.probability == D("0.4000")
    assert result.raw_value == D("0.4000")
    assert result.diagnostics[-1].value is False


def test_poisson_near_tie_is_ambiguous() -> None:
    result = adapt_poisson_signal(poisson("0.4000", "0.39995", "0.19995"))
    assert result.signal_status is SignalStatus.AMBIGUOUS
    assert result.selection is None


def test_poisson_residual_above_tolerance_is_unavailable() -> None:
    result = adapt_poisson_signal(poisson(represented="0.99"))
    assert result.signal_status is SignalStatus.ANALYSIS_UNAVAILABLE
    assert result.normalized_strength is None


def test_poisson_unavailable_status_maps_to_input_insufficient() -> None:
    result = adapt_poisson_signal(poisson(status=PoissonModelStatus.INPUT_INSUFFICIENT))
    assert result.signal_status is SignalStatus.INPUT_INSUFFICIENT


def test_poisson_supports_an_implemented_non_result_market() -> None:
    totals = (
        MarketProbability(MarketFamily.TOTAL_GOALS, Selection.OVER, D("2.5"), D("0.6")),
        MarketProbability(MarketFamily.TOTAL_GOALS, Selection.UNDER, D("2.5"), D("0.4")),
    )
    result = adapt_poisson_signal(
        poisson(extra_values=totals),
        market=MarketFamily.TOTAL_GOALS,
        line=D("2.5"),
    )
    assert result.signal_status is SignalStatus.READY
    assert result.selection is Selection.OVER


def test_poisson_missing_market_is_explicitly_unsupported() -> None:
    result = adapt_poisson_signal(poisson(), market=MarketFamily.BTTS)
    assert result.signal_status is SignalStatus.UNSUPPORTED_MARKET


@pytest.mark.parametrize(
    ("expected_home", "direction", "selection"),
    [
        ("0.70", DirectionalPreference.HOME, Selection.HOME),
        ("0.30", DirectionalPreference.AWAY, Selection.AWAY),
        ("0.50", DirectionalPreference.NEUTRAL, None),
        ("0.55", DirectionalPreference.HOME, Selection.HOME),
        ("0.45", DirectionalPreference.AWAY, Selection.AWAY),
    ],
)
def test_elo_adapter_direction_and_boundaries(
    expected_home: str,
    direction: DirectionalPreference,
    selection: Selection | None,
) -> None:
    result = adapt_elo_signal(elo(expected_home))
    assert result.signal_status is SignalStatus.READY
    assert result.direction is direction
    assert result.selection is selection


def test_elo_strength_is_bounded_distance_not_probability() -> None:
    result = adapt_elo_signal(elo("0.70"))
    assert result.normalized_strength == D("0.40")
    assert result.probability is None
    assert result.raw_value == D("0.70")


def test_elo_missing_snapshot_is_unavailable() -> None:
    result = adapt_elo_signal(None, match_id="match")
    assert result.signal_status is SignalStatus.ANALYSIS_UNAVAILABLE


def test_missing_analysis_requires_explicit_match_id() -> None:
    with pytest.raises(ValueError, match="match_id"):
        adapt_elo_signal(None)
    with pytest.raises(ValueError, match="match_id"):
        adapt_form_signal(None)


def test_elo_invalid_snapshot_is_invalid_signal() -> None:
    invalid = replace(elo("0.70"), expected_away_score=D("0.40"))
    assert adapt_elo_signal(invalid).signal_status is SignalStatus.INVALID


def test_elo_non_result_market_is_unsupported() -> None:
    result = adapt_elo_signal(elo("0.70"), market=MarketFamily.BTTS)
    assert result.signal_status is SignalStatus.UNSUPPORTED_MARKET


@pytest.mark.parametrize(
    ("relative", "direction", "selection"),
    [
        ("0.40", DirectionalPreference.HOME, Selection.HOME),
        ("-0.40", DirectionalPreference.AWAY, Selection.AWAY),
        ("0.01", DirectionalPreference.NEUTRAL, None),
        ("0.10", DirectionalPreference.HOME, Selection.HOME),
        ("-0.10", DirectionalPreference.AWAY, Selection.AWAY),
    ],
)
def test_form_adapter_direction_and_boundaries(
    relative: str,
    direction: DirectionalPreference,
    selection: Selection | None,
) -> None:
    result = adapt_form_signal(form(relative))
    assert result.signal_status is SignalStatus.READY
    assert result.direction is direction
    assert result.selection is selection
    assert result.normalized_strength == abs(D(relative))


def test_form_signal_is_not_exposed_as_probability() -> None:
    result = adapt_form_signal(form("0.40"))
    assert result.probability is None
    assert result.raw_value == D("0.40")


def test_form_input_insufficient_maps_without_neutral_fabrication() -> None:
    result = adapt_form_signal(form(None, status=FormModelStatus.INPUT_INSUFFICIENT))
    assert result.signal_status is SignalStatus.INPUT_INSUFFICIENT
    assert result.direction is None


def test_form_non_result_market_is_unsupported() -> None:
    result = adapt_form_signal(form("0.40"), market=MarketFamily.TOTAL_GOALS)
    assert result.signal_status is SignalStatus.UNSUPPORTED_MARKET


def test_canonical_family_order_is_stable() -> None:
    assert CANONICAL_MODEL_FAMILY_ORDER == (
        ModelFamily.POISSON,
        ModelFamily.ELO,
        ModelFamily.FORM,
        ModelFamily.ML,
    )


def test_config_is_immutable() -> None:
    config = SignalAgreementConfig()
    changed = replace(config, minimum_usable_models=2)
    assert config.minimum_usable_models == 3
    assert changed.minimum_usable_models == 2
    with pytest.raises(FrozenInstanceError):
        config.minimum_usable_models = 1  # type: ignore[misc]
