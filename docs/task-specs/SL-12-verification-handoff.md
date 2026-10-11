# SL-12 — Kiểm chứng, independent review và handoff

## Status

`SPEC_ONLY`. Deterministic pre-review gate hiện ghi nhận `HANDOFF_BLOCKED` do `validate_scaffold.py` phát hiện lỗi schema tại tệp demo `scripts/demo/demo-output/BASELINE-...` (ngoài allowlist). Đã xác lập build ID `SL12-PREVIEW-ee45e60-20261011`, run ID `RUN-SL11-HANDOFF-20261011`, `CURRENT_REVIEW_SOURCE_MANIFEST` 27 files, 18 check receipts PASS; `REVIEW_CONTRACT` đã được tạo sẵn sàng. Dừng theo Stop Rules chờ chỉ thị scope; chưa có independent review / approval mới; không tự nâng `VALIDATED`.

## Purpose

Đối chiếu sản phẩm và assessment với acceptance criteria bằng deterministic checks, rồi bàn giao independent review; không tự chứng nhận hoàn thành hoặc che giấu phần chưa kiểm chứng.

## Background

Product implementation, fixture pass, Docker runtime, provider-backed AI và seven-phase completion là các claim khác nhau. Working tree có user changes từ trước; review phải biết exact baseline/scope, không dùng diff tổng làm bằng chứng mọi thay đổi thuộc build.

## Scope

