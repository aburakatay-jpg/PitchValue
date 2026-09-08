"""Windows-compatible local API server command."""

from __future__ import annotations

import uvicorn

from pitchvalue.config import load_settings


def main() -> None:
    """Run the API with configured host and port."""
    settings = load_settings()
    uvicorn.run(
        "pitchvalue.api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        log_level=settings.log_level.lower(),
    )
