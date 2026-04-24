---
name: typer-cli
description: Typer-first CLI implementation standards for Nave trading copilot, including terminal UX patterns, Rich tables, JSON contracts for Hermes/Telegram agents, and VPS-safe command design.
---

# Typer CLI Skill

Use this skill when implementing or modifying CLI commands in Nave.

## Context

Nave is a trading copilot used in:
- terminal workflows (human operators)
- Telegram/Hermes agent chat workflows (machine consumers)

Runtime target is often a VPS, so commands must be robust, script-friendly, and predictable.

## Core rules

1. Typer-first command design
- Use Typer command groups and typed options.
- Provide concise help text for every parameter.
- Validate early and fail with clear BadParameter messages.

2. Dual output model
- Human-readable terminal output for operators.
- JSON output for automation and agents.
- Keep JSON payloads stable and free from decorative text.

3. Terminal UX quality
- Use clean sectioning and aligned columns.
- Prefer Rich tables for report-like views.
- Keep status/progress output concise and consistent.

4. Agent integration contract
- Hermes and other agents should receive JSON payloads.
- Include metadata fields useful for downstream formatting:
  - generated_at
  - criteria
  - source
  - summary
- Avoid ambiguous key names and mixed scalar types.

5. VPS-safe behavior
- Deterministic exit codes.
- Low-noise logs.
- Explicit retry/backoff on network and rate-limit failures.
- No interactive prompts in command paths intended for automation.

## Recommended command pattern

For report commands:
- --json: machine contract output
- --sheet: Rich table output for humans
- default: concise human output (or sheet if command is report-heavy)

## Typer references

- Docs: https://typer.tiangolo.com
- Commands: https://typer.tiangolo.com/tutorial/commands/
- Arguments: https://typer.tiangolo.com/tutorial/arguments/
- Options: https://typer.tiangolo.com/tutorial/options/

## Minimal checklist before merge

- Command has clear help and typed options.
- JSON mode is valid JSON and parseable.
- Human mode is readable in narrow terminal widths.
- Errors are actionable and non-verbose.
- README examples reflect actual command usage.
- Tests cover output schema changes.
