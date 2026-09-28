"""Followed matches ownership and lifecycle management."""

from sqlalchemy import Connection, text


def follow_match(
    connection: Connection,
    user_id: str,
    match_id: int,
) -> None:
    """Follow a match, safely ignoring duplicates."""
    connection.execute(
        text(
            """
            INSERT INTO followed_matches (user_id, match_id, created_at)
            VALUES (:user_id, :match_id, now())
            ON CONFLICT (user_id, match_id) DO NOTHING
            """
        ),
        {"user_id": user_id, "match_id": match_id},
    )


def unfollow_match(
    connection: Connection,
    user_id: str,
    match_id: int,
) -> None:
    """Hard delete a followed match."""
    connection.execute(
        text(
            """
            DELETE FROM followed_matches
            WHERE user_id = :user_id AND match_id = :match_id
            """
        ),
        {"user_id": user_id, "match_id": match_id},
    )


def get_followed_match_ids(
    connection: Connection,
    user_id: str,
) -> list[int]:
    """Get all match IDs followed by a user."""
    result = connection.execute(
        text(
            """
            SELECT match_id FROM followed_matches
            WHERE user_id = :user_id
            """
        ),
        {"user_id": user_id},
    )
    return [row.match_id for row in result.mappings()]
