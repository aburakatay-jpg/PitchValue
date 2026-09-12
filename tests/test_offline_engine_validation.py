from __future__ import annotations

import socket
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from pitchvalue.markets.edge import RawMLProbability
from pitchvalue.markets.edge_evaluation import RawMLOOSRow
from pitchvalue.markets.history.contracts import ObservationRole
from pitchvalue.ml.config import FeatureProfile
from pitchvalue.ml.contracts import (
    FeatureKind,
    FeatureRecord,
    RowStatus,
    TargetDefinition,
    TargetMode,
    TrainingRow,
)
from pitchvalue.ml.model import MLClassProbability
from pitchvalue.ml.provenance import DatasetRowProvenance, FeatureProvenance, SourceMatchReference
from pitchvalue.models.signals.config import ModelFamily
from pitchvalue.models.signals.contracts import (
    DirectionalPreference,
    ModelSignal,
    SignalStatus,
)
from pitchvalue.operations import offline_validation as offline
from pitchvalue.prediction.contracts import MarketFamily, Selection

NOW = datetime(2025, 5, 2, 12, tzinfo=UTC)
TARGET = TargetDefinition(
    MarketFamily.MATCH_RESULT,
    TargetMode.MULTICLASS,
    (Selection.HOME, Selection.DRAW, Selection.AWAY),
)


def _row(*, leaking: bool = False) -> TrainingRow:
    source_kickoff = NOW if leaking else NOW - timedelta(days=2)
    provenance = FeatureProvenance(
        "feature-v1",
        "test.offline",
        "historical-v1",
        "calculation-v1",
        (SourceMatchReference("source-match", source_kickoff),),
    )
    return TrainingRow(
        "row-1",
        "match-1",
        "competition-1",
        "season-1",
        NOW + timedelta(days=1),
        NOW,
        "schema-v1",
        FeatureProfile.FOOTBALL_PERFORMANCE_ONLY,
        TARGET,
        Selection.HOME,
        (
            FeatureRecord(
                "feature",
                Decimal("1.25"),
                NOW,
                "schema-v1",
                provenance,
                FeatureKind.FOOTBALL_PERFORMANCE,
            ),
        ),
        DatasetRowProvenance("historical-v1"),
        RowStatus.READY,
    )


def _oos() -> RawMLOOSRow:
    return RawMLOOSRow(
        "fold-1",
        "competition-1",
        "season-1",
        Selection.HOME,
        RawMLProbability(
            "row-1",
            "match-1",
            "multinomial_logistic_v1",
            FeatureProfile.FOOTBALL_PERFORMANCE_ONLY.value,
            NOW,
            (
                MLClassProbability(Selection.HOME, Decimal("0.5")),
                MLClassProbability(Selection.DRAW, Decimal("0.3")),
                MLClassProbability(Selection.AWAY, Decimal("0.2")),
            ),
        ),
    )


def _signal() -> ModelSignal:
    return ModelSignal(
        ModelFamily.ML,
        "multinomial_logistic_v1",
        "match-1",
        MarketFamily.MATCH_RESULT,
        Selection.HOME,
        DirectionalPreference.HOME,
        SignalStatus.READY,
        Decimal("0.5"),
        probability=Decimal("0.5"),
    )


def _patch_pipeline(
    monkeypatch: pytest.MonkeyPatch,
    *,
    oos: bool = True,
    market: bool = False,
    leaking: bool = False,
) -> None:
    row = _row(leaking=leaking)
    monkeypatch.setattr(
        offline,
        "_database_counts",
        lambda connection: (("prediction_snapshots", 0), ("engine_runs", 0)),
    )
    monkeypatch.setattr(offline, "_statistics_availability", lambda connection: {"match-1": True})
    monkeypatch.setattr(
        offline,
        "load_real_match_result_dataset",
        lambda connection: SimpleNamespace(dataset=SimpleNamespace(rows=(row,))),
    )
    monkeypatch.setattr(offline, "generate_raw_ml_oos", lambda dataset: (_oos(),) if oos else ())
    monkeypatch.setattr(
        offline,
        "load_real_ensemble_evidence",
        lambda connection, dataset, row_ids: (SimpleNamespace(row_id="row-1"),) if oos else (),
    )
    group = SimpleNamespace(match_id="match-1", observation_role=ObservationRole.SOURCE_PREMATCH)
    monkeypatch.setattr(
        offline,
        "load_historical_match_result_markets",
        lambda connection: SimpleNamespace(groups=(group,) if market else ()),
    )
    monkeypatch.setattr(offline, "build_real_model_signals", lambda row, evidence: (_signal(),))
    if market:
        edge = SimpleNamespace(
            edges=(SimpleNamespace(selection=Selection.HOME, edge=Decimal("0.04")),)
        )
        monkeypatch.setattr(offline, "build_market_probability", lambda group: object())
        monkeypatch.setattr(offline, "calculate_market_edges", lambda model, probability: edge)


