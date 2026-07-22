"""Erkenne die Auflösung des am Pi angeschlossenen Monitors."""
from __future__ import annotations

import glob
import logging
import os
import re
import shutil
import subprocess
from typing import Optional

log = logging.getLogger("bridge.display")


def _from_fb() -> Optional[tuple[int, int, str]]:
    """Linux-Framebuffer /sys/class/graphics/fb0/virtual_size."""
    try:
        with open("/sys/class/graphics/fb0/virtual_size", "r", encoding="utf-8") as f:
            raw = f.read().strip()
        parts = raw.split(",")
        if len(parts) == 2:
            w, h = int(parts[0]), int(parts[1])
            if w > 0 and h > 0:
                return w, h, "framebuffer"
    except Exception:  # noqa: BLE001
        pass
    return None


def _from_drm() -> Optional[tuple[int, int, str]]:
    """DRM-Modes unter /sys/class/drm/card*-*/modes (erste Zeile = aktueller Modus)."""
    for path in sorted(glob.glob("/sys/class/drm/card*-*/modes")):
        status_path = os.path.join(os.path.dirname(path), "status")
        try:
            with open(status_path, "r", encoding="utf-8") as f:
                if f.read().strip() != "connected":
                    continue
            with open(path, "r", encoding="utf-8") as f:
                first = f.readline().strip()
            m = re.match(r"(\d+)x(\d+)", first)
            if m:
                return int(m.group(1)), int(m.group(2)), "drm"
        except Exception:  # noqa: BLE001
            continue
    return None


def _from_tvservice() -> Optional[tuple[int, int, str]]:
    """Legacy Raspberry Pi: `tvservice -s`."""
    if not shutil.which("tvservice"):
        return None
    try:
        out = subprocess.run(
            ["tvservice", "-s"], capture_output=True, text=True, timeout=3
        ).stdout
        m = re.search(r"(\d+)x(\d+)", out)
        if m:
            return int(m.group(1)), int(m.group(2)), "tvservice"
    except Exception:  # noqa: BLE001
        return None
    return None


def detect() -> Optional[dict[str, object]]:
    """Erste erfolgreiche Quelle gewinnt. Gibt {'width','height','source'} zurück."""
    for probe in (_from_drm, _from_fb, _from_tvservice):
        result = probe()
        if result:
            w, h, src = result
            log.info("Display erkannt: %dx%d via %s", w, h, src)
            return {"width": w, "height": h, "source": src}
    log.debug("Keine Display-Info gefunden.")
    return None