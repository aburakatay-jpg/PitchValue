"""Conservative canonical transformation of accepted staged domestic rows."""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import Connection, text

from pitchvalue.ingestion.football_data_uk.parser import (
    ParsedDataset,
    ParsedRow,
    ParseError,
    parse_nullable_int,
    parse_source_date,
    parse_source_time,
)
from pitchvalue.ingestion.football_data_uk.registry import SourceDefinition

logger = logging.getLogger(__name__)

TIMEZONES = {
    "ENG": "Europe/London",
    "FRA": "Europe/Paris",
    "DEU": "Europe/Berlin",
    "TUR": "Europe/Istanbul",
    "PRT": "Europe/Lisbon",
    "ESP": "Europe/Madrid",
    "SCO": "Europe/London",
    "ITA": "Europe/Rome",
    "NLD": "Europe/Amsterdam",
}

STAT_COLUMN_MAP = {
    "HS": "home_shots",
    "AS": "away_shots",
    "HST": "home_shots_on_target",
    "AST": "away_shots_on_target",
    "HC": "home_corners",
    "AC": "away_corners",
    "HF": "home_fouls",
    "AF": "away_fouls",
    "HY": "home_yellow_cards",
    "AY": "away_yellow_cards",
    "HR": "home_red_cards",
    "AR": "away_red_cards",
}


class CanonicalImportError(ValueError):
    """Raised when a source row cannot safely become canonical data."""


@dataclass
class CanonicalImportMetrics:
    """Per-source canonical transformation counts."""

    seasons_created: int = 0
    seasons_reused: int = 0
    teams_created: int = 0
    teams_reused: int = 0
    aliases_created: int = 0
    aliases_reused: int = 0
    matches_created: int = 0
    matches_reused: int = 0
    provider_refs_created: int = 0
    provider_refs_reused: int = 0
    ambiguous_matches: int = 0
    statistics_created: int = 0
    statistics_reused: int = 0
    statistics_updated: int = 0
    rejected_canonical_rows: int = 0


def normalize_team_name(value: str) -> str:
    """Normalize conservatively without removing words or fuzzy matching."""
    normalized = unicodedata.normalize("NFKC", value)
    normalized = normalized.translate(str.maketrans("’‘‐‑–—", "''----"))
    normalized = re.sub(r"\s+", " ", normalized.strip())
    return normalized.casefold()


def local_kickoff_to_utc(source_date: str, source_time: str, jurisdiction_code: str) -> datetime:
    """Convert an explicit local date/time to a timezone-aware UTC instant."""
    parsed_date = parse_source_date(source_date)
    parsed_time = parse_source_time(source_time)
    if parsed_date is None or parsed_time is None:
        raise CanonicalImportError("date and time are both required for kickoff conversion")
    timezone_name = TIMEZONES.get(jurisdiction_code)
    if timezone_name is None:
        raise CanonicalImportError(f"no timezone configured for {jurisdiction_code}")
    return datetime.combine(parsed_date, parsed_time, ZoneInfo(timezone_name)).astimezone(UTC)


def _competition_id(connection: Connection, source: SourceDefinition) -> int:
    rows = connection.execute(
        text(
            """
            SELECT competition_id, country_code, jurisdiction_code
            FROM competitions
            WHERE canonical_name = :name AND gender = 'men'
            """
        ),
        {"name": source.canonical_competition},
    ).all()
    if len(rows) != 1:
        raise CanonicalImportError(
            f"canonical competition mapping is not unique: {source.canonical_competition}"
        )
    row = rows[0]
    if row.country_code != source.country_code or row.jurisdiction_code != source.jurisdiction_code:
        raise CanonicalImportError(
            f"competition geography mismatch: {source.canonical_competition}"
        )
    assert isinstance(row.competition_id, int)
    return row.competition_id


