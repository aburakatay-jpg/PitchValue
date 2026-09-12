"""Secret-safe 5DFA Free-plan configuration."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from urllib.parse import urlsplit

from pitchvalue.config.settings import ConfigurationError

DEFAULT_BASE_URL = "https://api.5dollarfootballapi.com/v1"


@dataclass(frozen=True, repr=False)
class FiveDfaConfig:
    api_key: str
    base_url: str = DEFAULT_BASE_URL
    timeout_seconds: float = 10.0
    plan_name: str = "FREE"
    max_safe_retries: int = 1

    def __post_init__(self) -> None:
        if not self.api_key.strip():
            raise ConfigurationError("FIVEDFA_API_KEY is required when the provider is used")
        parsed = urlsplit(self.base_url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.query or parsed.fragment:
            raise ConfigurationError("FIVEDFA_BASE_URL must be an HTTPS base URL")
        if self.timeout_seconds <= 0:
            raise ConfigurationError("FIVEDFA_TIMEOUT_SECONDS must be positive")
        if self.plan_name != "FREE":
            raise ConfigurationError("only the 5DFA FREE plan is authorized")
        if self.max_safe_retries not in {0, 1}:
            raise ConfigurationError("FIVEDFA_MAX_SAFE_RETRIES must be 0 or 1")

    def __repr__(self) -> str:
        return (
            "FiveDfaConfig(api_key='<redacted>', "
            f"base_url={self.base_url!r}, timeout_seconds={self.timeout_seconds!r}, "
            f"plan_name={self.plan_name!r}, max_safe_retries={self.max_safe_retries!r})"
        )


def load_five_dfa_config(environment: Mapping[str, str]) -> FiveDfaConfig:
    """Load provider configuration without making it mandatory for the application."""
    raw_timeout = environment.get("FIVEDFA_TIMEOUT_SECONDS", "10").strip()
    raw_retries = environment.get("FIVEDFA_MAX_SAFE_RETRIES", "1").strip()
    try:
        timeout = float(raw_timeout)
        retries = int(raw_retries)
    except ValueError as error:
        raise ConfigurationError("invalid 5DFA numeric configuration") from error
    return FiveDfaConfig(
        api_key=environment.get("FIVEDFA_API_KEY", ""),
        base_url=environment.get("FIVEDFA_BASE_URL", DEFAULT_BASE_URL).strip().rstrip("/"),
        timeout_seconds=timeout,
        plan_name=environment.get("FIVEDFA_PLAN", "FREE").strip().upper(),
        max_safe_retries=retries,
    )
