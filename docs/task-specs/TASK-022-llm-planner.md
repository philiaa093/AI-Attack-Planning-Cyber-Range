# TASK-022 — LLM planner

## Status

`IMPLEMENTED` cho phần xem xét metadata bằng chứng ngoại tuyến, cập nhật ngày 2026-10-12 theo yêu cầu người dùng. Chưa `VALIDATED`; repository gate và independent review chưa đạt, provider/runtime integration `UNRESOLVED`.

## Purpose

Cung cấp LLMPlanner dùng chung giao diện Task 20 để đề xuất xem xét bằng chứng từ snapshot Task 19. Planner output giữ vai trò proposal tới khi safety gate và approval chấp thuận; phạm vi triển khai hiện tại chỉ ngoại tuyến.

## Background

ADR-005/006 giữ separation và shared interface. Phần hiện tại xem xét metadata của candidates đã nhập/chuẩn hóa; không tự chọn hoặc thực hiện kiểm thử khai thác. Provider responses, mode labels và token counters trong tests là synthetic fixtures, không chứng minh model/provider thật đã chạy.

## Scope

[LLMPlanner](../../runtime/planners/llm_planner.py), [thiết kế/receipts](../implementation/llm_planner.md) và [focused tests](../../tests/runtime/test_llm_planner.py). Context có giới hạn và coverage, system prompt, một strict tool schema, JSON/revision validation, feedback-bound replan, completion filtering và explicit fallback provenance. Chỉ đề xuất `ACTION-PLAN-003` hoặc dừng trong ANALYSIS/REPLAN.

## Out of Scope

Không triển khai API transport/SDK, credentials, model/tokenizer thật, scanner/executor/runner integration, active verification hoặc exploit workflow. Không đổi contracts/catalog/configuration/action semantics, thêm public targets, arbitrary shell, dynamic actions, payloads, deployment/runtime success claims hoặc fabricated evidence. TASK-026/032 giữ `DEFERRED`.

## Inputs

PlanningInput với immutable StateSnapshot, StoreContext, candidate action/target sets do caller thu hẹp và fallback_allowed mặc định false. Trusted ReviewProvider injection, token counter và ContextLimits; provider không nhận writable store. Replan nhận previous decision và Feedback gắn context/revision/action trước. Context chỉ chứa metadata/IDs/fingerprint/coverage, không raw fact values, HTML, source target, ground truth hoặc session secrets.

## Outputs

PlanningDecision chứa đúng một canonical PlanProposal hoặc stop reason. Python gắn objective, target, source observation và fixed action từ snapshot; evidence_refs rỗng, confidence=0.0 là usefulness chưa đánh giá. Stop không chứng minh objective complete. ProviderFailure trả static reason code; không copy raw response hoặc exception text. Unavailable/timeout fallback được phép ghi actual mode RULE và fallback_reason ngoài plan JSON.

## Interfaces

Planner.plan/replan giữ shared validation; LLMPlanner chỉ implement mode/_plan/_replan. ReviewProvider.complete nhận immutable request JSON, trả minimized JSON envelope status/output. Adapter cho provider cụ thể chưa triển khai. ContextLimits và trusted counter giới hạn request; llm_review_control_id chỉ tính completion identity, không ghi receipt hoặc approve execution.

## Data Contracts

Giữ [state schema](../../agent/planner/contracts/state.schema.json), [plan schema](../../agent/planner/contracts/plan.schema.json) và DTO Task 20. Provider tool schema là lớp trung gian riêng, có singleton input_revision và candidate_version enum; Python chuyển selection thành canonical plan. Request/context/provenance không thêm field vào plan JSON đóng. Candidate fingerprint gắn context/objective/action/full fact, độc lập budget/unrelated changes; SHA-256 không phải chữ ký. Completion CONTROL kiểm shape/target/source identity; durable evidence/source integrity còn cần integration.

## Dependencies

TASK-020, TASK-003

Task 19 cung cấp snapshot thông qua Task 20; StateManager giữ budget ownership. Dependency IDs trong TASKS.md không đổi.
## Implementation Requirements

