"""Immutable local raw-artifact preservation."""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from pitchvalue.ingestion.football_data_uk.registry import SourceDefinition

logger = logging.getLogger(__name__)


def sha256_bytes(content: bytes) -> str:
    """Hash original source bytes without transforming them."""
    return hashlib.sha256(content).hexdigest()


@dataclass(frozen=True)
class RawArtifact:
    """Result of preserving or recognizing one immutable artifact."""

    path: Path
    metadata_path: Path
    content_hash: str
    already_known: bool


class RawArtifactStore:
    """Content-addressed raw storage that never overwrites known evidence."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def preserve(
        self,
        content: bytes,
        source: SourceDefinition,
        fetched_at: datetime,
        original_filename: str,
        *,
        acquisition_mode: str = "network",
        mirror_url: str | None = None,
        mirror_id: str | None = None,
        mirror_name: str | None = None,
    ) -> RawArtifact:
        """Store original bytes and first-seen metadata under their content hash."""
        content_hash = sha256_bytes(content)
        safe_filename = Path(original_filename).name
        if not safe_filename:
            raise ValueError("original_filename must not be blank")
        artifact_dir = (
            self.root
            / source.provider.replace(".", "_")
            / source.season_name.replace("/", "-")
            / source.source_code
            / content_hash
        )
        artifact_dir.mkdir(parents=True, exist_ok=True)
        path = artifact_dir / safe_filename
        if acquisition_mode == "verified_mirror":
            if not mirror_id or not mirror_url or not mirror_name:
                raise ValueError("verified mirror provenance is incomplete")
            provenance_key = sha256_bytes(f"{mirror_id}|{mirror_url}".encode())[:16]
            metadata_path = artifact_dir / f"metadata.verified_mirror.{provenance_key}.json"
        else:
            metadata_path = artifact_dir / "metadata.json"
        already_known = path.exists()

        if already_known:
            if path.read_bytes() != content:
                raise RuntimeError("content-addressed raw artifact collision")
            logger.info("raw artifact already known: %s", content_hash)
        else:
            with path.open("xb") as raw_file:
                raw_file.write(content)
            logger.info("raw artifact stored: %s", path)

        if not metadata_path.exists():
            metadata = {
                "provider": source.provider,
                "source_url": source.url,
                "competition_source_code": source.source_code,
                "canonical_competition": source.canonical_competition,
                "season_name": source.season_name,
                "fetched_at": fetched_at.isoformat(),
                "content_hash": content_hash,
                "original_filename": safe_filename,
                "acquisition_mode": acquisition_mode,
                "source_key": source.key,
                "mirror_url": mirror_url,
                "mirror_id": mirror_id,
                "mirror_name": mirror_name,
            }
            with metadata_path.open("x", encoding="utf-8", newline="\n") as metadata_file:
                json.dump(metadata, metadata_file, ensure_ascii=False, indent=2, sort_keys=True)
                metadata_file.write("\n")
            logger.info("raw acquisition metadata stored: %s", metadata_path)

        return RawArtifact(path, metadata_path, content_hash, already_known)
