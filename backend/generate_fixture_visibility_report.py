import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from urllib import parse, request
from urllib.error import HTTPError, URLError

from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from sqlalchemy import text

from pitchvalue.api.database import create_database
from pitchvalue.config.settings import load_settings


REPORT_DIR = Path(__file__).parent / "reports" / "fixture_visibility"

TIMEZONE_NAME = "Europe/Istanbul"

FRESHNESS_WINDOW = timedelta(days=5)

TELEGRAM_API_TIMEOUT_SECONDS = 15

DRIVE_SCOPES = [
    "https://www.googleapis.com/auth/drive",
]

DRIVE_FOLDER_MIME_TYPE = "application/vnd.google-apps.folder"

DRIVE_TOKEN_FILE = (
    Path(__file__).parent.parent
    / "secrets"
    / "google-drive-oauth-token.json"
)


def send_telegram_message(
    message: str,
) -> tuple[bool, str]:
    bot_token = os.getenv(
        "TELEGRAM_BOT_TOKEN"
    )

    chat_id = os.getenv(
        "TELEGRAM_CHAT_ID"
    )

    if not bot_token or not chat_id:
        return (
            False,
            "SKIPPED_MISSING_CONFIGURATION",
        )

    telegram_url = (
        f"https://api.telegram.org/"
        f"bot{bot_token}/sendMessage"
    )

    payload = parse.urlencode(
        {
            "chat_id": chat_id,
            "text": message,
            "disable_web_page_preview": "true",
        }
    ).encode("utf-8")

    telegram_request = request.Request(
        telegram_url,
        data=payload,
        method="POST",
        headers={
            "Content-Type":
                "application/x-www-form-urlencoded",
        },
    )

    try:
        with request.urlopen(
            telegram_request,
            timeout=TELEGRAM_API_TIMEOUT_SECONDS,
        ) as response:
            response_body = (
                response.read().decode("utf-8")
            )

            result = json.loads(
                response_body
            )

            if result.get("ok") is True:
                return True, "DELIVERED"

            return (
                False,
                "TELEGRAM_API_REJECTED",
            )

    except HTTPError as exc:
        return (
            False,
            f"HTTP_ERROR_{exc.code}",
        )

    except URLError:
        return (
            False,
            "NETWORK_ERROR",
        )

    except TimeoutError:
        return (
            False,
            "TIMEOUT",
        )

    except json.JSONDecodeError:
        return (
            False,
            "INVALID_TELEGRAM_RESPONSE",
        )

    except Exception as exc:
        return (
            False,
            (
                "UNEXPECTED_ERROR_"
                f"{type(exc).__name__}"
            ),
        )


def load_drive_credentials():
    if not DRIVE_TOKEN_FILE.exists():
        raise RuntimeError(
            "Google Drive OAuth token file "
            "does not exist."
        )

    credentials = (
        Credentials.from_authorized_user_file(
            str(DRIVE_TOKEN_FILE),
            DRIVE_SCOPES,
        )
    )

    if (
        credentials.expired
        and credentials.refresh_token
    ):
        credentials.refresh(
            Request()
        )

        DRIVE_TOKEN_FILE.write_text(
            credentials.to_json(),
            encoding="utf-8",
        )

    if not credentials.valid:
        raise RuntimeError(
            "Google Drive OAuth credentials "
            "are not valid."
        )

    return credentials


def get_or_create_drive_folder(
    drive,
    parent_id: str,
    folder_name: str,
) -> str:
    safe_name = folder_name.replace(
        "'",
        "\\'",
    )

    result = (
        drive.files()
        .list(
            q=(
                f"name = '{safe_name}' "
                f"and '{parent_id}' in parents "
                f"and mimeType = "
                f"'{DRIVE_FOLDER_MIME_TYPE}' "
                "and trashed = false"
            ),
            fields="files(id,name)",
            pageSize=10,
        )
        .execute()
    )

    folders = result.get(
        "files",
        [],
    )

    if folders:
        return folders[0]["id"]

    metadata = {
        "name": folder_name,
        "mimeType": DRIVE_FOLDER_MIME_TYPE,
        "parents": [parent_id],
    }

    folder = (
        drive.files()
        .create(
            body=metadata,
            fields="id,name",
        )
        .execute()
    )

    return folder["id"]