1. Dùng shared entry points và immutable snapshots; không ghi state hoặc trừ budget lần hai.
2. Lọc scope và validate candidate/source/target IDs trước provider; chỉ expose offline review tool.
3. Context sort xác định, bỏ nguyên record và cập nhật coverage; counter bao gồm instructions/tools/feedback, dành riêng output space. Mandatory context không vừa thì fail trước provider.
4. Reject duplicate JSON keys, non-finite numbers, unknown fields, malformed/wrong/multiple calls, refusal/incomplete output, stale revision/version và selection ngoài context.
5. DENIED dừng; FAILURE/ERROR không lặp candidate version chưa thay đổi; PARTIAL cần source observation trong feedback; SUCCESS cần completion CONTROL liên kết feedback.
6. Chỉ unavailable/timeout có fallback được cho phép rõ ràng; fallback RULE là local deterministic selection, không gọi Task 21 backend. Không conceal mode/provider errors hoặc suy LLM runtime từ fixture.

## Safety Requirements

Planner chỉ tạo proposal; caller candidate scope và strict schema không cấp quyền. Dispatcher vẫn phải kiểm canonical catalog, lab mode, target/action allowlists, approval, rate/order/budget, kill switch, refusal, audit và restore. Provider injection/counter là trusted Python, không sandbox; transport/timeouts/tokenizer/evidence binding cần scope riêng. Không log raw provider output/secrets, overwrite evidence, self-approve hoặc finalize.

## Testing Requirements

Receipts triển khai ngày 2026-10-12: `python -B -m unittest discover -s tests/runtime -p test_llm_planner.py -v` exit 0, 31 focused tests PASS; Task 20 28 tests, Task 19 21 tests, Task 21 28 tests và planner contracts 16 tests PASS, từng suite exit 0 (124 distinct tests). AST/document/link/whitespace PASS. Coverage gồm bounded context, strict schema, injection data omitted, scope/revision/version checks, malformed output, refusal/incomplete, explicit fallback, no dispatch/mutation và feedback-bound replan/completion. Lần focused ban đầu exit 1 do sai fixture API được giữ trong receipts; không tính các reruns vào tổng. Source hashes đối chiếu khớp khi cập nhật trạng thái; không chạy lại suites trong lần sửa tài liệu này.

Checker triển khai exit 1 với 613 lỗi ngoài scope, 0 lỗi thuộc ba artifacts Task 22. Required checks tài liệu/trạng thái của lần cập nhật này được ghi riêng tại receipts; focused tests không còn deferred, repository gate chưa đạt.

## Acceptance Criteria

Offline artifacts và focused checks đã có; IMPLEMENTED chỉ áp dụng metadata evidence-review subset. Acceptance chưa đóng: repository gate và review độc lập interface/context/selection/replan/provenance còn chờ. Provider/model/tokenizer/transport thật, durable evidence/history/reference integrity và coordinator/gate integration `UNRESOLVED`; không chuyển fixture/fallback hoặc SL-09 evidence thành validation/runtime success Task 22.

## Evidence Required

Build BUILD-TASK022-REVIEW-OFFLINE-20261012, plan PLAN-TASK022-REVIEW-OFFLINE-20261012, base HEAD d9ae6ca0d5bb03ce381d7249665237f272eeddc9; receipt UTC 2026-10-11T20:57:12.3960969Z, synthetic RUN-022-FIXTURE, source SIMULATED_FIXTURE, SHA-256 và expected/observed tại [receipts](../implementation/llm_planner.md). Redaction: synthetic fixtures, không credentials/raw provider errors. Tài liệu receipts không thay immutable evidence recorder hoặc signed approval; provenance thật và reference/evidence binding giữ `UNRESOLVED`.

## Failure Conditions

Malformed input/output, stale revision, scope/objective/feedback mismatch, unauthorized fallback, conflicting evidence hoặc evidence-loss risk phải fail closed. Handoff `HANDOFF_BLOCKED`, blocker `REPOSITORY_CHECKER_FAILED_OUTSIDE_SCOPE`; không sửa ngoài allowlist. Pending: repository blockers trong scope riêng → independent review → approved provider/reference/evidence/coordinator integration. Không self-approve/finalize hoặc append history.

## Related Guides

Xem [LLM agent planning](../guides/08-llm-agent-planning.md) và [planning/replanning](../guides/07-planning-and-replanning.md); executable scope chỉ theo approved task/contract.

## Related Runbooks

[Run LLM planner](../runbooks/run-llm-planner.md) không cấp runtime authorization; phần hiện tại không thêm live/provider command.

## Related ADRs

ADR-005/006/009/011/012 giữ separation, shared interface, ground-truth isolation, same budgets và final policy authorization.
