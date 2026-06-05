# Historical Fact Replay Contract

Historical facts are cold-path research and debugging records. A fact is not an actionable factor, and a replay scenario is not a trading signal.

## Fact Usage

Every historical fact must carry:

- `fact_id`
- `fact_type`
- `symbol` when the source event is symbol-specific
- `event_time`
- `available_at`
- `source`
- `usage`: one of `debug_only`, `research_context`, `label`, `factor_candidate`
- `leakage_policy`

By default, facts are usable only for debug or research. They must not enter `RiskManager`, execution, `execution_preview`, or `order_intents`.

## Point-In-Time Rules

Only facts with `usage=factor_candidate` can ever be considered for factor-like research promotion, and only if `available_at <= decision_time`.

`factor_candidate` facts must set `leakage_policy.usable_before_available_at=false`. Missing `available_at` is invalid unless the fact is `debug_only` and includes an explicit missing-availability reason.

Future outcomes and forward returns are labels. They must use `usage=label`; they must not be consumed as factor inputs, risk inputs, execution inputs, or actionable BUY evidence.

## Replay Boundaries

Replay scenarios are debug-only bundles of related historical facts. They may explain why a dual-run, label join, data-health check, or approval integrity check failed, but they do not modify the system.

Backfilled facts must be labeled as backfill or historical context. They must not impersonate live shadow evidence, live paper evidence, or production trading evidence.

Historical fact collection may read existing research artifacts and logs, but it must not write `rules/rules.json`, `factors/registry.json`, `.env`, `properties/*`, `runtime/*`, `logs/latest/*`, or broker artifacts.
