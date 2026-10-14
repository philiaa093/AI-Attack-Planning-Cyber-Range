# TASK-020 — Planner interface

## Status

`IMPLEMENTED` cho ABC/DTO và adapter đọc snapshot ngoại tuyến, cập nhật ngày 2026-10-12 theo yêu cầu người dùng. Chưa `VALIDATED`; repository gate và independent review còn chờ, runtime integration `UNRESOLVED`.

## Purpose

Cung cấp giao diện Python chung để thay thế RULE, LLM, RL và HYBRID trên cùng state/proposal contracts. Planner output giữ vai trò đề xuất tới khi safety gate và approval chấp thuận.

## Background

ADR-005/006 giữ separation và shared interface. Task 19 cung cấp state snapshot theo run/session/episode; StateManager là budget owner duy nhất. Mode labels trong focused tests thuộc synthetic fixtures, không chứng minh backend/model thực tế đã chạy.

## Scope

[Planner ABC/DTO](../../runtime/planners/planner_interface.py), [thiết kế/receipts](../implementation/planner_interface.md) và [focused tests](../../tests/runtime/test_planner_interface.py). Bao gồm immutable canonical snapshot/proposal, read-only store adapter, identity/revision/scope checks và explicit fallback provenance.

## Out of Scope

Không triển khai strategy thực tế, provider call, RL training, runner/executor integration, runtime dispatch hoặc evidence recorder. Không đổi contracts/catalog/configuration/action semantics, thêm public targets, credentials, arbitrary shell, dynamic actions, exploit payloads hoặc claim runtime success. TASK-026/032 giữ `DEFERRED`.

## Inputs

Canonical state đã chuẩn hóa/redact từ Task 19, StoreContext, candidate action/target sets do caller thu hẹp và fallback_allowed mặc định false. Replan nhận snapshot hiện tại, previous decision và feedback gắn với context/revision/action trước. Không truyền writable store, ground truth hoặc target source vào strategy.

## Outputs

PlanningDecision chứa đúng một PlanProposal hoặc stop reason, kèm context, input revision, requested/actual mode và fallback reason. PlanProposal.to_dict() giữ canonical plan schema; output không cấp quyền execution hoặc suy objective/vulnerability chỉ từ nhãn phase.

## Interfaces

StateSnapshot.from_state/from_store, StateReader.get_state, Planner.plan/replan, PlanningInput, PlanningDecision, PlanProposal và Feedback. Subclass implement mode và abstract hook _plan; _replan mặc định gọi _plan, backend cần lịch sử có thể override. Entry points plan/replan không được override để bỏ shared checks. ABC không phải sandbox cho code Python không tin cậy.

## Data Contracts

Giữ nguyên [state schema](../../agent/planner/contracts/state.schema.json) và [plan schema](../../agent/planner/contracts/plan.schema.json). Snapshot/proposal giữ JSON canonical immutable, to_dict trả detached copy; revision SHA-256 gồm context key và state, không phải chữ ký. Provenance/context nằm ngoài plan JSON đóng. Feedback dùng SUCCESS/FAILURE/PARTIAL/DENIED/ERROR theo observation vocabulary; identity là nhãn mô phỏng, không session token.

## Dependencies

TASK-004, TASK-005, TASK-019

## Implementation Requirements

1. Dùng chung entry points/DTO, tách strategy hooks và giữ budgets cho mọi backend.
2. Reject malformed schema/types/IDs, unknown fields, duplicate identities/JSON keys, non-finite numbers, detected unredacted secrets và documents quá 1 MiB.
3. Kiểm output context/revision/objective/candidate scope; kiểm feedback context/revision/action trước replan.
4. Mode đổi trong một decision cần fallback reason và explicit permission; coordinator có thể chọn backend khác giữa hai decisions.
5. Budget bằng 0, scope rỗng hoặc TERMINAL dừng trước strategy; không tự suy objective success hoặc trừ ngân sách lần hai.

## Safety Requirements

Candidate sets chỉ là bộ lọc caller cung cấp; dispatcher vẫn phải kiểm canonical catalog, lab mode, target/action allowlists, approval, rate/order/budget, kill switch, refusal, audit và restore. Existing redactor không chứng minh loại bỏ mọi secret/ground truth trong arbitrary fact values. Reference integrity và evidence-before-state cần integration riêng; bảo toàn evidence hiện có.

## Testing Requirements

Receipts triển khai ngày địa phương 2026-10-12: `python -B -m unittest discover -s tests/runtime -p test_planner_interface.py -v` exit 0, 28 tests PASS; Task 19 regression 21 tests và planner contracts 16 tests PASS, từng suite exit 0. AST/example/whitespace checks PASS. Coverage gồm ABC, immutable data, identity/revision isolation, scope/schema, stops, fallback, default/overridden replan và store update không double-charge. Không chạy lại suites khi cập nhật trạng thái; source hashes được đối chiếu với receipts. Repository checker phiên triển khai exit 1, 656 errors và 0 errors trong ba paths Task 20; focused tests không còn deferred.

## Acceptance Criteria

Shared interface/offline checks đã có; IMPLEMENTED chỉ áp dụng ABC/DTO/state-read adapter. Acceptance chưa đóng: repository gate và independent review shared boundary/identity/provenance phải đạt trước VALIDATED. Không chuyển receipts SL-09, validation lịch sử Task 19 hoặc fixture mode labels thành validation/runtime success của Task 20.

## Evidence Required

Build label BUILD-TASK020-INTERFACE-OFFLINE-20261012, source HEAD/hashes, receipt UTC 2026-10-11T20:19:17.7509756Z, exact commands và expected/observed tại [receipts Task 20](../implementation/planner_interface.md). Synthetic RUN-020 fixtures, không live run. Immutable evidence binding, reference integrity, consumer integration và independent approval giữ UNRESOLVED; tài liệu receipts không thay evidence recorder.

## Failure Conditions

Malformed input/output, context/revision/action mismatch, scope violation, silent/unauthorized fallback hoặc evidence-loss risk phải fail closed. Handoff HANDOFF_BLOCKED, blocker REPOSITORY_CHECKER_FAILED; pending: repository blockers trong scope riêng → independent review → approved integration với coordinator/gate/recorder. Không self-approve/finalize hoặc sửa lỗi ngoài allowlist.

## Related Guides

See matching exact guide under docs/guides/.

## Related Runbooks

See applicable exact runbook under docs/runbooks/; no runtime authorization.

## Related ADRs

ADR-005, ADR-006, ADR-009, ADR-011 và ADR-012 giữ separation, shared interface, ground-truth isolation, same budgets và final policy authorization.
