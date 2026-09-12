"""Explicit source-reference mapping without provider IDs becoming canonical IDs."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

from pitchvalue.providers.five_dfa.capabilities import PROVIDER_NAME, SUPPORTED_COMPETITIONS

MAPPING_VERSION = "five_dfa_free_mapping_v1"


class MappingStatus(StrEnum):
    RESOLVED = "RESOLVED"
    UNSUPPORTED = "UNSUPPORTED"
    UNRESOLVED = "UNRESOLVED"


@dataclass(frozen=True)
class CompetitionReference:
    provider: str
    provider_competition_id: str
    provider_name: str
    canonical_name: str | None
    status: MappingStatus
    mapping_version: str = MAPPING_VERSION


@dataclass(frozen=True)
class TeamReference:
    provider: str
    provider_team_id: str
    provider_name: str
    canonical_team_id: int | None
    status: MappingStatus
    provenance: str
    mapping_version: str = MAPPING_VERSION


def map_competition(provider_competition_id: object, provider_name: object) -> CompetitionReference:
    """Map documented names while retaining the provider ID as an opaque source reference."""
    external_id = _source_id(provider_competition_id, "provider competition id")
    name = _text(provider_name, "provider competition name")
    canonical = name if name in SUPPORTED_COMPETITIONS else None
    return CompetitionReference(
        PROVIDER_NAME,
        external_id,
        name,
        canonical,
        MappingStatus.RESOLVED if canonical else MappingStatus.UNSUPPORTED,
    )


def map_team(
    provider_team_id: object,
    provider_name: object,
    explicit_mappings: Mapping[str, int],
    *,
    provenance: str,
) -> TeamReference:
    """Resolve only explicit source-ID mappings; names are never fuzzy-merged."""
    external_id = _source_id(provider_team_id, "provider team id")
    name = _text(provider_name, "provider team name")
    canonical = explicit_mappings.get(external_id)
    if canonical is not None and canonical <= 0:
        raise ValueError("canonical team id must be positive")
    return TeamReference(
        PROVIDER_NAME,
        external_id,
        name,
        canonical,
        MappingStatus.RESOLVED if canonical is not None else MappingStatus.UNRESOLVED,
        _text(provenance, "provenance"),
    )


def _source_id(value: object, name: str) -> str:
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise ValueError(f"{name} must be a string or integer")
    return _text(str(value), name)


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be nonblank")
    return value.strip()
