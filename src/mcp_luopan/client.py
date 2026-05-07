"""HTTP client for the Four Pillars FastAPI backend."""

from __future__ import annotations

from typing import Any

import httpx

from .config import Config


class LuopanServiceError(Exception):
    """Raised when the upstream backend cannot be reached or returns an unrecoverable error."""

    def __init__(self, kind: str, detail: str):
        super().__init__(f"{kind}: {detail}")
        self.kind = kind
        self.detail = detail


class LuopanClient:
    """Thin async HTTP client. One request per method, no caching, no session reuse."""

    def __init__(self, config: Config):
        self._config = config

    async def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self._config.api_base}{path}"
        last_err: Exception | None = None
        for _ in range(self._config.http_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self._config.timeout_seconds) as c:
                    r = await c.post(url, json=payload)
                if r.status_code == 404:
                    raise LuopanServiceError("session_expired", f"{path} returned 404")
                if r.status_code == 429:
                    raise LuopanServiceError("rate_limited", r.text or "429")
                if r.status_code >= 500:
                    raise LuopanServiceError("backend_error", f"{r.status_code} {r.text[:200]}")
                if r.status_code >= 400:
                    raise LuopanServiceError("bad_request", f"{r.status_code} {r.text[:200]}")
                return r.json()
            except httpx.ConnectError as e:
                last_err = e
                continue
            except httpx.TimeoutException as e:
                last_err = e
                continue
        raise LuopanServiceError("service_unreachable", str(last_err) if last_err else "connect failed")

    async def analyze(self, year: int, month: int, day: int, hour: int, gender: int) -> dict[str, Any]:
        return await self._post(
            "/api/analyze",
            {"year": year, "month": month, "day": day, "hour": hour, "gender": gender},
        )

    async def chat(self, session_id: str, question: str) -> dict[str, Any]:
        return await self._post(
            "/api/chat",
            {"session_id": session_id, "question": question},
        )
