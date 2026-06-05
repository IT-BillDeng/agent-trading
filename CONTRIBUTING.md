# Contributing

Thanks for considering a contribution to `agent-trading`.

This project is a paper-first, safety-gated trading research framework. Contributions should preserve the default safety posture and keep runtime state out of version control.

## Development Setup

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
cp .env.example .env
cp rules/rules.example.json rules/rules.json
cp data/watchlist.json.example data/watchlist.json
```

## Tests

Run both suites before opening a pull request:

```bash
PYTHONPATH="$PWD:$PWD/system/engine/src" python -m pytest -q tests
PYTHONPATH="$PWD:$PWD/system/engine/src" python -m pytest -q system/engine/tests
```

## Safety Requirements

Pull requests must not:

- Enable live order submission by default.
- Set `execution.live_submit=true` or `execution.live_cancel=true` in committed defaults.
- Change the default dashboard host to a public bind address.
- Enable broker config upload by default.
- Commit credentials, private keys, Telegram targets, account IDs, runtime logs, order history, positions, or PnL.
- Make factor output actionable by default before explicit governance changes.

Pull requests that touch execution, broker adapters, risk gates, control state, config upload, or scheduler behavior should include tests that prove the safe default remains intact.

## Code Style

- Prefer small, reviewable changes.
- Keep broker-specific code behind adapter boundaries.
- Keep runtime-generated JSON/JSONL out of Git.
- Use sanitized fixtures and examples for tests.
- Document any new environment variable in README and SECURITY.md when it affects security posture.

## Pull Request Checklist

- Tests pass locally.
- No ignored local runtime files are added.
- No credentials or account data are present in the diff.
- README or docs are updated when behavior changes.
- Default config remains paper-first, guarded, and local-only.
