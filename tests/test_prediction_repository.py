from __future__ import annotations

import os
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import Connection, Engine, create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from pitchvalue.config import load_settings
from pitchvalue.prediction.persistence import (
    PredictionPersistenceError,
    PredictionPersistenceRequest,
    PredictionWriteStatus,
)
from pitchvalue.prediction.repository import (
    current_predictions,
    invalidate_prediction,
    persist_match_prediction,
    prediction_by_identity,
    predictions_for_match,
)
from test_prediction_persistence import AS_OF, GENERATED, make_decision

D = Decimal


@pytest.fixture(scope="session")
def prediction_engine() -> Engine:
    return create_engine(load_settings(os.environ).database_url)


@pytest.fixture
def db(prediction_engine: Engine):
    with prediction_engine.connect() as connection:
        transaction = connection.begin()
        yield connection
        transaction.rollback()


def _lineage(db: Connection) -> tuple[int, int, int]:
    existing = db.execute(
        text(
            """SELECT refs.match_id, staging.staging_row_id, refs.match_provider_ref_id
            FROM providers
            JOIN import_batches batch USING (provider_id)
            JOIN football_data_staging_rows staging USING (import_batch_id)
            JOIN match_provider_refs refs
              ON refs.provider_id = providers.provider_id
             AND refs.source_url = batch.source_identifier
             AND refs.source_record_hash = staging.row_hash
            WHERE providers.name = 'TASK 21 fixture provider'"""
        )
    ).one_or_none()
    if existing is not None:
        return (
            int(existing.match_id),
            int(existing.staging_row_id),
            int(existing.match_provider_ref_id),
        )
    provider_id = db.execute(
        text(
            """INSERT INTO providers (name, provider_type, priority)
            VALUES ('TASK 21 fixture provider', 'football_data', 1)
            RETURNING provider_id"""
        )
    ).scalar_one()
    competition_id = db.execute(
        text(
            """INSERT INTO competitions (
                canonical_name, country_code, jurisdiction_code, competition_type
            ) VALUES ('TASK 21 Competition', 'TUR', 'TUR', 'domestic_league')
            RETURNING competition_id"""
        )
    ).scalar_one()
    season_id = db.execute(
        text(
            """INSERT INTO seasons (
                competition_id, season_name, start_year, end_year, status
            ) VALUES (:competition_id, '2099/00', 2099, 2100, 'planned')
            RETURNING season_id"""
        ),
        {"competition_id": competition_id},
    ).scalar_one()
    team_ids = [
        db.execute(
            text(
                """INSERT INTO teams (canonical_name, normalized_name, country_code)
                VALUES (:name, :normalized, 'TUR') RETURNING team_id"""
            ),
            {"name": f"TASK 21 Team {index}", "normalized": f"task 21 team {index}"},
        ).scalar_one()
        for index in (1, 2)
    ]
    match_id = db.execute(
        text(
            """INSERT INTO matches (
                competition_id, season_id, home_team_id, away_team_id, status
            ) VALUES (
                :competition_id, :season_id, :home_team_id, :away_team_id, 'SCHEDULED'
            ) RETURNING match_id"""
        ),
        {
            "competition_id": competition_id,
            "season_id": season_id,
            "home_team_id": team_ids[0],
            "away_team_id": team_ids[1],
        },
    ).scalar_one()
    source_identifier = "task21://fixture"
    source_hash = "a" * 64
    batch_id = db.execute(
        text(
            """INSERT INTO import_batches (
                provider_id, started_at, source_identifier, source_hash, status
            ) VALUES (
                :provider_id, :started_at, :source_identifier, :source_hash, 'completed'
            ) RETURNING import_batch_id"""
        ),
        {
            "provider_id": provider_id,
            "started_at": AS_OF - timedelta(days=1),
            "source_identifier": source_identifier,
            "source_hash": source_hash,
        },
    ).scalar_one()
    staging_id = db.execute(
        text(
            """INSERT INTO football_data_staging_rows (
                import_batch_id, source_row_number, competition_source_code,
                season_name, raw_row, row_hash, parsing_status
            ) VALUES (
                :batch_id, 1, 'T21', '2099/00', CAST('{}' AS jsonb), :row_hash, 'parsed'
            ) RETURNING staging_row_id"""
        ),
        {"batch_id": batch_id, "row_hash": source_hash},
    ).scalar_one()
    provider_ref_id = db.execute(
        text(
            """INSERT INTO match_provider_refs (
                match_id, provider_id, source_url, source_record_hash
            ) VALUES (
                :match_id, :provider_id, :source_url, :source_record_hash
            ) RETURNING match_provider_ref_id"""
        ),
        {
            "match_id": match_id,
            "provider_id": provider_id,
            "source_url": source_identifier,
            "source_record_hash": source_hash,
        },
    ).scalar_one()
    return int(match_id), int(staging_id), int(provider_ref_id)


