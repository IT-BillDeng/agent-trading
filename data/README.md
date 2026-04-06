# Tiger Trading Data Directory

This directory contains runtime data files for the Tiger Trading system.

## Files

- `watchlist.json` - Shared watchlist for yuuka and Tiger subagents (single source of truth)
- `watchlist.json.example` - Example watchlist file
- `closer_outbox.json` - Outbox for tiger-closer agent

## Notes

- `watchlist.json` is the single source of truth for all Tiger subagents
- Keep this file in sync with `app_config.paper.json` symbols list
- Updated by dashboard and yuuka agent
