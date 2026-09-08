from dataclasses import replace
from decimal import Decimal

import pytest

from pitchvalue.models.signals.agreement import (
    evaluate_agreement,
    evaluate_match_result_agreement,
)
from pitchvalue.models.signals.config import (
    DEFAULT_SIGNAL_AGREEMENT_CONFIG,
    ModelFamily,
    SignalAgreementConfig,
    SignalValidationError,
)
from pitchvalue.models.signals.contracts import (
    AgreementResult,
    DirectionalPreference,
    ModelSignal,
    SignalStatus,
)
from pitchvalue.prediction.contracts import MarketFamily, Selection

D = Decimal


def ready(
    family: ModelFamily,
    selection: Selection | None,
    *,
    market: MarketFamily = MarketFamily.MATCH_RESULT,
    line: Decimal | None = None,
) -> ModelSignal:
    direction = (
        DirectionalPreference.HOME
        if selection is Selection.HOME
        else DirectionalPreference.AWAY
        if selection is Selection.AWAY
        else DirectionalPreference.NEUTRAL
        if selection is None
        else None
    )
    return ModelSignal(
        model_family=family,
        model_name=f"{family.value.lower()}-v1",
        match_id="match",
        market=market,
        selection=selection,
        direction=direction,
        signal_status=SignalStatus.READY,
        normalized_strength=D("0.6"),
        line=line,
        probability=D("0.6") if family in (ModelFamily.POISSON, ModelFamily.ML) else None,
    )


def unavailable(
    family: ModelFamily,
    status: SignalStatus = SignalStatus.ANALYSIS_UNAVAILABLE,
    *,
    market: MarketFamily = MarketFamily.MATCH_RESULT,
) -> ModelSignal:
    return ModelSignal(
        model_family=family,
        model_name=f"{family.value.lower()}-v1",
        match_id="match",
        market=market,
        selection=None,
        direction=None,
        signal_status=status,
        normalized_strength=None,
    )


def agreement(
    signals: list[ModelSignal],
    candidate: Selection = Selection.HOME,
    config: SignalAgreementConfig = DEFAULT_SIGNAL_AGREEMENT_CONFIG,
) -> AgreementResult:
    return evaluate_agreement(
        signals,
        match_id="match",
        market=MarketFamily.MATCH_RESULT,
        candidate_selection=candidate,
        config=config,
    )


def test_three_current_models_home_separates_both_denominators() -> None:
    result = agreement(
        [
            ready(ModelFamily.POISSON, Selection.HOME),
            ready(ModelFamily.ELO, Selection.HOME),
            ready(ModelFamily.FORM, Selection.HOME),
        ]
    )
    assert result.supporting_model_count == 3
    assert result.usable_model_count == 3
    assert result.configured_model_count == 4
    assert result.usable_agreement_ratio == D("1")
    assert result.configured_agreement_ratio == D("0.75")
    assert result.sufficient_usable_models
    assert result.meets_configured_agreement_ratio
    assert result.unavailable_models == (ModelFamily.ML,)


def test_two_home_one_away_has_explicit_conflict() -> None:
    result = agreement(
        [
            ready(ModelFamily.POISSON, Selection.HOME),
            ready(ModelFamily.ELO, Selection.HOME),
            ready(ModelFamily.FORM, Selection.AWAY),
        ]
    )
    assert result.supporting_model_count == 2
    assert result.usable_agreement_ratio == D(2) / D(3)
    assert result.agreeing_models == (ModelFamily.POISSON, ModelFamily.ELO)
    assert result.conflicting_models == (ModelFamily.FORM,)


def test_two_home_one_neutral_keeps_neutral_usable_but_not_supporting() -> None:
    result = agreement(
        [
            ready(ModelFamily.POISSON, Selection.HOME),
            ready(ModelFamily.ELO, Selection.HOME),
            ready(ModelFamily.FORM, None),
        ]
    )
    assert result.supporting_model_count == 2
    assert result.usable_model_count == 3
    assert result.neutral_models == (ModelFamily.FORM,)
    assert ModelFamily.FORM not in result.agreeing_models
    assert ModelFamily.FORM not in result.conflicting_models


