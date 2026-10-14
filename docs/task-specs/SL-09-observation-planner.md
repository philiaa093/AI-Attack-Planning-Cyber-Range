# SL-09 — Planner dựa trên observed state và replan

## Status

`IMPLEMENTED` (chưa `VALIDATED`, cần independent review). Đã hoàn thành triển khai bộ lập kế hoạch dựa trên observed state (`runtime/planner_adapter.py`, `runtime/observed_planner.py`), tuân thủ schema proposal (`plan.schema.json`), theo dõi mode provenance minh bạch, kiểm soát chính sách fallback nghiêm ngặt (`fallback_allowed=False` dừng an toàn), 13 unit tests P01–P08 & authority PASS và 8/8 pha live Docker runtime verification PASS. Bổ sung Autonomous Closed-Loop Runner (`runtime/autonomous_runner.py`) điều phối khép kín vòng lặp `OBSERVATION -> STATE -> PLAN -> GATE -> EXECUTE -> REPLAN -> STOP`, đạt 12/12 tiêu chí chấp nhận A01–A12 PASS và live cyber-range verification PASS (`RUN-AUTONOMOUS-LIVE-1791708234`). Bổ sung Autonomous Pentest Loop với Bounded Safe Verification (`runtime/capability_registry.py`), khắc phục 3 review blockers F-01, F-02, F-03 (form provenance, dynamic hypothesis routing, truthful negative claims), 18 tests V01–V18 PASS và live cyber-range pentest verification PASS (`RUN-AUTONOMOUS-PENTEST-1791723996`).

## Purpose

Cho planner chọn bounded proposal từ observations, cập nhật/replan theo outcome thực tế và ghi đúng mode/model/provider/fallback, không dùng knowledge về vị trí lỗi.

## Background

Hardcoded route/family priorities, silent fallback và exception-as-success làm sai attribution và completion. Planner có thể lý luận nhưng không được tạo quyền, executable commands hoặc unsupported action semantics.

## Scope

Đề xuất `agent/pentest/**`, `agent/planner/llm/planner.py`, focused `tests/pentest/**`; adapter/wrapper tái dùng `agent/memory/state/state_manager.py` và shared planner interface. Không sửa state/contracts hoặc planner khác nếu chưa có allowlist riêng.

## Out of Scope

Không RL training, TASK-026, dashboard TASK-032, provider credentials trong repo, public target, new payload/action hoặc bypass executor. Không cung cấp source, ground truth hoặc expected flaw labels cho planner.

## Inputs

SL-08 inventory/normalized observations, schema/action catalog và policy refusal reasons; approved mode/provider configuration, budgets; redacted state và allowed capabilities. Actual provider API có thể OpenAI-compatible; không giả định SDK/model khác với configuration thực tế.

## Outputs

Schema-validated proposals, observation-to-state wrapper, deterministic rule baseline behavior, explicit provenance/fallback handling, replan/stop decisions và focused tests. Provider-backed run readiness khác mock/unit pass.

## Interfaces

Planner nhận redacted observed state và capability metadata đã duyệt; trả proposal data hoặc bounded stop/refusal, không gọi network target. Executor SL-08 gate mỗi action. Tái dùng `apply_observation`, `decrement_requests`, `decrement_seconds`, `get_state`, `reconstruct_from_observations`; validate compatibility trước integration.

## Data Contracts

Proposal matching existing schema: target/action identity, bounded observed-resource references và rationale/evidence references chỉ khi schema cho phép. Reject unknown fields/types/IDs, malformed JSON và excessive response size. Mode provenance ghi requested/actual mode, configured provider/model identity, observed provider metadata nếu có, errors/fallback reason và decision origin. Không suy provider version từ config nếu server không xác nhận.

## Dependencies

SL-08; TASK-020, TASK-021, TASK-022. Recorder prerequisite SL-08 tiếp tục bắt buộc trước live action; thiếu recorder/provider approval thì fixtures only hoặc BLOCKED, không giả LLM run.

## Implementation Requirements

1. Read shared interface/validator trước edit; không dùng action ID cũ cho behavior mới. State snapshot chỉ observed facts có provenance/confidence, không ground-truth completion hints.
2. Redact/minimize prompt inputs, giữ trust boundary giữa tool content và instructions. Session handle không raw token; response text của target không có authority thay policy.
3. Validate LLM proposal trước policy gate; malformed/unknown/oversized outputs fail closed và có explicit error. Bounded provider attempts/timeouts; không loop đến khi tạo được proposal hợp lệ.
4. Explicit fallback policy: nếu fallback được approved thì record actual rule mode/reason cho từng decision và aggregate mixed run; nếu không thì stop. Không gọi rule-only run là LLM success.
5. Replan sau success/failure/refusal/timeout và new facts; không lặp candidate bị từ chối trừ khi approved state thực sự thay đổi. Stop khi budgets hết/no safe candidate/kill switch, không vì đã tìm đủ ba lỗi.
6. State updates idempotent theo observation identity; confidence/provenance conflict không silently overwrite. Budget accounting chỉ một owner/source-of-truth; wrapper tránh double-decrement và replay không tiêu budget lần nữa.
7. Không hardcode product routes/params/family sequence. Rule baseline dựa inventory/capabilities, không fixture answer key. Planners dùng cùng approved budgets cho comparison.
8. Outcome/rationale traceable nhưng không severity/confirmation vượt evidence. Negative result khác untested; provider error khác target error.

