"""Persistence for versioned DQ evaluations and their evidence families."""

from __future__ import annotations

import json

from sqlalchemy import Connection, text

from pitchvalue.quality.contracts import DataQualityEvaluation


def persist_evaluation(connection: Connection, evaluation: DataQualityEvaluation) -> bool:
    """Persist one scoreless evaluation atomically and idempotently."""
    with connection.begin_nested():
        inserted = connection.execute(
            text(
                """INSERT INTO data_quality_evaluations (
                    evaluation_id, match_id, run_id, evaluated_at, evidence_profile,
                    evidence_version, quality_score
                ) VALUES (
                    :evaluation_id, :match_id, :run_id, :evaluated_at, :profile,
                    :evidence_version, NULL
                ) ON CONFLICT (evaluation_id) DO NOTHING RETURNING evaluation_id"""
            ),
            {
                "evaluation_id": evaluation.evaluation_id,
                "match_id": evaluation.match_id,
                "run_id": evaluation.run_id,
                "evaluated_at": evaluation.evaluated_at,
                "profile": evaluation.profile.value,
                "evidence_version": evaluation.evidence_version,
            },
        ).scalar_one_or_none()
        if inserted is None:
            return False
        for item in evaluation.evidence:
            connection.execute(
                text(
                    """INSERT INTO data_quality_evidence (
                        evaluation_id, evidence_family, availability, hard_fail,
                        reason_codes, provenance, observed_at
                    ) VALUES (
                        :evaluation_id, :family, :availability, :hard_fail,
                        :reason_codes, CAST(:provenance AS jsonb), :observed_at
                    )"""
                ),
                {
                    "evaluation_id": evaluation.evaluation_id,
                    "family": item.family.value,
                    "availability": item.availability.value,
                    "hard_fail": item.hard_fail,
                    "reason_codes": list(item.reason_codes),
                    "provenance": json.dumps(
                        dict(item.provenance), sort_keys=True, separators=(",", ":")
                    ),
                    "observed_at": item.observed_at,
                },
            )
    return True
