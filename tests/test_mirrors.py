from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import httpx
import pytest
from sqlalchemy import create_engine, text

from pitchvalue.config import load_settings
from pitchvalue.ingestion.football_data_uk.comparison import compare_artifacts
from pitchvalue.ingestion.football_data_uk.mirrors import (
    FallbackDownloader,
    MirrorDefinition,
    TransformationStatus,
    get_mirror,
    mirror_url,
)
from pitchvalue.ingestion.football_data_uk.pipeline import LocalSourceError
from pitchvalue.ingestion.football_data_uk.raw import RawArtifactStore
from pitchvalue.ingestion.football_data_uk.registry import get_source


def csv_bytes(*rows: str, line_ending: str = "\n", extra_column: bool = False) -> bytes:
    header = "Div,Date,HomeTeam,AwayTeam,FTHG,FTAG,FTR"
    if extra_column:
        header += ",Optional"
    return (header + line_ending + line_ending.join(rows) + line_ending).encode()


def synthetic_mirror(
    *,
    transformation_status: TransformationStatus = "raw_equivalent",
    enabled: bool = True,
) -> MirrorDefinition:
    return MirrorDefinition(
        mirror_id="synthetic_verified",
        display_name="Synthetic verified mirror",
        url_template="https://mirror.example/{season_code}/{source_code}.csv",
        homepage="https://mirror.example/project",
        upstream_identity="football-data.co.uk",
        supported_source_codes=frozenset({"E0"}),
        supported_seasons=frozenset({"2024/25"}),
        enabled=enabled,
        transformation_status=transformation_status,
        notes="test only",
        license_status="test only",
    )


def test_arbitrary_mirror_id_is_rejected_and_configured_candidate_resolves() -> None:
    with pytest.raises(KeyError, match="unknown mirror"):
        get_mirror("https://arbitrary.example/file.csv")
    assert get_mirror("morobang_warehouse").upstream_identity == "football-data.co.uk"


def test_transformed_or_disabled_mirror_is_ineligible() -> None:
    source = get_source("E0:2024/25")
    with pytest.raises(ValueError, match="raw-equivalent"):
        mirror_url(synthetic_mirror(transformation_status="transformed"), source)
    with pytest.raises(ValueError, match="disabled"):
        mirror_url(synthetic_mirror(enabled=False), source)


def test_verified_mirror_preserves_bytes_and_provenance(tmp_path: Path) -> None:
    source = get_source("E0:2024/25")
    content = csv_bytes("E0,16/08/2024,Alpha,Beta,1,0,H")
    mirror = synthetic_mirror()
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, content=content, request=request)
    )
    with httpx.Client(transport=transport) as client:
        artifact = FallbackDownloader(client, (mirror,)).fetch(
            mirror.mirror_id, source, RawArtifactStore(tmp_path)
        )
    metadata = json.loads(artifact.metadata_path.read_text(encoding="utf-8"))
    assert artifact.path.read_bytes() == content
    assert artifact.content_hash == hashlib.sha256(content).hexdigest()
    assert metadata["source_url"] == source.url
    assert metadata["source_key"] == source.key
    assert metadata["mirror_url"] == "https://mirror.example/2425/E0.csv"
    assert metadata["mirror_id"] == mirror.mirror_id
    assert metadata["mirror_name"] == mirror.display_name
    assert metadata["acquisition_mode"] == "verified_mirror"


@pytest.mark.parametrize(
    ("content", "message"),
    [
        (b"<html>upstream error</html>", "HTML"),
        (csv_bytes("F1,16/08/2024,Alpha,Beta,1,0,H"), "do not match E0"),
        (b"Div,Date\nE0,16/08/2024\n", "required CSV columns"),
    ],
)
def test_fallback_rejects_invalid_response(tmp_path: Path, content: bytes, message: str) -> None:
    source = get_source("E0:2024/25")
    mirror = synthetic_mirror()
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, content=content, request=request)
    )
    with (
        httpx.Client(transport=transport) as client,
        pytest.raises(LocalSourceError, match=message),
    ):
        FallbackDownloader(client, (mirror,)).fetch(
            mirror.mirror_id, source, RawArtifactStore(tmp_path)
        )
    assert not list(tmp_path.rglob("*.csv"))


def test_optional_columns_may_differ() -> None:
    basic = csv_bytes("E0,16/08/2024,Alpha,Beta,1,0,H")
    extended = csv_bytes("E0,16/08/2024,Alpha,Beta,1,0,H,kept", extra_column=True)
    report = compare_artifacts(basic, extended)
    assert report.columns_only_b == ("Optional",)
    assert report.rows_only_a == report.rows_only_b == 0


def test_comparison_detects_exact_and_semantic_matches() -> None:
    unix = csv_bytes("E0,16/08/2024,Alpha,Beta,1,0,H")
    windows = csv_bytes("E0,16/08/2024,Alpha,Beta,1,0,H", line_ending="\r\n")
    exact = compare_artifacts(unix, unix)
    semantic = compare_artifacts(unix, windows)
    assert exact.status == "EXACT_MATCH"
    assert exact.sha256_a == exact.sha256_b
    assert semantic.status == "SEMANTIC_MATCH_BYTE_DIFFERENCE"
    assert semantic.sha256_a != semantic.sha256_b
    assert semantic.differing_matching_rows == 0


def test_comparison_detects_data_difference_and_ambiguous_keys() -> None:
    first = csv_bytes("E0,16/08/2024,Alpha,Beta,1,0,H")
    changed = csv_bytes("E0,16/08/2024,Alpha,Beta,2,0,H")
    duplicate = csv_bytes(
        "E0,16/08/2024,Alpha,Beta,1,0,H",
        "E0,16/08/2024,Alpha,Beta,1,0,H",
    )
    difference = compare_artifacts(first, changed)
    ambiguous = compare_artifacts(first, duplicate)
    assert difference.status == "DATA_DIFFERENCE"
    assert difference.differing_matching_rows == 1
    assert ambiguous.status == "AMBIGUOUS"
    assert ambiguous.ambiguous_keys_b == 1


@pytest.mark.integration
def test_fallback_acquisition_does_not_touch_historical_or_odds_tables(
    tmp_path: Path,
) -> None:
    engine = create_engine(load_settings(os.environ).database_url)
    tables = ("seasons", "teams", "matches", "match_statistics", "odds_snapshots")
    with engine.connect() as connection:
        before = {
            table: connection.execute(text(f"SELECT count(*) FROM {table}")).scalar_one()
            for table in tables
        }
    source = get_source("E0:2024/25")
    mirror = synthetic_mirror()
    content = csv_bytes("E0,16/08/2024,Alpha,Beta,1,0,H")
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, content=content, request=request)
    )
    with httpx.Client(transport=transport) as client:
        FallbackDownloader(client, (mirror,)).fetch(
            mirror.mirror_id, source, RawArtifactStore(tmp_path)
        )
    with engine.connect() as connection:
        after = {
            table: connection.execute(text(f"SELECT count(*) FROM {table}")).scalar_one()
            for table in tables
        }
    engine.dispose()
    assert after == before
