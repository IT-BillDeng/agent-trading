# Factors Directory

`factors/` stores reviewed factor metadata and future factor implementation
assets. In FR-01 this directory is documentation-first and registry-first only.

## Files

- `registry.json`: approved factor metadata contract for shadow-mode factors

## FR-01 Rules

- this directory does not change trading behavior by itself
- no factor in the initial registry is actionable
- extended-hours factors remain context-only
- no live gate, broker submit path, or dashboard scheduler permission is changed

## Relationship To Artifacts

- checked-in metadata belongs here
- generated research outputs do not belong here
- runtime snapshots should live under `artifacts/factors/` or
  `artifacts/factor_research/` and must not be committed as generated `.jsonl`
  or `latest` outputs
