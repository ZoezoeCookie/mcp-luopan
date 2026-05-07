"""Environment-based configuration for mcp-luopan."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    api_base: str
    timeout_seconds: float
    http_retries: int


def load_config() -> Config:
    return Config(
        api_base=os.environ.get("LUOPAN_API_BASE", "http://127.0.0.1:8000").rstrip("/"),
        timeout_seconds=float(os.environ.get("LUOPAN_TIMEOUT_SECONDS", "60")),
        http_retries=int(os.environ.get("LUOPAN_HTTP_RETRIES", "1")),
    )
