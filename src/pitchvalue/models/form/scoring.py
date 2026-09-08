"""Pure Decimal normalization and component scoring functions."""

from __future__ import annotations

from decimal import Decimal

from pitchvalue.features.contracts import (
    FeatureAvailability,
    TeamForm,
    TeamSchedule,
)
from pitchvalue.models.form.config import (
    FormModelConfig,
    FormValidationError,
    PartialCoveragePolicy,
)
from pitchvalue.models.form.contracts import (
    ComponentAnalysis,
    DiagnosticMetric,
    FormComponent,
)


def _score(value: Decimal) -> Decimal:
    if value < 0:
        return Decimal(0)
    if value > 100:
        return Decimal(100)
    return value


def normalize_ppg(ppg: Decimal) -> Decimal:
    if not isinstance(ppg, Decimal) or not ppg.is_finite() or not Decimal(0) <= ppg <= 3:
        raise FormValidationError("PPG must be a Decimal between 0 and 3")
    return ppg / Decimal(3) * Decimal(100)


def normalize_goal_difference(value: Decimal, config: FormModelConfig) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise FormValidationError("goal difference must be a finite Decimal")
    position = (value - config.goal_difference_minimum) / (
        config.goal_difference_maximum - config.goal_difference_minimum
    )
    return _score(position * Decimal(100))


def normalize_attack_ratio(value: Decimal, config: FormModelConfig) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite() or value < 0:
        raise FormValidationError("attack ratio must be a non-negative finite Decimal")
    return _score(value / config.attack_ratio_maximum * Decimal(100))


def normalize_defense_ratio(value: Decimal, config: FormModelConfig) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite() or value < 0:
        raise FormValidationError("defense ratio must be a non-negative finite Decimal")
    return _score(
        (config.defense_ratio_maximum - value) / config.defense_ratio_maximum * Decimal(100)
    )


def _coverage_allowed(coverage: FeatureAvailability, config: FormModelConfig) -> bool:
    return coverage is FeatureAvailability.COMPLETE or (
        coverage is FeatureAvailability.PARTIAL
        and config.partial_coverage_policy is PartialCoveragePolicy.USE_PARTIAL
    )


def score_form_component(
    aggregate: TeamForm,
    component: FormComponent,
    config: FormModelConfig,
) -> ComponentAnalysis:
    inputs = (
        DiagnosticMetric("points_per_game", aggregate.points_per_game),
        DiagnosticMetric("goal_difference_per_game", aggregate.goal_difference_per_game),
    )
    if not _coverage_allowed(aggregate.coverage.availability, config):
        return ComponentAnalysis(
            component,
            None,
            aggregate.coverage.availability,
            False,
            "COVERAGE_EXCLUDED",
            inputs,
            (),
        )
    if aggregate.points_per_game is None or aggregate.goal_difference_per_game is None:
        return ComponentAnalysis(
            component,
            None,
            aggregate.coverage.availability,
            False,
            "FORM_INPUT_MISSING",
            inputs,
            (),
        )
    ppg_score = normalize_ppg(aggregate.points_per_game)
    gd_score = normalize_goal_difference(aggregate.goal_difference_per_game, config)
    weights = config.form_inner_weights
    score = ppg_score * weights.primary + gd_score * weights.secondary
    return ComponentAnalysis(
        component,
        _score(score),
        aggregate.coverage.availability,
        True,
        None,
        inputs,
        (
            DiagnosticMetric("normalized_ppg", ppg_score),
            DiagnosticMetric("normalized_goal_difference", gd_score),
        ),
    )


def _combined_coverage(
    first_available: bool,
    second_available: bool,
    first_coverage: FeatureAvailability,
    second_coverage: FeatureAvailability,
) -> FeatureAvailability:
    if not first_available and not second_available:
        return FeatureAvailability.UNAVAILABLE
    if (
        first_available
        and second_available
        and first_coverage is FeatureAvailability.COMPLETE
        and second_coverage is FeatureAvailability.COMPLETE
    ):
        return FeatureAvailability.COMPLETE
    return FeatureAvailability.PARTIAL


