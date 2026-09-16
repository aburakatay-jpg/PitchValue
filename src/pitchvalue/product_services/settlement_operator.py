"""Explicit replay-safe operator path for saved-selection settlement."""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime

from sqlalchemy import Connection, text

from pitchvalue.product_services.settlement import SettlementError
from pitchvalue.product_services.tracking import settle_saved_selection


@dataclass(frozen=True)
class SettlementRunResult:
    run_id: str
    generated_at: datetime
    scanned: int
    settled: int
    unchanged: int
    review_required: tuple[str, ...]
    outcomes: tuple[tuple[str, str], ...]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def run_settlement(
    connection: Connection,
    *,
    limit: int = 500,
    now: datetime | None = None,
    run_id: str | None = None,
) -> SettlementRunResult:
    """Settle only canonical terminal fixtures under an explicit DB transaction."""
    if not 1 <= limit <= 5000:
        raise ValueError("settlement limit must be between one and 5000")
    generated_at = now or datetime.now(UTC)
    if generated_at.tzinfo is None or generated_at.utcoffset() is None:
        raise ValueError("settlement time must be timezone-aware")
    identifiers = tuple(
        str(value)
        for value in connection.execute(
            text(
                "SELECT s.saved_selection_id FROM saved_selections s "
                "JOIN matches m ON m.match_id=s.match_id "
                "WHERE s.tracking_status IN ('ACTIVE','SETTLED') "
                "AND m.status IN ('FINISHED','AWARDED','CANCELLED','ABANDONED') "
                "ORDER BY s.created_at,s.saved_selection_id "
                "FOR UPDATE OF s SKIP LOCKED LIMIT :limit"
            ),
            {"limit": limit},
        ).scalars()
    )
    outcomes: list[tuple[str, str]] = []
    review: list[str] = []
    unchanged = 0
    for saved_id in identifiers:
        try:
            outcome = settle_saved_selection(connection, saved_id, now=generated_at)
        except SettlementError:
            review.append(saved_id)
            continue
        if outcome is None:
            unchanged += 1
        else:
            outcomes.append((saved_id, outcome.value))
    return SettlementRunResult(
        run_id or str(uuid.uuid4()),
        generated_at,
        len(identifiers),
        len(outcomes),
        unchanged,
        tuple(review),
        tuple(outcomes),
    )
