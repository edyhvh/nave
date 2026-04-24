---
applyTo: "cli/**/*.py, hermes/**/*.py, trading/**/*.py, README.md, docs/**/*.md"
description: Terminal-first CLI standards for Nave trading copilot (Typer + Rich + JSON contracts for agents)
---

# Nave CLI and Agent Standards

Nave is a trading copilot designed for two primary interaction surfaces:
- terminal operators (human users)
- agent chat surfaces (Telegram and Hermes-compatible tools)

Deployments are expected to run on a VPS, so reliability, scriptability, and concise output contracts are mandatory.

## Product priorities

1. CLI UX/UI quality is a top-level feature, not a nice-to-have.
2. Human terminal output should be clear, fast to scan, and visually consistent.
3. Agent integrations must prefer strict JSON contracts.
4. Keep behavior stable and backward compatible unless explicitly requested.

## Typer-first CLI policy

- Use Typer for CLI command groups and options.
- Keep command names predictable and composable.
- Prefer explicit options over hidden behavior.
- Add useful help text for every option and command.
- Use typed signatures and validation (bad input should fail fast with actionable messages).

Reference: https://typer.tiangolo.com

## Output contract policy

- Human mode: readable terminal output (tables, summaries, status lines).
- Machine mode: JSON-only output for automation and agents.
- Never mix prose/log noise into JSON payload stdout.
- Operational/status logs should go to stderr when possible.

Recommended pattern for report commands:
- --json: emit machine-stable JSON payload.
- --sheet or default human mode: render terminal table output (Rich is preferred when available).

## Agent-facing policy (Hermes/Telegram/other agents)

- If the consumer is an agent, return structured JSON.
- Keep payloads stable and explicit (versionable keys, predictable types).
- Include enough metadata for downstream formatting (timestamps, criteria, source, summary counts).
- Agent layers should decide presentation style; CLI should provide clean data contracts.

## VPS and operations policy

- Optimize for non-interactive and cron-safe execution.
- Ensure commands have deterministic exit codes.
- Keep startup logs concise; avoid noisy banners.
- Handle rate limits and network errors with clear retry/backoff behavior.
- Fail gracefully with actionable error messages.

## Trading copilot safety policy

- Default to safe execution paths (dry-run where applicable).
- Distinguish clearly between analysis output and execution intent.
- Surface risk-relevant context (limits, filters, missing data, stale data windows).
- Do not imply broker execution success without explicit confirmation from broker responses.

## Implementation quality guidelines

- Keep command output consistent across modules (stocks, cot, hermes, core).
- Prefer small, reusable rendering helpers over ad-hoc print formatting.
- Preserve API and CLI compatibility where practical.
- Add or update tests when changing output schema or command behavior.
- Update README examples whenever command behavior/options change.
