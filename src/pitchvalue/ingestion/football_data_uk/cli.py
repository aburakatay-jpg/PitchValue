"""Minimal Windows-compatible execution surface for source foundation operations."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from sqlalchemy import create_engine

from pitchvalue.config import get_database_url
from pitchvalue.ingestion.football_data_uk.batch import (
    BatchCounters,
    ensure_provider,
    finish_batch,
    start_batch,
)
from pitchvalue.ingestion.football_data_uk.comparison import compare_artifacts
from pitchvalue.ingestion.football_data_uk.downloader import FootballDataDownloader
from pitchvalue.ingestion.football_data_uk.mirrors import MIRRORS, FallbackDownloader
from pitchvalue.ingestion.football_data_uk.parser import parse_csv
from pitchvalue.ingestion.football_data_uk.pipeline import import_local_source, import_source
from pitchvalue.ingestion.football_data_uk.profile import profile_dataset
from pitchvalue.ingestion.football_data_uk.raw import RawArtifactStore, sha256_bytes
from pitchvalue.ingestion.football_data_uk.registry import SOURCES, get_source
from pitchvalue.ingestion.football_data_uk.staging import stage_dataset

logger = logging.getLogger(__name__)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pitchvalue-ingest")
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("sources", help="list enabled source definitions")

    profile = subcommands.add_parser("profile", help="profile a preserved CSV")
    profile.add_argument("path", type=Path)

    fetch = subcommands.add_parser("fetch", help="fetch and preserve one registered source")
    fetch.add_argument("source_key", choices=[source.key for source in SOURCES])
    fetch.add_argument("--raw-root", type=Path, default=Path("data/raw/football_data_uk"))

    stage = subcommands.add_parser("stage", help="parse and stage a preserved raw CSV")
    stage.add_argument("source_key", choices=[source.key for source in SOURCES])
    stage.add_argument("path", type=Path)
    import_all = subcommands.add_parser(
        "import-all", help="fetch, stage, and canonically import all enabled sources"
    )
    import_all.add_argument("--raw-root", type=Path, default=Path("data/raw/football_data_uk"))
    import_local = subcommands.add_parser(
        "import-local", help="import one manually supplied registered source CSV"
    )
    import_local.add_argument("source_key", choices=[source.key for source in SOURCES])
    import_local.add_argument("path", type=Path)
    import_local.add_argument("--raw-root", type=Path, default=Path("data/raw/football_data_uk"))
    subcommands.add_parser("mirrors", help="list reviewed fallback mirror candidates")
    fallback = subcommands.add_parser(
        "fetch-fallback", help="preserve one eligible allowlisted mirror artifact"
    )
    fallback.add_argument("source_key", choices=[source.key for source in SOURCES])
    fallback.add_argument("mirror_id", choices=[mirror.mirror_id for mirror in MIRRORS])
    fallback.add_argument("--raw-root", type=Path, default=Path("data/raw/football_data_uk"))
    compare = subcommands.add_parser(
        "compare-artifacts", help="compare two football-data-style CSV artifacts"
    )
    compare.add_argument("artifact_a", type=Path)
    compare.add_argument("artifact_b", type=Path)
    return parser


def _list_sources() -> int:
    records = [
        {
            "key": source.key,
            "competition": source.canonical_competition,
            "season": source.season_name,
            "source_code": source.source_code,
            "url": source.url,
        }
        for source in SOURCES
        if source.enabled
    ]
    print(json.dumps(records, ensure_ascii=False, indent=2))
    return 0


def _profile(path: Path) -> int:
    dataset = parse_csv(path.read_bytes())
    print(json.dumps(profile_dataset(dataset).as_dict(), ensure_ascii=False, indent=2))
    return 0


def _fetch(source_key: str, raw_root: Path) -> int:
    source = get_source(source_key)
    engine = create_engine(get_database_url())
    with engine.begin() as connection:
        provider_id = ensure_provider(connection)
        batch_id = start_batch(connection, provider_id, source.url)
    downloader = FootballDataDownloader()
    try:
        artifact = downloader.fetch(source, RawArtifactStore(raw_root))
    except Exception as error:
        with engine.begin() as connection:
            finish_batch(
                connection,
                batch_id,
                "failed",
                BatchCounters(),
                error_summary=str(error),
            )
        logger.exception("batch failed: %s", batch_id)
        engine.dispose()
        return 1
    finally:
        downloader.close()
    with engine.begin() as connection:
        finish_batch(
            connection,
            batch_id,
            "completed",
            BatchCounters(),
            source_hash=artifact.content_hash,
        )
    print(artifact.path)
    engine.dispose()
    return 0


def _fetch_fallback(source_key: str, mirror_id: str, raw_root: Path) -> int:
    source = get_source(source_key)
    engine = create_engine(get_database_url())
    with engine.begin() as connection:
        provider_id = ensure_provider(connection)
        batch_id = start_batch(connection, provider_id, source.url)
    downloader = FallbackDownloader()
    try:
        artifact = downloader.fetch(mirror_id, source, RawArtifactStore(raw_root))
    except Exception as error:
        with engine.begin() as connection:
            finish_batch(
                connection,
                batch_id,
                "failed",
                BatchCounters(),
                error_summary=str(error),
            )
        logger.exception("fallback fetch failed: %s", batch_id)
        engine.dispose()
        return 1
    finally:
        downloader.close()
    with engine.begin() as connection:
        finish_batch(
            connection,
            batch_id,
            "completed",
            BatchCounters(),
            source_hash=artifact.content_hash,
        )
    print(artifact.path)
    engine.dispose()
    return 0


def _stage(source_key: str, path: Path) -> int:
    source = get_source(source_key)
    content = path.read_bytes()
    source_hash = sha256_bytes(content)
    engine = create_engine(get_database_url())
    with engine.begin() as connection:
        provider_id = ensure_provider(connection)
        batch_id = start_batch(connection, provider_id, source.url)
    try:
        dataset = parse_csv(content)
        with engine.begin() as connection:
            result = stage_dataset(connection, batch_id, source, dataset)
            status = "completed_with_errors" if result.rows_rejected else "completed"
            finish_batch(
                connection,
                batch_id,
                status,
                BatchCounters(
                    rows_read=result.rows_read,
                    rows_inserted=result.rows_staged,
                    rows_rejected=result.rows_rejected,
                ),
                source_hash=source_hash,
                error_summary=(
                    f"{result.rows_rejected} row(s) rejected" if result.rows_rejected else None
                ),
            )
    except Exception as error:
        with engine.begin() as connection:
            finish_batch(
                connection,
                batch_id,
                "failed",
                BatchCounters(),
                source_hash=source_hash,
                error_summary=str(error),
            )
        logger.exception("batch failed: %s", batch_id)
        return 1
    finally:
        engine.dispose()
    print(json.dumps(result.__dict__, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    """Run one non-interactive ingestion foundation command."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    arguments = _parser().parse_args(argv)
    if arguments.command == "sources":
        return _list_sources()
    if arguments.command == "profile":
        return _profile(arguments.path)
    if arguments.command == "fetch":
        return _fetch(arguments.source_key, arguments.raw_root)
    if arguments.command == "stage":
        return _stage(arguments.source_key, arguments.path)
    if arguments.command == "import-all":
        engine = create_engine(get_database_url())
        downloader = FootballDataDownloader()
        try:
            reports = [
                import_source(engine, source, arguments.raw_root, downloader)
                for source in SOURCES
                if source.enabled
            ]
        finally:
            downloader.close()
            engine.dispose()
        print(json.dumps([report.as_dict() for report in reports], ensure_ascii=False, indent=2))
        return int(any(report.batch_status == "failed" for report in reports))
    if arguments.command == "import-local":
        engine = create_engine(get_database_url())
        try:
            report = import_local_source(
                engine,
                get_source(arguments.source_key),
                arguments.path,
                arguments.raw_root,
            )
        finally:
            engine.dispose()
        print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2))
        return int(report.batch_status == "failed")
    if arguments.command == "mirrors":
        print(
            json.dumps(
                [
                    {
                        "mirror_id": mirror.mirror_id,
                        "name": mirror.display_name,
                        "homepage": mirror.homepage,
                        "upstream_identity": mirror.upstream_identity,
                        "supported_source_codes": sorted(mirror.supported_source_codes),
                        "supported_seasons": sorted(mirror.supported_seasons),
                        "enabled": mirror.enabled,
                        "transformation_status": mirror.transformation_status,
                        "license_status": mirror.license_status,
                        "notes": mirror.notes,
                    }
                    for mirror in MIRRORS
                ],
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    if arguments.command == "fetch-fallback":
        return _fetch_fallback(arguments.source_key, arguments.mirror_id, arguments.raw_root)
    if arguments.command == "compare-artifacts":
        comparison = compare_artifacts(
            arguments.artifact_a.read_bytes(), arguments.artifact_b.read_bytes()
        )
        print(json.dumps(comparison.as_dict(), ensure_ascii=False, indent=2))
        return 0
    raise AssertionError("unreachable command")


if __name__ == "__main__":
    raise SystemExit(main())
