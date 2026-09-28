import os
from collections.abc import Iterator
from unittest.mock import patch

import pytest
from sqlalchemy import Connection, Engine, create_engine, text

from pitchvalue.config import load_settings
from pitchvalue.product_services.account_deletion import initiate_account_deletion
from pitchvalue.product_services.auth import (
    ProductUser,
    VerifiedExternalIdentity,
    _issue_session,
    _now,
    logout,
)
from pitchvalue.product_services.followed_matches import (
    follow_match,
    get_followed_match_ids,
    unfollow_match,
)
from pitchvalue.product_services.push_tokens import (
    PushTokenError,
    register_push_token,
    remove_invalid_push_token,
)


def seed_canonical_match(db):
    db.execute(
        text(
            "INSERT INTO competitions (competition_id, canonical_name, country_code, "
            "competition_type, gender) VALUES (99991, 'Test', 'GBR', 'domestic_league', 'men') "
            "ON CONFLICT DO NOTHING"
        )
    )
    db.execute(
        text(
            "INSERT INTO seasons (season_id, competition_id, season_name, start_year, end_year, "
            "status) VALUES (99991, 99991, '2020', 2020, 2021, 'active') ON CONFLICT DO NOTHING"
        )
    )
    db.execute(
        text(
            "INSERT INTO teams (team_id, canonical_name, normalized_name) VALUES "
            "(99991, 'T1', 't1'), (99992, 'T2', 't2') ON CONFLICT DO NOTHING"
        )
    )
    db.execute(
        text(
            "INSERT INTO matches (match_id, competition_id, season_id, home_team_id, away_team_id, "
            "kickoff_at_utc, status) VALUES (99991, 99991, 99991, 99991, 99992, "
            "'2026-09-13 12:00:00', 'SCHEDULED') ON CONFLICT DO NOTHING"
        )
    )
    db.execute(
        text(
            "INSERT INTO matches (match_id, competition_id, season_id, home_team_id, away_team_id, "
            "kickoff_at_utc, status) VALUES (99992, 99991, 99991, 99991, 99992, "
            "'2026-09-13 12:00:00', 'SCHEDULED') ON CONFLICT DO NOTHING"
        )
    )


@pytest.fixture(scope="session")
def database_engine() -> Iterator[Engine]:
    settings = load_settings(os.environ)
    engine = create_engine(settings.database_url)
    yield engine
    engine.dispose()


@pytest.fixture
def db(database_engine: Engine) -> Iterator[Connection]:
    with database_engine.connect() as connection:
        transaction = connection.begin()
        yield connection
        transaction.rollback()


def test_followed_matches_lifecycle(db):
    seed_canonical_match(db)
    user_id_1 = "test_user_fm_1"
    user_id_2 = "test_user_fm_2"
    db.execute(
        text(
            "INSERT INTO app_users (user_id, account_kind, created_at, updated_at) "
            "VALUES (:u, 'AUTHENTICATED', now(), now()) ON CONFLICT DO NOTHING"
        ),
        {"u": user_id_1},
    )
    db.execute(
        text(
            "INSERT INTO app_users (user_id, account_kind, created_at, updated_at) "
            "VALUES (:u, 'AUTHENTICATED', now(), now()) ON CONFLICT DO NOTHING"
        ),
        {"u": user_id_2},
    )

    match_id_1 = 99991
    match_id_2 = 99992

    follow_match(db, user_id_1, match_id_1)
    assert get_followed_match_ids(db, user_id_1) == [match_id_1]

    follow_match(db, user_id_1, match_id_1)
    assert get_followed_match_ids(db, user_id_1) == [match_id_1]

    follow_match(db, user_id_2, match_id_1)
    assert get_followed_match_ids(db, user_id_2) == [match_id_1]

    follow_match(db, user_id_1, match_id_2)
    follows = get_followed_match_ids(db, user_id_1)
    assert match_id_1 in follows
    assert match_id_2 in follows

    unfollow_match(db, user_id_1, match_id_1)
    follows = get_followed_match_ids(db, user_id_1)
    assert follows == [match_id_2]

    follow_match(db, user_id_1, match_id_1)
    assert match_id_1 in get_followed_match_ids(db, user_id_1)