def _request(db: Connection, **kwargs: object) -> PredictionPersistenceRequest:
    match_id, staging_id, provider_ref_id = _lineage(db)
    decision = make_decision(
        match_id=str(match_id),
        source_staging_row_id=staging_id,
        source_match_provider_ref_id=provider_ref_id,
        **kwargs,
    )
    return PredictionPersistenceRequest(decision, GENERATED)


@pytest.mark.integration
def test_same_output_is_idempotent_and_decimal_values_round_trip(db: Connection) -> None:
    request = _request(db)
    first = persist_match_prediction(db, request)
    second = persist_match_prediction(db, request)
    assert (first.status, first.created, first.unchanged) == (PredictionWriteStatus.CREATED, 3, 0)
    assert (second.status, second.created, second.unchanged) == (
        PredictionWriteStatus.UNCHANGED,
        0,
        3,
    )
    rows = predictions_for_match(db, int(request.decision.match_id))
    assert len(rows) == 3
    assert rows[0].model_probability in {D("0.50"), D("0.30"), D("0.20")}
    assert all(row.bet_score is None for row in rows)
    assert all(row.market_observed_at is None for row in rows)
    assert all(not row.publication_eligible for row in rows)
    assert all(row.policy_decision == "PICK" for row in rows)
    assert all(row.agreement_support_count == 3 for row in rows)
    assert all(row.data_quality_score == D("90") for row in rows)
    assert prediction_by_identity(db, rows[0].identity) == rows[0]


@pytest.mark.integration
def test_model_versions_coexist_and_old_version_remains_queryable(db: Connection) -> None:
    first = _request(db, model_version="model-v1")
    second = _request(db, model_version="model-v2")
    persist_match_prediction(db, first)
    persist_match_prediction(db, second)
    rows = predictions_for_match(db, int(first.decision.match_id))
    assert {row.model_version for row in rows} == {"model-v1", "model-v2"}
    assert len(rows) == 6


@pytest.mark.integration
def test_same_identity_with_changed_payload_is_not_silently_overwritten(db: Connection) -> None:
    request = _request(db)
    persist_match_prediction(db, request)
    decisions = list(request.decision.selection_decisions)
    decisions[0] = replace(decisions[0], policy_decision=decisions[0].policy_decision.NO_BET)
    conflict = replace(request.decision, selection_decisions=tuple(decisions))
    with pytest.raises(PredictionPersistenceError, match="different payload"):
        persist_match_prediction(db, PredictionPersistenceRequest(conflict, GENERATED))
    rows = predictions_for_match(db, int(request.decision.match_id))
    assert len(rows) == 3
    assert rows[0].policy_decision == "PICK"


@pytest.mark.integration
def test_match_write_is_atomic_when_one_selection_violates_database_constraint(
    db: Connection,
) -> None:
    request = _request(db, model_version="atomic-v1")
    decisions = list(request.decision.selection_decisions)
    decisions[-1] = replace(decisions[-1], decimal_odds=D("1"))
    broken = replace(request.decision, selection_decisions=tuple(decisions))
    with pytest.raises(IntegrityError):
        persist_match_prediction(db, PredictionPersistenceRequest(broken, GENERATED))
    assert not [
        row
        for row in predictions_for_match(db, int(request.decision.match_id))
        if row.model_version == "atomic-v1"
    ]


