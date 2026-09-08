"""Pure composition of TASK 06 features into relative form signals."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

from pitchvalue.features.contracts import FeatureAvailability, MatchFeatures, TeamFeatures
from pitchvalue.models.form.config import (
    DEFAULT_FORM_CONFIG,
    FormModelConfig,
    FormValidationError,
    MissingComponentPolicy,
)
from pitchvalue.models.form.contracts import (
    ComponentAnalysis,
    FormComponent,
    FormModelAnalysis,
    FormModelDiagnostics,
    FormModelStatus,
    TeamFormSignal,
    TeamSignalCoverage,
)
from pitchvalue.models.form.scoring import (
    score_form_component,
    score_performance_component,
    score_schedule_component,
)


def _component_weights(config: FormModelConfig) -> dict[FormComponent, Decimal]:
    weights = config.component_weights
    return {
        FormComponent.RECENT_FORM: weights.recent_form,
        FormComponent.EXTENDED_FORM: weights.extended_form,
        FormComponent.VENUE_FORM: weights.venue_form,
        FormComponent.ATTACK: weights.attack,
        FormComponent.DEFENSE: weights.defense,
        FormComponent.SCHEDULE: weights.schedule,
    }


def _team_signal(
    team: TeamFeatures,
    *,
    is_home: bool,
    league_home_rate: Decimal | None,
    league_away_rate: Decimal | None,
    league_total_rate: Decimal | None,
    config: FormModelConfig,
) -> TeamFormSignal:
    recent = score_form_component(team.recent, FormComponent.RECENT_FORM, config)
    extended = score_form_component(team.extended, FormComponent.EXTENDED_FORM, config)
    venue = score_form_component(team.venue_split, FormComponent.VENUE_FORM, config)
    overall_baseline = league_total_rate / Decimal(2) if league_total_rate is not None else None
    venue_attack_baseline = league_home_rate if is_home else league_away_rate
    venue_defense_baseline = league_away_rate if is_home else league_home_rate
    attack = score_performance_component(
        component=FormComponent.ATTACK,
        recent_rate=team.recent.goals_for_per_game,
        venue_rate=team.venue_split.goals_for_per_game,
        recent_baseline=overall_baseline,
        venue_baseline=venue_attack_baseline,
        recent_coverage=team.recent.coverage.availability,
        venue_coverage=team.venue_split.coverage.availability,
        defense=False,
        config=config,
    )
    defense = score_performance_component(
        component=FormComponent.DEFENSE,
        recent_rate=team.recent.goals_against_per_game,
        venue_rate=team.venue_split.goals_against_per_game,
        recent_baseline=overall_baseline,
        venue_baseline=venue_defense_baseline,
        recent_coverage=team.recent.coverage.availability,
        venue_coverage=team.venue_split.coverage.availability,
        defense=True,
        config=config,
    )
    schedule = score_schedule_component(team.schedule, config)
    original: tuple[ComponentAnalysis, ...] = (
        recent,
        extended,
        venue,
        attack,
        defense,
        schedule,
    )
    actual_available = tuple(component for component in original if component.score is not None)
    overall_ready = recent.score is not None or extended.score is not None
    venue_ready = venue.score is not None
    performance_ready = attack.score is not None or defense.score is not None
    reasons: list[str] = []
    if config.require_overall_form and not overall_ready:
        reasons.append("OVERALL_FORM_REQUIRED")
    if config.require_venue_form and not venue_ready:
        reasons.append("VENUE_FORM_REQUIRED")
    if config.require_attack_or_defense and not performance_ready:
        reasons.append("ATTACK_OR_DEFENSE_REQUIRED")
    if len(actual_available) < config.minimum_scored_components:
        reasons.append("MINIMUM_COMPONENTS_NOT_MET")

    components = original
    if config.missing_component_policy is MissingComponentPolicy.NEUTRAL_IMPUTE:
        components = tuple(
            component
            if component.score is not None
            else replace(
                component,
                score=config.neutral_score,
                used=True,
                reason="NEUTRAL_IMPUTED",
            )
            for component in original
        )
    weights = _component_weights(config)
    used = tuple(component for component in components if component.score is not None)
    effective_weight = sum((weights[item.component] for item in used), Decimal(0))
    weighted_score = None
    ready = not reasons and effective_weight > 0
    if ready:
        weighted_score = (
            sum(
                (item.score * weights[item.component] for item in used if item.score is not None),
                Decimal(0),
            )
            / effective_weight
        )
        if not Decimal(0) <= weighted_score <= Decimal(100):
            raise FormValidationError("weighted form score escaped 0 to 100")
    complete = sum(item.coverage is FeatureAvailability.COMPLETE for item in original)
    partial = sum(item.coverage is FeatureAvailability.PARTIAL for item in original)
    unavailable = sum(item.coverage is FeatureAvailability.UNAVAILABLE for item in original)
    by_name = {component.component: component.score for component in components}
    return TeamFormSignal(
        team_id=team.team_id,
        ready=ready,
        recent_form_score=by_name[FormComponent.RECENT_FORM],
        extended_form_score=by_name[FormComponent.EXTENDED_FORM],
        venue_form_score=by_name[FormComponent.VENUE_FORM],
        attack_score=by_name[FormComponent.ATTACK],
        defense_score=by_name[FormComponent.DEFENSE],
        schedule_score=by_name[FormComponent.SCHEDULE],
        weighted_form_score=weighted_score,
        coverage=TeamSignalCoverage(
            complete_components=complete,
            partial_components=partial,
            unavailable_components=unavailable,
            used_components=tuple(item.component for item in used),
            effective_weight_sum=effective_weight,
        ),
        components=components,
        reasons=tuple(reasons),
    )


def analyze_form_signal(
    features: MatchFeatures,
    config: FormModelConfig = DEFAULT_FORM_CONFIG,
) -> FormModelAnalysis:
    """Analyze pre-match aggregate features without history or model cross-coupling."""
    if not isinstance(features, MatchFeatures):
        raise FormValidationError("features must use MatchFeatures")
    league = features.league_baseline
    home = _team_signal(
        features.home_team,
        is_home=True,
        league_home_rate=league.home_goals_per_match,
        league_away_rate=league.away_goals_per_match,
        league_total_rate=league.total_goals_per_match,
        config=config,
    )
    away = _team_signal(
        features.away_team,
        is_home=False,
        league_home_rate=league.home_goals_per_match,
        league_away_rate=league.away_goals_per_match,
        league_total_rate=league.total_goals_per_match,
        config=config,
    )
    ready = home.ready and away.ready
    reasons = tuple(
        [f"HOME_{reason}" for reason in home.reasons]
        + [f"AWAY_{reason}" for reason in away.reasons]
    )
    difference = None
    home_relative = None
    away_relative = None
    if ready:
        assert home.weighted_form_score is not None
        assert away.weighted_form_score is not None
        difference = home.weighted_form_score - away.weighted_form_score
        home_relative = max(Decimal(-1), min(difference / Decimal(100), Decimal(1)))
        away_relative = -home_relative
    return FormModelAnalysis(
        match_id=features.target.match_id,
        home_team_id=features.target.home_team_id,
        away_team_id=features.target.away_team_id,
        status=FormModelStatus.READY if ready else FormModelStatus.INPUT_INSUFFICIENT,
        home_team=home,
        away_team=away,
        home_form_score=home.weighted_form_score,
        away_form_score=away.weighted_form_score,
        raw_form_difference=difference,
        home_relative_form_signal=home_relative,
        away_relative_form_signal=away_relative,
        diagnostics=FormModelDiagnostics(
            home_effective_weight_sum=home.coverage.effective_weight_sum,
            away_effective_weight_sum=away.coverage.effective_weight_sum,
            home_partial_components=home.coverage.partial_components,
            away_partial_components=away.coverage.partial_components,
            missing_component_policy=config.missing_component_policy.value,
            partial_coverage_policy=config.partial_coverage_policy.value,
        ),
        reasons=reasons,
    )