def score_performance_component(
    *,
    component: FormComponent,
    recent_rate: Decimal | None,
    venue_rate: Decimal | None,
    recent_baseline: Decimal | None,
    venue_baseline: Decimal | None,
    recent_coverage: FeatureAvailability,
    venue_coverage: FeatureAvailability,
    defense: bool,
    config: FormModelConfig,
) -> ComponentAnalysis:
    recent_available = recent_rate is not None and recent_baseline is not None
    venue_available = venue_rate is not None and venue_baseline is not None
    coverage = _combined_coverage(
        recent_available,
        venue_available,
        recent_coverage,
        venue_coverage,
    )
    inputs = (
        DiagnosticMetric("recent_rate", recent_rate),
        DiagnosticMetric("recent_baseline", recent_baseline),
        DiagnosticMetric("venue_rate", venue_rate),
        DiagnosticMetric("venue_baseline", venue_baseline),
    )
    if not _coverage_allowed(coverage, config):
        return ComponentAnalysis(component, None, coverage, False, "COVERAGE_EXCLUDED", inputs, ())
    scores: list[tuple[Decimal, Decimal, str, Decimal]] = []
    weights = config.performance_inner_weights
    if recent_available:
        assert recent_rate is not None and recent_baseline is not None
        if recent_baseline <= 0:
            raise FormValidationError("recent league baseline must be positive")
        ratio = recent_rate / recent_baseline
        normalized = (
            normalize_defense_ratio(ratio, config)
            if defense
            else normalize_attack_ratio(ratio, config)
        )
        scores.append((normalized, weights.primary, "recent_ratio", ratio))
    if venue_available:
        assert venue_rate is not None and venue_baseline is not None
        if venue_baseline <= 0:
            raise FormValidationError("venue league baseline must be positive")
        ratio = venue_rate / venue_baseline
        normalized = (
            normalize_defense_ratio(ratio, config)
            if defense
            else normalize_attack_ratio(ratio, config)
        )
        scores.append((normalized, weights.secondary, "venue_ratio", ratio))
    if not scores:
        return ComponentAnalysis(
            component, None, coverage, False, "PERFORMANCE_INPUT_MISSING", inputs, ()
        )
    denominator = sum((weight for _, weight, _, _ in scores), Decimal(0))
    score = sum((value * weight for value, weight, _, _ in scores), Decimal(0)) / denominator
    return ComponentAnalysis(
        component,
        _score(score),
        coverage,
        True,
        None,
        inputs,
        tuple(DiagnosticMetric(name, ratio) for _, _, name, ratio in scores)
        + tuple(DiagnosticMetric(f"normalized_{name}", value) for value, _, name, _ in scores),
    )


def score_schedule_component(
    schedule: TeamSchedule,
    config: FormModelConfig,
) -> ComponentAnalysis:
    density = {item.window_days: item.match_count for item in schedule.density}
    inputs = (
        DiagnosticMetric("rest_days", schedule.days_since_previous_match),
        DiagnosticMetric("matches_in_7_days", density.get(7)),
        DiagnosticMetric("matches_in_14_days", density.get(14)),
    )
    if schedule.days_since_previous_match is None:
        return ComponentAnalysis(
            FormComponent.SCHEDULE,
            None,
            FeatureAvailability.UNAVAILABLE,
            False,
            "REST_MISSING",
            inputs,
            (),
        )
    coverage = (
        FeatureAvailability.COMPLETE
        if 7 in density and 14 in density
        else FeatureAvailability.PARTIAL
    )
    if not _coverage_allowed(coverage, config):
        return ComponentAnalysis(
            FormComponent.SCHEDULE,
            None,
            coverage,
            False,
            "COVERAGE_EXCLUDED",
            inputs,
            (),
        )
    score = config.neutral_score
    if schedule.days_since_previous_match < config.short_rest_days:
        score -= config.short_rest_penalty
    elif schedule.days_since_previous_match >= config.adequate_rest_days:
        score += config.adequate_rest_bonus
    score -= Decimal(max(density.get(7, 0) - config.congestion_7_day_threshold, 0)) * (
        config.congestion_7_day_penalty
    )
    score -= Decimal(max(density.get(14, 0) - config.congestion_14_day_threshold, 0)) * (
        config.congestion_14_day_penalty
    )
    score = max(config.schedule_score_minimum, min(score, config.schedule_score_maximum))
    return ComponentAnalysis(
        FormComponent.SCHEDULE,
        score,
        coverage,
        True,
        None,
        inputs,
        (DiagnosticMetric("bounded_schedule_score", score),),
    )
