"""Secret-safe local operator diagnostics and explicit stale-run recovery."""

from __future__ import annotations

import argparse
import os
from dataclasses import asdict
from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine, text

from pitchvalue.config import load_settings
from pitchvalue.operations.hardening import (
    StaleRun,
    canonical_json,
    evaluate_health,
    evaluate_readiness,
    load_activation_gates,
    recover_stale_run,
    stale_runs,
)
from pitchvalue.providers.five_dfa.config import load_five_dfa_project_config


def system_status(*, stale_after: timedelta = timedelta(hours=2)) -> dict[str, object]:
    settings = load_settings()
    provider_configured = False
    readiness_values = dict(os.environ)
    try:
        provider_config = load_five_dfa_project_config(os.environ)
        provider_configured = True
        readiness_values["FIVEDFA_API_KEY"] = provider_config.api_key
    except Exception:
        pass
    readiness = evaluate_readiness(settings, readiness_values, provider_required=False)
    health = evaluate_health(settings)
    gates = load_activation_gates(os.environ)
    stuck: tuple[StaleRun, ...] = ()
    runs: list[dict[str, object]] = []
    critical: list[dict[str, object]] = []
    public_count: int | None = None
    last_provider_success: object = None
    if health.database_reachable and health.migration_current:
        engine = create_engine(settings.database_url, pool_pre_ping=True)
        try:
            with engine.connect() as connection:
                stuck = stale_runs(
                    connection,
                    now=datetime.now(UTC),
                    older_than=stale_after,
                )
                runs = [
                    dict(row)
                    for row in connection.execute(
                        text(
                            """SELECT run_id,status,scheduled_for,started_at,finished_at
                            FROM engine_runs ORDER BY persisted_at DESC LIMIT 10"""
                        )
                    ).mappings()
                ]
                critical = [
                    dict(row)
                    for row in connection.execute(
                        text(
                            """SELECT event_id,event_type,severity,occurred_at,run_id,reason_code
                            FROM operational_events WHERE severity IN ('ERROR','CRITICAL')
                            ORDER BY occurred_at DESC,event_id LIMIT 10"""
                        )
                    ).mappings()
                ]
                public_count = int(
                    connection.execute(
                        text(
                            "SELECT count(*) FROM prediction_snapshots "
                            "WHERE publication_eligible=true AND record_status='active'"
                        )
                    ).scalar_one()
                )
                last_provider_success = connection.execute(
                    text(
                        """SELECT finished_at FROM engine_runs
                        WHERE provider_id IS NOT NULL
                          AND status IN ('SUCCEEDED','PARTIAL_WITH_QUARANTINES')
                        ORDER BY finished_at DESC NULLS LAST LIMIT 1"""
                    )
                ).scalar_one_or_none()
        finally:
            engine.dispose()
    return {
        "health": health.to_dict(),
        "readiness": readiness.to_dict(),
        "provider": {
            "configured": provider_configured,
            "authenticated": "NOT_PROBED",
            "plan": "FREE" if provider_configured else None,
            "quota": "UNKNOWN_NOT_PROBED",
            "supported_capabilities": ["fixtures", "results", "match_statistics", "odds"],
            "last_successful_interaction": last_provider_success,
        },
        "activation": {
            "scheduler": gates.scheduler_enabled,
            "publication": gates.publication_enabled,
            "external_alerts": gates.external_alerts_enabled,
        },
        "stuck_runs": [asdict(item) for item in stuck],
        "recent_runs": runs,
        "recent_critical_events": critical,
        "public_eligible_predictions": public_count,
    }


def inspect_run(run_id: str) -> dict[str, object]:
    if not run_id.strip():
        raise ValueError("run_id must be nonblank")
    settings = load_settings()
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            run = (
                connection.execute(
                    text(
                        """SELECT run_id,run_type,status,scheduled_for,started_at,finished_at,
                    fixture_horizon,model_version,feature_profile,orchestrator_version,
                    policy_version,provider_contract_version,provider_id
                    FROM engine_runs WHERE run_id=:run_id"""
                    ),
                    {"run_id": run_id},
                )
                .mappings()
                .one_or_none()
            )
            if run is None:
                return {"status": "NOT_FOUND", "run_id": run_id}
            quarantines = connection.execute(
                text(
                    """SELECT reason_code,count(*) AS count FROM run_quarantines
                    WHERE run_id=:run_id GROUP BY reason_code ORDER BY reason_code"""
                ),
                {"run_id": run_id},
            ).mappings()
            events = connection.execute(
                text(
                    """SELECT event_type,severity,occurred_at,reason_code FROM operational_events
                    WHERE run_id=:run_id ORDER BY occurred_at,event_id"""
                ),
                {"run_id": run_id},
            ).mappings()
            shadow_count = int(
                connection.execute(
                    text("SELECT count(*) FROM shadow_analysis_snapshots WHERE run_id=:run_id"),
                    {"run_id": run_id},
                ).scalar_one()
            )
        return {
            "status": "FOUND",
            "run": dict(run),
            "quarantines": [dict(item) for item in quarantines],
            "shadow_analyses": shadow_count,
            "events": [dict(item) for item in events],
            "report_location": "NOT_PERSISTED_IN_DATABASE",
        }
    finally:
        engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description="PitchValue local operator diagnostics")
    subparsers = parser.add_subparsers(dest="command", required=True)
    status_parser = subparsers.add_parser("status")
    status_parser.add_argument("--stale-after-minutes", type=int, default=120)
    inspect_parser = subparsers.add_parser("inspect")
    inspect_parser.add_argument("run_id")
    recover_parser = subparsers.add_parser("recover-stale")
    recover_parser.add_argument("run_id")
    recover_parser.add_argument("--older-than-minutes", type=int, default=120)
    args = parser.parse_args()
    if args.command == "status":
        if args.stale_after_minutes <= 0:
            parser.error("stale boundary must be positive")
        output = system_status(stale_after=timedelta(minutes=args.stale_after_minutes))
    elif args.command == "inspect":
        output = inspect_run(args.run_id)
    else:
        if args.older_than_minutes <= 0:
            parser.error("stale boundary must be positive")
        settings = load_settings()
        engine = create_engine(settings.database_url, pool_pre_ping=True)
        try:
            with engine.begin() as connection:
                output = asdict(
                    recover_stale_run(
                        connection,
                        args.run_id,
                        now=datetime.now(UTC),
                        older_than=timedelta(minutes=args.older_than_minutes),
                    )
                )
        finally:
            engine.dispose()
    print(canonical_json(output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
