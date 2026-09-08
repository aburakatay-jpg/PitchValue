"""Conventional ASGI entry point for Uvicorn."""

from pitchvalue.api.app import create_app

app = create_app()
