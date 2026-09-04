# AI Agent Fundamentals

## Learning Objectives

Separate agent proposal, policy, execution, and evidence roles.

## Why This Matters

Authority separation limits model error and preserves audit.

## Core Concepts

State, observation, action proposal, policy, executor, evidence.

## Terminology

Planner interface is shared; policy remains final boundary.

## Mathematical / Technical Foundations

No autonomous attack runtime.

## Project Mapping

Maps to TASK-019, TASK-020, and ADR-005/006.

## Security Boundaries

Generated or learned output is untrusted input.

## Common Mistakes

Passing model text directly to tools.

## Self-check Questions

Which component owns final approval?

## Related Artifacts

../../PROJECT_CONTEXT.md; ../task-specs/TASK-020-planner-interface.md; ../adr/ADR-005-planner-executor-perception-separation.md

## Read Next

[07 Planning And Replanning](07-planning-and-replanning.md)

## References

Primary source register: `../references.md`. No network fetch performed.

## Status

`IMPLEMENTED` guide artifact; validation review pending.
