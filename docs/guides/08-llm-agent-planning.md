# LLM Agent Planning

## Learning Objectives

Use LLM as schema-bound proposal generator.

## Why This Matters

LLM output is untrusted and needs parsing, validation, and refusal.

## Core Concepts

Structured action IDs, canonical parameters, model identity, refusal.

## Terminology

Schema validation precedes policy approval.

## Mathematical / Technical Foundations

No provider, model version, prompt secret, or result claim.

## Project Mapping

Maps to TASK-022 and ADR-007-equivalent shared decisions.

## Security Boundaries

No direct tool execution from generated text.

## Common Mistakes

Accepting free-form command or fabricated observation.

## Self-check Questions

What makes output valid?

## Related Artifacts

../task-specs/TASK-022-llm-planner.md; ../safety-model.md; ../../AGENTS.md

## Read Next

[09 Reinforcement Learning](09-reinforcement-learning.md)

## References

Primary source register: `../references.md`. No network fetch performed.

## Status

`IMPLEMENTED` guide artifact; validation review pending.
