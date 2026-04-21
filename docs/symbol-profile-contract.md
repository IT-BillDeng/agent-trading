# Symbol Profile Contract

## Why Shared Strategy Code Stays Primary

`Symbol Profile / Per-symbol Rule Override v1` keeps `rules/rules.json` base rules as the only shared strategy code path. We do not fork strategy implementations per symbol. Instead, the engine resolves an effective rule per `symbol × rule_id` by layering:

1. base rule
2. profile template overrides
3. symbol-level overrides

This keeps strategist / proposal / hot apply governance on one rule surface and avoids hidden per-symbol strategy drift.

## Config Shape

`rules/rules.json` may include two optional top-level objects:

```json
{
  "symbol_profile_templates": {
    "default_shared_30m": {
      "description": "Behavior-preserving default profile.",
      "enabled_rules": {},
      "rule_overrides": {}
    }
  },
  "symbol_profiles": {
    "AAPL": {
      "profile": "default_shared_30m",
      "enabled_rules": {},
      "rule_overrides": {}
    }
  }
}
```

If a symbol has no explicit `symbol_profiles` entry, the resolver uses `default_shared_30m`.

## Override Whitelist

v1 intentionally keeps the override surface narrow:

- `enabled_rules.{rule_id}`: `true` or `false`
- `rule_overrides.{rule_id}.entry.conditions`
- `rule_overrides.{rule_id}.exit.conditions`
- `rule_overrides.{rule_id}.risk.stop_loss_pct`
- `rule_overrides.{rule_id}.risk.take_profit_pct`
- `rule_overrides.{rule_id}.risk.risk_budget`

Forbidden override targets include:

- `rule_id`
- `name`
- `strategy_id`
- `symbols`
- `broker`
- `execution`
- `live_submit`
- `submit_mode`

Profiles cannot re-enable a base-disabled rule, cannot bypass `rule.symbols`, and cannot raise global risk / execution / live permissions.

## Approval And Hot Apply Boundary

Profile and per-symbol override changes remain governed by the existing strategist proposal flow:

1. strategist proposes changes to `rules/rules.json`
2. schema validation checks profile references, rule references, whitelist keys, and numeric ranges
3. validation / backtest / approval queue runs
4. applier hot applies the rules file only after validation passes

Dashboard pages are read-only for symbol profiles. There is no direct profile edit endpoint and no UI button that writes `rules.json`.

## Attribution Output

Backtest now emits `attribution.symbols` and `attribution.rules` summaries. Entry attribution belongs to the `primary_rule_id` that opened the trade. If attribution cannot be resolved safely, the result includes `attribution.attribution_unknown` instead of inventing ownership.

Signal and runtime metadata also include:

- `base_rule_id`
- `symbol_profile`
- `effective_config_hash`
- `overrides_applied`
- `primary_rule_id`
- `source_rule_ids`
