"""Minimal safe logging configuration for API processes."""

from __future__ import annotations

import logging


class RequestIdFilter(logging.Filter):
    """Ensure every formatted record has a bounded request-id field."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "request_id"):
            record.request_id = "-"
        return True


def configure_logging(level: str) -> None:
    """Configure standard logging without including sensitive configuration."""
    logging.basicConfig(
        level=level,
        format="%(levelname)s %(name)s request_id=%(request_id)s %(message)s",
    )
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    for handler in root_logger.handlers:
        if not any(isinstance(item, RequestIdFilter) for item in handler.filters):
            handler.addFilter(RequestIdFilter())