def upload_or_replace_drive_file(
    drive,
    parent_id: str,
    local_path: Path,
    mime_type: str,
):
    safe_name = local_path.name.replace(
        "'",
        "\\'",
    )

    result = (
        drive.files()
        .list(
            q=(
                f"name = '{safe_name}' "
                f"and '{parent_id}' in parents "
                "and trashed = false"
            ),
            fields="files(id,name)",
            pageSize=10,
        )
        .execute()
    )

    existing_files = result.get(
        "files",
        [],
    )

    media = MediaFileUpload(
        str(local_path),
        mimetype=mime_type,
        resumable=False,
    )

    if existing_files:
        file_id = existing_files[0]["id"]

        result = (
            drive.files()
            .update(
                fileId=file_id,
                media_body=media,
                fields="id,name",
            )
            .execute()
        )

        return (
            "REPLACED",
            result["id"],
        )

    metadata = {
        "name": local_path.name,
        "parents": [parent_id],
    }

    result = (
        drive.files()
        .create(
            body=metadata,
            media_body=media,
            fields="id,name",
        )
        .execute()
    )

    return (
        "UPLOADED",
        result["id"],
    )


def upload_reports_to_drive(
    report_date: str,
    json_path: Path,
    markdown_path: Path,
) -> tuple[bool, str]:
    root_folder_id = os.getenv(
        "GOOGLE_DRIVE_ROOT_FOLDER_ID"
    )

    if not root_folder_id:
        return (
            False,
            "SKIPPED_MISSING_ROOT_FOLDER_ID",
        )

    try:
        credentials = (
            load_drive_credentials()
        )

        drive = build(
            "drive",
            "v3",
            credentials=credentials,
            cache_discovery=False,
        )

        reports_folder_id = (
            get_or_create_drive_folder(
                drive,
                root_folder_id,
                "Reports",
            )
        )

        fixture_visibility_folder_id = (
            get_or_create_drive_folder(
                drive,
                reports_folder_id,
                "Fixture Visibility",
            )
        )

        year_folder_id = (
            get_or_create_drive_folder(
                drive,
                fixture_visibility_folder_id,
                report_date[:4],
            )
        )

        date_folder_id = (
            get_or_create_drive_folder(
                drive,
                year_folder_id,
                report_date,
            )
        )

        json_action, _ = (
            upload_or_replace_drive_file(
                drive,
                date_folder_id,
                json_path,
                "application/json",
            )
        )

        markdown_action, _ = (
            upload_or_replace_drive_file(
                drive,
                date_folder_id,
                markdown_path,
                "text/markdown",
            )
        )

        return (
            True,
            (
                f"JSON_{json_action};"
                f"MARKDOWN_{markdown_action}"
            ),
        )

    except Exception as exc:
        return (
            False,
            (
                "DRIVE_ERROR_"
                f"{type(exc).__name__}"
            ),
        )


