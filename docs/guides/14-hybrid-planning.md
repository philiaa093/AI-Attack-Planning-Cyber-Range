# Hybrid Planning

## Learning Objectives

Combine rule, LLM, and RL candidates under one safety policy.

## Why This Matters

Composition must not create a bypass.

## Core Concepts

Candidate provenance, selection, shared interface, policy gate, refusal.

## Terminology

Final action undergoes same validation regardless of source.

## Mathematical / Technical Foundations

No comparison result exists.

## Project Mapping

Maps to TASK-021, TASK-022, TASK-025, TASK-027.

## Security Boundaries

Safety engine retains final control.

## Common Mistakes

Allowing one candidate to override refusal.

## Self-check Questions

Where does final approval happen?

## Related Artifacts

../task-specs/TASK-027-hybrid-planner.md; ../adr/ADR-006-shared-planner-interface.md; ../adr/ADR-012-safety-engine-control.md

## Read Next

[15 Ground Truth](15-ground-truth.md)

## References

Primary source register: `../references.md`. No network fetch performed.

## Status

`IMPLEMENTED` guide artifact; validation review pending.
