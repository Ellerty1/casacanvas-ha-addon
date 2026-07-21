"""Minimaler Client für die Home-Assistant-Supervisor-API."""
from __future__ import annotations

import json
import logging
from typing import Any
from urllib.parse import urlparse

import httpx

try:
    import websockets  # type: ignore
except ImportError:  # pragma: no cover
    websockets = None  # type: ignore

log = logging.getLogger("bridge.ha")

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

    def _ws_url(self) -> str:
        """Leite ws(s)://<host>/api/websocket aus der REST-Base-URL ab."""
        p = urlparse(self._base)
        scheme = "wss" if p.scheme == "https" else "ws"
        return f"{scheme}://{p.netloc}/api/websocket"

    async def get_dashboard_config_ws(self, url_path: str | None) -> dict[str, Any] | None:
        """Hole die Lovelace-Config über die WebSocket-API — funktioniert auch im YAML-Modus."""
        if websockets is None:
            log.warning("websockets-Paket fehlt — nutze REST-Fallback.")
            return await self.get_dashboard_config(url_path)
        try:
            async with websockets.connect(self._ws_url(), max_size=32 * 1024 * 1024) as ws:
                hello = json.loads(await ws.recv())
                if hello.get("type") != "auth_required":
                    log.warning("Unerwartete WS-Antwort: %s", hello)
                    return None
                await ws.send(json.dumps({"type": "auth", "access_token": self._token}))
                auth_resp = json.loads(await ws.recv())
                if auth_resp.get("type") != "auth_ok":
                    log.warning("WS-Auth fehlgeschlagen: %s", auth_resp)
                    return None
                req: dict[str, Any] = {"id": 1, "type": "lovelace/config", "force": False}
                if url_path:
                    req["url_path"] = url_path
                await ws.send(json.dumps(req))
                resp = json.loads(await ws.recv())
                if not resp.get("success"):
                    log.info("WS lovelace/config (%s) fehlgeschlagen: %s", url_path, resp.get("error"))
                    return None
                result = resp.get("result")
                return result if isinstance(result, dict) else None
        except Exception as exc:  # noqa: BLE001
            log.warning("WS-Fetch (%s) Exception: %s", url_path, exc)
            return None

    async def list_lovelace_dashboards_ws(self) -> list[dict[str, Any]]:
        if websockets is None:
            return await self.list_lovelace_dashboards()
        try:
            async with websockets.connect(self._ws_url(), max_size=8 * 1024 * 1024) as ws:
                hello = json.loads(await ws.recv())
                if hello.get("type") != "auth_required":
                    return []
                await ws.send(json.dumps({"type": "auth", "access_token": self._token}))
                auth_resp = json.loads(await ws.recv())
                if auth_resp.get("type") != "auth_ok":
                    return []
                await ws.send(json.dumps({"id": 1, "type": "lovelace/dashboards/list"}))
                resp = json.loads(await ws.recv())
                if not resp.get("success"):
                    return []
                return resp.get("result") or []
        except Exception as exc:  # noqa: BLE001
            log.warning("WS-Dashboards-Liste Exception: %s", exc)
            return []
