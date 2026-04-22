# Factor Registry Schema v1

## Goal

`factors/registry.json` is the canonical metadata file for approved factor
definitions. Schema v1 is intentionally narrow and behavior-preserving:

- the registry is metadata, not execution code
- the default operating mode is `shadow`
- actionable consumption is disabled by default
- extended-hours factors are context-only by default

## Top-Level Shape

```json
{
  "schema_version": 1,
  "defaults": {
    "mode": "shadow",
    "allow_actionable_consumption": false,
    "regular_session_only_for_indicators": true,
    "default_timezone": "America/New_York"
  },
  "factors": {
    "<factor_id>": {
      "...": "factor definition"
    }
  }
}
```

## Top-Level Fields

| Field | Type | Required | Rules |
| --- | --- | --- | --- |
| `schema_version` | integer | yes | must be `1` |
| `defaults.mode` | string | yes | FR-01 default must be `shadow` |
| `defaults.allow_actionable_consumption` | boolean | yes | FR-01 default must be `false` |
| `defaults.regular_session_only_for_indicators` | boolean | yes | `true` means regular technical indicators use completed regular-session bars only |
| `defaults.default_timezone` | string | yes | US-session default must be `America/New_York` |
| `factors` | object | yes | keys are `factor_id` values |

## Factor Definition Fields

Each factor entry is keyed by `factor_id` and must match:

| Field | Type | Required | Rules |
| --- | --- | --- | --- |
| `type` | string | yes | one of `technical`, `session`, `risk`, `cost`, `fundamental`, `text`, `context_only` |
| `implementation` | string | yes | implementation identifier such as `builtin:rsi` |
| `inputs` | array[string] | yes | one or more declared input sources |
| `params` | object | yes | implementation parameters; may be empty |
| `session` | string | yes | one of `regular`, `premarket`, `afterhours`, `context_only` |
| `timeframe` | string | yes | bar granularity or `context_only` |
| `output` | string | yes | one of `numeric`, `boolean`, `categorical`, `vector` |
| `usage` | array[string] | yes | subset of `shadow`, `rule_condition_candidate`, `context_only`, `risk_hint_candidate` |
| `actionable` | boolean | yes | FR-01 initial registry uses `false` for every factor |
| `point_in_time` | boolean | yes | must be reproducible without future data |
| `required_bars` | integer | yes | minimum completed bars required before compute |
| `lookback_bars` | integer | yes | backward window in completed bars |
| `horizon_bars` | integer | yes | forward evaluation horizon for research/attribution metadata |
| `timezone` | string | yes | US-session values must be `America/New_York` |
| `no_lookahead` | boolean | yes | must be `true` for approved factors |
| `version` | integer | yes | positive integer version |

## Validation Rules

### Factor ID

- regex: `^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$`
- must be unique within the registry
- should remain stable across metadata-only revisions

### Inputs

Canonical input families:

- `regular_session_bars`
- `extended_hours_bars`
- `quotes`
- `account`
- `news`

Derived or timeframe-specific aliases are allowed when they remain
unambiguous, such as `regular_session_30m_bars` or
`previous_regular_close`.

### Session And Timezone

- `regular`, `premarket`, and `afterhours` factors for US equities must use
  `timezone = "America/New_York"`
- regular technical factors should consume completed regular-session bars only
- any factor that depends on `extended_hours_bars` is non-actionable by default

### Actionability

- if `defaults.allow_actionable_consumption = false`, an actionable factor is
  invalid for the default FR-01 registry
- if `session` is `premarket` or `afterhours`, `usage` must include
  `context_only`
- extended-hours factors must not introduce an actionable usage

### Point-In-Time

- `point_in_time` must be `true`
- `no_lookahead` must be `true`
- `required_bars`, `lookback_bars`, and `horizon_bars` refer to completed bars
  only

## Initial Usage Semantics

Usage values in v1 are descriptive metadata only:

- `shadow`: the factor may be computed in shadow mode
- `rule_condition_candidate`: the factor is a candidate for future approved rule
  conditions
- `context_only`: the factor may be used only for context or diagnostics
- `risk_hint_candidate`: the factor may provide non-binding future risk hints

No `usage` value in FR-01 grants permission to create or submit live orders.

## Example Entry

```json
{
  "rsi_14_30m": {
    "type": "technical",
    "implementation": "builtin:rsi",
    "inputs": ["regular_session_30m_bars"],
    "params": {"period": 14},
    "session": "regular",
    "timeframe": "30min",
    "output": "numeric",
    "usage": ["shadow", "rule_condition_candidate"],
    "actionable": false,
    "point_in_time": true,
    "required_bars": 14,
    "lookback_bars": 14,
    "horizon_bars": 1,
    "timezone": "America/New_York",
    "no_lookahead": true,
    "version": 1
  }
}
```

## Out Of Scope For v1

Schema v1 does not introduce:

- factor computation code
- rule-engine consumption
- broker submit paths
- live-submit overrides
- scheduler submit permissions
- research artifact uploads in git
