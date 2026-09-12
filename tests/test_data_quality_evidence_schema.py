from __future__ import annotations

from pathlib import Path


def test_dq_migration_preserves_legacy_table_and_adds_versioned_evidence() -> None:
    root = Path(__file__).resolve().parents[1]
    migration = (root / "migrations/versions/20260912_0010_data_quality_evidence.py").read_text()
    assert "CREATE TABLE data_quality_evaluations" in migration
    assert "CREATE TABLE data_quality_evidence" in migration
    assert "DROP TABLE data_quality;" not in migration
    assert "HISTORICAL_RECONSTRUCTED" in migration
    assert "LIVE_OPERATIONAL" in migration
