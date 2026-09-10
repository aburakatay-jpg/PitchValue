"""Run deterministic historical odds normalization for the configured database."""

import json
import os

from sqlalchemy import create_engine

from pitchvalue.config import load_settings
from pitchvalue.markets.history.normalization import normalize_historical_odds


def main() -> int:
    engine = create_engine(load_settings(os.environ).database_url)
    try:
        summary = normalize_historical_odds(engine)
    finally:
        engine.dispose()
    print(json.dumps(summary.to_dict(), sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
