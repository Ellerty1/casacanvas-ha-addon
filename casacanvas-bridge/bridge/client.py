"""HTTP-Client für die CasaCanvas-Public-API."""
from __future__ import annotations

from typing import Any

import httpx


class CasaCanvasClient:
    def __init__(self, base_url: str, client: httpx.AsyncClient, token: str | None = None) -> None:
        self._base = base_url.rstrip("/")
        self._client = client
        self._token = token

    def with_token(self, token: str) -> "CasaCanvasClient":
        return CasaCanvasClient(self._base, self._client, token)

    @property
    def _auth(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}"} if self._token else {}

    async def pair(self, code: str, ha_version: str, name: str) -> dict[str, Any]:
        r = await self._client.post(
            f"{self._base}/api/public/bridge/pair",
            json={"code": code, "ha_version": ha_version, "name": name, "addon_version": "0.1.0"},
            timeout=30,
        )
        r.raise_for_status()
        return r.json()

    async def heartbeat(self, version: str) -> None:
        r = await self._client.post(
            f"{self._base}/api/public/bridge/heartbeat",
            headers=self._auth,
            json={"addon_version": version},
            timeout=15,
        )
        r.raise_for_status()

    async def push_entities(self, entities: list[dict[str, Any]]) -> None:
        chunk_size = 500
        for i in range(0, max(len(entities), 1), chunk_size):
            chunk = entities[i : i + chunk_size]
            if not chunk:
                break
            r = await self._client.post(
                f"{self._base}/api/public/bridge/entities",
                headers=self._auth,
                json={"entities": chunk, "replace": i == 0},
                timeout=60,
            )
            r.raise_for_status()

    async def push_dashboards(self, dashboards: list[dict[str, Any]]) -> None:
        r = await self._client.post(
            f"{self._base}/api/public/bridge/dashboards",
            headers=self._auth,
            json={"dashboards": dashboards, "replace": True},
            timeout=60,
        )
        r.raise_for_status()

    async def next_deployments(self) -> list[dict[str, Any]]:
        r = await self._client.get(
            f"{self._base}/api/public/bridge/deployments/pending",
            headers=self._auth,
            timeout=15,
        )
        if r.status_code == 204:
            return []
        r.raise_for_status()
        data = r.json() or {}
        return data.get("jobs") or []

    async def ack_deployment(
        self,
        deployment_id: str,
        status: str,
        error: str | None = None,
    ) -> None:
        r = await self._client.post(
            f"{self._base}/api/public/bridge/deployments/ack",
            headers=self._auth,
            json={"id": deployment_id, "status": status, "error": error},
            timeout=30,
        )
        r.raise_for_status()
