import sys
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

# Runtime script import; the adjacent .pyi supplies its test-facing type contract.
sys.path.append(str(Path(__file__).parent.parent / "backend"))

import generate_fixture_visibility_report


class TestTelegramSummary(unittest.TestCase):
    def test_telegram_summary_includes_drive_success(self) -> None:
        with (
            patch("generate_fixture_visibility_report.create_database") as mock_create_database,
            patch("generate_fixture_visibility_report.load_settings"),
            patch("generate_fixture_visibility_report.upload_reports_to_drive") as mock_upload,
            patch("generate_fixture_visibility_report.send_telegram_message") as mock_send,
        ):
            # Setup mock DB result
            mock_db = MagicMock()
            mock_create_database.return_value = mock_db
            mock_conn = MagicMock()
            mock_db.connect.return_value.__enter__.return_value = mock_conn

            # Mocking the mapping execution for operational events
            mock_mappings = MagicMock()
            mock_mappings.mappings.return_value.one_or_none.return_value = {
                "occurred_at": datetime.now().astimezone(),
                "metadata": {
                    "provider": "TEST_PROVIDER",
                    "provider_fixture_count": 10,
                    "canonical_fixture_count": 10,
                    "parsed_fixture_count": 10,
                    "malformed_fixture_count": 0,
                    "quarantine_count": 0,
                },
            }

            # Mocking the scalar execution for canonical count
            mock_scalar = MagicMock()
            mock_scalar.scalar_one.return_value = 10

            # Mocking the all execution for quarantine rows
            mock_all = MagicMock()
            mock_all.all.return_value = []

            # Assign returns based on call order
            mock_conn.execute.side_effect = [mock_mappings, mock_scalar, mock_all]

            # Force drive success
            mock_upload.return_value = (True, "JSON_UPLOADED;MARKDOWN_UPLOADED")
            mock_send.return_value = (True, "DELIVERED")

            generate_fixture_visibility_report.generate_report()

            mock_send.assert_called_once()
            summary = mock_send.call_args[0][0]
            self.assertIn("Google Drive: ✅ SUCCESS", summary)
            self.assertNotIn("Google Drive: ❌ FAILED", summary)

    def test_telegram_summary_includes_drive_failure(self) -> None:
        with (
            patch("generate_fixture_visibility_report.create_database") as mock_create_database,
            patch("generate_fixture_visibility_report.load_settings"),
            patch("generate_fixture_visibility_report.upload_reports_to_drive") as mock_upload,
            patch("generate_fixture_visibility_report.send_telegram_message") as mock_send,
        ):
            # Setup mock DB result
            mock_db = MagicMock()
            mock_create_database.return_value = mock_db
            mock_conn = MagicMock()
            mock_db.connect.return_value.__enter__.return_value = mock_conn

            # Mocking the mapping execution for operational events
            mock_mappings = MagicMock()
            mock_mappings.mappings.return_value.one_or_none.return_value = {
                "occurred_at": datetime.now().astimezone(),
                "metadata": {
                    "provider": "TEST_PROVIDER",
                    "provider_fixture_count": 10,
                    "canonical_fixture_count": 10,
                    "parsed_fixture_count": 10,
                    "malformed_fixture_count": 0,
                    "quarantine_count": 0,
                },
            }

            # Mocking the scalar execution for canonical count
            mock_scalar = MagicMock()
            mock_scalar.scalar_one.return_value = 10

            # Mocking the all execution for quarantine rows
            mock_all = MagicMock()
            mock_all.all.return_value = []

            # Assign returns based on call order
            mock_conn.execute.side_effect = [mock_mappings, mock_scalar, mock_all]

            # Force drive failure
            mock_upload.return_value = (False, "DRIVE_ERROR_RuntimeError")
            mock_send.return_value = (True, "DELIVERED")

            generate_fixture_visibility_report.generate_report()

            mock_send.assert_called_once()
            summary = mock_send.call_args[0][0]
            self.assertIn("Google Drive: ❌ FAILED", summary)
            self.assertIn("Reason: DRIVE_ERROR_RuntimeError", summary)
            self.assertNotIn("Google Drive: ✅ SUCCESS", summary)


if __name__ == "__main__":
    unittest.main()
