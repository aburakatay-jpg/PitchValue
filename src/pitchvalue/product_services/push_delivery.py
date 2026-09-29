"""Push notification delivery implementation."""

import logging
import os
from typing import Any

import httpx
from sqlalchemy import Connection

from pitchvalue.product_services.push_tokens import (
    get_user_expo_push_tokens,
    remove_invalid_push_token,
)

logger = logging.getLogger(__name__)

EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"


def send_push_to_user(
    connection: Connection,
    user_id: str,
    title: str,
    body: str,
    data: dict[str, Any] | None = None,
) -> None:
    """Send a push notification to all EXPO devices owned by a user."""
    tokens = get_user_expo_push_tokens(connection, user_id)
    if not tokens:
        return

    messages = [
        {
            "to": token,
            "sound": "default",
            "title": title,
            "body": body,
            "data": data or {},
        }
        for token in tokens
    ]

    headers = {
        "Accept": "application/json",
        "Accept-encoding": "gzip, deflate",
        "Content-Type": "application/json",
    }

    expo_access_token = os.getenv("EXPO_ACCESS_TOKEN")
    if expo_access_token:
        headers["Authorization"] = f"Bearer {expo_access_token}"

    for i in range(0, len(messages), 100):
        batch = messages[i : i + 100]
        batch_tokens = tokens[i : i + 100]

        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.post(
                    EXPO_PUSH_URL,
                    json=batch,
                    headers=headers,
                )

            if response.status_code >= 500:
                logger.warning(
                    f"Transient Expo Push API error (HTTP {response.status_code}): {response.text}"
                )
                continue

            response.raise_for_status()

            try:
                response_json = response.json()
                response_data = response_json.get("data", [])
            except ValueError:
                logger.error(f"Malformed JSON response from Expo Push API: {response.text}")
                continue

            for token, ticket in zip(batch_tokens, response_data, strict=False):
                if ticket.get("status") == "error":
                    details = ticket.get("details", {})
                    error_type = details.get("error")

                    if error_type == "DeviceNotRegistered":
                        logger.info(f"Removing invalid EXPO push token for user {user_id}")
                        remove_invalid_push_token(connection, "EXPO", token)
                    else:
                        logger.warning(f"Expo push error for token {token}: {ticket}")

        except httpx.RequestError as error:
            logger.warning(f"Transient network error sending Expo push: {error}")
            continue
        except httpx.HTTPStatusError as error:
            logger.warning(
                f"Unexpected HTTP {error.response.status_code} sending Expo push: "
                f"{error.response.text}"
            )
            continue
        except Exception as error:
            logger.exception(f"Unexpected error in push delivery: {error}")
            continue