def _connection(*, read_only: bool = True) -> MagicMock:
    connection = MagicMock()
    connection.execute.return_value.scalar_one.return_value = "on" if read_only else "off"
    return connection


def test_phase_one_requires_database_enforced_read_only_transaction() -> None:
    with pytest.raises(RuntimeError, match="read-only transaction"):
        offline.run_offline_validation(_connection(read_only=False), sample_size=1)


def test_model_only_execution_is_deterministic_and_non_public(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_pipeline(monkeypatch)
    first = offline.run_offline_validation(_connection(), sample_size=1)
    second = offline.run_offline_validation(_connection(), sample_size=1)
    assert first.to_dict() == second.to_dict()
    assert first.executable_matches == 1
    assert first.matches[0].odds_mode is offline.OfflineOddsMode.MODEL_ONLY
    assert first.matches[0].publication_eligible is False
    assert first.database_writes == 0
    assert first.network_requests == 0


def test_missing_temporal_model_evidence_is_insufficient_not_fabricated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_pipeline(monkeypatch, oos=False)
    report = offline.run_offline_validation(_connection(), sample_size=1)
    assert report.insufficient_data_matches == 1
    assert report.matches[0].raw_ml_probabilities == ()
    assert "TEMPORAL_OOS_MODEL_EVIDENCE_UNAVAILABLE" in report.matches[0].diagnostics


def test_same_time_historical_source_is_quarantined(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_pipeline(monkeypatch, leaking=True)
    report = offline.run_offline_validation(_connection(), sample_size=1)
    assert report.quarantined_matches == 1
    assert report.matches[0].leakage_safe is False
    assert report.matches[0].diagnostics == ("HISTORICAL_LEAKAGE_DETECTED",)


def test_optional_provider_features_remain_explicitly_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_pipeline(monkeypatch)
    result = offline.run_offline_validation(_connection(), sample_size=1).matches[0]
    assert "MARKET_STABILITY" in result.unavailable_features
    assert "FINAL_CHECK" in result.unavailable_features
    assert "MARKET_EXACT_TIMESTAMP" in result.unavailable_features
    assert result.bet_score_complete is False


def test_one_engine_exception_is_isolated_as_engine_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_pipeline(monkeypatch, market=True)

    def fail(*args: object) -> tuple[()]:
        raise ArithmeticError("synthetic isolated failure")

    report = offline.run_offline_validation(_connection(), sample_size=1, decision_runner=fail)
    assert report.engine_failures == 1
    assert report.matches[0].disposition is offline.OfflineDisposition.ENGINE_FAILURE
    assert report.matches[0].diagnostics == ("ENGINE_EXCEPTION:ArithmeticError",)


def test_sample_selection_covers_insufficient_and_missing_statistics() -> None:
    first = _row()
    second = TrainingRow(
        "row-2",
        "match-2",
        first.competition_id,
        first.season_id,
        first.kickoff + timedelta(days=1),
        first.prediction_as_of + timedelta(days=1),
        first.feature_schema_version,
        first.feature_profile,
        first.target_definition,
        Selection.DRAW,
        first.features,
        first.provenance,
        first.status,
    )
    selected = offline._select_rows(
        (first, second), frozenset({"row-2"}), {"match-1": False, "match-2": True}, 2
    )
    assert tuple(item.row_id for item in selected) == ("row-1", "row-2")


def test_offline_execution_has_no_network_requirement(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_pipeline(monkeypatch)

    def reject_network(*args: object, **kwargs: object) -> None:
        raise AssertionError("network access is forbidden")

    monkeypatch.setattr(socket, "create_connection", reject_network)
    report = offline.run_offline_validation(_connection(), sample_size=1)
    assert report.executable_matches == 1
    assert report.network_requests == 0
