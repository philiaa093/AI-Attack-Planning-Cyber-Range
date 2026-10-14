# TASK-017 — Nuclei adapter

## Status

`IMPLEMENTED` trong phạm vi parser/safety wrapper nhập báo cáo Nuclei ngoại tuyến, theo yêu cầu người dùng. Chưa `VALIDATED`; scanner runtime scaffold giữ `SPEC_ONLY`, thực thi scanner và durable evidence integration còn `UNRESOLVED`. Trạng thái này không cấp runtime approval hoặc đóng acceptance/review.

## Purpose

Deliver nuclei adapter for bounded AI planning in isolated Web Cyber Range.

## Background

Project covers SQL injection, cross-site scripting, and path traversal with RULE, LLM, RL, and HYBRID planners.

## Scope

Parser/wrapper ngoại tuyến: nhập JSON list hoặc JSONL đã có trong bộ nhớ, validate all-or-nothing, allowlist template ID cụ thể mặc định rỗng, target/HTTP origin checks, dữ liệu tối giản và giới hạn quota/rate. `execute` luôn `DENIED`; không scanner, network, process hoặc ghi evidence. Chi tiết implementation/handoff tại [adapter README](../../tools/adapters/nuclei/README.md).

## Out of Scope

Public targets, Internet scanning, credentials, arbitrary shell, dynamic actions, executable exploit payloads, runtime claims, and fabricated results.

## Inputs

Approved source documents, typed contracts, and dependency outputs.

## Outputs

Reviewable nuclei adapter artifact with explicit status and evidence boundary.

## Interfaces

Canonical root docs, typed planner/policy boundaries, and evidence references.

## Data Contracts

Typed IDs, canonical fields, explicit status, and redacted or append-only evidence where applicable.

## Dependencies

TASK-004, TASK-006, TASK-011
## Implementation Requirements

Produce allowlisted templates; preserve source hierarchy and status vocabulary.

## Safety Requirements

Validate trust-boundary input. Enforce lab target/action allowlists, budget, rate, approval, refusal, and evidence preservation.

## Testing Requirements

Focused checks của phiên triển khai ngày 2026-10-11: 28 Nuclei offline + 27 shared adapter + 17 safety tests PASS (exit 0), AST và scoped diff check PASS. Repository validator exit 1 với 643 lỗi ngoài scope, không có lỗi thuộc năm paths TASK-017 trong lần chạy cuối của phiên đó. Receipts tại [TASKS.md](../../TASKS.md#task-017--parser-và-safety-wrapper-nuclei-ngoại-tuyến). Tương thích report thật và independent review chưa được xác minh; không tái chạy suites khi chỉ sửa trạng thái.

## Acceptance Criteria

Allowlisted templates exists as topic-specific reviewable artifact; no VALIDATED claim without required review and evidence.

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
