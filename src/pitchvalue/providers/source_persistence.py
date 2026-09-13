"""Provider-neutral current-season source identity and fixture persistence."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import Connection, text

from pitchvalue.ingestion.football_data_uk.canonical import normalize_team_name
from pitchvalue.providers.five_dfa.fixtures import FixtureStatus, ProviderFixture
from pitchvalue.providers.lifecycle import (
    CanonicalFixtureState,
    LifecycleDecision,
    evaluate_transition,
    kickoff_revision_allowed,
)


class FixtureWriteStatus(StrEnum):
    INSERTED = "INSERTED"
    UNCHANGED = "UNCHANGED"
    KICKOFF_REVISED = "KICKOFF_REVISED"
    FINISHED = "FINISHED"
    RESULT_REVISION_REVIEW = "RESULT_REVISION_REVIEW"
    LIFECYCLE_REVIEW = "LIFECYCLE_REVIEW"
    PROVIDER_ID_REPLACEMENT_REVIEW = "PROVIDER_ID_REPLACEMENT_REVIEW"


@dataclass(frozen=True)
class FixtureWriteResult:
    status: FixtureWriteStatus
    match_id: int | None
    source_entity_ref_id: int


def ensure_provider(connection: Connection, name: str, *, plan: str) -> int:
    """Create/reuse one source provider; plan is metadata, never a credential."""
    return int(
        connection.execute(
            text(
                """INSERT INTO providers (
                    name, provider_type, base_url, license_type, priority, active
                ) VALUES (:name, 'fixture_and_odds', NULL, :plan, 50, true)
                ON CONFLICT (name) DO UPDATE SET
                    license_type = EXCLUDED.license_type,
                    active = true,
                    updated_at = now()
                RETURNING provider_id"""
            ),
            {"name": name, "plan": plan},
        ).scalar_one()
    )


def resolve_explicit_team_mappings(connection: Connection, provider_id: int) -> dict[str, int]:
    """Read only reviewed provider IDs; canonical/alias names are discovery candidates only."""
    rows = connection.execute(
        text(
            """SELECT provider_entity_id, canonical_team_id
            FROM source_entity_references
            WHERE provider_id=:provider_id AND entity_type='TEAM'
              AND mapping_status='RESOLVED' AND canonical_team_id IS NOT NULL"""
        ),
        {"provider_id": provider_id},
    )
    return {str(source_id): int(team_id) for source_id, team_id in rows}


def discover_team_candidate(connection: Connection, provider_name: str) -> int | None:
    normalized = normalize_team_name(provider_name)
    rows = connection.execute(
        text(
            """SELECT team_id FROM teams WHERE normalized_name=:name
            UNION
            SELECT team_id FROM team_aliases WHERE normalized_alias=:name"""
        ),
        {"name": normalized},
    ).scalars()
    candidates = tuple(sorted({int(value) for value in rows}))
    return candidates[0] if len(candidates) == 1 else None


def upsert_source_reference(
    connection: Connection,
    *,
    provider_id: int,
    entity_type: str,
    provider_entity_id: str,
    provider_display_name: str,
    mapping_status: str,
    mapping_version: str,
    provenance: str,
    seen_at: datetime,
    canonical_competition_id: int | None = None,
    canonical_team_id: int | None = None,
    canonical_match_id: int | None = None,
    payload: object | None = None,
) -> int:
    payload_hash = None
    if payload is not None:
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        payload_hash = hashlib.sha256(canonical.encode()).hexdigest()
    return int(
        connection.execute(
            text(
                """INSERT INTO source_entity_references (
                    provider_id, entity_type, provider_entity_id, provider_display_name,
                    canonical_competition_id, canonical_team_id, canonical_match_id,
                    mapping_status, mapping_version, provenance, source_payload_hash,
                    first_seen_at, last_seen_at
                ) VALUES (
                    :provider_id, :entity_type, :provider_entity_id, :provider_display_name,
                    :canonical_competition_id, :canonical_team_id, :canonical_match_id,
                    :mapping_status, :mapping_version, :provenance, :payload_hash,
                    :seen_at, :seen_at
                ) ON CONFLICT (provider_id, entity_type, provider_entity_id) DO UPDATE SET
                    provider_display_name=EXCLUDED.provider_display_name,
                    last_seen_at=GREATEST(
                        source_entity_references.last_seen_at, EXCLUDED.last_seen_at
                    ),
                    source_payload_hash=EXCLUDED.source_payload_hash,
                    canonical_competition_id=COALESCE(
                        source_entity_references.canonical_competition_id,
                        EXCLUDED.canonical_competition_id
                    ),
                    canonical_team_id=COALESCE(
                        source_entity_references.canonical_team_id, EXCLUDED.canonical_team_id
                    ),
                    canonical_match_id=COALESCE(
                        source_entity_references.canonical_match_id, EXCLUDED.canonical_match_id
                    ),
                    mapping_status=CASE
                        WHEN source_entity_references.mapping_status='RESOLVED'
                        THEN 'RESOLVED' ELSE EXCLUDED.mapping_status END,
                    mapping_version=EXCLUDED.mapping_version,
                    provenance=EXCLUDED.provenance
                RETURNING source_entity_ref_id"""
            ),
            {
                "provider_id": provider_id,
                "entity_type": entity_type,
                "provider_entity_id": provider_entity_id,
                "provider_display_name": provider_display_name,
                "canonical_competition_id": canonical_competition_id,
                "canonical_team_id": canonical_team_id,
                "canonical_match_id": canonical_match_id,
                "mapping_status": mapping_status,
                "mapping_version": mapping_version,
                "provenance": provenance,
                "payload_hash": payload_hash,
                "seen_at": seen_at,
            },
        ).scalar_one()
    )


def assign_team_reference(
    connection: Connection, source_entity_ref_id: int, team_id: int, *, mapping_version: str
) -> None:
    """Operator review path: explicitly bind one provider team identity."""
    changed = connection.execute(
        text(
            """UPDATE source_entity_references SET canonical_team_id=:team_id,
            mapping_status='RESOLVED', mapping_version=:mapping_version
            WHERE source_entity_ref_id=:reference_id AND entity_type='TEAM'"""
        ),
        {
            "team_id": team_id,
            "mapping_version": mapping_version,
            "reference_id": source_entity_ref_id,
        },
    ).rowcount
    if changed != 1:
        raise ValueError("team source reference was not found")


def ensure_season(
    connection: Connection, competition_id: int, name: str = "2026/27"
) -> tuple[int, bool]:
    inserted = connection.execute(
        text(
            """INSERT INTO seasons (
                competition_id, season_name, start_year, end_year, status
            ) VALUES (:competition_id, :name, 2026, 2027, 'current')
            ON CONFLICT (competition_id, season_name) DO NOTHING RETURNING season_id"""
        ),
        {"competition_id": competition_id, "name": name},
    ).scalar_one_or_none()
    if inserted is not None:
        return int(inserted), True
    season_id = connection.execute(
        text(
            """SELECT season_id FROM seasons
            WHERE competition_id=:competition_id AND season_name=:name"""
        ),
        {"competition_id": competition_id, "name": name},
    ).scalar_one()
    return int(season_id), False


def persist_fixture(
    connection: Connection,
    fixture: ProviderFixture,
    *,
    provider_id: int,
    competition_id: int,
    season_id: int,
    mapping_version: str,
    seen_at: datetime,
) -> FixtureWriteResult:
    """Persist one resolved fixture atomically without silently revising final results."""
    if fixture.home_team.canonical_team_id is None or fixture.away_team.canonical_team_id is None:
        raise ValueError("fixture teams must be explicitly resolved")
    with connection.begin_nested():
        existing = (
            connection.execute(
                text(
                    """SELECT m.match_id,m.kickoff_at_utc,m.status,m.home_score,m.away_score
                FROM match_provider_refs r JOIN matches m ON m.match_id=r.match_id
                WHERE r.provider_id=:provider_id AND r.provider_match_id=:provider_match_id"""
                ),
                {"provider_id": provider_id, "provider_match_id": fixture.provider_fixture_id},
            )
            .mappings()
            .one_or_none()
        )
        status = _canonical_status(fixture.status)
        result = _result(fixture.home_score, fixture.away_score) if status == "FINISHED" else None
        if existing is None:
            candidate = connection.execute(
                text(
                    """SELECT match_id FROM matches WHERE competition_id=:competition_id
                    AND season_id=:season_id AND home_team_id=:home_team_id
                    AND away_team_id=:away_team_id AND kickoff_at_utc=:kickoff"""
                ),
                {
                    "competition_id": competition_id,
                    "season_id": season_id,
                    "home_team_id": fixture.home_team.canonical_team_id,
                    "away_team_id": fixture.away_team.canonical_team_id,
                    "kickoff": fixture.kickoff_utc,
                },
            ).scalar_one_or_none()
            if candidate is not None:
                source_ref = upsert_source_reference(
                    connection,
                    provider_id=provider_id,
                    entity_type="FIXTURE",
                    provider_entity_id=fixture.provider_fixture_id,
                    provider_display_name=_fixture_name(fixture),
                    mapping_status="REVIEW_REQUIRED",
                    mapping_version=mapping_version,
                    provenance="provider_fixture_sync_v1",
                    seen_at=seen_at,
                )
                return FixtureWriteResult(
                    FixtureWriteStatus.PROVIDER_ID_REPLACEMENT_REVIEW, None, source_ref
                )
            match_id = int(
                connection.execute(
                    text(
                        """INSERT INTO matches (
                competition_id,season_id,kickoff_at_utc,kickoff_timezone,
                home_team_id,away_team_id,status,home_score,away_score,result,decided_by)
                VALUES (:competition_id,:season_id,:kickoff,'UTC',:home_team_id,:away_team_id,
                :status,:home_score,:away_score,:result,:decided_by) RETURNING match_id"""
                    ),
                    {
                        "competition_id": competition_id,
                        "season_id": season_id,
                        "kickoff": fixture.kickoff_utc,
                        "home_team_id": fixture.home_team.canonical_team_id,
                        "away_team_id": fixture.away_team.canonical_team_id,
                        "status": status,
                        "home_score": fixture.home_score if status == "FINISHED" else None,
                        "away_score": fixture.away_score if status == "FINISHED" else None,
                        "result": result,
                        "decided_by": "regular_time" if status == "FINISHED" else None,
                    },
                ).scalar_one()
            )
            connection.execute(
                text(
                    """INSERT INTO match_provider_refs (match_id,provider_id,provider_match_id)
                VALUES (:match_id,:provider_id,:provider_match_id)"""
                ),
                {
                    "match_id": match_id,
                    "provider_id": provider_id,
                    "provider_match_id": fixture.provider_fixture_id,
                },
            )
            write_status = FixtureWriteStatus.INSERTED
        else:
            match_id = int(existing["match_id"])
            current_state = CanonicalFixtureState(str(existing["status"]))
            incoming_state = _provider_lifecycle(fixture.status)
            if incoming_state is None:
                source_ref = _fixture_reference(
                    connection, fixture, provider_id, match_id, mapping_version, seen_at
                )
                return FixtureWriteResult(FixtureWriteStatus.LIFECYCLE_REVIEW, match_id, source_ref)
            result_changed = (
                current_state is CanonicalFixtureState.FINISHED
                and incoming_state is CanonicalFixtureState.FINISHED
                and (existing["home_score"], existing["away_score"])
                != (fixture.home_score, fixture.away_score)
            )
            transition = evaluate_transition(
                current_state, incoming_state, result_changed=result_changed
            )
            if transition.decision is LifecycleDecision.REVIEW_REQUIRED:
                source_ref = _fixture_reference(
                    connection, fixture, provider_id, match_id, mapping_version, seen_at
                )
                review_status = (
                    FixtureWriteStatus.RESULT_REVISION_REVIEW
                    if transition.reason == "RESULT_REVISION_REVIEW"
                    else FixtureWriteStatus.LIFECYCLE_REVIEW
                )
                return FixtureWriteResult(review_status, match_id, source_ref)
            kickoff_changed = existing["kickoff_at_utc"] != fixture.kickoff_utc
            if kickoff_changed and not kickoff_revision_allowed(current_state):
                source_ref = _fixture_reference(
                    connection, fixture, provider_id, match_id, mapping_version, seen_at
                )
                return FixtureWriteResult(FixtureWriteStatus.LIFECYCLE_REVIEW, match_id, source_ref)
            if status == "FINISHED" and existing["status"] != "FINISHED":
                connection.execute(
                    text(
                        """UPDATE matches SET kickoff_at_utc=:kickoff,status='FINISHED',
                        home_score=:home_score,away_score=:away_score,result=:result,
                        decided_by='regular_time',updated_at=now()
                        WHERE match_id=:match_id"""
                    ),
                    {
                        "kickoff": fixture.kickoff_utc,
                        "home_score": fixture.home_score,
                        "away_score": fixture.away_score,
                        "result": result,
                        "match_id": match_id,
                    },
                )
                write_status = FixtureWriteStatus.FINISHED
            elif kickoff_changed:
                connection.execute(
                    text(
                        """UPDATE matches SET kickoff_at_utc=:kickoff,updated_at=now()
                        WHERE match_id=:match_id"""
                    ),
                    {
                        "kickoff": fixture.kickoff_utc,
                        "match_id": match_id,
                    },
                )
                write_status = FixtureWriteStatus.KICKOFF_REVISED
            else:
                write_status = FixtureWriteStatus.UNCHANGED
        source_ref = _fixture_reference(
            connection, fixture, provider_id, match_id, mapping_version, seen_at
        )
        _persist_statistics(connection, match_id, provider_id, fixture)
    return FixtureWriteResult(write_status, match_id, source_ref)


def _fixture_reference(
    connection: Connection,
    fixture: ProviderFixture,
    provider_id: int,
    match_id: int,
    mapping_version: str,
    seen_at: datetime,
) -> int:
    return upsert_source_reference(
        connection,
        provider_id=provider_id,
        entity_type="FIXTURE",
        provider_entity_id=fixture.provider_fixture_id,
        provider_display_name=_fixture_name(fixture),
        mapping_status="RESOLVED",
        mapping_version=mapping_version,
        provenance="provider_fixture_sync_v1",
        seen_at=seen_at,
        canonical_match_id=match_id,
    )


def _persist_statistics(
    connection: Connection, match_id: int, provider_id: int, fixture: ProviderFixture
) -> None:
    stats = fixture.statistics
    values = {
        "match_id": match_id,
        "provider_id": provider_id,
        "home_shots_on_target": stats.home_shots_on_target,
        "away_shots_on_target": stats.away_shots_on_target,
        "home_possession": stats.home_possession,
        "away_possession": stats.away_possession,
        "home_corners": stats.home_corners,
        "away_corners": stats.away_corners,
        "home_yellow_cards": stats.home_yellow_cards,
        "away_yellow_cards": stats.away_yellow_cards,
        "home_red_cards": stats.home_red_cards,
        "away_red_cards": stats.away_red_cards,
    }
    if all(
        value is None for key, value in values.items() if key not in {"match_id", "provider_id"}
    ):
        return
    connection.execute(
        text(
            """INSERT INTO match_statistics (match_id,provider_id,home_shots_on_target,
        away_shots_on_target,home_possession,away_possession,home_corners,away_corners,
        home_yellow_cards,away_yellow_cards,home_red_cards,away_red_cards)
        VALUES (:match_id,:provider_id,:home_shots_on_target,:away_shots_on_target,
        :home_possession,:away_possession,:home_corners,:away_corners,:home_yellow_cards,
        :away_yellow_cards,:home_red_cards,:away_red_cards)
        ON CONFLICT (match_id,provider_id) DO UPDATE SET
        home_shots_on_target=COALESCE(EXCLUDED.home_shots_on_target,match_statistics.home_shots_on_target),
        away_shots_on_target=COALESCE(EXCLUDED.away_shots_on_target,match_statistics.away_shots_on_target),
        home_possession=COALESCE(EXCLUDED.home_possession,match_statistics.home_possession),
        away_possession=COALESCE(EXCLUDED.away_possession,match_statistics.away_possession),
        home_corners=COALESCE(EXCLUDED.home_corners,match_statistics.home_corners),
        away_corners=COALESCE(EXCLUDED.away_corners,match_statistics.away_corners),
        home_yellow_cards=COALESCE(EXCLUDED.home_yellow_cards,match_statistics.home_yellow_cards),
        away_yellow_cards=COALESCE(EXCLUDED.away_yellow_cards,match_statistics.away_yellow_cards),
        home_red_cards=COALESCE(EXCLUDED.home_red_cards,match_statistics.home_red_cards),
        away_red_cards=COALESCE(EXCLUDED.away_red_cards,match_statistics.away_red_cards),updated_at=now()"""
        ),
        values,
    )


def _canonical_status(status: FixtureStatus) -> str:
    return {
        FixtureStatus.SCHEDULED: "SCHEDULED",
        FixtureStatus.IN_PLAY: "SCHEDULED",
        FixtureStatus.FINISHED: "FINISHED",
        FixtureStatus.UNKNOWN: "SCHEDULED",
    }[status]


def _provider_lifecycle(status: FixtureStatus) -> CanonicalFixtureState | None:
    return {
        FixtureStatus.SCHEDULED: CanonicalFixtureState.SCHEDULED,
        FixtureStatus.IN_PLAY: CanonicalFixtureState.IN_PLAY,
        FixtureStatus.FINISHED: CanonicalFixtureState.FINISHED,
        FixtureStatus.UNKNOWN: None,
    }[status]


def _result(home: int | None, away: int | None) -> str:
    if home is None or away is None:
        raise ValueError("finished fixture requires scores")
    return "H" if home > away else "A" if away > home else "D"


def _fixture_name(fixture: ProviderFixture) -> str:
    return f"{fixture.home_team.provider_name} v {fixture.away_team.provider_name}"


def utc_now() -> datetime:
    return datetime.now(UTC)
