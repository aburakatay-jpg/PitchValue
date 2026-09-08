"""Pure deterministic construction of typed supervised-learning datasets."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable

from pitchvalue.ml.config import DatasetBuilderConfig, MissingValuePolicy
from pitchvalue.ml.contracts import (
    DatasetDiagnostic,
    DatasetStatus,
    DiagnosticCode,
    MLDataset,
    RejectedTrainingRow,
    RowStatus,
    TrainingCandidate,
    TrainingRow,
)
from pitchvalue.ml.features import order_features
from pitchvalue.ml.targets import derive_target
from pitchvalue.ml.validation import validate_candidate


def build_dataset(
    candidates: Iterable[TrainingCandidate], config: DatasetBuilderConfig | None = None
) -> MLDataset:
    config = config or DatasetBuilderConfig()
    inputs = tuple(candidates)
    ordered = tuple(sorted(inputs, key=_candidate_sort_key))
    identities = Counter(
        f"{candidate.identity}|{config.feature_schema.version}" for candidate in ordered
    )
    rows: list[TrainingRow] = []
    rejected: list[RejectedTrainingRow] = []
    for candidate in ordered:
        identity = f"{candidate.identity}|{config.feature_schema.version}"
        if identities[identity] > 1:
            diagnostic = DatasetDiagnostic(DiagnosticCode.DUPLICATE_TRAINING_ROW, identity)
            rejected.append(RejectedTrainingRow(identity, RowStatus.DUPLICATE_ROW, (diagnostic,)))
            continue
        target = derive_target(candidate.target_definition, candidate.outcome)
        if target.status is not RowStatus.READY or target.value is None:
            code = (
                DiagnosticCode.TARGET_UNAVAILABLE
                if target.status is RowStatus.TARGET_UNAVAILABLE
                else DiagnosticCode.INVALID_TARGET
            )
            rejected.append(
                RejectedTrainingRow(identity, target.status, (DatasetDiagnostic(code, identity),))
            )
            continue
        status, diagnostics = validate_candidate(candidate, config)
        features_by_name = {feature.name: feature for feature in candidate.features}
        absent_required = any(
            name not in features_by_name for name in config.feature_schema.required_features
        )
        explicit_required_missing = any(
            features_by_name[name].value is None
            for name in config.feature_schema.required_features
            if name in features_by_name
        )
        preserve_missing = (
            status is RowStatus.MISSING_FEATURE
            and not absent_required
            and (
                not explicit_required_missing
                or config.missing_value_policy is MissingValuePolicy.PRESERVE_MISSING
            )
        )
        if status is not RowStatus.READY and not preserve_missing:
            rejected.append(RejectedTrainingRow(identity, status, diagnostics))
            continue
        rows.append(
            TrainingRow(
                identity,
                candidate.match_id,
                candidate.competition_id,
                candidate.season_id,
                candidate.kickoff,
                candidate.prediction_as_of,
                config.feature_schema.version,
                config.feature_profile,
                candidate.target_definition,
                target.value,
                order_features(candidate.features, config.feature_schema),
                candidate.provenance,
                status,
                diagnostics,
            )
        )
    target_definitions = tuple(
        sorted({row.target_definition for row in rows}, key=lambda item: item.identity)
    )
    ready_count = sum(row.status is RowStatus.READY for row in rows)
    missing_count = sum(row.status is RowStatus.MISSING_FEATURE for row in rows)
    dataset_status = _dataset_status(len(inputs), ready_count, missing_count, len(rejected))
    return MLDataset(
        config.dataset_version,
        config.feature_schema.version,
        config.feature_profile,
        target_definitions,
        tuple(rows),
        tuple(rejected),
        len(inputs),
        ready_count,
        missing_count,
        len(rejected),
        sum(row.status is RowStatus.LEAKAGE_DETECTED for row in rejected),
        sum(
            row.status in (RowStatus.SCHEMA_MISMATCH, RowStatus.INVALID_FEATURE) for row in rejected
        ),
        sum(
            row.status in (RowStatus.TARGET_UNAVAILABLE, RowStatus.INVALID_TARGET)
            for row in rejected
        ),
        dataset_status,
    )


def _candidate_sort_key(candidate: TrainingCandidate) -> tuple[object, ...]:
    return (
        candidate.kickoff,
        candidate.match_id,
        candidate.target_definition.identity,
        candidate.prediction_as_of,
        tuple(feature.name for feature in candidate.features),
    )


def _dataset_status(inputs: int, ready: int, missing: int, rejected: int) -> DatasetStatus:
    if inputs == 0:
        return DatasetStatus.EMPTY
    if ready == inputs:
        return DatasetStatus.READY
    if ready + missing > 0:
        return DatasetStatus.PARTIAL
    return DatasetStatus.INVALID
