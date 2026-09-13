from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import Engine, create_engine, text

from pitchvalue.config import load_settings
from pitchvalue.operations.metadata import (
    FreshnessState,
    ReportLocationState,
    load_fixture_refresh_metadata,
    resolve_report_location,
)


@pytest.fixture(scope="session")
def metadata_engine() -> Iterator[Engine]:
    engine = create_engine(load_settings(os.environ).database_url)
    yield engine
    engine.dispose()


def test_fixture_refresh_falls_back_to_durable_source_last_seen(metadata_engine: Engine) -> None:
    with metadata_engine.connect() as connection:
        latest = connection.execute(
            text(
                """SELECT max(last_seen_at) FROM source_entity_references
                WHERE entity_type='FIXTURE'"""
            )
        ).scalar_one()
        result = load_fixture_refresh_metadata(connection, now=latest + timedelta(hours=1))
    assert result.state is FreshnessState.FRESH
    assert result.last_success_at == latest
    assert result.evidence_source in {"fixture_source_last_seen", "fixture_refresh_event"}


def test_fixture_refresh_can_be_stale_without_manufacturing_timestamp(
    metadata_engine: Engine,
) -> None:
    with metadata_engine.connect() as connection:
        result = load_fixture_refresh_metadata(
            connection,
            now=datetime(2100, 1, 1, tzinfo=UTC),
        )
    assert result.state is FreshnessState.STALE
    assert result.last_success_at is not None


def test_report_location_resolves_from_durable_event_metadata(metadata_engine: Engine) -> None:
    with metadata_engine.connect() as connection:
        run_id = connection.execute(
            text("SELECT run_id FROM engine_runs ORDER BY persisted_at LIMIT 1")
        ).scalar_one()
        durable = resolve_report_location(connection, str(run_id))
        fallback = resolve_report_location(
            connection,
            str(run_id),
            configured_root=Path("C:/safe/reports"),
        )
    assert durable.state in {ReportLocationState.DURABLE, ReportLocationState.UNAVAILABLE}
    if durable.state is ReportLocationState.UNAVAILABLE:
        assert fallback.state is ReportLocationState.DETERMINISTIC
        assert fallback.path is not None and str(run_id) in fallback.path
