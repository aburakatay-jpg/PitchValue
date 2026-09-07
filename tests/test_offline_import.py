from __future__ import annotations

import hashlib
import json
import os
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import Engine, create_engine, text

from pitchvalue.config import load_settings
from pitchvalue.ingestion.football_data_uk.pipeline import (
    LocalSourceError,
    import_local_source,
    validate_local_source,
)
from pitchvalue.ingestion.football_data_uk.registry import get_source

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def valid_csv(division: str = "E0") -> bytes:
    return (
        "Div,Date,Time,HomeTeam,AwayTeam,FTHG,FTAG,FTR,HS\n"
        f"{division},16/08/2024,20:00,Offline Alpha,Offline Beta,1,0,H,0\n"
    ).encode()


@pytest.fixture(scope="module")
def engine() -> Iterator[Engine]:
    value = create_engine(load_settings(os.environ).database_url)
    yield value
    value.dispose()


@pytest.mark.parametrize(
    ("kind", "content", "message"),
    [
        ("missing", None, "does not exist"),
        ("empty", b"", "empty"),
        ("html", b"<!doctype html><html>503 unavailable</html>", "HTML"),
        ("wrong_division", valid_csv("F1"), "do not match E0"),
    ],
)
def test_invalid_local_sources_are_rejected(
    tmp_path: Path, kind: str, content: bytes | None, message: str
) -> None:
    path = tmp_path / f"{kind}.csv"
    if content is not None:
        path.write_bytes(content)
    with pytest.raises(LocalSourceError, match=message):
        validate_local_source(path, get_source("E0:2024/25"))


def test_missing_required_columns_are_rejected(tmp_path: Path) -> None:
    path = tmp_path / "not-football-data.csv"
    path.write_bytes(b"Div,Date\nE0,16/08/2024\n")
    with pytest.raises(LocalSourceError, match="required CSV columns"):
        validate_local_source(path, get_source("E0:2024/25"))


@pytest.mark.integration
def test_local_import_preserves_stages_and_replays_idempotently(
    engine: Engine, tmp_path: Path
) -> None:
    source = get_source("E0:2024/25")
    manual_path = tmp_path / "E0_2425.csv"
    content = valid_csv()
    manual_path.write_bytes(content)
    raw_root = tmp_path / "raw"
    reports = []
    try:
        reports.append(import_local_source(engine, source, manual_path, raw_root))
        reports.append(import_local_source(engine, source, manual_path, raw_root))
        first, second = reports
        assert first.batch_status == second.batch_status == "completed"
        assert first.fetch_status == "local_preserved"
        assert second.fetch_status == "already_preserved"
        assert first.content_hash == hashlib.sha256(content).hexdigest()
        assert first.canonical.matches_created == 1
        assert second.canonical.matches_created == 0
        assert second.canonical.matches_reused == 1
        assert second.canonical.provider_refs_created == 0
        assert second.canonical.statistics_reused == 1

        metadata_path = Path(first.raw_path or "").with_name("metadata.json")
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        assert metadata["acquisition_mode"] == "local_manual"
        assert metadata["original_filename"] == manual_path.name
        assert metadata["source_url"] == source.url

        batch_ids = [report.batch_id for report in reports]
        with engine.connect() as connection:
            batches = connection.execute(
                text(
                    "SELECT source_identifier, source_hash FROM import_batches "
                    "WHERE import_batch_id = ANY(:batch_ids) ORDER BY import_batch_id"
                ),
                {"batch_ids": batch_ids},
            ).all()
            assert [row.source_identifier for row in batches] == [source.url, source.url]
            assert {row.source_hash for row in batches} == {hashlib.sha256(content).hexdigest()}
            assert (
                connection.execute(
                    text(
                        "SELECT count(*) FROM football_data_canonical_lineage AS l "
                        "JOIN football_data_staging_rows AS s USING (staging_row_id) "
                        "WHERE s.import_batch_id = ANY(:batch_ids)"
                    ),
                    {"batch_ids": batch_ids},
                ).scalar_one()
                == 2
            )
            assert (
                connection.execute(
                    text("SELECT count(*) FROM matches WHERE referee IS NULL")
                ).scalar_one()
                >= 1
            )
    finally:
        if reports:
            _cleanup(engine, [report.batch_id for report in reports])


def _cleanup(engine: Engine, batch_ids: list[int]) -> None:
    with engine.begin() as connection:
        match_ids = (
            connection.execute(
                text(
                    "SELECT DISTINCT l.match_id FROM football_data_canonical_lineage AS l "
                    "JOIN football_data_staging_rows AS s USING (staging_row_id) "
                    "WHERE s.import_batch_id = ANY(:batch_ids)"
                ),
                {"batch_ids": batch_ids},
            )
            .scalars()
            .all()
        )
        if match_ids:
            for table in (
                "football_data_canonical_lineage",
                "data_quality",
                "match_statistics",
                "match_provider_refs",
            ):
                connection.execute(
                    text(f"DELETE FROM {table} WHERE match_id = ANY(:match_ids)"),
                    {"match_ids": match_ids},
                )
            connection.execute(
                text("DELETE FROM matches WHERE match_id = ANY(:match_ids)"),
                {"match_ids": match_ids},
            )
        connection.execute(
            text("DELETE FROM football_data_staging_rows WHERE import_batch_id = ANY(:ids)"),
            {"ids": batch_ids},
        )
        connection.execute(
            text("DELETE FROM import_batches WHERE import_batch_id = ANY(:ids)"),
            {"ids": batch_ids},
        )
        team_ids = (
            connection.execute(
                text("SELECT team_id FROM teams WHERE canonical_name LIKE 'Offline %'")
            )
            .scalars()
            .all()
        )
        if team_ids:
            connection.execute(
                text("DELETE FROM team_aliases WHERE team_id = ANY(:ids)"), {"ids": team_ids}
            )
            connection.execute(
                text("DELETE FROM teams WHERE team_id = ANY(:ids)"), {"ids": team_ids}
            )
        connection.execute(
            text(
                "DELETE FROM seasons WHERE competition_id = "
                "(SELECT competition_id FROM competitions WHERE canonical_name='Premier League') "
                "AND season_name='2024/25'"
            )
        )


def test_manual_drop_directory_is_ignored_but_placeholder_is_trackable() -> None:
    ignored = subprocess.run(
        ["git", "check-ignore", "data/manual/football_data_uk/E0_2425.csv"],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    placeholder = subprocess.run(
        ["git", "check-ignore", "data/manual/football_data_uk/.gitkeep"],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert ignored.returncode == 0
    assert placeholder.returncode == 1


def test_downloader_contains_no_tls_verification_bypass() -> None:
    python_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (PROJECT_ROOT / "src" / "pitchvalue" / "ingestion").rglob("*.py")
    )
    assert "verify" + "=False" not in python_text
    assert "verify" + " = False" not in python_text
    assert "CERT_NONE" not in python_text