def test_one_home_two_unavailable_fails_minimum_usable_models() -> None:
    result = agreement(
        [
            ready(ModelFamily.POISSON, Selection.HOME),
            unavailable(ModelFamily.ELO),
            unavailable(ModelFamily.FORM, SignalStatus.INPUT_INSUFFICIENT),
        ]
    )
    assert result.usable_model_count == 1
    assert result.usable_agreement_ratio == D(1)
    assert not result.sufficient_usable_models
    assert result.unavailable_models == (
        ModelFamily.ELO,
        ModelFamily.FORM,
        ModelFamily.ML,
    )


def test_no_usable_models_has_no_usable_ratio() -> None:
    result = agreement([])
    assert result.supporting_model_count == 0
    assert result.usable_model_count == 0
    assert result.usable_agreement_ratio is None
    assert result.configured_agreement_ratio == 0
    assert not result.sufficient_usable_models


def test_minimum_usable_models_is_configurable_without_changing_ratio_semantics() -> None:
    config = SignalAgreementConfig(minimum_usable_models=2)
    result = agreement(
        [
            ready(ModelFamily.POISSON, Selection.HOME),
            ready(ModelFamily.ELO, Selection.HOME),
        ],
        config=config,
    )
    assert result.sufficient_usable_models
    assert result.usable_agreement_ratio == 1
    assert result.configured_agreement_ratio == D("0.5")


def test_neutral_nonprobabilistic_signals_do_not_support_draw() -> None:
    result = agreement(
        [
            ready(ModelFamily.POISSON, Selection.DRAW),
            ready(ModelFamily.ELO, None),
            ready(ModelFamily.FORM, None),
        ],
        Selection.DRAW,
    )
    assert result.supporting_model_count == 1
    assert result.agreeing_models == (ModelFamily.POISSON,)
    assert result.neutral_models == (ModelFamily.ELO, ModelFamily.FORM)


def test_synthetic_future_ml_can_explicitly_support_draw() -> None:
    result = agreement(
        [
            ready(ModelFamily.POISSON, Selection.DRAW),
            ready(ModelFamily.ELO, None),
            ready(ModelFamily.FORM, None),
            ready(ModelFamily.ML, Selection.DRAW),
        ],
        Selection.DRAW,
    )
    assert result.supporting_model_count == 2
    assert result.agreeing_models == (ModelFamily.POISSON, ModelFamily.ML)


def test_unavailable_is_not_classified_as_neutral() -> None:
    result = agreement([unavailable(ModelFamily.ELO)])
    assert result.unavailable_models == (
        ModelFamily.POISSON,
        ModelFamily.ELO,
        ModelFamily.FORM,
        ModelFamily.ML,
    )
    assert result.neutral_models == ()


def test_unsupported_signal_does_not_count_as_usable() -> None:
    result = agreement([unavailable(ModelFamily.ELO, SignalStatus.UNSUPPORTED_MARKET)])
    assert result.usable_model_count == 0
    assert ModelFamily.ELO in result.unavailable_models


def test_different_market_line_does_not_count_as_usable() -> None:
    poisson_over = ready(
        ModelFamily.POISSON,
        Selection.OVER,
        market=MarketFamily.TOTAL_GOALS,
        line=D("2.5"),
    )
    result = evaluate_agreement(
        [poisson_over],
        match_id="match",
        market=MarketFamily.TOTAL_GOALS,
        candidate_selection=Selection.OVER,
        candidate_line=D("1.5"),
    )
    assert result.usable_model_count == 0
    assert result.candidate_line == D("1.5")


def test_ambiguous_signal_does_not_count_as_usable() -> None:
    result = agreement([unavailable(ModelFamily.POISSON, SignalStatus.AMBIGUOUS)])
    assert result.usable_model_count == 0
    assert ModelFamily.POISSON in result.unavailable_models


def test_buckets_use_canonical_family_order() -> None:
    result = agreement(
        [
            ready(ModelFamily.FORM, Selection.AWAY),
            ready(ModelFamily.POISSON, Selection.HOME),
            ready(ModelFamily.ELO, None),
        ]
    )
    assert result.agreeing_models == (ModelFamily.POISSON,)
    assert result.neutral_models == (ModelFamily.ELO,)
    assert result.conflicting_models == (ModelFamily.FORM,)


