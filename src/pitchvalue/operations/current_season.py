"""Replay-safe provider-neutral persistence for authenticated current-season evidence."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import Connection, text

from pitchvalue.operations.contracts import (
    EngineRun,
    FixtureHorizon,
    Quarantine,
    QuarantineScope,
    RunStatus,
    RunType,
)
from pitchvalue.operations.events import (
    DeliveryVisibility,
    EventType,
    OperationalEvent,
    severity_for,
)
from pitchvalue.operations.repository import persist_event, persist_quarantine, persist_run
from pitchvalue.providers.five_dfa.capabilities import PROVIDER_NAME
from pitchvalue.providers.five_dfa.fixtures import ProviderFixture, parse_runtime_fixture
from pitchvalue.providers.five_dfa.mapping import MAPPING_VERSION, MappingStatus, map_competition
from pitchvalue.providers.five_dfa.team_mapping_review import (
    TEAM_MAPPING_REVIEW_VERSION,
    apply_reviewed_team_mappings,
)
from pitchvalue.providers.source_persistence import (
    FixtureWriteResult,
    discover_team_candidate,
    ensure_provider,
    ensure_season,
    persist_fixture,
    resolve_explicit_team_mappings,
    upsert_source_reference,
)

PERSISTENCE_VERSION = "provider_neutral_current_season_v2"
EVENT_VERSION = "persisted_shadow_event_v1"
MAPPING_CONTRACT_VERSION = f"{MAPPING_VERSION}:{TEAM_MAPPING_REVIEW_VERSION}"


@dataclass(frozen=True)
class CurrentSeasonPersistenceResult:
    provider_id: int
    run_id: str
    fixtures: tuple[ProviderFixture, ...]
    fixture_writes: tuple[FixtureWriteResult, ...]
    match_ids: tuple[tuple[str, int], ...]
    source_reference_counts: tuple[tuple[str, int], ...]
    season_inserted: int
    quarantines_created: int
    events_created: int
    malformed: int
    terminal_status: RunStatus


def persist_current_season_payloads(
    connection: Connection,
    payloads: Sequence[Mapping[str, object]],
    *,
    run_id: str,
    window_start: datetime,
    window_end: datetime,
    prediction_as_of: datetime,
    plan: str = "FREE",
) -> CurrentSeasonPersistenceResult:
    """Persist source identities and safe resolved fixtures as one run transaction."""
    provider_id = ensure_provider(connection, PROVIDER_NAME, plan=plan)
    mappings = resolve_explicit_team_mappings(connection, provider_id)
    reference_counts: Counter[str] = Counter()
    malformed = 0
    observed_competition_ids: set[int] = set()

    # First pass records every observable competition/team source identity.
    for payload in payloads:
        league = payload.get("league")
        teams = payload.get("teams")
        if not isinstance(league, dict) or not isinstance(teams, dict):
            malformed += 1
            continue
        try:
            competition = map_competition(league.get("id"), league.get("name"))
            competition_id = _competition_id(connection, competition.canonical_name)
            upsert_source_reference(
                connection,
                provider_id=provider_id,
                entity_type="COMPETITION",
                provider_entity_id=competition.provider_competition_id,
                provider_display_name=competition.provider_name,
                mapping_status=competition.status.value,
                mapping_version=MAPPING_VERSION,
                provenance="five_dfa_authenticated_fixture_v1",
                seen_at=prediction_as_of,
                canonical_competition_id=competition_id,
                payload=league,
            )
            reference_counts[f"COMPETITION_{competition.status.value}"] += 1
            if competition_id is not None:
                observed_competition_ids.add(competition_id)
                _competition_provider_ref(
                    connection,
                    provider_id,
                    competition_id,
                    competition.provider_competition_id,
                    competition.provider_name,
                )
            for side in ("home", "away"):
                team = teams.get(side)
                if not isinstance(team, dict):
                    raise ValueError("team payload missing")
                source_id = _source_id(team.get("id"))
                name = _source_name(team.get("name"))
                canonical = mappings.get(source_id)
                if canonical is None:
                    canonical = discover_team_candidate(connection, name)
                status = "RESOLVED" if canonical is not None else "UNRESOLVED"
                upsert_source_reference(
                    connection,
                    provider_id=provider_id,
                    entity_type="TEAM",
                    provider_entity_id=source_id,
                    provider_display_name=name,
                    mapping_status=status,
                    mapping_version=MAPPING_VERSION,
                    provenance=(
                        "reviewed_source_id_mapping"
                        if source_id in mappings
                        else "exact_canonical_or_alias_name"
                        if canonical is not None
                        else "unresolved_provider_identity"
                    ),
                    seen_at=prediction_as_of,
                    canonical_team_id=canonical,
                    payload=team,
                )
                reference_counts[f"TEAM_{status}"] += 1
                if canonical is not None:
                    mappings[source_id] = canonical
        except ValueError:
            malformed += 1

    apply_reviewed_team_mappings(connection, provider_id)
    mappings = resolve_explicit_team_mappings(connection, provider_id)

    parsed: list[ProviderFixture] = []
    writes: list[FixtureWriteResult] = []
    match_ids: dict[str, int] = {}
    season_ids: dict[int, int] = {}
    seasons_inserted = 0
    for competition_id in sorted(observed_competition_ids):
        season_id, inserted = ensure_season(connection, competition_id)
        season_ids[competition_id] = season_id
        seasons_inserted += int(inserted)
    pending_quarantines: list[tuple[int, str]] = []
    for payload in payloads:
        try:
            fixture = parse_runtime_fixture(payload, explicit_team_mappings=mappings)
            parsed.append(fixture)
        except ValueError:
            continue
        competition_id = _competition_id(connection, fixture.competition.canonical_name)
        if (
            fixture.competition.status is not MappingStatus.RESOLVED
            or competition_id is None
            or fixture.home_team.canonical_team_id is None
            or fixture.away_team.canonical_team_id is None
        ):
            source_ref = upsert_source_reference(
                connection,
                provider_id=provider_id,
                entity_type="FIXTURE",
                provider_entity_id=fixture.provider_fixture_id,
                provider_display_name=(
                    f"{fixture.home_team.provider_name} v {fixture.away_team.provider_name}"
                ),
                mapping_status=(
                    "UNSUPPORTED"
                    if fixture.competition.status is MappingStatus.UNSUPPORTED
                    else "UNRESOLVED"
                ),
                mapping_version=MAPPING_VERSION,
                provenance="five_dfa_authenticated_fixture_v1",
                seen_at=prediction_as_of,
                payload=payload,
            )
            reason = (
                "UNSUPPORTED_COMPETITION"
                if fixture.competition.status is MappingStatus.UNSUPPORTED
                else "FIXTURE_MAPPING_UNRESOLVED"
            )
            pending_quarantines.append((source_ref, reason))
            reference_counts[
                f"FIXTURE_{'UNSUPPORTED' if reason == 'UNSUPPORTED_COMPETITION' else 'UNRESOLVED'}"
            ] += 1
            continue
        if fixture.status.value == "unknown":
            source_ref = upsert_source_reference(
                connection,
                provider_id=provider_id,
                entity_type="FIXTURE",
                provider_entity_id=fixture.provider_fixture_id,
                provider_display_name=(
                    f"{fixture.home_team.provider_name} v {fixture.away_team.provider_name}"
                ),
                mapping_status="REVIEW_REQUIRED",
                mapping_version=MAPPING_VERSION,
                provenance="five_dfa_authenticated_fixture_v1",
                seen_at=prediction_as_of,
                payload=payload,
            )
            pending_quarantines.append((source_ref, "UNKNOWN_LIFECYCLE_REVIEW"))
            reference_counts["FIXTURE_REVIEW_REQUIRED"] += 1
            continue
        write = persist_fixture(
            connection,
            fixture,
            provider_id=provider_id,
            competition_id=competition_id,
            season_id=season_ids[competition_id],
            mapping_version=MAPPING_VERSION,
            seen_at=prediction_as_of,
        )
        writes.append(write)
        if write.match_id is not None:
            match_ids[fixture.provider_fixture_id] = write.match_id
        if write.status.value.endswith("REVIEW"):
            pending_quarantines.append((write.source_entity_ref_id, write.status.value))
        reference_counts["FIXTURE_RESOLVED"] += int(write.match_id is not None)

    status = (
        RunStatus.PARTIAL_WITH_QUARANTINES
        if pending_quarantines or malformed
        else RunStatus.SUCCEEDED
    )
    run = EngineRun(
        run_id,
        RunType.SHADOW,
        prediction_as_of,
        prediction_as_of,
        None,
        RunStatus.RUNNING,
        PERSISTENCE_VERSION,
        FixtureHorizon(
            "UTC",
            tuple(sorted({window_start.date(), (window_end - timedelta(microseconds=1)).date()})),
            PERSISTENCE_VERSION,
        ),
        "raw_multinomial_logistic_v1",
        "FOOTBALL_PERFORMANCE_ONLY",
        "authenticated_shadow_orchestrator_v1",
        "shadow_not_public_v1",
        "live_operational_dq_v1",
        "UNAVAILABLE",
        "UNAVAILABLE",
        "task11_proportional_no_vig_v1",
        MAPPING_CONTRACT_VERSION,
    )
    persist_run(connection, run)
    connection.execute(
        text("UPDATE engine_runs SET provider_id=:provider_id WHERE run_id=:run_id"),
        {"provider_id": provider_id, "run_id": run_id},
    )
    quarantines = sum(
        _persist_source_quarantine(connection, run_id, source_ref, reason, prediction_as_of)
        for source_ref, reason in pending_quarantines
    )
    events = 0
    for event_type in (EventType.RUN_STARTED, EventType.CURRENT_SEASON_SYNC_SUCCEEDED):
        event = OperationalEvent(
            OperationalEvent.deterministic_id(
                event_type, run_id, "current_season", event_type.value
            ),
            event_type,
            EVENT_VERSION,
            prediction_as_of,
            severity_for(event_type),
            run_id,
            "current_season",
            {
                "provider": PROVIDER_NAME,
                "persistence_version": PERSISTENCE_VERSION,
                "mapping_review_version": TEAM_MAPPING_REVIEW_VERSION,
            },
            DeliveryVisibility.INTERNAL,
            run_id=run_id,
            provider_domain="fixtures",
        )
        events += int(persist_event(connection, event))
    return CurrentSeasonPersistenceResult(
        provider_id,
        run_id,
        tuple(parsed),
        tuple(writes),
        tuple(sorted(match_ids.items())),
        tuple(sorted(reference_counts.items())),
        seasons_inserted,
        quarantines,
        events,
        malformed,
        status,
    )


def _persist_source_quarantine(
    connection: Connection, run_id: str, source_ref: int, reason: str, at: datetime
) -> int:
    quarantine = Quarantine(
        Quarantine.deterministic_id(run_id, None, QuarantineScope.MATCH, None, reason, source_ref),
        run_id,
        None,
        None,
        QuarantineScope.MATCH,
        reason,
        at,
        {"source_entity_ref_id": str(source_ref)},
        source_entity_ref_id=source_ref,
    )
    return int(persist_quarantine(connection, quarantine))


def _competition_id(connection: Connection, name: str | None) -> int | None:
    if name is None:
        return None
    value = connection.execute(
        text("SELECT competition_id FROM competitions WHERE canonical_name=:name AND gender='men'"),
        {"name": name},
    ).scalar_one_or_none()
    return None if value is None else int(value)


def _competition_provider_ref(
    connection: Connection, provider_id: int, competition_id: int, source_id: str, name: str
) -> None:
    connection.execute(
        text(
            """INSERT INTO competition_provider_refs (
        competition_id,provider_id,provider_competition_id,provider_name)
        VALUES (:competition_id,:provider_id,:source_id,:name)
        ON CONFLICT (provider_id,provider_competition_id) WHERE provider_competition_id IS NOT NULL
        DO UPDATE SET provider_name=EXCLUDED.provider_name,updated_at=now()"""
        ),
        {
            "competition_id": competition_id,
            "provider_id": provider_id,
            "source_id": source_id,
            "name": name,
        },
    )


def _source_id(value: object) -> str:
    if isinstance(value, bool) or not isinstance(value, (str, int)) or not str(value).strip():
        raise ValueError("source identity missing")
    return str(value).strip()


def _source_name(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("source name missing")
    return value.strip()


def deterministic_run_id(
    payloads: Sequence[Mapping[str, object]], prediction_as_of: datetime
) -> str:
    normalized = sorted(
        (json.dumps(item, sort_keys=True, separators=(",", ":"), default=str) for item in payloads),
        key=lambda item: item,
    )
    canonical = json.dumps(
        [
            PERSISTENCE_VERSION,
            MAPPING_CONTRACT_VERSION,
            prediction_as_of.isoformat(),
            normalized,
        ],
        separators=(",", ":"),
    )
    return "persisted-shadow-" + hashlib.sha256(canonical.encode()).hexdigest()[:16]
