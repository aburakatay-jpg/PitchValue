from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from pitchvalue.ml import (
    DatasetBuilderConfig,
    DatasetRowProvenance,
    FeatureKind,
    FeatureProfile,
    FeatureProvenance,
    FeatureRecord,
    FeatureSchema,
    MarketFeatureSemantics,
    MissingReason,
    MissingValuePolicy,
    MLDatasetValidationError,
    SourceMatchReference,
    order_features,
)

NOW = datetime(2026, 1, 2, tzinfo=UTC)


def _provenance(*sources: SourceMatchReference) -> FeatureProvenance:
    return FeatureProvenance("calc-v1", "pitchvalue.features", "synthetic-v1", "form-v1", sources)


def _feature(name: str, value: object = Decimal("1.2"), **changes: object) -> FeatureRecord:
    values: dict[str, object] = {
        "name": name,
        "value": value,
        "available_at": NOW,
        "schema_version": "v1",
        "provenance": _provenance(),
    }
    values.update(changes)
    return FeatureRecord(**values)  # type: ignore[arg-type]


def test_default_config_is_valid_and_football_only() -> None:
    config = DatasetBuilderConfig()
    assert config.feature_profile is FeatureProfile.FOOTBALL_PERFORMANCE_ONLY
    assert config.missing_value_policy is MissingValuePolicy.PRESERVE_MISSING


def test_odds_experiment_profile_is_distinct_and_valid() -> None:
    config = DatasetBuilderConfig(feature_profile=FeatureProfile.ODDS_INCLUSIVE_EXPERIMENT)
    assert config.feature_profile is FeatureProfile.ODDS_INCLUSIVE_EXPERIMENT
    assert len({profile.value for profile in FeatureProfile}) == 2


def test_config_and_schema_are_immutable() -> None:
    with pytest.raises(FrozenInstanceError):
        DatasetBuilderConfig().dataset_version = "changed"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        FeatureSchema().version = "changed"  # type: ignore[misc]


@pytest.mark.parametrize("version", ["", "  "])
def test_invalid_schema_version_rejected(version: str) -> None:
    with pytest.raises(MLDatasetValidationError):
        FeatureSchema(version=version)


def test_empty_feature_schema_is_explicitly_valid() -> None:
    assert FeatureSchema().feature_order == ()


@pytest.mark.parametrize(
    ("required", "optional"),
    [(("a", "a"), ()), ((), ("a", "a")), (("a",), ("a",))],
)
def test_schema_collisions_rejected(required: tuple[str, ...], optional: tuple[str, ...]) -> None:
    with pytest.raises(MLDatasetValidationError):
        FeatureSchema(required_features=required, optional_features=optional)


def test_invalid_missing_policy_rejected() -> None:
    with pytest.raises(MLDatasetValidationError):
        DatasetBuilderConfig(missing_value_policy="IMPUTE_ZERO")  # type: ignore[arg-type]


def test_config_serialization_is_deterministic() -> None:
    config = DatasetBuilderConfig(feature_schema=FeatureSchema("v1", ("home_ppg",), ("rest",)))
    assert config.to_dict() == config.to_dict()
    assert config.to_dict()["feature_schema"]["required_features"] == ["home_ppg"]


@pytest.mark.parametrize("value", [Decimal("1.25"), 4, True, False, 0])
def test_supported_scalar_feature_values(value: object) -> None:
    assert _feature("feature", value).value == value


@pytest.mark.parametrize("value", [1.5, "1.5", Decimal("NaN"), Decimal("Infinity"), object()])
def test_unsupported_feature_values_rejected(value: object) -> None:
    with pytest.raises(MLDatasetValidationError):
        _feature("feature", value)


def test_missing_feature_requires_reason_and_preserves_none() -> None:
    feature = _feature("rest", None, missing_reason=MissingReason.INSUFFICIENT_HISTORY)
    assert feature.value is None
    assert feature.missing_reason is MissingReason.INSUFFICIENT_HISTORY


def test_missing_feature_without_reason_rejected() -> None:
    with pytest.raises(MLDatasetValidationError):
        _feature("rest", None)


def test_available_feature_with_missing_reason_rejected() -> None:
    with pytest.raises(MLDatasetValidationError):
        _feature("rest", 5, missing_reason=MissingReason.NOT_APPLICABLE)


def test_naive_available_at_rejected() -> None:
    with pytest.raises(MLDatasetValidationError):
        _feature("form", available_at=NOW.replace(tzinfo=None))


def test_source_matches_are_canonically_ordered() -> None:
    later = SourceMatchReference("later", NOW)
    earlier = SourceMatchReference("earlier", NOW - timedelta(days=1))
    provenance = _provenance(later, earlier)
    assert [item.match_id for item in provenance.source_matches] == ["earlier", "later"]


def test_duplicate_source_match_ids_rejected() -> None:
    with pytest.raises(MLDatasetValidationError):
        _provenance(
            SourceMatchReference("same", NOW), SourceMatchReference("same", NOW - timedelta(days=1))
        )


def test_feature_and_provenance_serialization_deterministic() -> None:
    feature = _feature("home_ppg")
    assert feature.to_dict() == feature.to_dict()
    assert feature.to_dict()["value"] == "1.2"


def test_feature_contract_immutable() -> None:
    with pytest.raises(FrozenInstanceError):
        _feature("home_ppg").value = Decimal(0)  # type: ignore[misc]


def test_market_feature_requires_explicit_semantics() -> None:
    with pytest.raises(MLDatasetValidationError):
        _feature("odds", kind=FeatureKind.MARKET_ODDS)
    feature = _feature(
        "odds",
        kind=FeatureKind.MARKET_ODDS,
        market_semantics=MarketFeatureSemantics.DECIMAL_ODDS,
    )
    assert feature.market_semantics is MarketFeatureSemantics.DECIMAL_ODDS


def test_football_feature_rejects_market_semantics() -> None:
    with pytest.raises(MLDatasetValidationError):
        _feature("form", market_semantics=MarketFeatureSemantics.RAW_IMPLIED_PROBABILITY)


def test_schema_order_not_input_order_controls_vector() -> None:
    schema = FeatureSchema("v1", ("home_ppg", "away_ppg"), ("rest",))
    features = (
        _feature("rest", 4),
        _feature("away_ppg", Decimal(1)),
        _feature("home_ppg", Decimal(2)),
    )
    ordered = order_features(features, schema)
    assert [item.name for item in ordered] == ["home_ppg", "away_ppg", "rest"]


def test_row_provenance_preserves_versions() -> None:
    provenance = DatasetRowProvenance("synthetic-v1", "builder-v2")
    assert provenance.to_dict() == {
        "source_version": "synthetic-v1",
        "builder_version": "builder-v2",
    }
