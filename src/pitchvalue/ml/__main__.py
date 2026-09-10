"""Read-only real historical TASK 16 evaluation command."""

from __future__ import annotations

import json
import os

from sqlalchemy import create_engine

from pitchvalue.config import load_settings
from pitchvalue.ml.evaluation import evaluate_walk_forward_ml
from pitchvalue.ml.real_data import load_real_match_result_dataset


def main() -> int:
    engine = create_engine(load_settings(os.environ).database_url)
    try:
        with engine.connect() as connection:
            build = load_real_match_result_dataset(connection)
            result = evaluate_walk_forward_ml(
                build.dataset,
                complete_rows=build.complete_count,
                partial_rows=build.partial_count,
                unavailable_rows=build.unavailable_count,
                competition_labels=build.competition_labels,
                season_labels=build.season_labels,
            )
        print(json.dumps(result.to_dict(), sort_keys=True, separators=(",", ":")))
        return 0
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
