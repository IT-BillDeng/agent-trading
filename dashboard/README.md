# Agent Trading Dashboard

Local-only FastAPI dashboard for the paper-first research framework.

The dashboard is an operations and inspection UI. It is not intended to be exposed to the public internet.

## Quick Start

From the repository root:

```bash
python -m pip install -r requirements-dev.txt
DASHBOARD_HOST=127.0.0.1 DASHBOARD_PORT=8088 python -m dashboard.main
```

Access it at `http://127.0.0.1:8088`.

## Safety Defaults

- The Python entry point defaults to `127.0.0.1`.
- Docker Compose binds the host port to `127.0.0.1:8088`.
- Broker config upload is disabled unless `DASHBOARD_ENABLE_CONFIG_UPLOAD=true`.
- The scheduler path is preview-only by default.
- Live order submission is not enabled by dashboard defaults.

If you run the dashboard in Docker, the container may listen on `0.0.0.0` internally so Docker port forwarding works, but the Compose host binding remains loopback-only.

## Architecture

```text
dashboard/
  main.py              FastAPI entry point
  api/                 Domain route modules
  services/            Broker, market-data, and runtime service helpers
  normalize/           Broker payload normalization
  static/              Single-page dashboard assets
  requirements.txt     Runtime dependencies
```

## Selected API Endpoints

| Endpoint | Description |
| --- | --- |
| `GET /api/account` | Account-like summary from the active local adapter |
| `GET /api/positions` | Local adapter position view |
| `GET /api/quotes` | Watchlist quotes |
| `GET /api/orders` | Order view from the active local adapter |
| `GET /api/pnl` | PnL view from the active local adapter |
| `GET /api/watchlist` | Shared local watchlist |
| `GET /api/agents` | Agent status summary |
| `GET /api/system` | Runtime status |
| `GET /api/broker-config` | Broker config metadata with sensitive fields masked |
| `POST /api/broker-config/upload` | Disabled by default; local trusted use only |
| `POST /api/config/mode` | Set paper/live mode metadata; does not enable live submission |
