from __future__ import annotations

import os
from dataclasses import replace

import pytest
from sqlalchemy import create_engine, text

from pitchvalue.config import load_settings
from pitchvalue.quality import DataQualityEvaluation
from pitchvalue.quality.repository import persist_evaluation
from test_data_quality_evidence import _evaluation
from test_prediction_api import _clean_fixture_data
from test_prediction_repository import _request


@pytest.mark.integration
def test_scoreless_versioned_evidence_persists_idempotently() -> None:
    engine = create_engine(load_settings(os.environ).database_url)
    try:
        with engine.begin() as connection:
            _clean_fixture_data(connection)
            match_id = int(_request(connection).decision.match_id)
            seed = _evaluation()
            evaluation = replace(
                seed,
                evaluation_id=DataQualityEvaluation.deterministic_id(
                    match_id, seed.evaluated_at, seed.profile, seed.evidence_version
                ),
                match_id=match_id,
            )
            assert persist_evaluation(connection, evaluation)
            assert not persist_evaluation(connection, evaluation)
            row = connection.execute(
                text(
                    "SELECT evidence_profile, quality_score FROM data_quality_evaluations "
                    "WHERE evaluation_id = :evaluation_id"
                ),
                {"evaluation_id": evaluation.evaluation_id},
            ).one()
            assert tuple(row) == ("HISTORICAL_RECONSTRUCTED", None)
            assert (
                connection.execute(text("SELECT count(*) FROM data_quality_evidence")).scalar_one()
                == 6
            )
            connection.execute(text("DELETE FROM data_quality_evidence"))
            connection.execute(text("DELETE FROM data_quality_evaluations"))
            _clean_fixture_data(connection)
    finally:
        engine.dispose()
