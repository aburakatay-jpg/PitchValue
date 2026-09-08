"""Small immutable lineage contracts for ML feature legality audits."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from pitchvalue.ml.config import MLDatasetValidationError, _identifier


def require_aware(value: datetime, name: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise MLDatasetValidationError(f"{name} must be timezone-aware")


@dataclass(frozen=True)
class SourceMatchReference:
    match_id: str
    kickoff: datetime

    def __post_init__(self) -> None:
        _identifier(self.match_id, "source match_id")
        require_aware(self.kickoff, "source kickoff")

    def to_dict(self) -> dict[str, str]:
        return {"match_id": self.match_id, "kickoff": self.kickoff.isoformat()}


@dataclass(frozen=True)
class FeatureProvenance:
    feature_version: str
    source_module: str
    source_data_version: str
    calculation_id: str
    source_matches: tuple[SourceMatchReference, ...] = ()
    contains_target_result: bool = False
    contains_target_goals: bool = False

    def __post_init__(self) -> None:
        for name in ("feature_version", "source_module", "source_data_version", "calculation_id"):
            _identifier(getattr(self, name), name)
        ids = [item.match_id for item in self.source_matches]
        if len(ids) != len(set(ids)):
            raise MLDatasetValidationError("duplicate source match ID")
        ordered = tuple(sorted(self.source_matches, key=lambda item: (item.kickoff, item.match_id)))
        object.__setattr__(self, "source_matches", ordered)

    def to_dict(self) -> dict[str, Any]:
        return {
            "feature_version": self.feature_version,
            "source_module": self.source_module,
            "source_data_version": self.source_data_version,
            "calculation_id": self.calculation_id,
            "source_matches": [item.to_dict() for item in self.source_matches],
            "contains_target_result": self.contains_target_result,
            "contains_target_goals": self.contains_target_goals,
        }


@dataclass(frozen=True)
class DatasetRowProvenance:
    source_version: str
    builder_version: str = "task15-v1"

    def __post_init__(self) -> None:
        _identifier(self.source_version, "source_version")
        _identifier(self.builder_version, "builder_version")

    def to_dict(self) -> dict[str, str]:
        return {"source_version": self.source_version, "builder_version": self.builder_version}
