"""Lädt Add-on-Optionen aus /data/options.json."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass

OPTIONS_PATH = "/data/options.json"


@dataclass(frozen=True)
class BridgeConfig:
    pairing_code: str
    base_url: str
    poll_interval: int
    heartbeat_interval: int
    log_level: str
    supervisor_token: str
    ha_url: str
    ha_token: str

    @classmethod
    def load(cls) -> "BridgeConfig":
        try:
            with open(OPTIONS_PATH, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except FileNotFoundError:
            raw = {}
        env = os.environ
        return cls(
            pairing_code=(raw.get("pairing_code") or env.get("PAIRING_CODE") or "").strip(),
            base_url=(raw.get("base_url") or env.get("BASE_URL") or "https://casacanvas.example.com").rstrip("/"),
            poll_interval=int(raw.get("poll_interval") or env.get("POLL_INTERVAL") or 5),
            heartbeat_interval=int(raw.get("heartbeat_interval") or env.get("HEARTBEAT_INTERVAL") or 30),
            log_level=(raw.get("log_level") or env.get("LOG_LEVEL") or "info").lower(),
            supervisor_token=env.get("SUPERVISOR_TOKEN", ""),
            ha_url=(env.get("HA_URL") or "").rstrip("/"),
            ha_token=env.get("HA_TOKEN", ""),
        )
