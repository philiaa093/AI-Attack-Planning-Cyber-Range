# SL-10 — Bảy giai đoạn PTES với exit evidence

## Status

`IMPLEMENTED`. PTES Coordinator đã được triển khai tại `runtime/ptes_coordinator.py`, kết nối SL-08 safety gate/recorder và SL-09 planner. Điều phối 7 giai đoạn PTES với entry/exit criteria, phân định trạng thái trung thực (Phase 1 COMPLETED, Phase 2 COMPLETED_BOUNDED, Phase 3 COMPLETED, Phase 4 COMPLETED, Phase 5 BLOCKED, Phase 6 NOT_RUN, Phase 7 COMPLETED). 8 unit tests T01–T08 (`tests/runtime/test_ptes_coordinator.py`) PASS; xác minh live Docker verification trên ShopLab stack 7/7 phase PASS; chưa có independent review / approval; giữ pending SL-12, không tự nâng `VALIDATED`.

## Purpose

Điều phối bảy giai đoạn có artifact, entry/exit checks và trạng thái trung thực; không ép đủ giai đoạn bằng hoạt động ngoài scope hoặc fabricated findings.

## Background

Mục tiêu là đánh giá sản phẩm từ observations sau khi sản phẩm đã được kiểm chứng. Scope hiện hành chỉ cho bounded safe verification; không authorize active exploitation hoặc post-exploitation tùy ý. Full PTES completion có thể bị chặn hợp lệ.

## Scope

Đề xuất `agent/pentest/**`, focused `tests/pentest/**`, bounded runtime integration chỉ khi assigned `runtime/**`. Phase coordinator tái dùng SL-08 gate và SL-09 planner, không thêm transport/probe bypass. Mapping PTES sang internal phases phải validate contracts; incompatible transition/action semantics cần scope riêng.

## Out of Scope

Không new exploit payload, persistence, credential theft, host file read, lateral movement, public targets hoặc dynamic actions. Không chỉnh expected ground truth để đạt coverage; không tự approve/finalize report hoặc task status.

## Inputs

SL-08/SL-09 acceptance receipts, approved scope/actions/budgets, product restore baseline, observed inventory/state và recorder availability. [PROJECT_PLAN](../../PROJECT_PLAN.md) là phase criteria source.

## Outputs

Phase-specific artifact/exit validators, coordinator state/transition trace, honest summary và negative/blocked tests. Reporting tạo được không có nghĩa preceding phases completed.

## Interfaces

Coordinator → planner proposal → common gate/executor → observation/evidence → exit validator → transition/stop. Policy có quyền từ chối bất kỳ phase nào. Internal state phases không đồng nhất PTES labels; record explicit mapping/compatibility thay vì gán phase name vào schema chưa hỗ trợ.

## Data Contracts

Mỗi phase record có run/phase identity, entry/exit check results, source artifact/evidence IDs, allowed capability/approval references, timestamps, outcome và limitations. `BLOCKED`, `NOT_RUN`, `UNRESOLVED` không là completed; `NOT_RUN` chỉ phase execution status, không task vocabulary. Exact serialized values phải chốt với existing contracts trước implementation, không tự thêm enum.

## Dependencies

SL-08, SL-09; TASK-020, TASK-028, TASK-033. Durable recorder prerequisite của SL-08 phải đạt trước live coordinator run. SL-11 hoàn thiện report/replay packaging sau coordinator, không trì hoãn việc ghi phase/action evidence.

## Implementation Requirements

