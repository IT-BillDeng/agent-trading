# Changelog

All notable changes to this project will be documented in this file.

The format is based on Keep a Changelog, and this project currently uses date-based unreleased notes until formal releases begin.

## Unreleased

### Added

- Public-facing README focused on a paper-first, safety-gated multi-agent trading research framework.
- Apache-2.0 license file.
- Security policy, contribution guide, changelog, and disclaimer.
- Root `requirements-dev.txt` for fresh-clone test setup.
- GitHub Actions CI for Python 3.11 root and engine tests.
- Sanitized `rules/rules.example.json` fixture and `rules/README.md`.

### Changed

- Dashboard Python entry point defaults to `127.0.0.1`.
- Docker Compose binds the dashboard host port to `127.0.0.1:8088`.
- Telegram notification dispatch defaults are disabled and preview-only.
- Broker config upload defaults to disabled behind `DASHBOARD_ENABLE_CONFIG_UPLOAD=false`.
- Tests that need canonical rules read the sanitized example rule file.

### Removed

- Tracked engine runtime logs, execution snapshots, and state files from version control.

### Security

- Reinforced defaults for `guarded`, `live_submit=false`, `live_cancel=false`, and shadow-only factor behavior.
- Documented non-commit rules for credentials, account data, Telegram targets, runtime logs, orders, positions, and PnL.
