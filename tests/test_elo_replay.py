from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from pitchvalue.features.contracts import (
    FeatureValidationError,
    HistoricalMatch,
    MatchStatus,
    TargetFixture,
)
from pitchvalue.models.elo.config import DEFAULT_ELO_CONFIG, EloValidationError
from pitchvalue.models.elo.rating import update_ratings
from pitchvalue.models.elo.replay import replay_elo, target_elo_snapshot

TARGET_TIME = datetime(2026, 8, 20, 18, tzinfo=UTC)
D = Decimal


def target(**overrides: object) -> TargetFixture:
    values: dict[str, object] = {
        "match_id": "target",
        "competition_id": "league",
        "season_id": "s2",
        "kickoff": TARGET_TIME,
        "home_team_id": "A",
        "away_team_id": "B",
    }
    values.update(overrides)
    return TargetFixture(**values)  # type: ignore[arg-type]


def match(
    match_id: str,
    days_before: int,
    home: str,
    away: str,
    home_score: int = 1,
    away_score: int = 0,
    *,
    season: str = "s2",
    competition: str = "league",
    status: MatchStatus = MatchStatus.FINISHED,
) -> HistoricalMatch:
    return HistoricalMatch(
        match_id,
        competition,
        season,
        TARGET_TIME - timedelta(days=days_before),
        home,
        away,
        status,
        home_score,
        away_score,
    )


def test_two_unseen_target_teams_use_initial_ratings_and_zero_counts() -> None:
    snapshot = target_elo_snapshot(target(), [], season_order=("s2",))
    assert snapshot.home_pre_match_rating == D("1500")
    assert snapshot.away_pre_match_rating == D("1500")
    assert snapshot.home_prior_match_count == 0
    assert snapshot.away_prior_match_count == 0
    assert snapshot.raw_rating_difference == 0
    assert snapshot.effective_home_rating == D("1600")
    assert snapshot.home_adjusted_rating_difference == D("100")
    assert snapshot.expected_home_score > D("0.5")


def test_one_known_and_one_unseen_team() -> None:
    snapshot = target_elo_snapshot(target(), [match("m1", 4, "A", "X")], season_order=("s2",))
    assert snapshot.home_pre_match_rating > D("1500")
    assert snapshot.home_prior_match_count == 1
    assert snapshot.away_pre_match_rating == D("1500")
    assert snapshot.away_prior_match_count == 0


def test_match_counts_track_every_processed_update() -> None:
    replay = replay_elo(
        [match("m1", 8, "A", "X"), match("m2", 4, "Y", "A")],
        competition_id="league",
        as_of=TARGET_TIME,
        season_order=("s2",),
    )
    assert replay.state_for("A").match_count == 2  # type: ignore[union-attr]
    assert replay.state_for("X").match_count == 1  # type: ignore[union-attr]


def test_pre_match_snapshots_use_only_prior_results() -> None:
    history = [match("m1", 8, "A", "B", 1, 0), match("m2", 4, "A", "C", 0, 5)]
    replay = replay_elo(
        history,
        competition_id="league",
        as_of=TARGET_TIME,
        season_order=("s2",),
        include_pre_match_snapshots=True,
    )
    first, second = replay.pre_match_snapshots
    after_first = update_ratings(D("1500"), D("1500"), 1, 0, DEFAULT_ELO_CONFIG)
    assert first.home_pre_match_rating == D("1500")
    assert first.away_pre_match_rating == D("1500")
    assert first.home_prior_match_count == 0
    assert second.home_pre_match_rating == after_first.new_home_rating
    assert second.home_prior_match_count == 1


def test_match_result_cannot_affect_its_own_pre_match_snapshot() -> None:
    common = [match("m1", 8, "A", "B", 1, 0)]
    home_win = replay_elo(
        common + [match("m2", 4, "A", "C", 8, 0)],
        competition_id="league",
        as_of=TARGET_TIME,
        season_order=("s2",),
        include_pre_match_snapshots=True,
    )
    away_win = replay_elo(
        common + [match("m2", 4, "A", "C", 0, 8)],
        competition_id="league",
        as_of=TARGET_TIME,
        season_order=("s2",),
        include_pre_match_snapshots=True,
    )
    assert home_win.pre_match_snapshots[1] == away_win.pre_match_snapshots[1]
    assert home_win.final_team_states != away_win.final_team_states


def test_shuffled_history_has_identical_replay_result() -> None:
    history = [
        match("m1", 9, "A", "X"),
        match("m2", 6, "B", "Y", 0, 1),
        match("m3", 3, "A", "B", 1, 1),
    ]
    first = replay_elo(
        history,
        competition_id="league",
        as_of=TARGET_TIME,
        season_order=("s2",),
        include_pre_match_snapshots=True,
    )
    second = replay_elo(
        [history[2], history[0], history[1]],
        competition_id="league",
        as_of=TARGET_TIME,
        season_order=("s2",),
        include_pre_match_snapshots=True,
    )
    assert first == second


def test_target_future_same_time_other_competition_and_awarded_are_ignored() -> None:
    history = [
        match("earlier", 3, "A", "X"),
        match("target", 0, "A", "B", 99, 0),
        match("same-time", 0, "A", "X", 99, 0),
        match("future", -2, "A", "X", 99, 0),
        match("cup", 2, "A", "X", 99, 0, competition="cup"),
        match("awarded", 2, "A", "X", 3, 0, status=MatchStatus.AWARDED),
        match("scheduled", 2, "A", "X", 3, 0, status=MatchStatus.SCHEDULED),
    ]
    replay = replay_elo(
        history,
        competition_id="league",
        as_of=TARGET_TIME,
        season_order=("s2",),
        target_match_id="target",
    )
    diagnostics = replay.diagnostics
    assert diagnostics.matches_processed == 1
    assert diagnostics.target_rows_ignored == 1
    assert diagnostics.same_time_rows_ignored == 1
    assert diagnostics.future_rows_ignored == 1
    assert diagnostics.different_competition_rows_ignored == 1
    assert diagnostics.awarded_rows_ignored == 1
    assert diagnostics.non_finished_rows_ignored == 1
    assert diagnostics.matches_ignored == 6
    state = replay.state_for("A")
    assert state is not None
    assert state.match_count == 1