Focused checks/tests trong `tests/integration/**`, `tests/runtime/**`, `tests/pentest/**` khi allowlist giao riêng; read-only repository checker và source/evidence inspection. Contract/handoff payload theo [index](index.md#shoplab-task-contracts). Fix chỉ quay lại task/allowed paths với matching contract, không opportunistic edits toàn repo. Documentation status changes cần explicit scope, không self-approval.

## Out of Scope

Không commit/push/PR khi chưa được yêu cầu, self-approve/finalize, append history, sửa old evidence/contracts/catalog/config, mở public/exploitation scope hoặc nâng TASK-026/TASK-032. Không chạy Docker/provider run thiếu approval.

## Inputs

SL-07–11 artifacts/check receipts, matching PLAN_CONTRACT/BUILD_CONTRACT, current baseline/head/diff/untracked inventory và independent reviewer availability. Required check list và budgets phải concrete trước build; tool availability cũ cần refresh chứ không mặc định còn lỗi.

## Outputs

Deterministic pre-review gate receipt, independent REVIEW_CONTRACT nếu gate đạt, ranked evidence-backed findings hoặc HANDOFF_BLOCKED, pending handoff payload liệt kê changed/deleted files, checks/unverified/blockers. Không final security certification.

## Interfaces

Build → deterministic pre-review gate → independent read-only Review → bounded repair nếu justified → recheck → pending handoff. Invalid worker contract được một retry; HANDOFF_BLOCKED không review và không tiêu repair budget. Only evidence-backed Review blocker tiêu repair budget. Pending handoff thay precommit.

## Data Contracts

Matching `task_id`, `plan_id`, `base_head`, `build_id`; exact allow/forbidden paths so baseline, no placeholders; receipts gồm exact command, execution state, exit code/result, artifact references khi có. Blocked-before-execution có exit_code null, không PASS/FAIL. Review verified findings có path/line/scenario/evidence, verdict và required action; structured contract không thay actual checks.

## Dependencies

SL-07, SL-08, SL-09, SL-10, SL-11; TASK-030, TASK-034, TASK-035. Không coi historical foundation validation là current runtime approval.

## Implementation Requirements

1. Refresh HEAD/status và preserve user baseline; inventory changed/new/deleted files thuộc từng build. No restore/reset/stash/commit tự ý; không đọc secrets để đưa vào report.
2. Required checks: gateway/storage; auth/CSRF/ownership; cart/money/stock/idempotency/concurrency; orders/reviews/admin; persistence/restore; discovery/gate zero-dispatch; planner/fallback/provenance; phase exit criteria; evidence/redaction/replay; safety regression và scaffold validator.
3. Chốt exact suite commands từ current runner, ghi output/exit/results. Fixtures/mock/static tests không Docker/provider evidence. Validator fail từ baseline phải báo rõ; không sửa unrelated artifacts cho pass.
4. Authorized Docker business-flow/isolation/durability/restore/teardown receipts và authorized provider-backed observations cần riêng. Missing approval/tool/provider không dùng mock thay thế; unverified là blocker cho claim tương ứng.
5. Deterministic gate validate contract fields/IDs/head/path scope/required receipts/no placeholders/no blockers và repository checker. Scope hoặc receipt invalid: HANDOFF_BLOCKED, no Review.
6. Independent reviewer read-only kiểm tra security/data-loss-sensitive diff và evidence: authorization/CSRF, atomic checkout, proxy/network boundary, every-request gate, evidence-loss/redaction, phase honesty. Builder không review/approve chính mình; unavailable reviewer giữ blocked.
7. Repair chỉ concrete reviewed defect, bounded original budget; forbidden scope/evidence risk dừng. Re-run affected checks và gate; không tự giảm required checks hoặc gọi repair success khi chưa chạy.
8. Handoff tách product readiness, Docker readiness, planner unit readiness, actual provider mode và seven-phase completion; liệt kê limitations/blocked phases. FINAL/APPROVE trong review là điều kiện lifecycle cần thiết nhưng không tự tạo permission commit/status/history; AGENTS.md vẫn cấm self-finalize và commit cần user request.

## Safety Requirements

Không permission laundering bằng peer/transport. Stop khi tool bị chặn, integrity/source conflict hoặc evidence loss. Review không active target commands/payloads; fixtures fake và no credential leakage.

## Testing Requirements

| Case | Scenario | Expected |
|---|---|---|
| V01 | ID/head/build mismatch hoặc malformed contract | Gate reject; one retry nếu worker malformed |
| V02 | Changed/deleted path ngoài allowlist | HANDOFF_BLOCKED, no Review |
| V03 | Required check blocked/skipped/missing receipt | No PASS substitution; claim blocked |
| V04 | Baseline validator error/unrelated dirty file | Trace baseline, preserve, no scope broadening |
| V05 | Fixture pass nhưng no Docker/provider observations | Runtime/AI claim unverified |
| V06 | Review blocker vs handoff blocker | Chỉ evidence-backed Review blocker tiêu repair budget |
| V07 | Builder tự approve hoặc seven labels completion | Reject lifecycle/unsupported claim |
| V08 | Complete authorized receipts + independent review | Pending handoff accurate; no unsolicited commit/history |

## Acceptance Criteria

V01–V08 và required focused checks có exact receipts; gate đạt trước Review; independent verdict matching build và verified findings resolved theo budget. Tài liệu có thể hoàn thành mà implementation/full goal chưa đạt; báo riêng. Không claim VALIDATED hoặc runtime success thiếu observed evidence/review.

## Evidence Required

Exact changed/deleted list, baseline identity, command/gate/review receipts, authorized run artifacts/hashes/redaction references, unverified/blockers và pending handoff. Không append historical evidence để hợp thức hóa new build.

## Failure Conditions

Unavailable checks/reviewer, scope drift, malformed contract sau retry, missing permission/evidence hoặc repair budget exhausted: HANDOFF_BLOCKED; không Review/commit/self-approval hoặc retry vô hạn.

## Related Guides

[Evaluation](../guides/16-evaluation-methodology.md), [Safety](../guides/17-cyber-range-safety.md).

## Related Runbooks

[Run experiment](../runbooks/run-experiment.md), [Collect evidence](../runbooks/collect-evidence.md), [Validate isolation](../runbooks/validate-isolation.md).

## Related ADRs

[ADR-008](../adr/ADR-008-held-out-scenarios.md), [ADR-010](../adr/ADR-010-evidence-immutability.md), [ADR-013](../adr/ADR-013-runtime-vertical-slice.md).
