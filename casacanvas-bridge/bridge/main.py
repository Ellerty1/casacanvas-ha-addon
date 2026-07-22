"""Event-Loop der CasaCanvas-Bridge."""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

import httpx
import yaml

from . import __version__
from .client import CasaCanvasClient
from .config import BridgeConfig
from . import display as display_probe
from .ha import HomeAssistantClient

TOKEN_PATH = "/data/token"


def _setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def _load_token() -> str | None:
    try:
        with open(TOKEN_PATH, "r", encoding="utf-8") as f:
            return f.read().strip() or None
    except FileNotFoundError:
        return None


def _save_token(token: str) -> None:
    os.makedirs(os.path.dirname(TOKEN_PATH), exist_ok=True)
    with open(TOKEN_PATH, "w", encoding="utf-8") as f:
        f.write(token)


def _map_entity(state: dict[str, Any]) -> dict[str, Any]:
    attrs = state.get("attributes") or {}
    entity_id = state.get("entity_id") or ""
    domain = entity_id.split(".", 1)[0] if "." in entity_id else ""
    return {
        "entity_id": entity_id,
        "domain": domain,
        "friendly_name": attrs.get("friendly_name") or entity_id,
        "area": attrs.get("area_id"),
        "device_class": attrs.get("device_class"),
        "unit": attrs.get("unit_of_measurement"),
        "icon": attrs.get("icon"),
        "last_state": state.get("state"),
    }


async def _ensure_paired(
    cc: CasaCanvasClient, cfg: BridgeConfig, log: logging.Logger
) -> CasaCanvasClient:
    token = _load_token()
    if token:
        return cc.with_token(token)
    if not cfg.pairing_code:
        log.error("Kein Pairing-Code konfiguriert. Bitte in den Add-on-Optionen setzen.")
        raise SystemExit(2)
    log.info("Tausche Pairing-Code gegen aktives Token ...")
    resp = await cc.pair(cfg.pairing_code, ha_version="unknown", name="Home Assistant")
    token = resp["token"]
    _save_token(token)
    log.info("Pairing erfolgreich. Token gespeichert.")
    return cc.with_token(token)


async def _sync_once(cc: CasaCanvasClient, ha: HomeAssistantClient, log: logging.Logger) -> None:
    states = await ha.list_states()
    entities = [_map_entity(s) for s in states if s.get("entity_id")]
    log.info("Synchronisiere %d Entitaeten ...", len(entities))
    await cc.push_entities(entities)

    # 1) User-registrierte Dashboards (Storage-Mode): REST + WS-Fallback
    try:
        dashboards_meta = await ha.list_lovelace_dashboards()
    except Exception as exc:  # noqa: BLE001
        log.warning("REST /lovelace/dashboards fehlgeschlagen: %s — versuche WebSocket.", exc)
        dashboards_meta = []
    if not dashboards_meta:
        dashboards_meta = await ha.list_lovelace_dashboards_ws()
    log.info("HA meldet %d zusaetzliche Lovelace-Dashboards.", len(dashboards_meta))

    payload: list[dict[str, Any]] = []

    # 2) Default-Dashboard (Uebersicht / Hausdisplay im YAML-Modus)
    default = None
    try:
        default = await ha.get_dashboard_config(None)
    except Exception as exc:  # noqa: BLE001
        log.info("REST-Default-Config fehlgeschlagen (%s) — nutze WebSocket.", exc)
    if default is None:
        default = await ha.get_dashboard_config_ws(None)
    if default is not None:
        title = (default.get("title") if isinstance(default, dict) else None) or "Uebersicht"
        payload.append({"url_path": None, "title": title, "config": default})
        log.info("Default-Dashboard '%s' geladen.", title)
    else:
        log.warning("Default-Dashboard konnte weder per REST noch WS geladen werden.")

    # 3) Alle uebrigen Dashboards
    for d in dashboards_meta:
        url_path = d.get("url_path")
        cfg = None
        try:
            cfg = await ha.get_dashboard_config(url_path)
        except Exception as exc:  # noqa: BLE001
            log.info("REST-Config fuer '%s' fehlgeschlagen (%s) — nutze WebSocket.", url_path, exc)
        if cfg is None:
            cfg = await ha.get_dashboard_config_ws(url_path)
        if cfg is not None:
            payload.append(
                {
                    "url_path": url_path,
                    "title": d.get("title") or url_path,
                    "config": cfg,
                }
            )
            log.info("Dashboard '%s' geladen.", d.get("title") or url_path)
        else:
            log.warning("Dashboard '%s' konnte nicht geladen werden.", url_path)

    # Serialize configs to YAML strings and normalise url_path (server requires non-empty).
    serialised = [
        {
            "url_path": p.get("url_path") or "lovelace",
            "title": p.get("title") or (p.get("url_path") or "Übersicht"),
            "yaml": yaml.safe_dump(p.get("config") or {}, sort_keys=False, allow_unicode=True),
        }
        for p in payload
    ]
    log.info("Synchronisiere %d Dashboards ...", len(serialised))
    if serialised:
        await cc.push_dashboards(serialised)
    else:
        log.warning(
            "Keine Dashboards gefunden. Falls dein 'Hausdisplay' in HA existiert, pruefe: "
            "1) Token hat Adminrechte, 2) Dashboard ist in HA sichtbar, 3) HA erreichbar via WS."
        )


