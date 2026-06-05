# agent-trading

Paper-first, safety-gated multi-agent trading research framework.

`agent-trading` is an experimental research workspace for building auditable trading research loops with a rule/factor engine, backtesting tools, broker adapter boundaries, a local FastAPI dashboard, and file-based multi-agent orchestration.

**Development status:** this project is still under active development and is not recommended for production use.

It is designed to keep live trading disabled by default. The default posture is paper-first, guarded, preview-only, and local-only.

## What It Is

`agent-trading` provides a Python research framework for:

- Evaluating rule-based and factor-based market signals.
- Running backtests and parameter experiments.
- Producing JSONL audit logs for research workflows.
- Coordinating multi-agent tasks such as news scanning, strategy review, watcher checks, and close summaries.
- Testing broker adapter boundaries without enabling live order submission by default.
- Inspecting local state through a dashboard that should stay on the local machine.

The project is intentionally not packaged as a one-click live trading system.

## Why It Exists

Trading research projects often become difficult to audit because strategy code, agent reasoning, broker state, and runtime logs get mixed together. This repository keeps those concerns separated:

- Engine code handles mechanical evaluation.
- Agents produce review artifacts and proposals.
- Risk gates and control state decide whether anything can proceed.
- Runtime files stay local and out of Git.
- Tests lock down safety defaults.

The result is a research framework that can be inspected, reproduced, and hardened before any user considers connecting real broker credentials.

## Core Features

- Rule and factor engine for signal research.
- Backtesting APIs and batch experiment support.
- Broker adapter abstraction with Tiger-specific adapter code isolated behind config boundaries.
- Risk gates for exposure, trade limits, cooldowns, reduce-only state, and emergency controls.
- Guarded execution preview path with `live_submit=false` and `live_cancel=false` by default.
- JSONL audit logs for cycles, strategy decisions, risk checks, notifications, and execution previews.
- Local FastAPI dashboard for account-like summaries, rules, backtests, logs, and control state.
- Multi-agent orchestration files for watcher, newswire, strategist, executor, scout, closer, applier, and factor researcher roles.
- Sanitized example rules and watchlists for fresh-clone testing.

## Safety Model

The repository defaults are intentionally conservative:

- `execution.submit_mode` defaults to `guarded`.
- `execution.live_submit` defaults to `false`.
- `execution.live_cancel` defaults to `false`.
- `factor_engine.mode` defaults to `shadow`.
- `factor_engine.allow_actionable_consumption` defaults to `false`.
- Dashboard scheduler behavior remains preview-only.
- Telegram dispatch is disabled by default.
- Broker config upload is disabled by default with `DASHBOARD_ENABLE_CONFIG_UPLOAD=false`.
- Runtime logs, local rules, broker credentials, account state, order history, positions, and PnL are ignored by Git.

Live trading is not enabled by default and requires explicit local configuration outside the repository. Even then, users must review the code, broker adapter behavior, risk gates, and local regulations before doing anything with real funds.

## Architecture

```text
config/ + rules.example.json + data/watchlist.example.json
        |
        v
system/engine/src/engine
  rule engine + factor engine + backtest + risk + control + broker adapters
        |
        v
dashboard/
  local FastAPI app + scheduler preview + APIs + static UI
        |
        v
logs/ + runtime/ + artifacts/
  local JSON/JSONL state, audit files, and agent outputs
        |
        v
agents/ + cron/ + docs/tasks/
  multi-agent orchestration contracts and task files
```

Important directories:

- `system/engine/src/engine/`: core Python engine.
- `dashboard/`: FastAPI dashboard and static UI.
- `rules/rules.example.json`: sanitized test and quick-start rule set.
- `config/`: default and Docker overlay configuration.
- `agents/`, `cron/`, `docs/tasks/`: multi-agent orchestration definitions.
- `tests/` and `system/engine/tests/`: root integration and engine tests.
- `logs/`, `runtime/`, `artifacts/`: local runtime outputs; do not commit real outputs.

## Quick Start

Create a virtual environment with Python 3.11:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
```

Prepare local-only runtime files:

```bash
cp .env.example .env
mkdir -p rules
cp rules/rules.example.json rules/rules.json
cp data/watchlist.json.example data/watchlist.json
```

Run the tests:

```bash
PYTHONPATH="$PWD:$PWD/system/engine/src" python -m pytest -q tests
PYTHONPATH="$PWD:$PWD/system/engine/src" python -m pytest -q system/engine/tests
```

Run the local dashboard:

```bash
DASHBOARD_HOST=127.0.0.1 DASHBOARD_PORT=8088 python -m dashboard.main
```

Open `http://127.0.0.1:8088`.

Docker Compose binds the dashboard to host loopback by default:

```bash
docker compose up --build dashboard
```

## Configuration

Configuration is layered as:

```text
config/app.defaults.json
  <- config/app_config.docker.json
  <- config/user.settings.json
  <- environment variables and local secret files
```

Committed files contain only defaults and examples. Local files such as `.env`, `config/user.settings.json`, `rules/rules.json`, `data/watchlist.json`, `properties/*.properties`, `runtime/`, and real logs are ignored.

To enable broker-specific local development, keep broker credentials in local ignored files such as `properties/tiger_openapi_config.properties`. Never commit broker credentials, private keys, account IDs, Telegram targets, runtime logs, order history, positions, or PnL.

Broker config upload is off by default. To use it in a trusted local environment only:

```bash
DASHBOARD_ENABLE_CONFIG_UPLOAD=true python -m dashboard.main
```

Do not enable broker config upload on a dashboard exposed beyond your local machine.

## Testing

The CI workflow runs:

```bash
python -m pytest -q tests
python -m pytest -q system/engine/tests
```

`rules/rules.example.json` is used as the sanitized fixture for tests that need a canonical rule set. Local `rules/rules.json` is intentionally ignored so personal research settings do not leak into commits.

## Security And Local-Only Dashboard Notes

The dashboard is a local operations UI, not an internet-facing service. Defaults bind to `127.0.0.1`; Docker Compose binds the host port to `127.0.0.1:8088`.

Never expose the dashboard directly to the public internet. It can display broker-derived account information when local credentials are configured, and the optional broker config upload path writes sensitive local files when explicitly enabled.

See [SECURITY.md](SECURITY.md) for reporting instructions and non-commit rules.

## Limitations

- This is research software, not a production trading platform.
- The project is still under active development and is not recommended for production use.
- Broker adapters are not a guarantee of broker compatibility or regulatory compliance.
- Backtest results can be misleading because of data quality, fees, liquidity, slippage, survivorship bias, and overfitting.
- Multi-agent workflows are file/artifact based and can have scheduling delays.
- Live trading is intentionally not available through default configuration.
- Users are responsible for reviewing every local configuration change.

## Non-Financial-Advice Disclaimer

This project is for software research and education. It is not financial, investment, legal, tax, or trading advice. Nothing in this repository is a recommendation to buy, sell, hold, or trade any security or financial instrument. You are solely responsible for your own decisions, compliance obligations, credentials, infrastructure, and risk.
