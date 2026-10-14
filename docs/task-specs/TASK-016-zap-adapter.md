# TASK-016 — ZAP adapter

## Status

`IMPLEMENTED` trong phạm vi parser JSON và safety wrapper ZAP ngoại tuyến; chưa `VALIDATED`, acceptance/handoff còn pending.

Implementation: `tools/parsers/zap_parser.py`, `tools/adapters/zap/adapter.py`. `import_report` trả candidates đã validate/minimize; `execute` luôn `DENIED`, không chạy ZAP. Check ngày 2026-10-11 khi cập nhật trạng thái: `python -B -m unittest discover -s tests/unit -p test_zap_adapter_offline.py -v`, exit 0, 16 tests PASS. Independent review chưa có approval; handoff trước đó `HANDOFF_BLOCKED` bởi repository checker ngoài scope, chưa chạy lại gate trong lần cập nhật này.

Chưa xác minh report từ ZAP thật, live scanner hoặc durable evidence integration. Chi tiết, receipts lịch sử và pending handoff tại [TASKS.md](../../TASKS.md#task-016--parser-và-safety-wrapper-zap-ngoại-tuyến).

## Purpose

Deliver zap adapter for bounded AI planning in isolated Web Cyber Range.

## Background

Project covers SQL injection, cross-site scripting, and path traversal with RULE, LLM, RL, and HYBRID planners.

## Scope

Topic-specific artifact for zap adapter.

## Out of Scope

Public targets, Internet scanning, credentials, arbitrary shell, dynamic actions, executable exploit payloads, runtime claims, and fabricated results.

## Inputs

Approved source documents, typed contracts, and dependency outputs.

## Outputs

Reviewable zap adapter artifact with explicit status and evidence boundary.

## Interfaces

Canonical root docs, typed planner/policy boundaries, and evidence references.

## Data Contracts

Typed IDs, canonical fields, explicit status, and redacted or append-only evidence where applicable.

## Dependencies

TASK-004, TASK-006, TASK-011
## Implementation Requirements

Produce parser/safety wrapper; preserve source hierarchy and status vocabulary.

## Safety Requirements

Validate trust-boundary input. Enforce lab target/action allowlists, budget, rate, approval, refusal, and evidence preservation.

## Testing Requirements

Focused check covers parser/safety wrapper; main validator and unit tests deferred to validator repair.

## Acceptance Criteria

Parser/safety wrapper exists as topic-specific reviewable artifact; no VALIDATED claim without required review and evidence.

## Evidence Required

Source record, check receipt, and immutable evidence or explicit UNRESOLVED marker.

## Failure Conditions

Missing dependency, malformed contract, unsupported claim, scope mismatch, broken link, or data-loss risk blocks completion.

## Related Guides

See matching exact guide under docs/guides/.

## Related Runbooks

See applicable exact runbook under docs/runbooks/; no runtime authorization.

## Related ADRs

See applicable decision under docs/adr/.
