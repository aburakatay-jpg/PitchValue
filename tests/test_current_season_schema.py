from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import Connection, Engine, create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from pitchvalue.config import load_settings


@pytest.fixture(scope="session")
def schema_engine() -> Iterator[Engine]:
    engine = create_engine(load_settings(os.environ).database_url)
    yield engine
    engine.dispose()


@pytest.fixture
def schema_db(schema_engine: Engine) -> Iterator[Connection]:
    with schema_engine.connect() as connection:
        transaction = connection.begin()
        yield connection
        transaction.rollback()


@pytest.mark.integration
def test_provider_neutral_tables_and_references_exist(schema_engine: Engine) -> None:
    inspector = inspect(schema_engine)
    tables = set(inspector.get_table_names())
    assert {"source_entity_references", "shadow_analysis_snapshots"} <= tables
    assert not any(name.startswith("five_dfa_") for name in tables)
    quarantine = {item["name"] for item in inspector.get_columns("run_quarantines")}
    assert "source_entity_ref_id" in quarantine


@pytest.mark.integration
def test_source_identity_is_database_unique(schema_db: Connection) -> None:
    provider = int(
        schema_db.execute(
            text(
                """INSERT INTO providers (name,provider_type,priority)
                VALUES ('Schema Source','test',1) RETURNING provider_id"""
            )
        ).scalar_one()
    )
    statement = text(
        """INSERT INTO source_entity_references (
        provider_id,entity_type,provider_entity_id,provider_display_name,mapping_status,
        mapping_version,provenance,first_seen_at,last_seen_at)
        VALUES (:provider,'TEAM','one','One','UNRESOLVED','v1','test',now(),now())"""
    )
    schema_db.execute(statement, {"provider": provider})
    with pytest.raises(IntegrityError), schema_db.begin_nested():
        schema_db.execute(statement, {"provider": provider})


@pytest.mark.integration
def test_quarantine_requires_exactly_one_identity(schema_db: Connection) -> None:
    with pytest.raises(IntegrityError), schema_db.begin_nested():
        schema_db.execute(
            text(
                """INSERT INTO run_quarantines (
                quarantine_id,run_id,match_id,source_entity_ref_id,scope,reason_code,
                occurred_at,evidence,status)
                VALUES (repeat('a',64),'missing',NULL,NULL,'MATCH','X',now(),'{}','ACTIVE')"""
            )
        )


def test_migration_is_single_provider_neutral_revision() -> None:
    source = Path(
        "migrations/versions/20260913_0011_current_season_shadow_persistence.py"
    ).read_text(encoding="utf-8")
    assert 'revision: str = "20260913_0011"' in source
    assert 'down_revision: str | None = "20260912_0010"' in source
    assert "CREATE TABLE source_entity_references" in source
    assert "CREATE TABLE shadow_analysis_snapshots" in source
    assert "five_dfa_matches" not in source
