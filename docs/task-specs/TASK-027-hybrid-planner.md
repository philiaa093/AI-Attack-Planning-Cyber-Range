# TASK-027 — Hybrid planner

## Status

`IMPLEMENTED` cho thiết kế và router tham chiếu metadata review ngoại tuyến,
cập nhật ngày 2026-10-12 theo yêu cầu người dùng; chưa `VALIDATED`.
Full hybrid runtime vẫn `SPEC_ONLY`; adapter/provider/coordinator/evidence
integration và independent review còn `UNRESOLVED`.

## Purpose

Deliver hybrid planner for bounded AI planning in isolated Web Cyber Range.

## Background

Project covers SQL injection, cross-site scripting, and path traversal with RULE, LLM, RL, and HYBRID planners.

## Scope

[Router tham chiếu](../../runtime/planners/hybrid_router.py) và
[thiết kế/receipts](../implementation/hybrid_router.md) cho rule-first routing,
metadata handoff khi no match/review thất bại, feedback/revision binding,
candidate-version exclusion và bounded stop conditions. Chỉ hỗ trợ action
`ACTION-PLAN-003` của phần offline Task 21/22; router trả dữ liệu điều hướng.

## Out of Scope

Public targets, Internet scanning, credentials, arbitrary shell, dynamic actions,
executable exploit payloads, runtime claims, and fabricated results. Không có
backend/provider/executor calls, LLM handoff adapter hoặc full hybrid/RL arbitration
trong implementation hiện tại.

## Inputs

Approved source documents, PlanningInput/StateSnapshot, original Task 21/22
PlanningDecision, Feedback và RoutingHistory theo run/session/episode. Candidate
scopes và history là input filters, không phải authorization.

## Outputs

RoutingResult chứa operation/backend/reason/revision và optional metadata handoff
JSON; không phải quyền thực thi. Source/tests/receipts có links kiểm được, explicit
implementation subset, blockers và pending handoff.

## Interfaces

[Task 20 DTO](../../runtime/planners/planner_interface.py) và immutable Task 19 snapshots.
`HybridReviewRouter.route()` chỉ chọn route; entry points/backend contracts hiện
hành không đổi. Task 22 không nhận RULE decision qua replan trực tiếp: API handoff
adapter riêng còn `UNRESOLVED`, không đổi mode/plan ID để bypass check.

## Data Contracts

Typed IDs, canonical schemas không đổi. Input revision gắn snapshot;
candidate fingerprint cùng thuật toán Task 21/22, độc lập budget/fact ordering.
Handoff bỏ raw fact values, giữ metadata/coverage và feedback IDs. History cần
coordinator kiểm nguồn/completion và lưu bền vững trong integration tiếp theo.

## Dependencies

TASK-021, TASK-022, TASK-025
## Implementation Requirements

Rule-first; no match hoặc FAILURE/ERROR/PARTIAL có feedback binding chuyển thành
LLM handoff/replan data. DENIED dừng; failed/excluded version không được lặp.
Giới hạn delegation/no progress, exhausted budget và revoked scope fail closed.
SUCCESS quay lại original backend để kiểm completion receipt; không tự xác nhận
thành công. Không sửa store/budget hoặc gọi transport.

## Safety Requirements

Validate trust-boundary input. Enforce lab target/action allowlists, budget, rate, approval, refusal, and evidence preservation.

## Testing Requirements

[20 focused router tests](../../tests/runtime/test_hybrid_router.py) và 87 Task 20–22
regression tests PASS trong phiên triển khai; AST/link/whitespace PASS.
Đồng bộ tài liệu đối chiếu source hashes, task statuses/dependencies và links,
không chạy lại 107 tests. Main checker chạy được nhưng exit 1 với 27 lỗi ngoài
scope; receipts đồng bộ mới được ghi riêng tại runtime/hybrid_router.md.

## Acceptance Criteria

Reviewable offline routing reference và bounded metadata handoff tồn tại với
focused checks/receipts. `IMPLEMENTED` chỉ bao phủ subset này; không xác nhận
full hybrid backend, independent approval hoặc runtime. Không `VALIDATED` khi
chưa có required review, integration checks và evidence.

## Evidence Required

[Source hashes, UTC, synthetic run identity, exact commands, expected/observed và
handoff](../implementation/hybrid_router.md#checks-và-bàn-giao). Hai source hashes khớp
receipts khi đồng bộ tài liệu. Durable audit/reference integrity/immutable run
evidence còn `UNRESOLVED`; không tạo hoặc overwrite evidence bằng cập nhật này.

## Failure Conditions

Missing dependency, malformed contract, unsupported claim, scope mismatch, broken
link, or data-loss risk blocks completion. Handoff hiện `HANDOFF_BLOCKED` do
repository errors ngoài scope; adapter/completion/history integrity, provider/
tokenizer thật, Task 25 arbitration và independent review chưa kiểm chứng.

## Related Guides

[Hybrid planning](../guides/14-hybrid-planning.md).

## Related Runbooks

[Run hybrid planner](../runbooks/run-hybrid-planner.md); không cấp runtime authorization.

## Related ADRs

[ADR-005](../adr/ADR-005-planner-executor-perception-separation.md),
[ADR-006](../adr/ADR-006-shared-planner-interface.md),
[ADR-011](../adr/ADR-011-same-budgets-across-planners.md),
[ADR-012](../adr/ADR-012-safety-engine-control.md) và
[ADR-013](../adr/ADR-013-runtime-vertical-slice.md).
