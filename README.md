# CasaCanvas AI Bridge — Home Assistant Add-on

Referenz-Implementierung des Home-Assistant-Add-ons, das Home Assistant mit
CasaCanvas AI verbindet. Die Bridge läuft im lokalen HA-Netzwerk, spricht per
Supervisor-API mit Home Assistant und ausgehend per HTTPS mit CasaCanvas — es
werden keine eingehenden Ports geöffnet.

## Repository-Struktur

```
ha-addon/
  repository.yaml                # Home-Assistant-Add-on-Repository-Manifest
  casacanvas-bridge/
    config.yaml                  # Add-on-Manifest (Version, Optionen, Berechtigungen)
    Dockerfile                   # Container-Definition
    run.sh                       # Entrypoint (startet den Python-Client)
    bridge/
      __init__.py
      main.py                    # Event-Loop
      client.py                  # HTTP-Client für CasaCanvas
      ha.py                      # Supervisor-/Websocket-Client für HA
      config.py                  # Optionen aus /data/options.json
```

## Endpunkte (CasaCanvas → HA-Bridge)

| Aufruf | Endpoint | Zweck |
| --- | --- | --- |
| POST | `/api/public/bridge/pair` | Einmalcode gegen aktives Bearer-Token tauschen |
| POST | `/api/public/bridge/heartbeat` | Alle 30 s: Bridge lebt, Version, Latenz |
| POST | `/api/public/bridge/entities` | Entitäten-Katalog (chunked upsert) |
| POST | `/api/public/bridge/dashboards` | Snapshot aller Lovelace-Dashboards |
| GET  | `/api/public/bridge/deployments/pending` | Nächsten Deploy-Job atomar claimen |
| POST | `/api/public/bridge/deployments/ack` | `applied` / `failed` melden |

Alle Aufrufe mit `Authorization: Bearer <token>`. Basis-URL wird beim Pairing
geliefert (Standard: die eigene stabile Lovable-Domain der CasaCanvas-Instanz).

## Installation (End-User)

1. In Home Assistant → **Einstellungen → Add-ons → Add-on-Store**.
2. Menü (⋮) → **Repositories** → URL dieses Repos hinzufügen.
3. „CasaCanvas AI Bridge" installieren, starten.
4. Kopplungscode aus CasaCanvas („Haus → Bridge koppeln") in die Add-on-Konfiguration eintragen.
5. Add-on neu starten — die Bridge tauscht den Code gegen ein Token und beginnt zu synchronisieren.

> Hinweis: Dies ist eine Referenz-Struktur. Für den Produktivbetrieb muss der
> Container gebaut und in der jeweiligen Architektur (aarch64, amd64, armv7,
> armhf, i386) publiziert werden.