def _season(
    connection: Connection,
    competition_id: int,
    source: SourceDefinition,
    metrics: CanonicalImportMetrics,
) -> int:
    existing = connection.execute(
        text(
            """
            SELECT season_id FROM seasons
            WHERE competition_id = :competition_id AND season_name = :season_name
            """
        ),
        {"competition_id": competition_id, "season_name": source.season_name},
    ).scalar_one_or_none()
    if existing is not None:
        metrics.seasons_reused += 1
        assert isinstance(existing, int)
        return existing
    start_year_text, end_year_short = source.season_name.split("/")
    start_year = int(start_year_text)
    end_year = (start_year // 100) * 100 + int(end_year_short)
    season_id = connection.execute(
        text(
            """
            INSERT INTO seasons (
                competition_id, season_name, start_year, end_year, status
            ) VALUES (
                :competition_id, :season_name, :start_year, :end_year, 'completed'
            ) RETURNING season_id
            """
        ),
        {
            "competition_id": competition_id,
            "season_name": source.season_name,
            "start_year": start_year,
            "end_year": end_year,
        },
    ).scalar_one()
    metrics.seasons_created += 1
    assert isinstance(season_id, int)
    return season_id


def _team(
    connection: Connection,
    provider_id: int,
    source_name: str,
    source: SourceDefinition,
    metrics: CanonicalImportMetrics,
) -> int:
    rows = connection.execute(
        text(
            """
            SELECT team_id, team_alias_id
            FROM team_aliases
            WHERE provider_id = :provider_id AND alias = :alias
            ORDER BY team_alias_id
            """
        ),
        {"provider_id": provider_id, "alias": source_name},
    ).all()
    team_ids = {row.team_id for row in rows}
    if len(team_ids) > 1:
        raise CanonicalImportError(f"provider alias maps to multiple teams: {source_name}")
    if team_ids:
        metrics.teams_reused += 1
        metrics.aliases_reused += 1
        team_id = team_ids.pop()
        assert isinstance(team_id, int)
        return team_id

    normalized = normalize_team_name(source_name)
    if not normalized:
        raise CanonicalImportError("team name is blank")
    team_id = connection.execute(
        text(
            """
            INSERT INTO teams (canonical_name, normalized_name, country_code)
            VALUES (:canonical_name, :normalized_name, :country_code)
            RETURNING team_id
            """
        ),
        {
            "canonical_name": source_name,
            "normalized_name": normalized,
            "country_code": source.country_code,
        },
    ).scalar_one()
    assert isinstance(team_id, int)
    connection.execute(
        text(
            """
            INSERT INTO team_aliases (
                team_id, provider_id, alias, normalized_alias
            ) VALUES (:team_id, :provider_id, :alias, :normalized_alias)
            """
        ),
        {
            "team_id": team_id,
            "provider_id": provider_id,
            "alias": source_name,
            "normalized_alias": normalized,
        },
    )
    metrics.teams_created += 1
    metrics.aliases_created += 1
    return team_id


def _validated_result(row: ParsedRow) -> tuple[int, int, str, int | None, int | None]:
    values = row.normalized_values
    try:
        home_score = parse_nullable_int(values.get("FTHG"))
        away_score = parse_nullable_int(values.get("FTAG"))
        home_ht = parse_nullable_int(values.get("HTHG"))
        away_ht = parse_nullable_int(values.get("HTAG"))
    except ParseError as error:
        raise CanonicalImportError(str(error)) from error
    result = values.get("FTR")
    if home_score is None or away_score is None or result not in {"H", "D", "A"}:
        raise CanonicalImportError("complete scores and a valid result are required")
    if home_score < 0 or away_score < 0:
        raise CanonicalImportError("scores cannot be negative")
    if home_ht is not None and home_ht < 0 or away_ht is not None and away_ht < 0:
        raise CanonicalImportError("half-time scores cannot be negative")
    expected = "H" if home_score > away_score else "A" if home_score < away_score else "D"
    if result != expected:
        raise CanonicalImportError("source result contradicts normal-time scores")
    if (home_ht is None) != (away_ht is None):
        raise CanonicalImportError("half-time scores must be present as a pair")
    return home_score, away_score, result, home_ht, away_ht


def _kickoff(row: ParsedRow, source: SourceDefinition) -> datetime | None:
    source_date = row.normalized_values.get("Date")
    if source_date is None:
        raise CanonicalImportError("source date is required")
    parsed_date = parse_source_date(source_date)
    if parsed_date is None:
        raise CanonicalImportError("source date is required")
    source_time = row.normalized_values.get("Time")
    if source_time is None:
        return None
    return local_kickoff_to_utc(source_date, source_time, source.jurisdiction_code)


def _existing_match_from_provider_ref(
    connection: Connection, provider_id: int, source: SourceDefinition, row_hash: str
) -> int | None:
    matches = (
        connection.execute(
            text(
                """
            SELECT DISTINCT match_id
            FROM match_provider_refs
            WHERE provider_id = :provider_id
              AND source_url = :source_url
              AND source_record_hash = :row_hash
            """
            ),
            {"provider_id": provider_id, "source_url": source.url, "row_hash": row_hash},
        )
        .scalars()
        .all()
    )
    if len(matches) > 1:
        raise CanonicalImportError("one source record hash maps to multiple canonical matches")
    if not matches:
        return None
    match_id = matches[0]
    assert isinstance(match_id, int)
    return match_id


def _candidate_matches(
    connection: Connection,
    *,
    competition_id: int,
    season_id: int,
    home_team_id: int,
    away_team_id: int,
    kickoff_at_utc: datetime | None,
    source_date: str,
    source_url: str,
) -> list[int]:
    if kickoff_at_utc is not None:
        values = connection.execute(
            text(
                """
                SELECT match_id FROM matches
                WHERE competition_id = :competition_id
                  AND season_id = :season_id
                  AND home_team_id = :home_team_id
                  AND away_team_id = :away_team_id
                  AND kickoff_at_utc = :kickoff_at_utc
                """
            ),
            {
                "competition_id": competition_id,
                "season_id": season_id,
                "home_team_id": home_team_id,
                "away_team_id": away_team_id,
                "kickoff_at_utc": kickoff_at_utc,
            },
        ).scalars()
    else:
        values = connection.execute(
            text(
                """
                SELECT DISTINCT m.match_id
                FROM matches AS m
                JOIN football_data_canonical_lineage AS lineage
                  ON lineage.match_id = m.match_id
                JOIN football_data_staging_rows AS staging
                  ON staging.staging_row_id = lineage.staging_row_id
                JOIN import_batches AS batch
                  ON batch.import_batch_id = staging.import_batch_id
                WHERE m.competition_id = :competition_id
                  AND m.season_id = :season_id
                  AND m.home_team_id = :home_team_id
                  AND m.away_team_id = :away_team_id
                  AND m.kickoff_at_utc IS NULL
                  AND staging.raw_row ->> 'Date' = :source_date
                  AND batch.source_identifier = :source_url
                """
            ),
            {
                "competition_id": competition_id,
                "season_id": season_id,
                "home_team_id": home_team_id,
                "away_team_id": away_team_id,
                "source_date": source_date,
                "source_url": source_url,
            },
        ).scalars()
    result = list(values)
    assert all(isinstance(value, int) for value in result)
    return result


def _create_match(
    connection: Connection,
    *,
    competition_id: int,
    season_id: int,
    home_team_id: int,
    away_team_id: int,
    kickoff_at_utc: datetime | None,
    source: SourceDefinition,
    row: ParsedRow,
    scores: tuple[int, int, str, int | None, int | None],
) -> int:
    home_score, away_score, result, home_ht, away_ht = scores
    match_id = connection.execute(
        text(
            """
            INSERT INTO matches (
                competition_id, season_id, kickoff_at_utc, kickoff_timezone,
                home_team_id, away_team_id, status,
                home_score, away_score, home_ht_score, away_ht_score,
                result, decided_by, referee
            ) VALUES (
                :competition_id, :season_id, :kickoff_at_utc, :kickoff_timezone,
                :home_team_id, :away_team_id, 'FINISHED',
                :home_score, :away_score, :home_ht_score, :away_ht_score,
                :result, 'regular_time', :referee
            ) RETURNING match_id
            """
        ),
        {
            "competition_id": competition_id,
            "season_id": season_id,
            "kickoff_at_utc": kickoff_at_utc,
            "kickoff_timezone": TIMEZONES[source.jurisdiction_code]
            if kickoff_at_utc is not None
            else None,
            "home_team_id": home_team_id,
            "away_team_id": away_team_id,
            "home_score": home_score,
            "away_score": away_score,
            "home_ht_score": home_ht,
            "away_ht_score": away_ht,
            "result": result,
            "referee": row.normalized_values.get("Referee"),
        },
    ).scalar_one()
    assert isinstance(match_id, int)
    return match_id


def _provider_ref(
    connection: Connection,
    match_id: int,
    provider_id: int,
    source: SourceDefinition,
    row_hash: str,
    metrics: CanonicalImportMetrics,
) -> None:
    exists = connection.execute(
        text(
            """
            SELECT match_provider_ref_id
            FROM match_provider_refs
            WHERE match_id = :match_id AND provider_id = :provider_id
              AND source_url = :source_url AND source_record_hash = :row_hash
            """
        ),
        {
            "match_id": match_id,
            "provider_id": provider_id,
            "source_url": source.url,
            "row_hash": row_hash,
        },
    ).scalar_one_or_none()
    if exists is not None:
        metrics.provider_refs_reused += 1
        return
    connection.execute(
        text(
            """
            INSERT INTO match_provider_refs (
                match_id, provider_id, provider_match_id, source_url, source_record_hash
            ) VALUES (:match_id, :provider_id, NULL, :source_url, :row_hash)
            """
        ),
        {
            "match_id": match_id,
            "provider_id": provider_id,
            "source_url": source.url,
            "row_hash": row_hash,
        },
    )
    metrics.provider_refs_created += 1


def _statistics_values(row: ParsedRow) -> dict[str, int | None]:
    values: dict[str, int | None] = {}
    for source_column, canonical_column in STAT_COLUMN_MAP.items():
        try:
            values[canonical_column] = parse_nullable_int(row.normalized_values.get(source_column))
        except ParseError as error:
            raise CanonicalImportError(str(error)) from error
        parsed_value = values[canonical_column]
        if parsed_value is not None and parsed_value < 0:
            raise CanonicalImportError(f"{source_column} cannot be negative")
    return values


def _statistics(
    connection: Connection,
    match_id: int,
    provider_id: int,
    row: ParsedRow,
    metrics: CanonicalImportMetrics,
) -> bool:
    values = _statistics_values(row)
    if not any(value is not None for value in values.values()):
        return False
    existing = connection.execute(
        text(
            "SELECT * FROM match_statistics WHERE match_id=:match_id AND provider_id=:provider_id"
        ),
        {"match_id": match_id, "provider_id": provider_id},
    ).one_or_none()
    parameters: dict[str, object] = {"match_id": match_id, "provider_id": provider_id, **values}
    columns = tuple(STAT_COLUMN_MAP.values())
    if existing is None:
        connection.execute(
            text(
                f"""
                INSERT INTO match_statistics (
                    match_id, provider_id, {", ".join(columns)}
                ) VALUES (
                    :match_id, :provider_id, {", ".join(f":{column}" for column in columns)}
                )
                """
            ),
            parameters,
        )
        metrics.statistics_created += 1
        return True
    changed = any(
        values[column] is not None and existing._mapping[column] != values[column]
        for column in columns
    )
    if changed:
        assignments = ", ".join(f"{column} = COALESCE(:{column}, {column})" for column in columns)
        connection.execute(
            text(
                f"""
                UPDATE match_statistics SET {assignments}, updated_at = now()
                WHERE match_id = :match_id AND provider_id = :provider_id
                """
            ),
            parameters,
        )
        metrics.statistics_updated += 1
    else:
        metrics.statistics_reused += 1
    return True


def _quality(connection: Connection, match_id: int, stats_available: bool) -> None:
    connection.execute(
        text(
            """
            INSERT INTO data_quality (
                match_id, result_available, stats_available, odds_available,
                xg_available, lineup_available, injury_available,
                result_verified, cross_provider_verified, quality_score
            ) VALUES (
                :match_id, true, :stats_available, false,
                false, false, false, true, false, NULL
            )
            ON CONFLICT (match_id) DO UPDATE
            SET result_available = true,
                stats_available = data_quality.stats_available OR EXCLUDED.stats_available,
                result_verified = true,
                updated_at = now()
            """
        ),
        {"match_id": match_id, "stats_available": stats_available},
    )


def _staging_row_id(connection: Connection, batch_id: int, source_row_number: int) -> int:
    value = connection.execute(
        text(
            """
            SELECT staging_row_id FROM football_data_staging_rows
            WHERE import_batch_id = :batch_id AND source_row_number = :source_row_number
            """
        ),
        {"batch_id": batch_id, "source_row_number": source_row_number},
    ).scalar_one()
    assert isinstance(value, int)
    return value


def import_staged_dataset(
    connection: Connection,
    batch_id: int,
    provider_id: int,
    source: SourceDefinition,
    dataset: ParsedDataset,
) -> CanonicalImportMetrics:
    """Transform accepted staged rows within the caller's source transaction."""
    metrics = CanonicalImportMetrics()
    connection.execute(
        text("SELECT provider_id FROM providers WHERE provider_id=:provider_id FOR UPDATE"),
        {"provider_id": provider_id},
    ).scalar_one()
    competition_id = _competition_id(connection, source)
    season_id = _season(connection, competition_id, source, metrics)
    for row in dataset.rows:
        if row.errors:
            continue
        try:
            if row.normalized_values.get("Div") != source.source_code:
                raise CanonicalImportError("row division does not match registered source")
            home_name = row.normalized_values.get("HomeTeam")
            away_name = row.normalized_values.get("AwayTeam")
            if home_name is None or away_name is None:
                raise CanonicalImportError("home and away teams are required")
            if normalize_team_name(home_name) == normalize_team_name(away_name):
                raise CanonicalImportError("home and away teams normalize identically")
            scores = _validated_result(row)
            kickoff_at_utc = _kickoff(row, source)
            home_team_id = _team(connection, provider_id, home_name, source, metrics)
            away_team_id = _team(connection, provider_id, away_name, source, metrics)
            existing_match = _existing_match_from_provider_ref(
                connection, provider_id, source, row.row_hash
            )
            if existing_match is None:
                candidates = _candidate_matches(
                    connection,
                    competition_id=competition_id,
                    season_id=season_id,
                    home_team_id=home_team_id,
                    away_team_id=away_team_id,
                    kickoff_at_utc=kickoff_at_utc,
                    source_date=row.normalized_values["Date"] or "",
                    source_url=source.url,
                )
                if len(candidates) > 1:
                    metrics.ambiguous_matches += 1
                    continue
                if candidates:
                    match_id = candidates[0]
                    metrics.matches_reused += 1
                else:
                    match_id = _create_match(
                        connection,
                        competition_id=competition_id,
                        season_id=season_id,
                        home_team_id=home_team_id,
                        away_team_id=away_team_id,
                        kickoff_at_utc=kickoff_at_utc,
                        source=source,
                        row=row,
                        scores=scores,
                    )
                    metrics.matches_created += 1
            else:
                match_id = existing_match
                metrics.matches_reused += 1
            _provider_ref(connection, match_id, provider_id, source, row.row_hash, metrics)
            stats_available = _statistics(connection, match_id, provider_id, row, metrics)
            _quality(connection, match_id, stats_available)
            staging_row_id = _staging_row_id(connection, batch_id, row.source_row_number)
            connection.execute(
                text(
                    """
                    INSERT INTO football_data_canonical_lineage (staging_row_id, match_id)
                    VALUES (:staging_row_id, :match_id)
                    ON CONFLICT (staging_row_id) DO NOTHING
                    """
                ),
                {"staging_row_id": staging_row_id, "match_id": match_id},
            )
        except (CanonicalImportError, ParseError) as error:
            metrics.rejected_canonical_rows += 1
            logger.warning("canonical row rejected %s: %s", row.source_row_number, error)
    return metrics