def test_repeated_evaluation_and_serialization_are_deterministic() -> None:
    signals = [
        ready(ModelFamily.FORM, Selection.AWAY),
        ready(ModelFamily.POISSON, Selection.HOME),
        ready(ModelFamily.ELO, None),
    ]
    first = agreement(signals)
    second = agreement(list(reversed(signals)))
    assert first == second
    assert first.to_dict() == second.to_dict()


def test_multiple_candidate_helper_uses_home_draw_away_order() -> None:
    results = evaluate_match_result_agreement(
        [ready(ModelFamily.POISSON, Selection.DRAW)],
        match_id="match",
    )
    assert tuple(item.candidate_selection for item in results) == (
        Selection.HOME,
        Selection.DRAW,
        Selection.AWAY,
    )
    assert tuple(item.supporting_model_count for item in results) == (0, 1, 0)


def test_duplicate_family_signal_is_rejected() -> None:
    with pytest.raises(SignalValidationError, match="one signal"):
        agreement(
            [
                ready(ModelFamily.POISSON, Selection.HOME),
                ready(ModelFamily.POISSON, Selection.AWAY),
            ]
        )


def test_mismatched_match_or_market_is_rejected() -> None:
    wrong_match = replace(ready(ModelFamily.POISSON, Selection.HOME), match_id="other")
    with pytest.raises(SignalValidationError, match="match and market"):
        agreement([wrong_match])
    wrong_market = ready(
        ModelFamily.POISSON,
        Selection.YES,
        market=MarketFamily.BTTS,
    )
    with pytest.raises(SignalValidationError, match="match and market"):
        agreement([wrong_market])


def test_unconfigured_family_signal_is_rejected() -> None:
    config = SignalAgreementConfig(
        configured_model_families=(
            ModelFamily.POISSON,
            ModelFamily.ELO,
            ModelFamily.FORM,
        )
    )
    with pytest.raises(SignalValidationError, match="not configured"):
        agreement([ready(ModelFamily.ML, Selection.HOME)], config=config)


def test_default_config_is_valid_and_serializable() -> None:
    config = SignalAgreementConfig()
    assert config.required_agreement_ratio == D("0.75")
    assert config.minimum_usable_models == 3
    assert config.as_dict()["configured_model_families"] == [
        "POISSON",
        "ELO",
        "FORM",
        "ML",
    ]


@pytest.mark.parametrize(
    ("override", "message"),
    [
        (
            {
                "configured_model_families": (
                    ModelFamily.POISSON,
                    ModelFamily.POISSON,
                )
            },
            "duplicates",
        ),
        ({"minimum_usable_models": 0}, "minimum_usable_models"),
        ({"minimum_usable_models": 5}, "minimum_usable_models"),
        ({"required_agreement_ratio": D("0")}, "required_agreement_ratio"),
        ({"required_agreement_ratio": D("1.1")}, "required_agreement_ratio"),
        ({"elo_home_threshold": D("0.50")}, "Elo thresholds"),
        ({"elo_away_threshold": D("0.40")}, "symmetric"),
        ({"form_home_threshold": D("0")}, "Form thresholds"),
        ({"form_away_threshold": D("-0.20")}, "symmetric"),
        ({"poisson_ambiguity_tolerance": D("-0.1")}, "ambiguity"),
        ({"poisson_residual_mass_tolerance": D("1.1")}, "residual"),
    ],
)
def test_invalid_config_rejected(override: dict[str, object], message: str) -> None:
    with pytest.raises(SignalValidationError, match=message):
        SignalAgreementConfig(**override)  # type: ignore[arg-type]


def test_noncanonical_family_order_rejected() -> None:
    with pytest.raises(SignalValidationError, match="canonical order"):
        SignalAgreementConfig(
            configured_model_families=(
                ModelFamily.ELO,
                ModelFamily.POISSON,
                ModelFamily.FORM,
            )
        )


def test_config_override_does_not_mutate_default_instance() -> None:
    original = SignalAgreementConfig()
    changed = replace(original, minimum_usable_models=2)
    assert original.minimum_usable_models == 3
    assert changed.minimum_usable_models == 2
