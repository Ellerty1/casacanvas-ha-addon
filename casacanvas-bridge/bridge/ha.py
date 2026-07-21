"""Minimaler Client für die Home-Assistant-Supervisor-API."""
from __future__ import annotations

from typing import Any

import httpx

SUPERVISOR_BASE = "http://supervisor/core/api"


class HomeAssistantClient:
    def __init__(self, token: str, client: httpx.AsyncClient, base_url: str | None = None) -> None:
        self._token = token
        self._client = client
        self._base = (base_url or SUPERVISOR_BASE).rstrip("/")
        if not self._base.endswith("/api"):
            self._base = f"{self._base}/api"

    @property
    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}"}

    async def list_states(self) -> list[dict[str, Any]]:
        r = await self._client.get(f"{self._base}/states", headers=self._headers, timeout=30)
        r.raise_for_status()
        return r.json()

    async def list_lovelace_dashboards(self) -> list[dict[str, Any]]:
        r = await self._client.get(
            f"{self._base}/lovelace/dashboards",
            headers=self._headers,
            timeout=30,
        )
        if r.status_code == 404:
            return []
        r.raise_for_status()
        return r.json() or []

    async def get_dashboard_config(self, url_path: str | None) -> dict[str, Any] | None:
        params = {"url_path": url_path} if url_path else None
        r = await self._client.get(
            f"{self._base}/lovelace/config",
            headers=self._headers,
            params=params,
            timeout=30,
        )
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()

    async def save_dashboard_config(self, url_path: str, config: dict[str, Any]) -> None:
        r = await self._client.post(
            f"{self._base}/lovelace/config",
            headers={**self._headers, "Content-Type": "application/json"},
            params={"url_path": url_path},
            json=config,
            timeout=60,
        )
        r.raise_for_status()