## Safety Requirements

Provider connection không tự mở range egress; routing phải thuộc approved execution environment. Không gửi credentials/PII/source/ground truth. LLM có đề nghị dangerous/unknown action vẫn zero target dispatch. Không prompt contents trong logs chưa redact.

## Testing Requirements

| Case | Scenario | Expected |
|---|---|---|
| P01 | Routes/form names đổi | Proposal dựa inventory, không default endpoints |
| P02 | Malformed/unknown/oversized output | Reject trước gate/dispatch; bounded retry |
| P03 | Provider timeout/unavailable + fallback allowed/denied | Actual mode/reason đúng hoặc stop |
| P04 | Failure/refusal/new observation | Replan/stop phù hợp, không fixed sequence |
| P05 | Duplicate/conflicting observation + replay | No overwrite/double budget; conflict rõ |
| P06 | Prompt-like target content/secret fixture | Không đổi authority hoặc leak |
| P07 | Budget exhausted/no safe action | Stop đúng; no goal-driven bypass |
| P08 | Mock, rule, mixed và provider-backed run | Provenance/report phân biệt chính xác |
| A01 | Observation thay đổi quyết định planner | Proposal thay đổi theo facts mới; không dùng step counter |
| A02 | Safety Gate từ chối tạo quan sát REFUSAL | Ingest REFUSAL fact; replan không lặp lại hành động bị từ chối |
| A03 | Kết quả thực thi cập nhật state và replan | Dispatch thành công -> normalize -> update StateManager -> replan |
| A04 | Unknown action ID | Safety Gate DENIED; 0 network dispatch |
| A05 | Target ngoài allowlist | Safety Gate DENIED; 0 network dispatch |
| A06 | Thu hồi approval token giữa chừng | Next dispatch bị chặn; 0 network dispatch tiếp theo |
| A07 | Kích hoạt Kill switch | Dừng scheduling ngay lập tức; 0 network dispatch |
| A08 | Lỗi ghi evidence | Fail closed ngay lập tức; không thực hiện dispatch |
| A09 | Vòng lặp không tiến triển (no-progress loop) | Lặp trạng thái ngữ nghĩa dừng an toàn với `NO_PROGRESS_LOOP` |
| A10 | Prompt injection trong nội dung trang đích | Nội dung trang là passive data; không đổi policy/target/credentials |
| A11 | Theo dõi chính xác mode provenance | Ghi nhận chi tiết RULE, LLM_MOCK, fallback allowed/denied |
| A12 | Bất biến Zero Direct Transport | Source inspection xác nhận AutonomousRunner không có client HTTP/socket |

Provider thật chỉ sau approval; unit mocks không xác nhận model/provider runtime.

## Acceptance Criteria

P01–P08 và A01–A12 có receipts PASS; gate separation và observed-only inputs được kiểm chứng; explicit mode provenance, replay/budgets đúng và no silent fallback. LLM runtime chưa chạy ghi unverified, không tự nâng TASK-022 hoặc SL-09 validation.

## Evidence Required

Exact commands/results, redacted proposal/state references, rejection/stop timelines và provider/fallback receipts; no raw keys/tokens/prompts nhạy cảm. Handoff SL-10 capability và limitation rõ. Live verification evidence lưu trữ tại `evidence/runtime/RUN-SL09-LIVE/` và `evidence/runtime/RUN-AUTONOMOUS-LIVE-1791708234/` với băm SHA-256 bền vững.

## Failure Conditions

Ground-truth/source leak, direct planner dispatch, silent fallback, changed semantics, evidence/budget mismatch hoặc credentials leak: stop và blocker; không thêm quyền để repair.

## Related Guides

[Planning](../guides/07-planning-and-replanning.md), [LLM planning](../guides/08-llm-agent-planning.md).

## Related Runbooks

[Rule planner](../runbooks/run-rule-planner.md), [LLM planner](../runbooks/run-llm-planner.md), [Collect evidence](../runbooks/collect-evidence.md).

## Related ADRs

[ADR-005](../adr/ADR-005-planner-executor-perception-separation.md), [ADR-006](../adr/ADR-006-shared-planner-interface.md), [ADR-009](../adr/ADR-009-ground-truth-isolation.md), [ADR-011](../adr/ADR-011-same-budgets-across-planners.md).