def generate_report():
    load_dotenv()

    now = datetime.now().astimezone()

    report_date = (
        now.date().isoformat()
    )

    settings = load_settings()

    database = create_database(
        settings
    )

    database.start()

    try:
        with database.connect() as connection:
            row = connection.execute(
                text(
                    """
                    SELECT occurred_at, metadata
                    FROM operational_events
                    WHERE event_type =
                        'FIXTURE_REFRESH_SUCCEEDED'
                      AND occurred_at <= :report_cutoff
                    ORDER BY
                        occurred_at DESC,
                        event_id DESC
                    LIMIT 1
                    """
                ),
                {
                    "report_cutoff": now,
                },
            ).mappings().one_or_none()

            canonical_today_count = (
                connection.execute(
                    text(
                        """
                        SELECT count(*)
                        FROM matches m
                        WHERE (
                            m.kickoff_at_utc
                            AT TIME ZONE :timezone
                        )::date = :fixture_date
                        """
                    ),
                    {
                        "timezone":
                            TIMEZONE_NAME,
                        "fixture_date":
                            report_date,
                    },
                ).scalar_one()
            )

            quarantine_rows = (
                connection.execute(
                    text(
                        """
                        SELECT
                            reason_code,
                            count(*) AS count
                        FROM run_quarantines
                        WHERE (
                            occurred_at
                            AT TIME ZONE :timezone
                        )::date = :report_date
                        GROUP BY reason_code
                        """
                    ),
                    {
                        "timezone":
                            TIMEZONE_NAME,
                        "report_date":
                            report_date,
                    },
                ).all()
            )

        metadata = (
            row["metadata"]
            if row is not None
            else {}
        )

        provider_fixture_count = (
            int(
                metadata[
                    "provider_fixture_count"
                ]
            )
            if "provider_fixture_count"
            in metadata
            else None
        )

        event_canonical_fixture_count = (
            int(
                metadata[
                    "canonical_fixture_count"
                ]
            )
            if "canonical_fixture_count"
            in metadata
            else None
        )

        parsed_fixture_count = (
            int(
                metadata[
                    "parsed_fixture_count"
                ]
            )
            if "parsed_fixture_count"
            in metadata
            else None
        )

        malformed_fixture_count = (
            int(
                metadata[
                    "malformed_fixture_count"
                ]
            )
            if "malformed_fixture_count"
            in metadata
            else None
        )

        quarantine_count = (
            int(
                metadata[
                    "quarantine_count"
                ]
            )
            if "quarantine_count"
            in metadata
            else None
        )

        if row is None:
            freshness_status = (
                "UNAVAILABLE"
            )

            last_refresh_at = None

            evidence_source = "none"

        else:
            last_refresh_at = (
                row["occurred_at"]
            )

            if (
                last_refresh_at
                >= now - FRESHNESS_WINDOW
            ):
                freshness_status = "FRESH"

            else:
                freshness_status = "STALE"

            evidence_source = (
                "fixture_refresh_event"
            )

        canonical_fixture_count = int(
            canonical_today_count
        )

        today_api_count = (
            canonical_fixture_count
        )

        mobile_visible_count = (
            today_api_count
        )

        quarantine_reason_counts = {
            str(reason_code): int(count)
            for reason_code, count
            in quarantine_rows
        }

        competition_not_authorized_count = (
            quarantine_reason_counts.get(
                "UNSUPPORTED_COMPETITION",
                0,
            )
        )

        mapping_unresolved_count = (
            quarantine_reason_counts.get(
                "FIXTURE_MAPPING_UNRESOLVED",
                0,
            )
        )

        if freshness_status == "FRESH":
            provider_not_fresh_count = 0

        elif provider_fixture_count is not None:
            provider_not_fresh_count = (
                provider_fixture_count
            )

        else:
            provider_not_fresh_count = 0

        excluded_total = (
            competition_not_authorized_count
            + mapping_unresolved_count
            + provider_not_fresh_count
        )

        report = {
            "schema_version": "1.0",
            "report_type":
                "fixture_visibility",
            "report_date":
                report_date,
            "generated_at":
                now.isoformat(),
            "timezone":
                TIMEZONE_NAME,

            "provider": {
                "name": metadata.get(
                    "provider",
                    "UNKNOWN",
                ),
                "fixture_count":
                    provider_fixture_count,
                "parsed_fixture_count":
                    parsed_fixture_count,
                "event_canonical_fixture_count":
                    event_canonical_fixture_count,
                "malformed_fixture_count":
                    malformed_fixture_count,
                "quarantine_count":
                    quarantine_count,
                "freshness_status":
                    freshness_status,
                "last_refresh_at": (
                    last_refresh_at.isoformat()
                    if last_refresh_at
                    is not None
                    else None
                ),
                "evidence_source":
                    evidence_source,
            },

            "funnel": {
                "provider_fixture_count":
                    provider_fixture_count,
                "canonical_fixture_count":
                    canonical_fixture_count,
                "today_api_count":
                    today_api_count,
                "mobile_visible_count":
                    mobile_visible_count,
            },

            "excluded": {
                "total":
                    excluded_total,

                "measurement_status": {
                    "OUTSIDE_DATE_WINDOW":
                        "NOT_OBSERVABLE_CURRENT_FLOW",

                    "COMPETITION_NOT_AUTHORIZED":
                        "MEASURED",

                    "COMPETITION_INACTIVE":
                        "NOT_APPLIED_CURRENT_FLOW",

                    "MAPPING_UNRESOLVED":
                        "MEASURED",

                    "PROVIDER_NOT_FRESH":
                        "DERIVED_STATE",

                    "INVALID_LIFECYCLE":
                        "MEASURED_ZERO",

                    "API_TRANSFORMATION_EXCLUDED":
                        "DERIVED_ZERO",

                    "MOBILE_FILTER_EXCLUDED":
                        "DERIVED_ZERO",
                },

                "by_reason": {
                    "OUTSIDE_DATE_WINDOW":
                        0,

                    "COMPETITION_NOT_AUTHORIZED":
                        competition_not_authorized_count,

                    "COMPETITION_INACTIVE":
                        0,

                    "MAPPING_UNRESOLVED":
                        mapping_unresolved_count,

                    "PROVIDER_NOT_FRESH":
                        provider_not_fresh_count,

                    "INVALID_LIFECYCLE":
                        0,

                    "API_TRANSFORMATION_EXCLUDED":
                        0,

                    "MOBILE_FILTER_EXCLUDED":
                        0,
                },
            },

            "dependencies": {
                "engine_required":
                    False,
                "publication_required":
                    False,
            },
        }

        REPORT_DIR.mkdir(
            parents=True,
            exist_ok=True,
        )

        json_path = (
            REPORT_DIR
            / (
                "fixture_visibility_"
                f"{report_date}.json"
            )
        )

        with json_path.open(
            "w",
            encoding="utf-8",
        ) as file:
            json.dump(
                report,
                file,
                ensure_ascii=False,
                indent=2,
            )

        last_refresh_text = (
            last_refresh_at.isoformat()
            if last_refresh_at is not None
            else "N/A"
        )

        markdown_content = f"""# PitchValue — Daily Fixture Visibility Report

## Report Info

- Report Date: {report_date}
- Generated At: {now.isoformat()}
- Timezone: {TIMEZONE_NAME}

## Provider

- Provider: {metadata.get("provider", "UNKNOWN")}
- Freshness Status: {freshness_status}
- Last Refresh At: {last_refresh_text}
- Provider Fixture Count: {provider_fixture_count}
- Parsed Fixture Count: {parsed_fixture_count}
- Canonical Fixture Count From Refresh Event: {event_canonical_fixture_count}
- Malformed Fixture Count: {malformed_fixture_count}
- Quarantine Count: {quarantine_count}

## Visibility Funnel

- Provider: {provider_fixture_count}
- Canonical DB Today: {canonical_fixture_count}
- Today API: {today_api_count}
- Mobile Visible: {mobile_visible_count}

## Exclusions

- OUTSIDE_DATE_WINDOW: 0
  - Status: NOT_OBSERVABLE_CURRENT_FLOW

- COMPETITION_NOT_AUTHORIZED: {competition_not_authorized_count}
  - Status: MEASURED

- COMPETITION_INACTIVE: 0
  - Status: NOT_APPLIED_CURRENT_FLOW

- MAPPING_UNRESOLVED: {mapping_unresolved_count}
  - Status: MEASURED

- PROVIDER_NOT_FRESH: {provider_not_fresh_count}
  - Status: DERIVED_STATE

- INVALID_LIFECYCLE: 0
  - Status: MEASURED_ZERO

- API_TRANSFORMATION_EXCLUDED: 0
  - Status: DERIVED_ZERO

- MOBILE_FILTER_EXCLUDED: 0
  - Status: DERIVED_ZERO

## Excluded Total

{excluded_total}

## Dependencies

- PV Engine Required: NO
- Publication Required: NO

## Operational Result

Fixture visibility reporting completed successfully for {report_date}.
"""

        markdown_path = (
            REPORT_DIR
            / (
                "fixture_visibility_"
                f"{report_date}.md"
            )
        )

        with markdown_path.open(
            "w",
            encoding="utf-8",
        ) as file:
            file.write(
                markdown_content
            )

        drive_success, drive_status = (
            upload_reports_to_drive(
                report_date,
                json_path,
                markdown_path,
            )
        )

        telegram_summary = f"""PitchValue — Fixture Visibility

Date: {report_date}
Provider: {metadata.get("provider", "UNKNOWN")}
Freshness: {freshness_status}

Provider Fixtures: {provider_fixture_count}
Canonical Today: {canonical_fixture_count}
Today API: {today_api_count}
Mobile Visible: {mobile_visible_count}

Excluded: {excluded_total}
Unauthorized Competition: {competition_not_authorized_count}
Mapping Unresolved: {mapping_unresolved_count}
Provider Not Fresh: {provider_not_fresh_count}

Engine Required: NO
Publication Required: NO
"""

        telegram_delivered, telegram_status = (
            send_telegram_message(
                telegram_summary
            )
        )

        print(
            f"JSON report created: "
            f"{json_path}"
        )

        print(
            f"Markdown report created: "
            f"{markdown_path}"
        )

        if row is None:
            print(
                "No eligible "
                "FIXTURE_REFRESH_SUCCEEDED "
                "event found."
            )

        else:
            print(
                "Latest eligible fixture "
                "refresh event found."
            )

            print(
                f"Occurred at: "
                f"{row['occurred_at']}"
            )

            print(
                f"Metadata: "
                f"{row['metadata']}"
            )

        print(
            f"Freshness: "
            f"{freshness_status}"
        )

        print(
            f"Freshness evidence: "
            f"{evidence_source}"
        )

        print(
            f"Canonical today count: "
            f"{canonical_fixture_count}"
        )

        print(
            "Competition not authorized: "
            f"{competition_not_authorized_count}"
        )

        print(
            f"Mapping unresolved: "
            f"{mapping_unresolved_count}"
        )

        print(
            f"Provider not fresh: "
            f"{provider_not_fresh_count}"
        )

        print(
            f"Excluded total: "
            f"{excluded_total}"
        )

        print("")

        if drive_success:
            print(
                "Google Drive delivery: "
                "SUCCESS"
            )
        else:
            print(
                "Google Drive delivery: "
                "FAILED/SKIPPED"
            )

        print(
            f"Google Drive status: "
            f"{drive_status}"
        )

        print("")

        print(
            "----- TELEGRAM SUMMARY -----"
        )

        print(
            telegram_summary
        )

        print(
            "----------------------------"
        )

        if telegram_delivered:
            print(
                "Telegram delivery: SUCCESS"
            )

        else:
            print(
                "Telegram delivery: "
                "FAILED/SKIPPED"
            )

        print(
            f"Telegram status: "
            f"{telegram_status}"
        )

    finally:
        database.dispose()


if __name__ == "__main__":
    generate_report()