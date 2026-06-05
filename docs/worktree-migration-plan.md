# Worktree Migration Plan

This note tracks how to move still-useful private worktree changes into the
public repository without importing private runtime history, local state, or
personal research artifacts.

## Principles

- Do not merge private worktree branches directly into `main`.
- Migrate one topic at a time through small patches or pull requests.
- Re-run the repository safety scan before every public push.
- Keep `rules/rules.json`, runtime logs, broker payloads, account state,
  Telegram targets, and personal watchlists out of Git.
- Preserve the public default posture: paper-first, guarded, preview-only,
  local-only dashboard.

## Current Private Worktrees

### Mainline Worktree

Path: `/Users/openclaw/.openclaw/workspace-yuuka/agent-trading`

Observed local changes:

- `system/engine/src/engine/watcher_api.py`
- Local-only/untracked files and temporary directories:
  - `.cache/`
  - `.tmp-newswire/`
  - `.tmp/`
  - `docs/project-pause-handoff-2026-06-01.md`
  - `tmp_newswire_fix.js`

Migration recommendation:

- Review only the `watcher_api.py` diff.
- Do not migrate temp/cache directories.
- Treat the pause handoff as private operational history unless a sanitized
  public version is intentionally written.

### Factor Researcher Worktree

Path: `/Users/openclaw/.openclaw/workspace-yuuka/agent-trading-factor-researcher`

Observed local changes:

- `dashboard/main.py`
- `dashboard/static/strategy.html`
- `docs/tasks/cron/FACTOR_RESEARCH_AFTERHOURS.md`
- `tests/test_factor_researcher_structure.py`
- `tests/test_strategy_overview_api.py`
- `tests/test_strategy_page_structure.py`
- `docs/historical-fact-replay-contract.md`
- `system/engine/src/engine/factors/facts.py`
- `system/engine/tests/test_factor_facts.py`

Migration recommendation:

1. Migrate the historical fact replay contract and factor facts module first.
2. Add focused engine tests for facts before touching dashboard views.
3. Migrate dashboard strategy overview changes only after API tests pass.
4. Keep task/cron docs sanitized and paper-first.
5. Run root tests, engine tests, and the safety scan before pushing.

## Suggested Migration Order

1. `factor-facts-core`
2. `factor-facts-dashboard-api`
3. `strategy-page-facts-ui`
4. `watcher-api-hardening`
5. sanitized factor afterhours docs

Each migration should land as a separate public commit or pull request.
