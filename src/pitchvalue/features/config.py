"""Central immutable configuration for initial football feature windows."""

from __future__ import annotations

from dataclasses import dataclass, fields
from enum import StrEnum
from typing import Any

from pitchvalue.features.contracts import FeatureValidationError


class SeasonHistoryScope(StrEnum):
    CURRENT_SEASON_ONLY = "CURRENT_SEASON_ONLY"
    CURRENT_AND_PREVIOUS_SEASON = "CURRENT_AND_PREVIOUS_SEASON"


@dataclass(frozen=True)
class FeatureConfig:
    """INITIAL FEATURE WINDOW — SUBJECT TO BACKTEST VALIDATION."""

    recent_window: int = 5
    extended_window: int = 10
    home_split_window: int = 5
    away_split_window: int = 5
    schedule_density_windows_days: tuple[int, ...] = (7, 14)
    minimum_rate_observations: int = 1
    season_history_scope: SeasonHistoryScope = SeasonHistoryScope.CURRENT_SEASON_ONLY
    previous_season_id: str | None = None

    def __post_init__(self) -> None:
        window_names = (
            "recent_window",
            "extended_window",
            "home_split_window",
            "away_split_window",
        )
        for field_name in window_names:
            value = getattr(self, field_name)
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise FeatureValidationError(f"{field_name} must be a positive integer")
        if self.recent_window > self.extended_window:
            raise FeatureValidationError("recent_window cannot exceed extended_window")
        density = self.schedule_density_windows_days
        if not isinstance(density, tuple) or not density:
            raise FeatureValidationError("schedule density windows must be a non-empty tuple")
        if any(
            not isinstance(value, int) or isinstance(value, bool) or value <= 0 for value in density
        ):
            raise FeatureValidationError("schedule density windows must be positive integers")
        if len(set(density)) != len(density):
            raise FeatureValidationError("schedule density windows cannot contain duplicates")
        if tuple(sorted(density)) != density:
            raise FeatureValidationError("schedule density windows must be ordered")
        if (
            not isinstance(self.minimum_rate_observations, int)
            or isinstance(self.minimum_rate_observations, bool)
            or self.minimum_rate_observations <= 0
            or self.minimum_rate_observations
            > min(self.recent_window, self.home_split_window, self.away_split_window)
        ):
            raise FeatureValidationError("minimum_rate_observations is not usable by all windows")
        if not isinstance(self.season_history_scope, SeasonHistoryScope):
            raise FeatureValidationError("season_history_scope must use SeasonHistoryScope")
        if self.season_history_scope is SeasonHistoryScope.CURRENT_SEASON_ONLY:
            if self.previous_season_id is not None:
                raise FeatureValidationError("previous_season_id requires previous-season scope")
        elif not isinstance(self.previous_season_id, str) or not self.previous_season_id.strip():
            raise FeatureValidationError("previous-season scope requires previous_season_id")

    def as_dict(self) -> dict[str, Any]:
        return {
            field.name: (
                getattr(self, field.name).value
                if isinstance(getattr(self, field.name), StrEnum)
                else list(getattr(self, field.name))
                if isinstance(getattr(self, field.name), tuple)
                else getattr(self, field.name)
            )
            for field in fields(self)
        }


DEFAULT_FEATURE_CONFIG = FeatureConfig()
