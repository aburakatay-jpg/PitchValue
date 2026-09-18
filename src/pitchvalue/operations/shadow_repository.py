"""Durable provider-neutral storage for internal, never-public shadow evidence."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Connection, text


@dataclass(frozen=True)
class ShadowAnalysisWrite:
    run_id: str
    logical_run_id: str
    match_id: int
    prediction_as_of: datetime
    model_version: str
    feature_version: str
    raw_ml_probabilities: Mapping[str, Decimal]
    elo: Mapping[str, object] | None
    poisson: Mapping[str, object] | None
    form: Mapping[str, object] | None
    agreement: Mapping[str, object] | None
    odds_mode: str
    dq_state: str
    market_stability: str
    calibration_confidence: str
    bet_score: Decimal | None
    bet_score_completeness: str
    diagnostics: tuple[str, ...] = ()
    publication_eligible: bool = False

    def __post_init__(self) -> None:
        if self.publication_eligible:
            raise ValueError("shadow analysis can never be publication eligible")
        if self.prediction_as_of.tzinfo is None or self.prediction_as_of.utcoffset() is None:
            raise ValueError("prediction_as_of must be timezone-aware")
        if not self.logical_run_id.strip():
            raise ValueError("logical_run_id must be nonblank")

    def canonical_payload(self) -> dict[str, object]:
        return {
            "logical_run_id": self.logical_run_id,
            "match_id": self.match_id,
            "prediction_as_of": self.prediction_as_of.isoformat(),
            "model_version": self.model_version,
            "feature_version": self.feature_version,
            "raw_ml_probabilities": {
                key: str(value) for key, value in sorted(self.raw_ml_probabilities.items())
            },
            "elo": self.elo,
            "poisson": self.poisson,
            "form": self.form,
            "agreement": self.agreement,
            "odds_mode": self.odds_mode,
            "dq_state": self.dq_state,
            "market_stability": self.market_stability,
            "calibration_confidence": self.calibration_confidence,
            "bet_score": None if self.bet_score is None else str(self.bet_score),
            "bet_score_completeness": self.bet_score_completeness,
            "diagnostics": list(self.diagnostics),
            "publication_eligible": False,
        }


def persist_shadow_analysis(connection: Connection, value: ShadowAnalysisWrite) -> bool:
    payload = value.canonical_payload()
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    fingerprint = hashlib.sha256(serialized.encode()).hexdigest()
    analysis_id = hashlib.sha256(
        f"{value.logical_run_id}|{value.match_id}|{value.model_version}|{value.feature_version}".encode()
    ).hexdigest()
    result = connection.execute(
        text(
            """INSERT INTO shadow_analysis_snapshots (
                shadow_analysis_id, run_id, logical_run_id, match_id, prediction_as_of, model_version,
                feature_version, raw_ml_probabilities, elo_output, poisson_output,
                form_output, agreement_output, odds_mode, dq_state, market_stability,
                calibration_confidence, bet_score, bet_score_completeness,
                publication_eligible, diagnostics, payload_hash
            ) VALUES (
                :analysis_id,:run_id,:logical_run_id,:match_id,:prediction_as_of,:model_version,
                :feature_version,CAST(:raw_ml AS jsonb),CAST(:elo AS jsonb),
                CAST(:poisson AS jsonb),CAST(:form AS jsonb),CAST(:agreement AS jsonb),
                :odds_mode,:dq_state,:market_stability,:calibration_confidence,
                :bet_score,:completeness,false,:diagnostics,:payload_hash
            ) ON CONFLICT DO NOTHING RETURNING shadow_analysis_id"""
        ),
        {
            "analysis_id": analysis_id,
            "run_id": value.run_id,
            "logical_run_id": value.logical_run_id,
            "match_id": value.match_id,
            "prediction_as_of": value.prediction_as_of,
            "model_version": value.model_version,
            "feature_version": value.feature_version,
            "raw_ml": _json(payload["raw_ml_probabilities"]),
            "elo": _json(value.elo),
            "poisson": _json(value.poisson),
            "form": _json(value.form),
            "agreement": _json(value.agreement),
            "odds_mode": value.odds_mode,
            "dq_state": value.dq_state,
            "market_stability": value.market_stability,
            "calibration_confidence": value.calibration_confidence,
            "bet_score": value.bet_score,
            "completeness": value.bet_score_completeness,
            "diagnostics": list(value.diagnostics),
            "payload_hash": fingerprint,
        },
    ).scalar_one_or_none()
    if result is not None:
        return True
    existing = connection.execute(
        text(
            """SELECT payload_hash FROM shadow_analysis_snapshots
            WHERE logical_run_id=:logical_run_id AND match_id=:match_id"""
        ),
        {"logical_run_id": value.logical_run_id, "match_id": value.match_id},
    ).scalar_one()
    if existing != fingerprint:
        raise ValueError("shadow semantic identity has conflicting payload")
    return False


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
