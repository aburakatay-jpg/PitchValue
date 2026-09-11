"""PostgreSQL repository for durable prediction snapshots and cache reads."""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import Connection, RowMapping, bindparam, text

from pitchvalue.prediction.persistence import (
    PersistedPrediction,
    PredictionIdentity,
    PredictionPersistenceError,
    PredictionPersistenceRequest,
    PredictionRecordStatus,
    PredictionWriteResult,
    PredictionWriteStatus,
    payload_hash,
    selection_payload,
)

logger = logging.getLogger(__name__)

_IDENTITY_COLUMNS = """
match_id, prediction_as_of, market, selection, probability_source, model_version, feature_profile,
orchestrator_version, policy_version, edge_engine_version, no_vig_version,
bookmaker, observation_role, timing_semantics, mapping_version,
normalization_version, quality_policy_version
"""

_INSERT = text(
    f"""
    INSERT INTO prediction_snapshots (
        {_IDENTITY_COLUMNS}, generated_at, market_observed_at,
        comparison_status, market_quality, model_probability, decimal_odds,
        no_vig_market_probability, edge, bet_score, bet_score_completeness,
        score_class, policy_decision, publication_eligible, agreement_support_count,
        agreement_usable_count, agreement_configured_count, agreement_status,
        data_quality_score, poisson_status, elo_status, form_status, components, gates,
        blockers, diagnostics, data_quality_diagnostics, source_match_provider_ref_id,
        source_staging_row_id, source_field, payload_hash
    ) VALUES (
        :match_id, :prediction_as_of, :market, :selection, :probability_source, :model_version,
        :feature_profile, :orchestrator_version, :policy_version, :edge_engine_version,
        :no_vig_version, :bookmaker, :observation_role, :timing_semantics,
        :mapping_version, :normalization_version, :quality_policy_version,
        :generated_at, :market_observed_at, :comparison_status,
        :market_quality, :model_probability, :decimal_odds, :no_vig_market_probability,
        :edge, :bet_score, :bet_score_completeness, :score_class, :policy_decision,
        :publication_eligible, :agreement_support_count, :agreement_usable_count,
        :agreement_configured_count, :agreement_status, :data_quality_score,
        :poisson_status, :elo_status, :form_status, CAST(:components AS jsonb),
        CAST(:gates AS jsonb), :blockers, :diagnostics, :data_quality_diagnostics,
        :source_match_provider_ref_id, :source_staging_row_id, :source_field, :payload_hash
    )
    ON CONFLICT ({_IDENTITY_COLUMNS}) DO NOTHING
    RETURNING prediction_snapshot_id
    """
)

_FIND_IDENTITY = text(
    f"""
    SELECT prediction_snapshot_id, payload_hash
    FROM prediction_snapshots
    WHERE ({_IDENTITY_COLUMNS}) = (
        :match_id, :prediction_as_of, :market, :selection, :probability_source, :model_version,
        :feature_profile, :orchestrator_version, :policy_version, :edge_engine_version,
        :no_vig_version, :bookmaker, :observation_role, :timing_semantics,
        :mapping_version, :normalization_version, :quality_policy_version
    )
    """
)

_READ_COLUMNS = """
prediction_snapshot_id, match_id, prediction_as_of, generated_at, persisted_at,
market, selection, model_probability, decimal_odds, no_vig_market_probability,
edge, bet_score, bet_score_completeness, score_class, policy_decision,
publication_eligible, blockers, diagnostics, components, gates, observation_role,
bookmaker,
agreement_support_count, agreement_usable_count, agreement_configured_count,
agreement_status, data_quality_score, data_quality_diagnostics,
poisson_status, elo_status, form_status,
timing_semantics, market_observed_at, comparison_status, market_quality,
probability_source, model_version, feature_profile, orchestrator_version,
policy_version, edge_engine_version, no_vig_version, source_match_provider_ref_id,
source_staging_row_id, source_field, mapping_version, normalization_version,
quality_policy_version, record_status, invalidated_at, invalidation_reason, payload_hash
"""


def _parameters(payload: dict[str, Any], generated_at: datetime) -> dict[str, Any]:
    values = dict(payload)
    values["prediction_as_of"] = datetime.fromisoformat(values["prediction_as_of"])
    observed = values["market_observed_at"]
    values["market_observed_at"] = None if observed is None else datetime.fromisoformat(observed)
    values["generated_at"] = generated_at
    values["components"] = json.dumps(values["components"], sort_keys=True, separators=(",", ":"))
    values["gates"] = json.dumps(values["gates"], sort_keys=True, separators=(",", ":"))
    values["payload_hash"] = payload_hash(payload)
    return values


def persist_match_prediction(
    connection: Connection, request: PredictionPersistenceRequest
) -> PredictionWriteResult:
    """Persist a whole match atomically; never recalculate supplied values."""
    created = 0
    unchanged = 0
    identifiers: list[int] = []
    try:
        with connection.begin_nested():
            for selection in request.decision.selection_decisions:
                payload = selection_payload(selection, request)
                parameters = _parameters(payload, request.generated_at)
                inserted = connection.execute(_INSERT, parameters).scalar_one_or_none()
                if inserted is not None:
                    created += 1
                    identifiers.append(inserted)
                    continue
                existing = connection.execute(_FIND_IDENTITY, parameters).one()
                if existing.payload_hash != parameters["payload_hash"]:
                    raise PredictionPersistenceError(
                        "semantic prediction identity already has a different payload"
                    )
                unchanged += 1
                identifiers.append(existing.prediction_snapshot_id)
    except Exception:
        logger.error(
            "prediction persistence failed",
            extra={"match_id": request.decision.match_id},
        )
        raise
    status = PredictionWriteStatus.CREATED if created else PredictionWriteStatus.UNCHANGED
    return PredictionWriteResult(status, created, unchanged, tuple(identifiers))


