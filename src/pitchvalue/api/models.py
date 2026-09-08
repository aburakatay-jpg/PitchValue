"""Typed system response models."""

from typing import Literal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"


class ReadinessResponse(BaseModel):
    status: Literal["ready"] = "ready"


class ApiVersionResponse(BaseModel):
    version: Literal["v1"] = "v1"