@pytest.mark.integration
def test_exact_time_publication_is_preserved_not_inferred(db: Connection) -> None:
    request = _request(db, exact=True, publication_eligible=True, bet_score=D("80"))
    persist_match_prediction(db, request)
    rows = current_predictions(db, [int(request.decision.match_id)], publication_only=True)
    assert len(rows) == 3
    assert all(row.public_candidate for row in rows)
    assert all(row.bet_score == D("80") for row in rows)


@pytest.mark.integration
def test_current_read_and_invalidation_keep_audit_history(db: Connection) -> None:
    request = _request(db, exact=True, publication_eligible=True, bet_score=D("80"))
    result = persist_match_prediction(db, request)
    assert invalidate_prediction(
        db,
        result.prediction_snapshot_ids[0],
        invalidated_at=datetime(2026, 1, 3, tzinfo=UTC),
        reason="SOURCE_CORRECTION",
    )
    current = current_predictions(db, [int(request.decision.match_id)], publication_only=True)
    history = predictions_for_match(db, int(request.decision.match_id))
    assert len(current) == 2
    assert len(history) == 3
    assert any(row.record_status.value == "invalidated" for row in history)


@pytest.mark.integration
def test_generated_prediction_and_persisted_timestamps_are_distinct(db: Connection) -> None:
    request = _request(db)
    persist_match_prediction(db, request)
    row = predictions_for_match(db, int(request.decision.match_id))[0]
    assert row.prediction_as_of == AS_OF
    assert row.generated_at == GENERATED
    assert row.persisted_at >= GENERATED - timedelta(days=365)


@pytest.mark.integration
def test_database_rejects_role_only_publication_even_for_direct_insert(db: Connection) -> None:
    request = _request(db)
    persist_match_prediction(db, request)
    prediction_id = predictions_for_match(db, int(request.decision.match_id))[
        0
    ].prediction_snapshot_id
    with pytest.raises(IntegrityError), db.begin_nested():
        db.execute(
            text(
                "UPDATE prediction_snapshots SET publication_eligible = true "
                "WHERE prediction_snapshot_id = :prediction_id"
            ),
            {"prediction_id": prediction_id},
        )


@pytest.mark.integration
def test_schema_exposes_required_constraints_indexes_and_foreign_keys(db: Connection) -> None:
    inspector = inspect(db)
    columns = {item["name"]: item for item in inspector.get_columns("prediction_snapshots")}
    assert columns["bet_score"]["nullable"] is True
    assert columns["prediction_as_of"]["nullable"] is False
    indexes = {item["name"] for item in inspector.get_indexes("prediction_snapshots")}
    assert indexes >= {
        "uq_prediction_semantic_identity",
        "ix_prediction_snapshots_match_current",
        "ix_prediction_snapshots_publishable",
    }
    foreign_keys = {item["name"] for item in inspector.get_foreign_keys("prediction_snapshots")}
    assert foreign_keys == {
        "prediction_snapshots_match_id_fkey",
        "prediction_snapshots_source_match_provider_ref_id_fkey",
        "prediction_snapshots_source_staging_row_id_fkey",
    }


@pytest.mark.integration
def test_database_rejects_blank_semantic_version(db: Connection) -> None:
    request = _request(db)
    persist_match_prediction(db, request)
    prediction_id = predictions_for_match(db, int(request.decision.match_id))[
        0
    ].prediction_snapshot_id
    with pytest.raises(IntegrityError), db.begin_nested():
        db.execute(
            text(
                "UPDATE prediction_snapshots SET policy_version = '   ' "
                "WHERE prediction_snapshot_id = :prediction_id"
            ),
            {"prediction_id": prediction_id},
        )


@pytest.mark.integration
def test_database_rejects_exact_timing_without_market_timestamp(db: Connection) -> None:
    request = _request(db)
    persist_match_prediction(db, request)
    prediction_id = predictions_for_match(db, int(request.decision.match_id))[
        0
    ].prediction_snapshot_id
    with pytest.raises(IntegrityError), db.begin_nested():
        db.execute(
            text(
                "UPDATE prediction_snapshots SET timing_semantics = 'exact' "
                "WHERE prediction_snapshot_id = :prediction_id"
            ),
            {"prediction_id": prediction_id},
        )
