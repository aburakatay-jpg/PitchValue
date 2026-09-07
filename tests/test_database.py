import os

import pytest
from sqlalchemy import create_engine, text

from pitchvalue.config import load_settings


@pytest.mark.integration
def test_database_connection() -> None:
    settings = load_settings(os.environ)

    engine = create_engine(settings.database_url)
    with engine.connect() as connection:
        assert connection.execute(text("SELECT 1")).scalar_one() == 1
    engine.dispose()
