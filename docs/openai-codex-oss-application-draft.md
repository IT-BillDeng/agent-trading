# OpenAI Codex for Open Source Application Draft

## Project

agent-trading

## One-Line Description

Paper-first multi-agent trading research framework with risk gates,
backtesting, broker adapters, and auditable JSONL workflows.

## Summary

agent-trading is a paper-first, safety-gated multi-agent trading research
framework. It is designed for experimenting with rule and factor research,
backtesting, broker adapter abstractions, JSONL audit trails, and local
operator dashboards while keeping live order submission disabled by default.

The project is still under active development and is not recommended for
production use.

## Why It Fits Codex

- The system is modular and benefits from careful code navigation across
  dashboard, engine, tests, docs, and agent task files.
- Safety constraints matter: Codex can help preserve paper-first defaults,
  review risk gates, and prevent accidental credential or runtime-state
  commits.
- The project has a useful test surface for iterative agent work, including
  root dashboard tests and engine-specific tests.
- Future contributions can be split into well-scoped tasks: broker adapter
  contracts, factor research tooling, backtest metrics, dashboard views,
  safety checks, and documentation hardening.

## Current Capabilities

- Paper-first execution posture.
- Guarded live-gate architecture with `live_submit=false` and
  `live_cancel=false` by default.
- Rule/factor/backtest engine.
- Broker adapter abstraction.
- Local-only FastAPI dashboard.
- JSONL audit-log workflow.
- Multi-agent orchestration docs and task templates.
- CI for root tests and engine tests on Python 3.11.

## Safety Model

- Credentials are never committed.
- Runtime logs, local rules, account state, order history, positions, PnL, and
  broker payloads are ignored by Git.
- Dashboard defaults to `127.0.0.1`.
- Broker config upload is disabled unless explicitly enabled locally.
- Live order submission requires explicit local configuration and must pass
  risk gates.

## Maintenance Plan

- Keep default configuration paper-first and guarded.
- Require tests and safety scans before public pushes.
- Migrate private worktree changes only through sanitized patches.
- Expand adapter tests and factor research tests before adding broader
  dashboard features.
- Keep README, SECURITY, DISCLAIMER, and CONTRIBUTING aligned with the safety
  posture.

## Non-Financial-Advice Statement

This project is for research and engineering experimentation only. It is not
financial advice, investment advice, trading advice, legal advice, or tax
advice.

## Suggested GitHub Metadata

Description:

Paper-first multi-agent trading research framework with risk gates,
backtesting, broker adapters, and auditable JSONL workflows.

Topics:

paper-trading, multi-agent-systems, trading-bot, risk-management, backtesting,
fastapi, broker-adapter, open-source, codex
