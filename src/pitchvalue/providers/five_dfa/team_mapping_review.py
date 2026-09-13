"""Audited 5DFA team mapping decisions for the supported 2026/27 scope."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from sqlalchemy import Connection, text

from pitchvalue.ingestion.football_data_uk.canonical import normalize_team_name

TEAM_MAPPING_REVIEW_VERSION = "five_dfa_team_review_2026_27_v2"


class TeamMappingClassification(StrEnum):
    RESOLVED_EXISTING_TEAM = "RESOLVED_EXISTING_TEAM"
    CANONICAL_TEAM_MISSING = "CANONICAL_TEAM_MISSING"
    AMBIGUOUS_REVIEW_REQUIRED = "AMBIGUOUS_REVIEW_REQUIRED"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"


@dataclass(frozen=True)
class ReviewedTeamMapping:
    provider_team_id: str
    provider_name: str
    classification: TeamMappingClassification
    canonical_name: str | None
    country_code: str | None
    scope: str


@dataclass(frozen=True)
class MappingApplicationSummary:
    reviewed: int
    resolved: int
    unsupported: int
    review_required: int
    conflicts: int
    canonical_teams_created: int


REVIEWED_TEAM_MAPPINGS = (
    ReviewedTeamMapping(
        "2449627216",
        "Atletico Madrid",
        TeamMappingClassification.RESOLVED_EXISTING_TEAM,
        "Ath Madrid",
        "ESP",
        "La Liga",
    ),
    ReviewedTeamMapping(
        "297909690",
        "Celta Vigo",
        TeamMappingClassification.RESOLVED_EXISTING_TEAM,
        "Celta",
        "ESP",
        "La Liga",
    ),
    ReviewedTeamMapping(
        "1193753576",
        "Coventry",
        TeamMappingClassification.CANONICAL_TEAM_MISSING,
        "Coventry",
        "GBR",
        "Premier League",
    ),
    ReviewedTeamMapping(
        "2308376387",
        "Deportivo A Coruna",
        TeamMappingClassification.CANONICAL_TEAM_MISSING,
        "Deportivo A Coruna",
        "ESP",
        "La Liga",
    ),
    ReviewedTeamMapping(
        "1604037063",
        "Elversberg",
        TeamMappingClassification.CANONICAL_TEAM_MISSING,
        "Elversberg",
        "DEU",
        "Bundesliga",
    ),
    ReviewedTeamMapping(
        "2801662321",
        "Le Mans",
        TeamMappingClassification.CANONICAL_TEAM_MISSING,
        "Le Mans",
        "FRA",
        "Ligue 1",
    ),
    ReviewedTeamMapping(
        "1391740278",
        "Malaga",
        TeamMappingClassification.CANONICAL_TEAM_MISSING,
        "Malaga",
        "ESP",
        "La Liga",
    ),
    ReviewedTeamMapping(
        "762247077",
        "Man Utd",
        TeamMappingClassification.RESOLVED_EXISTING_TEAM,
        "Man United",
        "GBR",
        "Premier League",
    ),
    ReviewedTeamMapping(
        "3976425434",
        "PSG",
        TeamMappingClassification.RESOLVED_EXISTING_TEAM,
        "Paris SG",
        "FRA",
        "Ligue 1",
    ),
    ReviewedTeamMapping(
        "513478939",
        "Real Sociedad",
        TeamMappingClassification.RESOLVED_EXISTING_TEAM,
        "Sociedad",
        "ESP",
        "La Liga",
    ),
    ReviewedTeamMapping(
        "886002894",
        "Troyes",
        TeamMappingClassification.CANONICAL_TEAM_MISSING,
        "Troyes",
        "FRA",
        "Ligue 1",
    ),
    ReviewedTeamMapping(
        "2527307407",
        "Bologna",
        TeamMappingClassification.OUT_OF_SCOPE,
        None,
        "ITA",
        "Serie A",
    ),
    ReviewedTeamMapping(
        "613131758",
        "Juventus",
        TeamMappingClassification.OUT_OF_SCOPE,
        None,
        "ITA",
        "Serie A",
    ),
    ReviewedTeamMapping(
        "3918943256",
        "Lecce",
        TeamMappingClassification.OUT_OF_SCOPE,
        None,
        "ITA",
        "Serie A",
    ),
    ReviewedTeamMapping(
        "3087691433",
        "Monza",
        TeamMappingClassification.OUT_OF_SCOPE,
        None,
        "ITA",
        "Serie A",
    ),
    ReviewedTeamMapping(
        "3080097740",
        "Napoli",
        TeamMappingClassification.OUT_OF_SCOPE,
        None,
        "ITA",
        "Serie A",
    ),
    ReviewedTeamMapping(
        "795967007",
        "Sassuolo",
        TeamMappingClassification.OUT_OF_SCOPE,
        None,
        "ITA",
        "Serie A",
    ),
    ReviewedTeamMapping(
        "1293297733",
        "Athletic Club",
        TeamMappingClassification.RESOLVED_EXISTING_TEAM,
        "Ath Bilbao",
        "ESP",
        "La Liga",
    ),
    ReviewedTeamMapping(
        "2897829406",
        "Bayer Leverkusen",
        TeamMappingClassification.RESOLVED_EXISTING_TEAM,
        "Leverkusen",
        "DEU",
        "Bundesliga",
    ),
    ReviewedTeamMapping(
        "1557303951",
        "Borussia Dortmund",
        TeamMappingClassification.RESOLVED_EXISTING_TEAM,
        "Dortmund",
        "DEU",
        "Bundesliga",
    ),
    ReviewedTeamMapping(
        "2857339925",
        "Borussia M'gladbach",
        TeamMappingClassification.RESOLVED_EXISTING_TEAM,
        "M'gladbach",
        "DEU",
        "Bundesliga",
    ),
    ReviewedTeamMapping(
        "3337328470",
        "CD Alaves",
        TeamMappingClassification.RESOLVED_EXISTING_TEAM,
        "Alaves",
        "ESP",
        "La Liga",
    ),
    ReviewedTeamMapping(
        "507330198",
        "Cologne",
        TeamMappingClassification.RESOLVED_EXISTING_TEAM,
        "FC Koln",
        "DEU",
        "Bundesliga",
    ),
    ReviewedTeamMapping(
        "3755696962",
        "Eintracht Frankfurt",
        TeamMappingClassification.RESOLVED_EXISTING_TEAM,
        "Ein Frankfurt",
        "DEU",
        "Bundesliga",
    ),
    ReviewedTeamMapping(
        "2420253385",
        "Espanyol",
        TeamMappingClassification.RESOLVED_EXISTING_TEAM,
        "Espanol",
        "ESP",
        "La Liga",
    ),
    ReviewedTeamMapping(
        "2133281510",
        "Hull",
        TeamMappingClassification.CANONICAL_TEAM_MISSING,
        "Hull",
        "GBR",
        "Premier League",
    ),
    ReviewedTeamMapping(
        "2220360869",
        "Nottm Forest",
        TeamMappingClassification.RESOLVED_EXISTING_TEAM,
        "Nott'm Forest",
        "GBR",
        "Premier League",
    ),
    ReviewedTeamMapping(
        "1564927013",
        "Paderborn",
        TeamMappingClassification.CANONICAL_TEAM_MISSING,
        "Paderborn",
        "DEU",
        "Bundesliga",
    ),
    ReviewedTeamMapping(
        "3477317007",
        "Racing Santander",
        TeamMappingClassification.CANONICAL_TEAM_MISSING,
        "Racing Santander",
        "ESP",
        "La Liga",
    ),
    ReviewedTeamMapping(
        "1673721661",
        "Rayo Vallecano",
        TeamMappingClassification.RESOLVED_EXISTING_TEAM,
        "Vallecano",
        "ESP",
        "La Liga",
    ),
    ReviewedTeamMapping(
        "2500958492",
        "SC Freiburg",
        TeamMappingClassification.RESOLVED_EXISTING_TEAM,
        "Freiburg",
        "DEU",
        "Bundesliga",
    ),
    ReviewedTeamMapping(
        "2128113652",
        "TSG Hoffenheim",
        TeamMappingClassification.RESOLVED_EXISTING_TEAM,
        "Hoffenheim",
        "DEU",
        "Bundesliga",
    ),
    ReviewedTeamMapping(
        "175125416",
        "VfB Stuttgart",
        TeamMappingClassification.RESOLVED_EXISTING_TEAM,
        "Stuttgart",
        "DEU",
        "Bundesliga",
    ),
    ReviewedTeamMapping(
        "3528898850",
        "AC Milan",
        TeamMappingClassification.OUT_OF_SCOPE,
        None,
        "ITA",
        "Serie A",
    ),
    ReviewedTeamMapping(
        "3319283321",
        "Atalanta",
        TeamMappingClassification.OUT_OF_SCOPE,
        None,
        "ITA",
        "Serie A",
    ),
    ReviewedTeamMapping(
        "3943216107",
        "Cagliari",
        TeamMappingClassification.OUT_OF_SCOPE,
        None,
        "ITA",
        "Serie A",
    ),
    ReviewedTeamMapping(
        "3934727729",
        "Como",
        TeamMappingClassification.OUT_OF_SCOPE,
        None,
        "ITA",
        "Serie A",
    ),
    ReviewedTeamMapping(
        "4162280280",
        "Frosinone",
        TeamMappingClassification.OUT_OF_SCOPE,
        None,
        "ITA",
        "Serie A",
    ),
    ReviewedTeamMapping(
        "3914200339",
        "Genoa",
        TeamMappingClassification.OUT_OF_SCOPE,
        None,
        "ITA",
        "Serie A",
    ),
    ReviewedTeamMapping(
        "949777321",
        "Inter Milan",
        TeamMappingClassification.OUT_OF_SCOPE,
        None,
        "ITA",
        "Serie A",
    ),
    ReviewedTeamMapping(
        "2872564940",
        "Lazio",
        TeamMappingClassification.OUT_OF_SCOPE,
        None,
        "ITA",
        "Serie A",
    ),
    ReviewedTeamMapping(
        "1065347653",
        "Parma",
        TeamMappingClassification.OUT_OF_SCOPE,
        None,
        "ITA",
        "Serie A",
    ),
    ReviewedTeamMapping(
        "2703903780",
        "Roma",
        TeamMappingClassification.OUT_OF_SCOPE,
        None,
        "ITA",
        "Serie A",
    ),
    ReviewedTeamMapping(
        "1733380253",
        "Torino",
        TeamMappingClassification.OUT_OF_SCOPE,
        None,
        "ITA",
        "Serie A",
    ),
    ReviewedTeamMapping(
        "2192805718",
        "Udinese",
        TeamMappingClassification.OUT_OF_SCOPE,
        None,
        "ITA",
        "Serie A",
    ),
)


def apply_reviewed_team_mappings(
    connection: Connection, provider_id: int
) -> MappingApplicationSummary:
    """Apply only explicit source-ID decisions to identities already observed from 5DFA."""
    counters = {
        "reviewed": 0,
        "resolved": 0,
        "unsupported": 0,
        "review_required": 0,
        "conflicts": 0,
        "canonical_teams_created": 0,
    }
    for review in REVIEWED_TEAM_MAPPINGS:
        source = (
            connection.execute(
                text(
                    """SELECT source_entity_ref_id,provider_display_name
                    FROM source_entity_references
                    WHERE provider_id=:provider_id AND entity_type='TEAM'
                      AND provider_entity_id=:provider_team_id"""
                ),
                {
                    "provider_id": provider_id,
                    "provider_team_id": review.provider_team_id,
                },
            )
            .mappings()
            .one_or_none()
        )
        if source is None:
            continue
        counters["reviewed"] += 1
        reference_id = int(source["source_entity_ref_id"])
        if source["provider_display_name"] != review.provider_name:
            _set_reference_state(connection, reference_id, "CONFLICT", "display_name_conflict")
            counters["conflicts"] += 1
            continue
        if review.classification is TeamMappingClassification.OUT_OF_SCOPE:
            _set_reference_state(connection, reference_id, "UNSUPPORTED", "explicit_out_of_scope")
            counters["unsupported"] += 1
            continue
        if review.classification is TeamMappingClassification.AMBIGUOUS_REVIEW_REQUIRED:
            _set_reference_state(connection, reference_id, "REVIEW_REQUIRED", "ambiguous_review")
            counters["review_required"] += 1
            continue
        assert review.canonical_name is not None
        team_ids = tuple(
            int(value)
            for value in connection.execute(
                text("SELECT team_id FROM teams WHERE canonical_name=:name ORDER BY team_id"),
                {"name": review.canonical_name},
            ).scalars()
        )
        if (
            not team_ids
            and review.classification is TeamMappingClassification.CANONICAL_TEAM_MISSING
        ):
            normalized = normalize_team_name(review.canonical_name)
            collision = connection.execute(
                text("SELECT team_id FROM teams WHERE normalized_name=:name"),
                {"name": normalized},
            ).scalar_one_or_none()
            if collision is not None:
                _set_reference_state(
                    connection, reference_id, "CONFLICT", "normalized_name_collision"
                )
                counters["conflicts"] += 1
                continue
            team_id = int(
                connection.execute(
                    text(
                        """INSERT INTO teams(canonical_name,normalized_name,country_code,active)
                        VALUES (:name,:normalized,:country,true) RETURNING team_id"""
                    ),
                    {
                        "name": review.canonical_name,
                        "normalized": normalized,
                        "country": review.country_code,
                    },
                ).scalar_one()
            )
            team_ids = (team_id,)
            counters["canonical_teams_created"] += 1
        if len(team_ids) != 1:
            _set_reference_state(connection, reference_id, "CONFLICT", "canonical_target_conflict")
            counters["conflicts"] += 1
            continue
        if not _ensure_provider_alias(connection, provider_id, review, team_ids[0]):
            _set_reference_state(connection, reference_id, "CONFLICT", "provider_alias_conflict")
            counters["conflicts"] += 1
            continue
        connection.execute(
            text(
                """UPDATE source_entity_references SET canonical_team_id=:team_id,
                mapping_status='RESOLVED',mapping_version=:version,
                provenance='explicit_reviewed_team_mapping'
                WHERE source_entity_ref_id=:reference_id"""
            ),
            {
                "team_id": team_ids[0],
                "version": TEAM_MAPPING_REVIEW_VERSION,
                "reference_id": reference_id,
            },
        )
        counters["resolved"] += 1
    return MappingApplicationSummary(**counters)


def _set_reference_state(
    connection: Connection, reference_id: int, status: str, provenance_suffix: str
) -> None:
    connection.execute(
        text(
            """UPDATE source_entity_references SET canonical_team_id=NULL,
            mapping_status=:status,mapping_version=:version,provenance=:provenance
            WHERE source_entity_ref_id=:reference_id"""
        ),
        {
            "status": status,
            "version": TEAM_MAPPING_REVIEW_VERSION,
            "provenance": f"explicit_team_review:{provenance_suffix}",
            "reference_id": reference_id,
        },
    )


def _ensure_provider_alias(
    connection: Connection,
    provider_id: int,
    review: ReviewedTeamMapping,
    team_id: int,
) -> bool:
    connection.execute(
        text(
            """INSERT INTO team_aliases(
                team_id,provider_id,alias,normalized_alias,provider_team_id
            ) VALUES (:team_id,:provider_id,:alias,:normalized,:provider_team_id)
            ON CONFLICT (provider_id,provider_team_id) WHERE provider_team_id IS NOT NULL
            DO NOTHING"""
        ),
        {
            "team_id": team_id,
            "provider_id": provider_id,
            "alias": review.provider_name,
            "normalized": normalize_team_name(review.provider_name),
            "provider_team_id": review.provider_team_id,
        },
    )
    existing = connection.execute(
        text(
            """SELECT team_id FROM team_aliases
            WHERE provider_id=:provider_id AND provider_team_id=:provider_team_id"""
        ),
        {
            "provider_id": provider_id,
            "provider_team_id": review.provider_team_id,
        },
    ).scalar_one()
    return int(existing) == team_id