async def _process_deployment(
    cc: CasaCanvasClient, ha: HomeAssistantClient, job: dict[str, Any], log: logging.Logger
) -> None:
    deployment_id = job["id"]
    url_path = job.get("target_url_path") or job.get("url_path") or "casacanvas"
    yaml_text = job.get("yaml") or ""
    try:
        config = yaml.safe_load(yaml_text) or {}
        if not isinstance(config, dict):
            raise ValueError("Dashboard-YAML muss ein Objekt sein.")
        await ha.save_dashboard_config(url_path, config)
        await cc.ack_deployment(deployment_id, "applied")
        log.info("Deployment %s -> %s angewendet.", deployment_id, url_path)
    except Exception as exc:  # noqa: BLE001
        log.exception("Deployment %s fehlgeschlagen: %s", deployment_id, exc)
        await cc.ack_deployment(deployment_id, "failed", error=str(exc))


async def _heartbeat_loop(cc: CasaCanvasClient, cfg: BridgeConfig, log: logging.Logger) -> None:
    last_display: dict[str, object] | None = None
    ticks = 0
    while True:
        try:
            # alle 5 Ticks (oder beim Start) Display neu prüfen
            if ticks % 5 == 0:
                detected = display_probe.detect()
                if detected:
                    last_display = detected
            await cc.heartbeat(__version__, display=last_display)
        except Exception:  # noqa: BLE001
            log.exception("Heartbeat fehlgeschlagen.")
        ticks += 1
        await asyncio.sleep(cfg.heartbeat_interval)


async def _sync_loop(
    cc: CasaCanvasClient, ha: HomeAssistantClient, cfg: BridgeConfig, log: logging.Logger
) -> None:
    while True:
        await asyncio.sleep(15 * 60)
        try:
            await _sync_once(cc, ha, log)
        except Exception:  # noqa: BLE001
            log.exception("Sync-Zyklus fehlgeschlagen.")


async def _deploy_loop(
    cc: CasaCanvasClient, ha: HomeAssistantClient, cfg: BridgeConfig, log: logging.Logger
) -> None:
    while True:
        try:
            jobs = await cc.next_deployments()
            if jobs:
                for job in jobs:
                    await _process_deployment(cc, ha, job, log)
                continue
        except Exception:  # noqa: BLE001
            log.exception("Deployment-Polling fehlgeschlagen.")
        await asyncio.sleep(cfg.poll_interval)


async def _run() -> None:
    cfg = BridgeConfig.load()
    _setup_logging(cfg.log_level)
    log = logging.getLogger("bridge")
    log.info("CasaCanvas Bridge %s startet.", __version__)

    async with httpx.AsyncClient() as http:
        if cfg.ha_url and cfg.ha_token:
            log.info("Standalone-Modus: verbinde direkt mit %s", cfg.ha_url)
            ha = HomeAssistantClient(cfg.ha_token, http, base_url=cfg.ha_url)
        else:
            ha = HomeAssistantClient(cfg.supervisor_token, http)
        cc = CasaCanvasClient(cfg.base_url, http)
        cc = await _ensure_paired(cc, cfg, log)

        try:
            await _sync_once(cc, ha, log)
        except Exception:  # noqa: BLE001
            log.exception("Initialer Sync fehlgeschlagen - versuche spaeter erneut.")

        await asyncio.gather(
            _heartbeat_loop(cc, cfg, log),
            _sync_loop(cc, ha, cfg, log),
            _deploy_loop(cc, ha, cfg, log),
        )


def main() -> None:
    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