def test_push_tokens_lifecycle(db):
    seed_canonical_match(db)
    user_id_1 = "test_user_pt_1"
    user_id_2 = "test_user_pt_2"
    db.execute(
        text(
            "INSERT INTO app_users (user_id, account_kind, created_at, updated_at) "
            "VALUES (:u, 'AUTHENTICATED', now(), now()) ON CONFLICT DO NOTHING"
        ),
        {"u": user_id_1},
    )
    db.execute(
        text(
            "INSERT INTO app_users (user_id, account_kind, created_at, updated_at) "
            "VALUES (:u, 'AUTHENTICATED', now(), now()) ON CONFLICT DO NOTHING"
        ),
        {"u": user_id_2},
    )

    token = "ExpoPushToken[xxxxxxxxxxxx]"
    provider = "EXPO"

    register_push_token(db, user_id_1, provider, token)
    register_push_token(db, user_id_1, provider, token)

    register_push_token(db, user_id_2, provider, token)
    result = db.execute(
        text("SELECT user_id FROM push_tokens WHERE token=:t"), {"t": token}
    ).scalar()
    assert result == user_id_2

    user_2 = ProductUser(user_id=user_id_2, email="del2@test.com", account_kind="AUTHENTICATED")
    issued = _issue_session(db, user_2, _now(None))
    logout(db, issued.access_token)

    result = db.execute(
        text("SELECT user_id FROM push_tokens WHERE token=:t"), {"t": token}
    ).scalar()
    assert result is None

    register_push_token(db, user_id_1, provider, token)
    result = db.execute(
        text("SELECT user_id FROM push_tokens WHERE token=:t"), {"t": token}
    ).scalar()
    assert result == user_id_1

    remove_invalid_push_token(db, provider, token)
    result = db.execute(
        text("SELECT user_id FROM push_tokens WHERE token=:t"), {"t": token}
    ).scalar()
    assert result is None

    with pytest.raises(PushTokenError):
        register_push_token(db, user_id_1, "APNS", token)


@patch("pitchvalue.product_services.account_deletion.UnconfiguredGoogleIdentityVerifier")
def test_account_deletion_cleanup(mock_verifier, db):
    mock_verifier.return_value.verify.return_value = VerifiedExternalIdentity(
        provider="GOOGLE", subject="del1@test.com", email="del1@test.com"
    )
    user_id = "test_user_del_1"
    match_id = 99991
    seed_canonical_match(db)
    db.execute(
        text(
            "INSERT INTO app_users (user_id, account_kind, created_at, updated_at) "
            "VALUES (:u, 'AUTHENTICATED', now(), now()) ON CONFLICT DO NOTHING"
        ),
        {"u": user_id},
    )
    db.execute(
        text(
            "INSERT INTO auth_identities (user_id, provider, provider_subject, created_at) "
            "VALUES (:u, 'GOOGLE', 'del1@test.com', now()) ON CONFLICT DO NOTHING"
        ),
        {"u": user_id},
    )

    follow_match(db, user_id, match_id)
    register_push_token(db, user_id, "EXPO", "token_del_1")

    sel_id = "test_selection_1"
    db.execute(
        text(
            "INSERT INTO saved_selections (saved_selection_id, user_id, match_id, market, "
            "selection, created_at) VALUES (:id, :u, :m, '1X2', 'H', now())"
        ),
        {"id": sel_id, "u": user_id, "m": match_id},
    )

    initiate_account_deletion(
        db,
        ProductUser(user_id=user_id, email="del1@test.com", account_kind="AUTHENTICATED"),
        password_or_token="dummy",
    )

    follows = get_followed_match_ids(db, user_id)
    assert len(follows) == 0

    result = db.execute(
        text("SELECT * FROM push_tokens WHERE user_id=:u"), {"u": user_id}
    ).fetchall()
    assert len(result) == 0

    result = db.execute(
        text("SELECT * FROM saved_selections WHERE user_id=:u"), {"u": user_id}
    ).fetchall()
    assert len(result) == 0

    result = db.execute(
        text("SELECT * FROM auth_identities WHERE user_id=:u"), {"u": user_id}
    ).fetchall()
    assert len(result) == 0

    result = db.execute(text("SELECT * FROM app_users WHERE user_id=:u"), {"u": user_id}).fetchall()
    assert len(result) == 0

    result = db.execute(
        text("SELECT match_id FROM matches WHERE match_id=:m"), {"m": match_id}
    ).fetchall()
    assert len(result) == 1
