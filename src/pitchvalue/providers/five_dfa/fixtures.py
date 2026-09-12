"""Current-season fixture normalization and deterministic refresh planning."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from pitchvalue.providers.five_dfa.mapping import (
    CompetitionReference,
    MappingStatus,
    TeamReference,
    map_competition,
    map_team,
)


class FixtureStatus(StrEnum):
    SCHEDULED = "scheduled"
    IN_PLAY = "in_play"
    FINISHED = "finished"
    UNKNOWN = "unknown"


class RefreshAction(StrEnum):
    ADD = "ADD"
    UNCHANGED = "UNCHANGED"
    KICKOFF_CHANGED = "KICKOFF_CHANGED"
    FINISHED = "FINISHED"
    UNKNOWN_REVIEW = "UNKNOWN_REVIEW"
    PROVIDER_ID_REPLACEMENT_REVIEW = "PROVIDER_ID_REPLACEMENT_REVIEW"
    UNSUPPORTED_COMPETITION = "UNSUPPORTED_COMPETITION"
    TEAM_MAPPING_UNRESOLVED = "TEAM_MAPPING_UNRESOLVED"
    DUPLICATE_PROVIDER_ROW = "DUPLICATE_PROVIDER_ROW"
    MISSING_SCORE = "MISSING_SCORE"


@dataclass(frozen=True)
class BasicStatistics:
    home_shots_on_target: int | None
    away_shots_on_target: int | None
    home_possession: int | None
    away_possession: int | None
    home_corners: int | None
    away_corners: int | None
    home_yellow_cards: int | None
    away_yellow_cards: int | None
    home_red_cards: int | None
    away_red_cards: int | None


@dataclass(frozen=True)
class ProviderFixture:
    provider_fixture_id: str
    competition: CompetitionReference
    home_team: TeamReference
    away_team: TeamReference
    kickoff_utc: datetime
    status: FixtureStatus
    status_reason: str | None
    status_code: str | None
    home_score: int | None
    away_score: int | None
    statistics: BasicStatistics

    def __post_init__(self) -> None:
        if self.kickoff_utc.tzinfo is None or self.kickoff_utc.utcoffset() is None:
            raise ValueError("kickoff_utc must be timezone-aware")
        if (self.home_score is None) != (self.away_score is None):
            raise ValueError("scores must be present as a pair")
        if (
            self.home_score is not None
            and self.away_score is not None
            and (self.home_score < 0 or self.away_score < 0)
        ):
            raise ValueError("scores cannot be negative")


@dataclass(frozen=True)
class ExistingFixture:
    match_id: int
    provider_fixture_ids: frozenset[str]
    competition_name: str
    home_team_id: int
    away_team_id: int
    kickoff_utc: datetime
    status: str


@dataclass(frozen=True)
class FixtureRefresh:
    provider_fixture_id: str
    match_id: int | None
    action: RefreshAction
    reason_code: str | None
    fixture: ProviderFixture


@dataclass(frozen=True)
class CurrentSeasonSyncPlan:
    refreshes: tuple[FixtureRefresh, ...]
    added: int
    changed_kickoff: int
    finished: int
    unchanged: int
    quarantined: int


def parse_runtime_fixture(
    payload: object,
    *,
    explicit_team_mappings: dict[str, int],
    provenance: str = "five_dfa_authenticated_fixture_v1",
) -> ProviderFixture:
    """Parse the runtime ``league``/``teams`` envelope without fuzzy matching."""
    if not isinstance(payload, dict):
        raise ValueError("fixture payload must be an object")
    league = payload.get("league")
    teams = payload.get("teams")
    if not isinstance(league, dict) or not isinstance(teams, dict):
        raise ValueError("runtime fixture requires league and teams objects")
    home = teams.get("home")
    away = teams.get("away")
    if not isinstance(home, dict) or not isinstance(away, dict):
        raise ValueError("runtime fixture requires home and away team objects")
    competition = map_competition(league.get("id"), league.get("name"))
    home_team = map_team(
        home.get("id"), home.get("name"), explicit_team_mappings, provenance=provenance
    )
    away_team = map_team(
        away.get("id"), away.get("name"), explicit_team_mappings, provenance=provenance
    )
    return parse_fixture(
        payload,
        competition=competition,
        home_team=home_team,
        away_team=away_team,
    )


def parse_fixture(
    payload: object,
    *,
    competition: CompetitionReference,
    home_team: TeamReference,
    away_team: TeamReference,
) -> ProviderFixture:
    if not isinstance(payload, dict):
        raise ValueError("fixture payload must be an object")
    fixture_id = _source_id(payload.get("id"), "fixture id")
    kickoff = _timestamp(payload.get("kickoff_utc"))
    raw_status = payload.get("status")
    if not isinstance(raw_status, str):
        raise ValueError("unsupported provider fixture status")
    try:
        status = FixtureStatus(raw_status)
    except ValueError as error:
        raise ValueError("unsupported provider fixture status") from error
    goals = payload.get("goals")
    home_score: int | None = None
    away_score: int | None = None
    if goals is not None:
        if not isinstance(goals, dict):
            raise ValueError("goals must be an object or null")
        home_score = _nonnegative_integer_or_none(goals.get("home"), "home score")
        away_score = _nonnegative_integer_or_none(goals.get("away"), "away score")
    return ProviderFixture(
        fixture_id,
        competition,
        home_team,
        away_team,
        kickoff,
        status,
        _optional_text(payload.get("status_reason")),
        _optional_text(payload.get("status_code")),
        home_score,
        away_score,
        normalize_statistics(payload.get("statistics"), payload),
    )


def normalize_statistics(statistics: object, fixture: object | None = None) -> BasicStatistics:
    """Map only explicit canonical fields; omission remains None, never zero."""
    values = statistics if isinstance(statistics, dict) else {}
    fixture_values = fixture if isinstance(fixture, dict) else {}
    corners = fixture_values.get("corners")
    cards = fixture_values.get("cards")
    return BasicStatistics(
        _side_integer(values, "shots_on_target", "home"),
        _side_integer(values, "shots_on_target", "away"),
        _side_integer(values, "possession", "home", maximum=100),
        _side_integer(values, "possession", "away", maximum=100),
        _nested_integer(corners, "home"),
        _nested_integer(corners, "away"),
        _card_integer(cards, "home", "yellow"),
        _card_integer(cards, "away", "yellow"),
        _card_integer(cards, "home", "red"),
        _card_integer(cards, "away", "red"),
    )


def build_sync_plan(
    incoming: tuple[ProviderFixture, ...], existing: tuple[ExistingFixture, ...]
) -> CurrentSeasonSyncPlan:
    """Plan safe canonical changes; ambiguous provider-ID replacement is quarantined."""
    existing_by_provider = {
        source_id: item for item in existing for source_id in item.provider_fixture_ids
    }
    seen: set[str] = set()
    refreshes: list[FixtureRefresh] = []
    for fixture in incoming:
        if fixture.provider_fixture_id in seen:
            refreshes.append(_refresh(fixture, None, RefreshAction.DUPLICATE_PROVIDER_ROW))
            continue
        seen.add(fixture.provider_fixture_id)
        if fixture.competition.status is not MappingStatus.RESOLVED:
            refreshes.append(_refresh(fixture, None, RefreshAction.UNSUPPORTED_COMPETITION))
            continue
        if (
            fixture.home_team.status is not MappingStatus.RESOLVED
            or fixture.away_team.status is not MappingStatus.RESOLVED
        ):
            refreshes.append(_refresh(fixture, None, RefreshAction.TEAM_MAPPING_UNRESOLVED))
            continue
        if fixture.status is FixtureStatus.FINISHED and fixture.home_score is None:
            refreshes.append(_refresh(fixture, None, RefreshAction.MISSING_SCORE))
            continue
        if fixture.status is FixtureStatus.UNKNOWN:
            refreshes.append(_refresh(fixture, None, RefreshAction.UNKNOWN_REVIEW))
            continue
        current = existing_by_provider.get(fixture.provider_fixture_id)
        if current is None:
            candidates = tuple(item for item in existing if _same_sides(item, fixture))
            if candidates:
                exact = tuple(
                    item for item in candidates if item.kickoff_utc == fixture.kickoff_utc
                )
                if len(exact) == 1:
                    current = exact[0]
                else:
                    refreshes.append(
                        _refresh(fixture, None, RefreshAction.PROVIDER_ID_REPLACEMENT_REVIEW)
                    )
                    continue
            else:
                refreshes.append(_refresh(fixture, None, RefreshAction.ADD, quarantined=False))
                continue
        if current.kickoff_utc != fixture.kickoff_utc:
            refreshes.append(
                _refresh(
                    fixture, current.match_id, RefreshAction.KICKOFF_CHANGED, quarantined=False
                )
            )
        elif fixture.status is FixtureStatus.FINISHED and current.status != "FINISHED":
            refreshes.append(
                _refresh(fixture, current.match_id, RefreshAction.FINISHED, quarantined=False)
            )
        else:
            refreshes.append(
                _refresh(fixture, current.match_id, RefreshAction.UNCHANGED, quarantined=False)
            )
    counts = {action: sum(item.action is action for item in refreshes) for action in RefreshAction}
    normal = {
        RefreshAction.ADD,
        RefreshAction.UNCHANGED,
        RefreshAction.KICKOFF_CHANGED,
        RefreshAction.FINISHED,
    }
    return CurrentSeasonSyncPlan(
        tuple(refreshes),
        counts[RefreshAction.ADD],
        counts[RefreshAction.KICKOFF_CHANGED],
        counts[RefreshAction.FINISHED],
        counts[RefreshAction.UNCHANGED],
        sum(item.action not in normal for item in refreshes),
    )


def _refresh(
    fixture: ProviderFixture,
    match_id: int | None,
    action: RefreshAction,
    *,
    quarantined: bool = True,
) -> FixtureRefresh:
    return FixtureRefresh(
        fixture.provider_fixture_id,
        match_id,
        action,
        action.value if quarantined else None,
        fixture,
    )


def _same_sides(existing: ExistingFixture, fixture: ProviderFixture) -> bool:
    return (
        existing.competition_name == fixture.competition.canonical_name
        and existing.home_team_id == fixture.home_team.canonical_team_id
        and existing.away_team_id == fixture.away_team.canonical_team_id
    )


def _timestamp(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("kickoff_utc must be an ISO-8601 string")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("kickoff_utc must include an offset")
    return parsed


def _source_id(value: object, name: str) -> str:
    if isinstance(value, bool) or not isinstance(value, (str, int)) or not str(value).strip():
        raise ValueError(f"{name} must be a nonblank source identity")
    return str(value).strip()


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _nonnegative_integer_or_none(value: object, name: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a nonnegative integer or null")
    return value


def _nested_integer(value: object, side: str) -> int | None:
    if not isinstance(value, dict):
        return None
    return _nonnegative_integer_or_none(value.get(side), f"{side} statistic")


def _side_integer(
    values: dict[object, object], metric: str, side: str, maximum: int | None = None
) -> int | None:
    container = values.get(metric)
    result = _nested_integer(container, side)
    if maximum is not None and result is not None and result > maximum:
        raise ValueError(f"{metric} must not exceed {maximum}")
    return result


def _card_integer(value: object, side: str, kind: str) -> int | None:
    if not isinstance(value, dict) or not isinstance(value.get(side), dict):
        return None
    return _nonnegative_integer_or_none(value[side].get(kind), f"{side} {kind} cards")
