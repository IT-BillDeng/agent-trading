# Factor System Contract

## Scope

This contract defines the factor-system boundary for the `factor-researcher`
branch. FR-01 adds documentation, registry metadata, and directory skeleton
only. It does not change the hot trading path, rule evaluation, risk behavior,
live gates, watchlists, or submit permissions.

## Hot Path And Cold Path

The intended architecture keeps research and trading separated:

```text
Cold path:
market data/history
  -> factor-researcher
  -> factor validation
  -> proposal
  -> approval
  -> applier
  -> approved registry and rules

Hot path:
market data
  -> approved factor engine
  -> rule engine / signal arbiter
  -> risk manager
  -> execution preview
  -> dashboard
```

Boundary rules:

- `factor-researcher` can research but cannot trade
- Dashboard scheduler remains preview-only
- factor metadata in `factors/registry.json` is behavior-preserving in FR-01
- no factor may bypass existing live gates, broker controls, or approval flow

## Factor ID Naming

`factor_id` must use lowercase snake_case and should be stable across versions.

Recommended patterns:

- `<name>_<lookback>_<timeframe>`
- `<name>_<param1>_<param2>_<timeframe>`

Examples:

- `rsi_14_30m`
- `bollinger_zscore_20_2_30m`
- `volume_ratio_20_30m`
- `premarket_gap_pct`

## Canonical Factor Types

Allowed v1 factor types:

- `technical`
- `session`
- `risk`
- `cost`
- `fundamental`
- `text`
- `context_only`

`context_only` is reserved for non-actionable context aggregates. Extended-hours
features should normally use `type: "session"` together with
`usage: ["context_only", ...]`.

## Canonical Input Data Types

The registry should describe inputs using these families:

- `regular_session_bars`
- `extended_hours_bars`
- `quotes`
- `account`
- `news`

Timeframe-specialized names are allowed when they stay readable and map back to
the same family, for example `regular_session_30m_bars`.

## Output Types

Allowed v1 output values:

- `numeric`
- `boolean`
- `categorical`
- `vector`

## Session Semantics

Allowed `session` values:

- `regular`
- `premarket`
- `afterhours`
- `context_only`

Rules:

- US-session factors must use timezone `America/New_York`
- regular technical indicators must consume completed regular-session bars only
- premarket and afterhours factors are context-only by default
- extended-hours data must not enter an actionable path in FR-01

## Required Metadata

Each factor definition must declare:

- `actionable`: whether the factor is ever allowed to drive an actionable path
- `point_in_time`: whether the value can be reproduced without future data
- `required_bars`: minimum completed bars required before computation
- `lookback`: the backward window used to compute the factor
- `horizon`: the forward evaluation horizon used for research or attribution
- `timezone`: required clock context
- `no_lookahead`: explicit confirmation that future data is not read

In the initial FR-01 registry, all factors are metadata-only and
`actionable=false`. Schema v1 encodes the windows as `lookback_bars` and
`horizon_bars`.

## Point-In-Time And No-Lookahead Rules

All approved factor definitions must be reproducible from data available at the
decision timestamp.

Requirements:

- only completed bars may be used for regular-session technical factors
- no future bar, future quote, future news item, or future account state may be
  referenced
- extended-hours context may inform diagnostics and risk hints, but not BUY/EXIT
  permissions in the default setup

## Governance Flow

Factors enter the trading system only through governance:

1. factor-researcher creates a hypothesis and supporting evidence
2. a proposal captures factor metadata, validation, IC, backtest, correlation,
   and cost notes
3. approval reviews safety and research quality
4. applier updates approved hot configuration
5. cold code changes still require code review and merge

No factor becomes tradable only because it exists in the registry.

## Hot Factor Config Vs Cold Factor Code Change

Hot factor config change:

- changes registry metadata or rule references only
- must use already-shipped implementations
- may be applied through proposal, approval, and applier after validation

Cold factor code change:

- introduces or changes implementation code
- requires tests, code review, and an explicit merge
- cannot be directly applied by `factor-researcher`

## FR-01 Safety Invariants

FR-01 must preserve these defaults:

- `defaults.mode = shadow`
- `defaults.allow_actionable_consumption = false`
- extended-hours factors stay `context_only`
- no BUY/HOLD/EXIT result changes
- no new submit path
- no live gate or scheduler privilege changes
