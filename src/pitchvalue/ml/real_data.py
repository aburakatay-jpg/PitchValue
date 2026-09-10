"""Read-only adapter from canonical matches to TASK 15 ML dataset contracts."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import Connection, text

from pitchvalue.features import compute_match_features
from pitchvalue.features.contracts import HistoricalMatch, MatchStatus, TargetFixture, TeamForm
from pitchvalue.ml.config import DatasetBuilderConfig, FeatureProfile, FeatureSchema
from pitchvalue.ml.contracts import (
    FeatureKind,
    FeatureRecord,
    MissingReason,
    MLDataset,
    ResolvedMatchOutcome,
    TargetDefinition,
    TargetMode,
    TrainingCandidate,
)
from pitchvalue.ml.dataset import build_dataset
from pitchvalue.ml.provenance import DatasetRowProvenance, FeatureProvenance, SourceMatchReference
from pitchvalue.models.elo import target_elo_snapshot
from pitchvalue.prediction.contracts import MarketFamily, Selection

REAL_FEATURE_SCHEMA_VERSION = "football_performance_match_result_v1"
REAL_DATASET_VERSION = "historical_match_result_v1"
REAL_SOURCE_VERSION = "canonical_domestic_history_v1"

FORM_FIELDS = (
    "points_per_game",
    "goals_for_per_game",
    "goals_against_per_game",
    "goal_difference_per_game",
    "clean_sheet_rate",
    "failed_to_score_rate",
    "btts_rate",
    "over_1_5_rate",
    "over_2_5_rate",
)

BASELINE_FEATURE_NAMES = (
    "elo_home_rating",
    "elo_away_rating",
    "elo_rating_difference",
    "elo_expected_home_score",
    *(f"home_recent_{name}" for name in FORM_FIELDS),
    *(f"away_recent_{name}" for name in FORM_FIELDS),
    "home_extended_points_per_game",
    "home_extended_goals_for_per_game",
    "home_extended_goals_against_per_game",
    "away_extended_points_per_game",
    "away_extended_goals_for_per_game",
    "away_extended_goals_against_per_game",
    "home_venue_points_per_game",
    "home_venue_goals_for_per_game",
    "home_venue_goals_against_per_game",
    "away_venue_points_per_game",
    "away_venue_goals_for_per_game",
    "away_venue_goals_against_per_game",
    "home_days_since_previous_match",
    "away_days_since_previous_match",
    "home_density_7_days",
    "home_density_14_days",
    "away_density_7_days",
    "away_density_14_days",
    "league_home_goals_per_match",
    "league_away_goals_per_match",
    "league_total_goals_per_match",
    "league_home_win_rate",
    "league_draw_rate",
    "league_away_win_rate",
    "league_btts_rate",
    "league_over_2_5_rate",
)

MATCH_RESULT_TARGET = TargetDefinition(
    MarketFamily.MATCH_RESULT,
    TargetMode.MULTICLASS,
    (Selection.HOME, Selection.DRAW, Selection.AWAY),
)


@dataclass(frozen=True)
class RealDatasetBuild:
    dataset: MLDataset
    canonical_match_count: int
    complete_count: int
    partial_count: int
    unavailable_count: int
    competition_labels: tuple[tuple[str, str], ...]
    season_labels: tuple[tuple[str, str], ...]


def load_real_match_result_dataset(connection: Connection) -> RealDatasetBuild:
    """Build football-only rows without querying odds or writing canonical data."""
    history, competition_seasons, competition_labels, season_labels = _load_history(connection)
    candidates: list[TrainingCandidate] = []
    complete = partial = unavailable = 0
    for match in history:
        prediction_as_of = match.kickoff - timedelta(days=1)
        target = TargetFixture(
            match.match_id,
            match.competition_id,
            match.season_id,
            match.kickoff,
            match.home_team_id,
            match.away_team_id,
            prediction_as_of,
        )
        computed = compute_match_features(target, history)
        elo = target_elo_snapshot(
            target,
            history,
            season_order=competition_seasons[match.competition_id],
        )
        source_matches = tuple(
            SourceMatchReference(item.match_id, item.kickoff)
            for item in history
            if item.competition_id == match.competition_id
            and item.kickoff < prediction_as_of
            and item.status is MatchStatus.FINISHED
        )
        provenance = FeatureProvenance(
            "task06-task07-v1",
            "pitchvalue.features+pitchvalue.models.elo",
            REAL_SOURCE_VERSION,
            "football-performance-match-result-v1",
            source_matches,
        )
        values = _feature_values(computed, elo)
        missing = sum(value is None for value in values.values())
        if missing == 0:
            complete += 1
        elif missing == len(values):
            unavailable += 1
        else:
            partial += 1
        records = tuple(
            FeatureRecord(
                name,
                values[name],
                prediction_as_of,
                REAL_FEATURE_SCHEMA_VERSION,
                provenance,
                FeatureKind.FOOTBALL_PERFORMANCE,
                MissingReason.INSUFFICIENT_HISTORY if values[name] is None else None,
            )
            for name in BASELINE_FEATURE_NAMES
        )
        assert match.home_score is not None and match.away_score is not None
        candidates.append(
            TrainingCandidate(
                match.match_id,
                match.competition_id,
                match.season_id,
                match.kickoff,
                prediction_as_of,
                MATCH_RESULT_TARGET,
                ResolvedMatchOutcome(
                    match.match_id, MatchStatus.FINISHED, match.home_score, match.away_score
                ),
                records,
                DatasetRowProvenance(REAL_SOURCE_VERSION, "task16-real-adapter-v1"),
            )
        )
    config = DatasetBuilderConfig(
        REAL_DATASET_VERSION,
        FeatureSchema(REAL_FEATURE_SCHEMA_VERSION, BASELINE_FEATURE_NAMES),
        FeatureProfile.FOOTBALL_PERFORMANCE_ONLY,
    )
    return RealDatasetBuild(
        build_dataset(candidates, config),
        len(history),
        complete,
        partial,
        unavailable,
        competition_labels,
        season_labels,
    )


def _load_history(
    connection: Connection,
) -> tuple[
    tuple[HistoricalMatch, ...],
    dict[str, tuple[str, ...]],
    tuple[tuple[str, str], ...],
    tuple[tuple[str, str], ...],
]:
    rows = connection.execute(
        text(
            """
            SELECT m.match_id,m.competition_id,m.season_id,m.kickoff_at_utc,
                   m.home_team_id,m.away_team_id,m.status,m.home_score,m.away_score,
                   s.start_year,c.canonical_name,s.season_name
            FROM matches m
            JOIN competitions c ON c.competition_id=m.competition_id
            JOIN seasons s ON s.season_id=m.season_id
            WHERE c.competition_type='domestic_league'
              AND m.status='FINISHED'
              AND m.kickoff_at_utc IS NOT NULL
            ORDER BY m.kickoff_at_utc,m.match_id
            """
        )
    ).mappings()
    history: list[HistoricalMatch] = []
    seasons: dict[str, dict[str, int]] = defaultdict(dict)
    competition_names: dict[str, str] = {}
    season_names: dict[str, str] = {}
    for row in rows:
        competition_id = str(row["competition_id"])
        season_id = str(row["season_id"])
        seasons[competition_id][season_id] = int(row["start_year"])
        competition_names[competition_id] = str(row["canonical_name"])
        season_names[season_id] = str(row["season_name"])
        history.append(
            HistoricalMatch(
                str(row["match_id"]),
                competition_id,
                season_id,
                row["kickoff_at_utc"],
                str(row["home_team_id"]),
                str(row["away_team_id"]),
                MatchStatus(row["status"]),
                row["home_score"],
                row["away_score"],
            )
        )
    season_order = {
        competition: tuple(
            season for season, _ in sorted(items.items(), key=lambda item: (item[1], item[0]))
        )
        for competition, items in seasons.items()
    }
    return (
        tuple(history),
        season_order,
        tuple(sorted(competition_names.items())),
        tuple(sorted(season_names.items())),
    )


def _feature_values(features: object, elo: object) -> dict[str, Decimal | int | bool | None]:
    # Concrete attribute access stays centralized here so TASK 15 sees only typed scalar records.
    from pitchvalue.features.contracts import MatchFeatures
    from pitchvalue.models.elo.contracts import EloSnapshot

    assert isinstance(features, MatchFeatures)
    assert isinstance(elo, EloSnapshot)
    result: dict[str, Decimal | int | bool | None] = {
        "elo_home_rating": elo.home_pre_match_rating,
        "elo_away_rating": elo.away_pre_match_rating,
        "elo_rating_difference": elo.raw_rating_difference,
        "elo_expected_home_score": elo.expected_home_score,
    }
    _add_form(result, "home_recent", features.home_team.recent)
    _add_form(result, "away_recent", features.away_team.recent)
    for side, form in (
        ("home_extended", features.home_team.extended),
        ("away_extended", features.away_team.extended),
        ("home_venue", features.home_team.venue_split),
        ("away_venue", features.away_team.venue_split),
    ):
        result[f"{side}_points_per_game"] = form.points_per_game
        result[f"{side}_goals_for_per_game"] = form.goals_for_per_game
        result[f"{side}_goals_against_per_game"] = form.goals_against_per_game
    result["home_days_since_previous_match"] = features.home_team.schedule.days_since_previous_match
    result["away_days_since_previous_match"] = features.away_team.schedule.days_since_previous_match
    for side, schedule in (
        ("home", features.home_team.schedule),
        ("away", features.away_team.schedule),
    ):
        for density in schedule.density:
            result[f"{side}_density_{density.window_days}_days"] = density.match_count
    league = features.league_baseline
    result.update(
        {
            "league_home_goals_per_match": league.home_goals_per_match,
            "league_away_goals_per_match": league.away_goals_per_match,
            "league_total_goals_per_match": league.total_goals_per_match,
            "league_home_win_rate": league.home_win_rate,
            "league_draw_rate": league.draw_rate,
            "league_away_win_rate": league.away_win_rate,
            "league_btts_rate": league.btts_rate,
            "league_over_2_5_rate": league.over_2_5_rate,
        }
    )
    return result


def _add_form(result: dict[str, Decimal | int | bool | None], prefix: str, form: TeamForm) -> None:
    for name in FORM_FIELDS:
        result[f"{prefix}_{name}"] = getattr(form, name)
