"""Push token ownership and lifecycle management."""

from sqlalchemy import Connection, text


class PushTokenError(ValueError):
    """Validation or state error for push tokens."""


def register_push_token(
    connection: Connection,
    user_id: str,
    provider: str,
    token: str,
) -> None:
    """Register or refresh a push token, transferring ownership if necessary."""
    if provider != "EXPO":
        raise PushTokenError(f"Unsupported provider: {provider}")

    connection.execute(
        text(
            """
            INSERT INTO push_tokens (user_id, provider, token, created_at, last_seen_at)
            VALUES (:user_id, :provider, :token, now(), now())
            ON CONFLICT (provider, token) DO UPDATE
            SET user_id = EXCLUDED.user_id,
                last_seen_at = now()
            """
        ),
        {"user_id": user_id, "provider": provider, "token": token},
    )


def unregister_user_push_tokens(
    connection: Connection,
    user_id: str,
) -> None:
    """Disassociate all push tokens from a user on logout."""
    connection.execute(
        text(
            """
            UPDATE push_tokens
            SET user_id = NULL
            WHERE user_id = :user_id
            """
        ),
        {"user_id": user_id},
    )


def remove_invalid_push_token(
    connection: Connection,
    provider: str,
    token: str,
) -> None:
    """Hard delete an invalid or permanently rejected token."""
    connection.execute(
        text(
            """
            DELETE FROM push_tokens
            WHERE provider = :provider AND token = :token
            """
        ),
        {"provider": provider, "token": token},
    )


def get_user_expo_push_tokens(
    connection: Connection,
    user_id: str,
) -> list[str]:
    """Get all EXPO push tokens owned by a user."""
    rows = connection.execute(
        text(
            """
            SELECT token FROM push_tokens
            WHERE user_id = :user_id AND provider = 'EXPO'
            """
        ),
        {"user_id": user_id},
    ).fetchall()
    return [row.token for row in rows]
