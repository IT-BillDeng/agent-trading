# Agent Trading Data Directory

This directory contains local user state and runtime data files for the Agent Trading system.

## Files

- `watchlist.json` - Local user watchlist state for yuuka and Tiger subagents
- `watchlist.json.example` - Tracked seed example for the watchlist
- `closer_outbox.json` - Runtime outbox for closer agent

## Notes

- `watchlist.json` is intentionally local state and should not be committed
- If `watchlist.json` is missing, the dashboard will seed it from `watchlist.json.example`
- Keep the local watchlist in sync with `app_config.paper.json` symbols list
- `closer_outbox.json` is runtime output and should not be committed
