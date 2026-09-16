from pathlib import Path


def test_product_service_migration_is_provider_neutral_and_user_scoped() -> None:
    source = Path("migrations/versions/20260916_0012_product_services.py").read_text(
        encoding="utf-8"
    )
    assert 'revision: str = "20260916_0012"' in source
    assert 'down_revision: str | None = "20260913_0011"' in source
    for table in (
        "app_users",
        "auth_identities",
        "auth_sessions",
        "entitlement_evidence",
        "commerce_evidence",
        "saved_selections",
    ):
        assert f"CREATE TABLE {table}" in source
        assert f"DROP TABLE {table}" in source
    assert "user_id" in source
    assert "prediction_snapshot_id" in source
    assert "raw payment" not in source.casefold()


def test_canonical_prediction_schema_remains_user_independent() -> None:
    prediction_schema = Path("migrations/versions/20260911_0008_prediction_snapshots.py").read_text(
        encoding="utf-8"
    )
    assert "user_id" not in prediction_schema
    migration = Path("migrations/versions/20260916_0012_product_services.py").read_text(
        encoding="utf-8"
    )
    assert "ALTER TABLE prediction_snapshots" not in migration
