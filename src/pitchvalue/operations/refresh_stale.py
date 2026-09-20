"""Explicit manual fixture refresh for stale SCHEDULED fixtures."""

from __future__ import annotations

import argparse
import os
import sys
from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine, text

from pitchvalue.config import load_settings
from pitchvalue.operations.current_season import persist_current_season_payloads
from pitchvalue.providers.five_dfa.adapter import FiveDfaFreeAdapter
from pitchvalue.providers.five_dfa.client import FiveDfaClient
from pitchvalue.providers.five_dfa.config import load_five_dfa_project_config


def run_refresh_stale(
    database_url: str,
    adapter: FiveDfaFreeAdapter,
    now: datetime | None = None,
) -> int:
    """Identify stale SCHEDULED fixtures, bounded to distinct days, and refresh."""
    check_time = now or datetime.now(UTC)
    threshold = check_time - timedelta(minutes=15)

    engine = create_engine(database_url)

    with engine.connect() as connection:
        rows = connection.execute(
            text(
                """SELECT DISTINCT (kickoff_at_utc::date) AS match_date
                   FROM matches
                   WHERE status = 'SCHEDULED' AND kickoff_at_utc < :threshold"""
            ),
            {"threshold": threshold},
        ).fetchall()

    dates = [row[0] for row in rows]
    if not dates:
        print("No stale SCHEDULED fixtures found.")
        return 0

    print(f"Found stale fixtures spanning {len(dates)} distinct calendar date(s): {dates}")

    refreshed_count = 0
    with engine.begin() as connection:
        for match_date in dates:
            start_time = datetime(match_date.year, match_date.month, match_date.day, tzinfo=UTC)
            end_time = start_time + timedelta(days=1)

            print(f"Fetching provider payloads for {start_time.date()}...")
            payloads, rate_states = adapter.fixture_payloads(
                start_time=start_time, end_time=end_time
            )

            if payloads:
                result = persist_current_season_payloads(
                    connection,
                    payloads,
                    logical_run_id=f"manual_refresh_stale_{int(check_time.timestamp())}",
                    window_start=start_time,
                    window_end=end_time,
                    prediction_as_of=check_time,
                )
                refreshed_count += len(result.match_ids)
                print(f"Persisted {len(result.match_ids)} fixtures for {start_time.date()}.")
            else:
                print(f"No fixtures found for {start_time.date()} from provider.")

    print(f"Refresh complete. Processed {refreshed_count} fixtures across {len(dates)} day(s).")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Refresh stale SCHEDULED fixtures")
    parser.parse_args()

    settings = load_settings()
    config = load_five_dfa_project_config(os.environ)
    client = FiveDfaClient(config)
    adapter = FiveDfaFreeAdapter(client)

    sys.exit(
        run_refresh_stale(
            database_url=settings.database_url,
            adapter=adapter,
        )
    )


if __name__ == "__main__":
    main()
