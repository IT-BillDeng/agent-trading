# Tiger Trading Dashboard

Web-based dashboard for monitoring the Tiger trading system.

## Quick Start

```bash
cd tiger-trading/dashboard
pip install -r requirements.txt
python main.py
```

Access at: http://0.0.0.0:8088

## Architecture

```
dashboard/
├── main.py              # FastAPI entry point
├── tiger_client.py      # Tiger API wrapper
├── data_cache.py        # Polling cache layer
├── requirements.txt     # Python dependencies
├── static/
│   └── index.html       # Single-page dashboard
└── config/              # Symlink to ../config
```

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| GET /api/account | Account info (assets, buying power) |
| GET /api/positions | Current positions |
| GET /api/quotes | Real-time quotes for watchlist |
| GET /api/orders | Today's orders |
| GET /api/pnl | P&L data |
| GET /api/watchlist | Shared watchlist |
| GET /api/agents | Subagent status |
| GET /api/system | System runtime status |
| GET /api/tiger-config | Tiger API config (sensitive fields masked) |
| POST /api/tiger-config/upload | Upload new tiger_openapi_config.properties |
| POST /api/config/mode | Set paper/live mode manually |