def test_future_extreme_results_and_target_result_cannot_leak_into_snapshot() -> None:
    base = [match("m1", 5, "A", "X", 1, 0)]
    before = target_elo_snapshot(target(), base, season_order=("s2",))
    after = target_elo_snapshot(
        target(),
        base + [match("target", 0, "A", "B", 100, 0), match("future", -3, "B", "A", 0, 999)],
        season_order=("s2",),
    )
    assert after == before


def test_duplicate_match_ids_are_rejected() -> None:
    duplicate = match("m1", 3, "A", "X")
    with pytest.raises(EloValidationError, match="duplicate historical match_id"):
        replay_elo(
            [duplicate, duplicate],
            competition_id="league",
            as_of=TARGET_TIME,
            season_order=("s2",),
        )


def test_invalid_match_is_rejected_by_shared_canonical_contract() -> None:
    with pytest.raises(FeatureValidationError, match="must differ"):
        match("invalid", 3, "A", "A")


@pytest.mark.parametrize(
    ("factor", "expected"),
    [("1", None), ("0", D("1500")), ("0.5", None)],
)
def test_season_transition_regression(factor: str, expected: Decimal | None) -> None:
    config = replace(DEFAULT_ELO_CONFIG, season_regression_factor=D(factor))
    first_match = match("s1-match", 30, "A", "X", 1, 0, season="s1")
    prior_update = update_ratings(D("1500"), D("1500"), 1, 0, config)
    replay = replay_elo(
        [first_match, match("s2-match", 10, "B", "Y", season="s2")],
        competition_id="league",
        as_of=TARGET_TIME,
        season_order=("s1", "s2"),
        include_pre_match_snapshots=True,
        config=config,
    )
    state = replay.state_for("A")
    assert state is not None
    expected_rating = (
        prior_update.new_home_rating
        if factor == "1"
        else D("1500")
        if factor == "0"
        else D("1500") + D("0.5") * (prior_update.new_home_rating - D("1500"))
    )
    assert state.rating == (expected if expected is not None else expected_rating)
    assert replay.diagnostics.season_transitions_applied == 1


def test_season_transition_is_applied_once_not_per_match() -> None:
    replay = replay_elo(
        [
            match("s1", 30, "A", "X", season="s1"),
            match("s2-first", 10, "B", "Y", season="s2"),
            match("s2-second", 5, "A", "B", season="s2"),
        ],
        competition_id="league",
        as_of=TARGET_TIME,
        season_order=("s1", "s2"),
    )
    assert replay.diagnostics.season_transitions_applied == 1


def test_first_observed_season_does_not_regress_initial_ratings() -> None:
    replay = replay_elo(
        [match("first", 5, "A", "B")],
        competition_id="league",
        as_of=TARGET_TIME,
        season_order=("s2",),
        include_pre_match_snapshots=True,
    )
    assert replay.pre_match_snapshots[0].home_pre_match_rating == D("1500")
    assert replay.diagnostics.season_transitions_applied == 0


def test_season_ids_are_never_guessed() -> None:
    with pytest.raises(EloValidationError, match="absent from explicit season_order"):
        replay_elo(
            [match("unknown", 5, "A", "B", season="2025")],
            competition_id="league",
            as_of=TARGET_TIME,
            season_order=("2026",),
        )


def test_explicit_season_order_must_agree_with_match_chronology() -> None:
    history = [
        match("newer-id", 10, "A", "B", season="s2"),
        match("later-kickoff", 5, "A", "B", season="s1"),
    ]
    with pytest.raises(EloValidationError, match="chronology conflicts"):
        replay_elo(
            history,
            competition_id="league",
            as_of=TARGET_TIME,
            season_order=("s1", "s2"),
        )


def test_target_season_transition_occurs_without_target_result() -> None:
    config = replace(DEFAULT_ELO_CONFIG, season_regression_factor=D("0"))
    snapshot = target_elo_snapshot(
        target(),
        [match("s1", 30, "A", "X", 1, 0, season="s1")],
        season_order=("s1", "s2"),
        config=config,
    )
    assert snapshot.home_pre_match_rating == D("1500")
    assert snapshot.home_prior_match_count == 1


def test_replay_and_snapshot_serialization_are_deterministic() -> None:
    replay = replay_elo(
        [match("m1", 5, "A", "B")],
        competition_id="league",
        as_of=TARGET_TIME,
        season_order=("s2",),
        include_pre_match_snapshots=True,
    )
    snapshot = target_elo_snapshot(target(), [], season_order=("s2",))
    assert replay.to_dict() == replay.to_dict()
    assert replay.to_dict()["diagnostics"]["matches_processed"] == 1
    assert snapshot.to_dict()["as_of"] == TARGET_TIME.isoformat()


def test_replay_does_not_mutate_input_list_or_matches() -> None:
    history = [match("later", 3, "A", "B"), match("earlier", 6, "A", "X")]
    original = list(history)
    replay_elo(
        history,
        competition_id="league",
        as_of=TARGET_TIME,
        season_order=("s2",),
    )
    assert history == original
    assert history[0].match_id == "later"
