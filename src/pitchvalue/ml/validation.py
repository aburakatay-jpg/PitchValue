"""Schema, profile, and temporal leakage validation for candidate rows."""

from __future__ import annotations

from collections import Counter

from pitchvalue.ml.config import DatasetBuilderConfig, FeatureProfile, MissingValuePolicy
from pitchvalue.ml.contracts import (
    DatasetDiagnostic,
    DiagnosticCode,
    FeatureKind,
    FeatureRecord,
    RowStatus,
    TrainingCandidate,
)


def validate_candidate(
    candidate: TrainingCandidate, config: DatasetBuilderConfig
) -> tuple[RowStatus, tuple[DatasetDiagnostic, ...]]:
    diagnostics: list[DatasetDiagnostic] = []
    identity = candidate.identity
    counts = Counter(feature.name for feature in candidate.features)
    for name in sorted(name for name, count in counts.items() if count > 1):
        diagnostics.append(DatasetDiagnostic(DiagnosticCode.DUPLICATE_FEATURE, identity, name))
    by_name = {feature.name: feature for feature in candidate.features}
    declared = set(config.feature_schema.feature_order)
    for name in sorted(set(by_name) - declared):
        diagnostics.append(DatasetDiagnostic(DiagnosticCode.UNKNOWN_FEATURE, identity, name))
    for name in config.feature_schema.required_features:
        if name not in by_name:
            diagnostics.append(
                DatasetDiagnostic(DiagnosticCode.REQUIRED_FEATURE_MISSING, identity, name)
            )
    for feature in candidate.features:
        _validate_feature(candidate, feature, config, diagnostics)
    status = _status_for(diagnostics, candidate.features, config)
    return status, tuple(
        sorted(diagnostics, key=lambda item: (item.code.value, item.feature_name or ""))
    )


def _validate_feature(
    candidate: TrainingCandidate,
    feature: FeatureRecord,
    config: DatasetBuilderConfig,
    diagnostics: list[DatasetDiagnostic],
) -> None:
    identity = candidate.identity
    if feature.schema_version != config.feature_schema.version:
        diagnostics.append(
            DatasetDiagnostic(DiagnosticCode.FEATURE_VERSION_MISMATCH, identity, feature.name)
        )
    if (
        feature.kind is FeatureKind.MARKET_ODDS
        and config.feature_profile is FeatureProfile.FOOTBALL_PERFORMANCE_ONLY
    ):
        diagnostics.append(
            DatasetDiagnostic(
                DiagnosticCode.ODDS_FEATURE_NOT_ALLOWED_IN_BASELINE, identity, feature.name
            )
        )
    if feature.available_at > candidate.prediction_as_of:
        code = (
            DiagnosticCode.ODDS_AVAILABLE_AFTER_AS_OF
            if feature.kind is FeatureKind.MARKET_ODDS
            else DiagnosticCode.FEATURE_AVAILABLE_AFTER_AS_OF
        )
        diagnostics.append(DatasetDiagnostic(code, identity, feature.name))
    if feature.provenance.contains_target_result or feature.provenance.contains_target_goals:
        diagnostics.append(
            DatasetDiagnostic(DiagnosticCode.TARGET_VALUE_IN_FEATURES, identity, feature.name)
        )
    for source in feature.provenance.source_matches:
        if source.match_id == candidate.match_id:
            diagnostics.append(
                DatasetDiagnostic(DiagnosticCode.TARGET_SELF_LEAKAGE, identity, feature.name)
            )
        if source.kickoff == candidate.prediction_as_of:
            diagnostics.append(
                DatasetDiagnostic(DiagnosticCode.SAME_TIME_SOURCE_MATCH, identity, feature.name)
            )
        elif source.kickoff > candidate.prediction_as_of:
            diagnostics.append(
                DatasetDiagnostic(DiagnosticCode.FUTURE_SOURCE_MATCH, identity, feature.name)
            )
    if feature.value is None and feature.name in config.feature_schema.required_features:
        diagnostics.append(
            DatasetDiagnostic(DiagnosticCode.REQUIRED_FEATURE_MISSING, identity, feature.name)
        )


def _status_for(
    diagnostics: list[DatasetDiagnostic],
    features: tuple[FeatureRecord, ...],
    config: DatasetBuilderConfig,
) -> RowStatus:
    codes = {item.code for item in diagnostics}
    leakage = {
        DiagnosticCode.FEATURE_AVAILABLE_AFTER_AS_OF,
        DiagnosticCode.ODDS_AVAILABLE_AFTER_AS_OF,
        DiagnosticCode.TARGET_SELF_LEAKAGE,
        DiagnosticCode.FUTURE_SOURCE_MATCH,
        DiagnosticCode.SAME_TIME_SOURCE_MATCH,
        DiagnosticCode.TARGET_VALUE_IN_FEATURES,
    }
    if codes & leakage:
        return RowStatus.LEAKAGE_DETECTED
    if DiagnosticCode.DUPLICATE_FEATURE in codes:
        return RowStatus.INVALID_FEATURE
    if codes & {
        DiagnosticCode.UNKNOWN_FEATURE,
        DiagnosticCode.FEATURE_VERSION_MISMATCH,
        DiagnosticCode.ODDS_FEATURE_NOT_ALLOWED_IN_BASELINE,
    }:
        return RowStatus.SCHEMA_MISMATCH
    missing = (
        any(feature.value is None for feature in features)
        or DiagnosticCode.REQUIRED_FEATURE_MISSING in codes
    )
    if missing:
        if (
            DiagnosticCode.REQUIRED_FEATURE_MISSING in codes
            and config.missing_value_policy is MissingValuePolicy.REJECT_ROW
        ):
            return RowStatus.MISSING_FEATURE
        return RowStatus.MISSING_FEATURE
    return RowStatus.READY