| Phase | Entry và đầu ra bắt buộc | Exit rule |
|---|---|---|
| 1. Pre-engagement | Target identity/scope, approval, budgets, stop conditions, restore baseline và recorder readiness | Missing/invalid điều kiện: BLOCKED trước dispatch |
| 2. Intelligence gathering | Observed endpoint/form/input inventory, source IDs, coverage/limits | Inventory và bounded discovery receipts; guessed routes không tính |
| 3. Threat modeling | Observed assets/roles/trust boundaries và hypotheses linked inventory | Hypotheses rõ support/unknown, không confirmed findings |
| 4. Vulnerability analysis | Passive/approved non-destructive observations, candidate/negative results | Evidence/rationale cho candidates, không confirm bằng HTTP 200/reflection/error đơn lẻ |
| 5. Exploitation | Chỉ safe verification capability được policy/approval cho phép | Không có capability phù hợp: BLOCKED/NOT_RUN, không fake completion |
| 6. Post-exploitation | Impact assessment từ evidence đã có và dữ liệu lab giả | Unsupported impact là UNRESOLVED; không thêm thao tác ngoài scope |
| 7. Reporting | Findings/negative results/coverage/limitations/remediation, phase statuses và actual planner provenance | Report traceable, honest; không auto-VALIDATED hoặc imply all completed |

1. Entry/exit validators thực sự đọc evidence references/invariants, không chỉ phase counter. Transitions bounded, record reason và failure; không fixed family sequence.
2. Phase 1 failure dừng live actions. Diagnostic report vẫn có thể ghi ở phase 7 nhưng ghi preceding phases NOT_RUN/BLOCKED, không đánh dấu execution completion.
3. Refusal/timeout/provider failure/evidence failure propagate đúng; không SUCCESS trong exception branch hoặc completed trong finally.
4. Preserve global budgets giữa phases/replans; mỗi action/request gate như SL-08. Không tự reset/restore hoặc cấp permission khi chuyển phase.
5. Findings là candidate cho tới đủ approved confirmation evidence; severity/impact dựa observed scope, unknown ghi rõ. Clean target/negative results được report, không fabricate finding cho đủ goal.
6. Tách pipeline-control completion khỏi seven-phase assessment completion; chỉ aggregate full completion khi mọi required exit criterion có observed receipts và independent review. Phạm vi hiện tại không hứa đạt full goal.

## Safety Requirements

Phase labels/rationale không là approval. Không active operation mới, source/ground-truth leak hoặc goal-pressure bypass. Prompt injection không thay exit validator/policy. Evidence write failure dừng request tiếp theo.

## Testing Requirements

| Case | Scenario | Expected |
|---|---|---|
| T01 | Seven labels nhưng thiếu artifacts/exit evidence | Không full-completion claim |
| T02 | Missing phase-1 approval/identity/restore | Zero dispatch; later phases NOT_RUN |
| T03 | Inventory/threat model không có source | Exit reject, không invented assets |
| T04 | HTTP 200/reflection/DB error đơn lẻ | Candidate/signal, không confirmed |
| T05 | Phase 5/6 capability vượt scope | BLOCKED/NOT_RUN/UNRESOLVED đúng |
| T06 | Clean fixture, no finding | Honest negative/coverage report |
| T07 | Budget/provider/evidence failure giữa phase | Stop/propagate đúng, không finally-completed |
| T08 | Fully evidenced permitted fixture flow | Exit references verified; fixture không live runtime proof |

## Acceptance Criteria

T01–T08 pass; seven phase records có traceable criteria/status; coordinator không bypass gate hoặc tự cấp quyền. Có thể acceptance cho honest blocked behavior mà full PTES goal vẫn chưa đạt; phải nói rõ hai claim. Runtime/provider claims cần actual approved receipts, không mocks.

## Evidence Required

Phase entry/exit traces, artifact IDs/hashes, action decisions/outcomes, coverage và limitations; exact commands/results. Handoff SL-11 findings/status/provenance without secrets và unresolved impacts.

## Failure Conditions

Counter-based completion, fake phase evidence, unsupported confirmation/severity, bypass hoặc evidence loss: blocker; stop và preserve state, không tự finalize.

## Related Guides

[Lifecycle](../guides/02-penetration-testing-lifecycle.md), [Planning](../guides/07-planning-and-replanning.md).

## Related Runbooks

[Run experiment](../runbooks/run-experiment.md), [Collect evidence](../runbooks/collect-evidence.md).

## Related ADRs

[ADR-003](../adr/ADR-003-three-vulnerability-families.md), [ADR-005](../adr/ADR-005-planner-executor-perception-separation.md), [ADR-012](../adr/ADR-012-safety-engine-control.md), [ADR-013](../adr/ADR-013-runtime-vertical-slice.md).