def _json_array(value: Any) -> tuple[dict[str, Any], ...]:
    decoded = json.loads(value) if isinstance(value, str) else value
    return tuple(decoded)


def _record(row: RowMapping) -> PersistedPrediction:
    return PersistedPrediction(
        **{
            **dict(row),
            "blockers": tuple(row["blockers"]),
            "diagnostics": tuple(row["diagnostics"]),
            "data_quality_diagnostics": tuple(row["data_quality_diagnostics"]),
            "components": _json_array(row["components"]),
            "gates": _json_array(row["gates"]),
            "record_status": PredictionRecordStatus(row["record_status"]),
        }
    )


def predictions_for_match(connection: Connection, match_id: int) -> tuple[PersistedPrediction, ...]:
    rows = connection.execute(
        text(
            f"""SELECT {_READ_COLUMNS} FROM prediction_snapshots
            WHERE match_id = :match_id
            ORDER BY prediction_as_of DESC, generated_at DESC, market, selection"""
        ),
        {"match_id": match_id},
    ).mappings()
    return tuple(_record(row) for row in rows)


def current_predictions(
    connection: Connection, match_ids: Sequence[int], *, publication_only: bool = False
) -> tuple[PersistedPrediction, ...]:
    """Return cached current rows for fixtures without invoking engine logic."""
    if not match_ids:
        return ()
    publication = "WHERE publication_eligible = true" if publication_only else ""
    statement = text(
        f"""
        SELECT * FROM (
            SELECT DISTINCT ON (match_id, market, selection) {_READ_COLUMNS}
            FROM prediction_snapshots
            WHERE match_id IN :match_ids AND record_status = 'active'
            ORDER BY match_id, market, selection, prediction_as_of DESC,
                     generated_at DESC, prediction_snapshot_id DESC
        ) AS current_predictions
        {publication}
        ORDER BY match_id, market, selection
        """
    ).bindparams(bindparam("match_ids", expanding=True))
    rows = connection.execute(statement, {"match_ids": list(match_ids)}).mappings()
    return tuple(_record(row) for row in rows)


def published_predictions(
    connection: Connection,
    *,
    match_ids: Sequence[int] | None = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[PersistedPrediction, ...]:
    """Return a bounded current publication cache, optionally for a fixture set."""
    if limit < 1 or limit > 100 or offset < 0:
        raise ValueError("published prediction bounds are invalid")
    if match_ids is not None and not match_ids:
        return ()
    fixture_filter = "AND match_id IN :match_ids" if match_ids is not None else ""
    statement = text(
        f"""
        SELECT * FROM (
            SELECT DISTINCT ON (match_id, market, selection) {_READ_COLUMNS}
            FROM prediction_snapshots
            WHERE record_status = 'active'
              {fixture_filter}
            ORDER BY match_id, market, selection, prediction_as_of DESC,
                     generated_at DESC, prediction_snapshot_id DESC
        ) AS current_predictions
        WHERE publication_eligible = true
        ORDER BY match_id, market, selection
        LIMIT :limit OFFSET :offset
        """
    )
    if match_ids is not None:
        statement = statement.bindparams(bindparam("match_ids", expanding=True))
    parameters: dict[str, object] = {"limit": limit, "offset": offset}
    if match_ids is not None:
        parameters["match_ids"] = list(match_ids)
    rows = connection.execute(statement, parameters).mappings()
    return tuple(_record(row) for row in rows)


def prediction_by_identity(
    connection: Connection, identity: PredictionIdentity
) -> PersistedPrediction | None:
    row = (
        connection.execute(
            text(
                f"SELECT {_READ_COLUMNS} FROM prediction_snapshots WHERE ({_IDENTITY_COLUMNS}) = ("
                ":match_id, :prediction_as_of, :market, :selection, :probability_source, "
                ":model_version, "
                ":feature_profile, :orchestrator_version, :policy_version, :edge_engine_version, "
                ":no_vig_version, :bookmaker, :observation_role, :timing_semantics, "
                ":mapping_version, :normalization_version, :quality_policy_version)"
            ),
            identity.parameters(),
        )
        .mappings()
        .one_or_none()
    )
    return None if row is None else _record(row)


def invalidate_prediction(
    connection: Connection,
    prediction_snapshot_id: int,
    *,
    invalidated_at: datetime,
    reason: str,
    superseded: bool = False,
) -> bool:
    if invalidated_at.tzinfo is None or invalidated_at.utcoffset() is None:
        raise PredictionPersistenceError("invalidated_at must be timezone-aware")
    if not reason.strip():
        raise PredictionPersistenceError("invalidation reason must be nonblank")
    status = "superseded" if superseded else "invalidated"
    result = connection.execute(
        text(
            """UPDATE prediction_snapshots
            SET record_status = :status, invalidated_at = :invalidated_at,
                invalidation_reason = :reason
            WHERE prediction_snapshot_id = :prediction_snapshot_id
              AND record_status = 'active'"""
        ),
        {
            "status": status,
            "invalidated_at": invalidated_at,
            "reason": reason,
            "prediction_snapshot_id": prediction_snapshot_id,
        },
    )
    changed = result.rowcount == 1
    if changed:
        logger.info(
            "prediction snapshot invalidated",
            extra={"prediction_snapshot_id": prediction_snapshot_id, "record_status": status},
        )
    return changed
