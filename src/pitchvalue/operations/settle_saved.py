"""Manual saved-selection settlement command; never scheduled implicitly."""

from __future__ import annotations

import argparse
import json

from pitchvalue.api.database import DatabaseResource
from pitchvalue.config import load_settings
from pitchvalue.product_services.settlement_operator import run_settlement


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Settle eligible saved selections from canonical final results"
    )
    parser.add_argument("--limit", type=int, default=500)
    arguments = parser.parse_args()
    settings = load_settings()
    database = DatabaseResource(settings.database_url)
    database.start()
    try:
        database.check()
        with database.transaction() as connection:
            result = run_settlement(connection, limit=arguments.limit)
        print(json.dumps(result.to_dict(), sort_keys=True, default=str))
    finally:
        database.dispose()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
