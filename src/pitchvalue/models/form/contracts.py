"""Auditable typed contracts for form/performance signal output."""

from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Any

from pitchvalue.features.contracts import FeatureAvailability


class FormModelStatus(StrEnum):
    READY = "READY"
    INPUT_INSUFFICIENT = "INPUT_INSUFFICIENT"
    INVALID_INPUT = "INVALID_INPUT"


class FormComponent(StrEnum):
    RECENT_FORM = "recent_form"
    EXTENDED_FORM = "extended_form"
    VENUE_FORM = "venue_form"
    ATTACK = "attack"
    DEFENSE = "defense"
    SCHEDULE = "schedule"


@dataclass(frozen=True)
class DiagnosticMetric:
    name: str
    value: Decimal | int | str | None


@dataclass(frozen=True)
class ComponentAnalysis:
    component: FormComponent
    score: Decimal | None
    coverage: FeatureAvailability
    used: bool
    reason: str | None
    inputs: tuple[DiagnosticMetric, ...]
    normalized_inputs: tuple[DiagnosticMetric, ...]


@dataclass(frozen=True)
class TeamSignalCoverage:
    complete_components: int
    partial_components: int
    unavailable_components: int
    used_components: tuple[FormComponent, ...]
    effective_weight_sum: Decimal


@dataclass(frozen=True)
class TeamFormSignal:
    team_id: str
    ready: bool
    recent_form_score: Decimal | None
    extended_form_score: Decimal | None
    venue_form_score: Decimal | None
    attack_score: Decimal | None
    defense_score: Decimal | None
    schedule_score: Decimal | None
    weighted_form_score: Decimal | None
    coverage: TeamSignalCoverage
    components: tuple[ComponentAnalysis, ...]
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class FormModelDiagnostics:
    home_effective_weight_sum: Decimal
    away_effective_weight_sum: Decimal
    home_partial_components: int
    away_partial_components: int
    missing_component_policy: str
    partial_coverage_policy: str


def _primitive(value: object) -> object:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, StrEnum):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: _primitive(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, tuple):
        return [_primitive(item) for item in value]
    return value


@dataclass(frozen=True)
class FormModelAnalysis:
    match_id: str
    home_team_id: str
    away_team_id: str
    status: FormModelStatus
    home_team: TeamFormSignal
    away_team: TeamFormSignal
    home_form_score: Decimal | None
    away_form_score: Decimal | None
    raw_form_difference: Decimal | None
    home_relative_form_signal: Decimal | None
    away_relative_form_signal: Decimal | None
    diagnostics: FormModelDiagnostics
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = _primitive(self)
        if not isinstance(value, dict):  # pragma: no cover - structural invariant
            raise TypeError("FormModelAnalysis must serialize to a mapping")
        return value
