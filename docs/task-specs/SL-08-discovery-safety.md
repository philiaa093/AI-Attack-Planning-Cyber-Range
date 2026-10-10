# SL-08 — Discovery dựa trên quan sát và safety gate

## Status

`SPEC_ONLY`. Crawler/prototype hiện có chưa chứng minh mọi request đi qua policy và approval.

## Purpose

Khám phá bề mặt sản phẩm từ seed và nội dung thực sự quan sát được, đồng thời chặn mọi dispatch vượt scope trước khi có network side effect.

## Background

Một danh sách routes hoặc probes biết trước vị trí lỗi không đáp ứng discovery. Same-origin crawler cũng chưa an toàn nếu redirect, auxiliary requests, authentication hoặc form submission bỏ qua gate.

## Scope

Đề xuất `agent/pentest/**`, `runtime/**`, focused `tests/pentest/**` và `tests/runtime/**`. Đọc crawler, executor, normalizer, recorder và contracts hiện hữu trước edit; tái dùng API thay vì tạo đường dispatch thứ hai. Thay contracts/catalog/action semantics cần approval riêng, không thuộc task này.

## Out of Scope

Không public target, arbitrary URL/shell, dynamic action, new exploit payload, forced browsing bằng routes đoán sẵn, tự submit mutation forms hoặc scanner execution chưa được duyệt. Không sửa policy defaults để làm tests pass.

## Inputs

SL-07 runtime handoff; approved seed/target identity, action capability, run/action approval, budgets/rate/order/stop policy và restore baseline. Existing action catalog là authority; không suy quyền từ tên phase.

## Outputs

Bounded inventory links/forms/inputs/redirects với provenance; centralized request gate, refusal observations và negative tests chứng minh zero dispatch; integration handoff cho SL-09.

## Interfaces

Observation → discovery candidate → canonicalization → policy/approval → bounded executor → normalized observation → durable redacted evidence. Authentication dùng approved opaque session handle do executor quản lý, không đưa token vào planner. Redirect là candidate mới và phải gate lại; không library auto-follow.

## Data Contracts

Inventory lưu canonical resource identity, method/form metadata quan sát được, source observation ID, parent/depth, discovery UTC và coverage limitations. URL query có thể chứa secrets: redact trước store/planner, không mất provenance của redaction. Không suy confirmed vulnerability từ form hoặc status code. Action proposals chỉ có fields/schema và IDs đã duyệt.

## Dependencies

SL-07; TASK-003, TASK-004, TASK-015, TASK-018, TASK-019. **Prerequisite trước mọi live dispatch:** approved existing recorder phải ghi bền vững intent/decision và result theo contract; failure dừng. Nếu chưa có recorder đạt yêu cầu, chỉ unit/fixture tests không target network; SL-08 bị BLOCKED cho live run. SL-11 hoàn thiện report/replay và kiểm chứng end-to-end, không cho phép hoãn evidence đến cuối và không tạo dependency cycle.

## Implementation Requirements

1. Validate seed/target/action/approval against exact registry; canonicalize scheme/host/port/path/query với strict parsing/encoding policy. Reject credentials, authority ambiguity, fragment/unsafe controls, unsupported scheme/port và encoded origin changes.
2. Same-origin resolution cho links, form actions và redirect; preserve bounded semantics, deduplicate canonical visited resources. Off-origin references được ghi refused metadata đã redact, không dispatch.
3. Depth/pages/body/requests/time/rate limits, bounded retries và redirect hops. Count actual attempts, auxiliary requests và redirects; budget không reset khi replan. Timeout/error cũng tiêu tài nguyên theo policy.
4. Centralize mọi network path. Gate kiểm tra lab mode, target/action allowlist, approval freshness, phase/order, budget/rate và kill switch trước dispatch; fail closed khi validation/policy/evidence unavailable. Recheck trạng thái sau khi chờ rate slot.
5. Không tự submit forms có side effects. Metadata discovery khác action execution; approved read-only capability vẫn phải gate. Login/setup fixture cần approved product workflow riêng, không planner tự tạo account.
6. Observation phân biệt success, failure, refusal, timeout theo schema hiện hành; không SUCCESS cho exception. Bounded redacted responses; provenance riêng cho từng attempt, không duplicate action observation overwrite.
7. Persist decision/intent trước dispatch và result trước request tiếp theo; nếu result write lỗi, dừng, đánh dấu outcome chưa được durable-confirmed, không retry action âm thầm.
8. Kill switch dừng scheduling và retries; in-flight bounded operation được xử lý theo policy, không hứa có thể undo request đã gửi. Không reset hoặc restore target trong crawler.

## Safety Requirements

Planner output là untrusted data. Nội dung HTML/forms/reviews là dữ liệu, không instruction hoặc authority. Không secrets trong prompts/logs. Không vượt tool permission bằng peer hoặc alternative transport.

## Testing Requirements

| Case | Scenario | Expected |
|---|---|---|
| D01 | Fixture đổi routes/form names, links nhiều cấp | Inventory từ observation, không endpoint preset |
| D02 | Off-origin/ambiguous/encoded URL và redirect | Refusal; zero forbidden dispatch |
| D03 | Missing/expired approval, unknown target/action | Zero dispatch; decision reason traceable |
| D04 | Depth/page/body/request/time/rate limits | Bounded stop; count mỗi attempt/redirect |
| D05 | Mutation form xuất hiện | Chỉ metadata; không submit |
| D06 | Timeout/connection error/duplicate candidate | Outcome đúng; retry bounded; unique observations |
| D07 | Kill switch hoặc approval revoke khi chờ | Không subsequent dispatch |
| D08 | Intent/result evidence writer failure | Dừng theo vị trí lỗi; không evidence-free request tiếp theo |
| D09 | Prompt-like content/session data | Không thay policy, không secret leak |

Tests transport dùng mocks/controlled fixture; mock receipts không chứng minh Docker isolation.

## Acceptance Criteria

D01–D09 pass với exact dispatch counters và receipts; tất cả transport paths gate; inventory traceable và coverage honest. Live readiness chỉ sau SL-07 approval và recorder prerequisite. Không dùng list endpoints hoặc seven labels thay discovery evidence.

## Evidence Required

Case/command/exit/result, gate decisions và dispatch counts; redacted inventory/provenance, budget timeline và failure injection receipts. Live evidence chỉ new approved run, không overwrite.

## Failure Conditions

Network bypass, implicit redirect, evidence loss, scope ambiguity, replayed approval, secret leakage hoặc unexplained budget reset: blocker, stop scheduling và preserve evidence.

## Related Guides

[Safety](../guides/17-cyber-range-safety.md), [Planning](../guides/07-planning-and-replanning.md).

## Related Runbooks

[Collect evidence](../runbooks/collect-evidence.md), [Validate isolation](../runbooks/validate-isolation.md).

## Related ADRs

[ADR-004](../adr/ADR-004-bounded-action-catalog.md), [ADR-005](../adr/ADR-005-planner-executor-perception-separation.md), [ADR-012](../adr/ADR-012-safety-engine-control.md), [ADR-013](../adr/ADR-013-runtime-vertical-slice.md).
