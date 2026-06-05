# Security Policy

## Supported Scope

This repository is prepared as a paper-first research framework. Security reports should focus on issues in the open-source code, default configuration, dashboard behavior, broker adapter boundaries, dependency chain, and unsafe examples.

## Local-Only Dashboard

The dashboard is intended for local use only.

- Do not expose it directly to the public internet.
- Defaults bind the Python entry point to `127.0.0.1`.
- Docker Compose binds the host port to `127.0.0.1:8088`.
- If you override `DASHBOARD_HOST`, understand that the dashboard may display sensitive local broker-derived state.

## Broker Config Upload

Broker config upload is a local development and local operations feature. It is disabled by default:

```bash
DASHBOARD_ENABLE_CONFIG_UPLOAD=false
```

Only enable it on a trusted local machine:

```bash
DASHBOARD_ENABLE_CONFIG_UPLOAD=true
```

Do not enable upload on a dashboard reachable by untrusted users or networks. Uploaded broker config files can contain private keys, account identifiers, and broker credentials.

## Files That Must Never Be Committed

Never commit:

- `.env`, `.env.local`, `.env.*.local`
- `config/user.settings.json`
- `config/app_config.local.json`
- `config/secrets*`
- `properties/*.properties`
- broker API keys, private keys, account IDs, or secrets
- Telegram bot tokens, chat IDs, user IDs, or delivery targets
- `rules/rules.json` if it contains personal strategy state
- `data/watchlist.json` if it contains personal watchlists
- `runtime/`
- `logs/` runtime JSON/JSONL files
- `artifacts/` runtime outputs that contain broker, account, order, position, or PnL data
- order history, positions, fills, account balances, PnL, or broker response payloads

Use the committed `*.example` files as templates.

## Reporting A Security Issue

Please do not open a public issue containing credentials, tokens, account IDs, broker payloads, or exploit details.

Report security issues privately to the repository owner. If GitHub private vulnerability reporting is enabled for the repository, use that channel. Otherwise, contact the maintainer through the private channel listed on the GitHub profile or organization page.

Include:

- A short description of the issue.
- Affected files or endpoints.
- Reproduction steps using sanitized data.
- Impact assessment.
- Suggested mitigation, if known.

## Before Publishing Or Releasing

Before making a repository public or cutting a release:

1. Run the test suite.
2. Run a secret scan against tracked files.
3. Confirm default config remains paper-first and guarded.
4. Confirm `live_submit=false` and `live_cancel=false`.
5. Confirm dashboard upload is disabled by default.
6. Confirm no runtime logs, broker responses, account IDs, positions, orders, PnL, private keys, tokens, or secrets are tracked.
