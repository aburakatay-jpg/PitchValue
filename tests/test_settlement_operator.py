from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from sqlalchemy import Connection

from pitchvalue.product_services import settlement_operator
from pitchvalue.product_services.settlement import SettlementError, SettlementOutcome


def test_operator_settles_reports_review_and_is_bounded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = MagicMock(spec=Connection)
    connection.execute.return_value.scalars.return_value = ("won", "same", "review")

    def fake_settle(
        ignored_connection: Connection, saved_id: str, *, now: datetime
    ) -> SettlementOutcome | None:
        assert ignored_connection is connection
        assert now == datetime(2026, 9, 16, 12, tzinfo=UTC)
        if saved_id == "won":
            return SettlementOutcome.WON
        if saved_id == "review":
            raise SettlementError("review")
        return None

    monkeypatch.setattr(settlement_operator, "settle_saved_selection", fake_settle)
    result = settlement_operator.run_settlement(
        connection,
        limit=20,
        now=datetime(2026, 9, 16, 12, tzinfo=UTC),
        run_id="operator-run",
    )
    assert result.run_id == "operator-run"
    assert result.scanned == 3
    assert result.settled == 1
    assert result.unchanged == 1
    assert result.review_required == ("review",)
    assert result.outcomes == (("won", "WON"),)
    statement = str(connection.execute.call_args.args[0])
    assert "FOR UPDATE OF s SKIP LOCKED" in statement
    assert "FINISHED" in statement
    assert connection.execute.call_args.args[1] == {"limit": 20}


def test_operator_rejects_unbounded_or_naive_runs() -> None:
    connection = MagicMock(spec=Connection)
    for limit in (0, 5001):
        with pytest.raises(ValueError, match="between one and 5000"):
            settlement_operator.run_settlement(connection, limit=limit)
    with pytest.raises(ValueError, match="timezone-aware"):
        settlement_operator.run_settlement(connection, now=datetime(2026, 9, 16, 12))
