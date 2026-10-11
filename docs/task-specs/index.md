# Task Specifications

[TASKS.md](../../TASKS.md) là nguồn trạng thái và dependencies hiện hành. Chỉ mục này không lặp status lịch sử để tránh lệch nguồn; mở từng spec để đọc yêu cầu và đối chiếu TASKS.md trước triển khai. Có đặc tả không có nghĩa task đã được kiểm chứng.

## Canonical foundation tasks

Giữ nguyên 35 canonical task IDs; SL-* bên dưới bổ sung work packages, không thay thế các task này hoặc tự nâng trạng thái.

- [TASK-001 — Foundation validator](TASK-001-foundation-validator.md)
- [TASK-002 — Root governance docs](TASK-002-root-governance-docs.md)
- [TASK-003 — Safety contracts](TASK-003-safety-contracts.md)
- [TASK-004 — Action catalog](TASK-004-action-catalog.md)
- [TASK-005 — State contract](TASK-005-state-contract.md)
- [TASK-006 — Observation contract](TASK-006-observation-contract.md)
- [TASK-007 — Evidence contract](TASK-007-evidence-contract.md)
- [TASK-008 — Scenario contract](TASK-008-scenario-contract.md)
- [TASK-009 — Ground-truth contract](TASK-009-ground-truth-contract.md)
- [TASK-010 — Experiment contract](TASK-010-experiment-contract.md)
- [TASK-011 — Cyber range network](TASK-011-cyber-range-network.md)
- [TASK-012 — Web target A](TASK-012-web-target-a.md)
- [TASK-013 — Web target B](TASK-013-web-target-b.md)
- [TASK-014 — Clean control target](TASK-014-clean-control-target.md)
- [TASK-015 — Discovery adapter](TASK-015-discovery-adapter.md)
- [TASK-016 — ZAP adapter](TASK-016-zap-adapter.md)
- [TASK-017 — Nuclei adapter](TASK-017-nuclei-adapter.md)
- [TASK-018 — Observation normalizer](TASK-018-observation-normalizer.md)
- [TASK-019 — Knowledge-state store](TASK-019-knowledge-state-store.md)
- [TASK-020 — Planner interface](TASK-020-planner-interface.md)
- [TASK-021 — Rule-based planner](TASK-021-rule-based-planner.md)
- [TASK-022 — LLM planner](TASK-022-llm-planner.md)
- [TASK-023 — RL environment](TASK-023-rl-environment.md)
- [TASK-024 — Reward model](TASK-024-reward-model.md)
- [TASK-025 — Q-learning baseline](TASK-025-q-learning-baseline.md)
- [TASK-026 — DQN/PPO candidate](TASK-026-dqn-ppo-candidate.md)
- [TASK-027 — Hybrid planner](TASK-027-hybrid-planner.md)
- [TASK-028 — Experiment runner](TASK-028-experiment-runner.md)
- [TASK-029 — Metrics engine](TASK-029-metrics-engine.md)
- [TASK-030 — Held-out evaluation](TASK-030-held-out-evaluation.md)
- [TASK-031 — Statistical analysis](TASK-031-statistical-analysis.md)
- [TASK-032 — Dashboard](TASK-032-dashboard.md)
- [TASK-033 — Report artifact generator](TASK-033-report-artifact-generator.md)
- [TASK-034 — Reproducibility package](TASK-034-reproducibility-package.md)
- [TASK-035 — Final foundation audit](TASK-035-final-foundation-audit.md)

## ShopLab implementation tasks

Nguồn roadmap: [PROJECT_PLAN.md](../../PROJECT_PLAN.md), `PLAN-SHOPLAB-PTES-001` / `SHOPLAB-PTES-001`. Hướng hiện hành `PLAN-OSCAR-ADOPTION-001`: tái sử dụng Django Oscar sandbox 4.2.1 thay vì tiếp tục tự xây nghiệp vụ. SL-01–03 giữ lịch sử ShopLab; SL-04–07 chuyển sang upstream fit-gap/configuration/acceptance, giữ IDs/dependencies và invariants. Dependency equivalence cần review explicit, không chuyển PASS sang target mới. Mỗi spec giữ 19 mục chuẩn; candidate đang bị chặn trước execution vì dependency/support/environment gate, xem [thẩm định Oscar](../../TASKS.md#oscar--thẩm-định-nguồn-offline).

| Task | Nội dung | Dependencies SL-* |
|---|---|---|
| [SL-01](SL-01-baseline-checks.md) | Baseline, gateway/storage checks và receipts | Không |
| [SL-02](SL-02-storage-lifecycle.md) | SQLite lifecycle, locking, transactions và persistence | SL-01 |
| [SL-03](SL-03-auth-authorization.md) | Auth, opaque session, CSRF, ownership và roles | SL-01, SL-02 |
| [SL-04](SL-04-cart-checkout.md) | Catalog, giỏ hàng, checkout transaction nguyên tử, atomic stock decrement, idempotency theo owner, tiền USD minor units, invoice post-commit | SL-02, SL-03 |
| [SL-05](SL-05-orders-reviews.md) | Đơn hàng, hóa đơn on-demand fallback, đánh giá sản phẩm, IDOR ownership, chống XSS, data minimization | SL-03, SL-04 |
| [SL-06](SL-06-product-admin.md) | Admin backoffice, forward-only order status transition state machine, cancellation policy, product archiving, audit log | SL-03, SL-04, SL-05 |
| [SL-07](SL-07-lab-runtime.md) | Docker lab isolation, Gateway loopback proxy, container persistence, failure 502 injection, restore baseline, E2E verification | SL-02, SL-03, SL-04, SL-05, SL-06 |
| [SL-08](SL-08-discovery-safety.md) | Observation-driven discovery và every-request safety gate | SL-07 |
| [SL-09](SL-09-observation-planner.md) | Observed-state planning/replan và actual-mode provenance | SL-08 |
| [SL-10](SL-10-ptes-orchestration.md) | Seven-phase artifacts, exit checks và honest statuses | SL-08, SL-09 |
| [SL-11](SL-11-evidence-reporting.md) | Append-only evidence, reports, integrity và offline replay | SL-07, SL-10 |
| [SL-12](SL-12-verification-handoff.md) | Focused checks, deterministic gate, independent review/handoff | SL-07, SL-08, SL-09, SL-10, SL-11 |

**Repository checker compatibility:** incompatibility với 12 SL specs đã được xử lý trong SL-01. `scripts/validation/validate_scaffold.py` và focused validator tests kiểm tra exact 35 canonical TASK + 12 SL specs, identities/status, 19 headings, links và dependencies mà không nới safety/canonical checks. SL-02 R1 có receipts validator 31 tests PASS và checker `SCAFFOLD VALID`, exit 0. Không sửa checker trong lần cập nhật tài liệu này; nguồn trạng thái và receipts là [TASKS.md](../../TASKS.md#checks-and-observed-implementation-state).

SL-01 baseline và SL-02 storage đã có checks/gate/review độc lập được xác minh trong phạm vi offline fixture/mock và SQLite temp. SL-03 hiện `IMPLEMENTED`: 114 tests và AST/checker/gate PASS trong offline scope; đã tự review/sửa findings theo yêu cầu người dùng nhưng chưa có independent APPROVE, chưa `VALIDATED`. SL-04 hiện `IMPLEMENTED`: 13 tests checkout và 65 tests ecommerce PASS (atomic decrement, idempotency theo owner, USD minor units, invoice decoupling). SL-05 hiện `IMPLEMENTED`: 16 tests orders/reviews PASS (IDOR protection, dynamic invoice fallback, lab notice, review validation, stored XSS defense). SL-06 hiện `IMPLEMENTED`: 14 tests admin PASS (forward-only state machine, cancellation policy, product archiving, audit log). SL-07 hiện `IMPLEMENTED`: 17 tests gateway E2E PASS và kịch bản live Docker `scripts/cyber-range/verify_live_docker.py` PASS toàn bộ 8/8 pha (health, full flow, IDOR isolation, restart, replacement, failure 502, baseline restore, bounded teardown). SL-08 hiện `IMPLEMENTED`: 7 tests preflight recorder PASS, 9 tests discovery safety PASS, 7/7 pha live Docker PASS (`evidence/runtime/RUN-SL08-LIVE/`). SL-09 hiện `IMPLEMENTED`: 13 tests observed planner PASS, 8/8 pha live Docker PASS (`evidence/runtime/RUN-SL09-LIVE/`). SL-10 hiện `IMPLEMENTED`: PTES coordinator điều phối 7 phase trung thực (Phase 5 BLOCKED, Phase 6 NOT_RUN, 0 confirmed vulns), 8 tests T01–T08 PASS, live Docker PASS. SL-11 hiện `IMPLEMENTED`: immutable evidence packaging, report generator, zero-network replay verifier, root containment, non-recurrence lock, 14 tests E01–E09 & B01–B05 PASS, và gói chuẩn mực bàn giao `evidence/runtime/RUN-SL11-HANDOFF-20261011/`. Tất cả các task trên đều chưa có independent review APPROVE; không tự nâng `VALIDATED`. Chuẩn bị sẵn sàng cho bàn giao và thẩm định độc lập tại SL-12.

Dependencies mới luôn tham chiếu task SL có số nhỏ hơn, không có dependency cycle. Danh sách TASK-* nền trong mỗi spec là liên kết/reuse context, không tuyên bố đã triển khai toàn bộ task nền. TASK-026/TASK-032 vẫn DEFERRED.

### Cập nhật web target snapshot

[TASK-011](TASK-011-cyber-range-network.md), [TASK-012](TASK-012-web-target-a.md), [TASK-013](TASK-013-web-target-b.md), [TASK-014](TASK-014-clean-control-target.md), [TASK-018](TASK-018-observation-normalizer.md) và [TASK-019](TASK-019-knowledge-state-store.md) chỉ dẫn impact assessment, receipts mới và phần lịch sử giữ nguyên khi web snapshot đổi. Validation cũ không áp dụng tự động cho snapshot mới; status/dependencies/evidence lịch sử không đổi. [TASK-008](TASK-008-scenario-contract.md)–[TASK-010](TASK-010-experiment-contract.md) version instance theo approved snapshot, shared schema không tự đổi và ground truth chỉ evaluation.

**Evidence prerequisite:** trước live dispatch ở SL-07–10 phải có approved existing recorder/destination và failure-stop checks. SL-11 là packaging và validation end-to-end, không cho phép ghi evidence muộn. Nếu recorder chưa đáp ứng thì live run BLOCKED; chỉ temp-fixture tests không network target được tiếp tục. Không tạo dependency SL-08 → SL-11 → SL-10 → SL-08 để giải quyết prerequisite này.

## ShopLab task contracts

Đây là yêu cầu lifecycle cho handoff, không sửa canonical JSON schemas/contracts trong repository và không là approval instance. Không đưa JSON template có placeholders sang gate. Concrete contracts phải được lập cho scope/build thực tế, baseline refresh và exact commands trước implementation; approved plan không tự cấp per-run/action approval.

### Authority và phạm vi

- Đọc AGENTS.md, PROJECT_CONTEXT.md, PROJECT_PLAN.md, TASKS.md, spec, relevant canonical contracts và ADR trước edit.
- User source/approved contracts outrank derivative docs; evidence outrank prose cho observed claims.
- Các đường dẫn trong Scope của spec là **đề xuất implementation allowlist**, không permission do file mới tự cấp. Task assignment/approved contract phải xác định exact paths; forbidden ngoài allowlist. Lần cập nhật trạng thái sau SL-02 chỉ mở PROJECT_CONTEXT.md, PROJECT_PLAN.md, TASKS.md, SL-02 spec, index và phần mô tả trạng thái liên quan trong ADR-013; không runtime/config/evidence edits.
- Bảo toàn dirty baseline và existing evidence; không append history, self-approve/finalize hoặc commit chưa được yêu cầu. Source conflict/evidence-loss risk dừng.

### PLAN_CONTRACT

Bắt buộc: `type`, `schema_version`, `task_id`, `plan_id`, `base_head`, `authority_inputs`, `baseline_worktree`, `allowed_paths`, `forbidden_paths`, `constants`, `acceptance_checks`, `required_checks`, `repair_budget`, `external_attempt_budget`, `blockers`, `handoff`.

`baseline_worktree` phải phân biệt user changes có trước build và build-owned changes. `allowed_paths`/`forbidden_paths` là exact scope, không toàn repo ngầm. `constants` giữ lab-only, no public targets/new credentials/new payloads/arbitrary shell/dynamic actions, approvals/rate/order/budgets/refusal/audit/restore và deferred tasks. Acceptance/checks phải measurable; runtime approval/evidence destination chưa có thì blockers rõ. Budget của approved plan không được tự tăng khi gặp tool failure.

### BUILD_CONTRACT

Bắt buộc matching `task_id`, `plan_id`, `base_head`; thêm `type`, `schema_version`, `build_id`, `status`, `observed_paths`, `changed_files`, `check_receipts`, `self_check`, `unverified`, `blockers`, `pending_handoff_payload`.

`observed_paths` và `changed_files` so với recorded baseline, không chỉ HEAD diff chứa user work. `pending_handoff_payload` phải có exact changed/deleted files, command receipts, unresolved risks và next safe step. `self_check` không independent approval. Receipts có exact command, execution state, exit code/result, UTC/source/artifact references khi có. Blocked trước execution dùng exit_code null, không PASS/FAIL; skipped/unverified không required-check success. Tách static/fixture/mock khỏi Docker/provider actual observations.

### REVIEW_CONTRACT

Bắt buộc matching `task_id`, `plan_id`, `base_head`, `build_id`; thêm `type`, `schema_version`, `pre_review_gate`, `verdict_status`, `verdict`, `verified_findings`, `blockers`, `non_blocking`, `required_action`, `test_gaps`.

Reviewer độc lập/read-only; verified finding có concrete scenario, file/line và evidence. Review không runtime approval, không self-finalization. Verdict FINAL/APPROVE là điều kiện lifecycle cần thiết, không tự cho commit/history/status edit; governance và explicit user permission vẫn áp dụng.

### Deterministic pre-review gate và repair

1. Validate đủ fields/schema, matching IDs/base head/build, no placeholders.
2. Validate exact observed/changed/deleted paths against allowlist/forbidden scope và baseline.
3. Validate required-check receipts/results, evidence references/integrity, no blockers; chạy repository checker khi khả dụng, không coi unavailable là pass.
4. Malformed worker output: một retry. Invalid gate hoặc unresolved prerequisite: HANDOFF_BLOCKED; không Review, không repair decrement.
5. Chỉ evidence-backed Review blocker tiêu repair budget. Repair theo original scope, chạy lại affected checks/gate, không đổi evidence cũ hoặc nới acceptance.
6. Pending handoff thay precommit. Không commit/PR khi user chưa yêu cầu; không tự approve, finalize hoặc append history.

### Status và completion claims

Documentation có thể IMPLEMENTED sau tạo nhưng không VALIDATED thiếu checks/review. Work package còn SPEC_ONLY/BLOCKED theo TASKS.md dù có partial code. Runtime SPEC_ONLY tới approved executable scope và UNRESOLVED tới observed evidence. NOT_RUN chỉ phase execution status. Product readiness, Docker runtime, provider-backed AI và seven-phase completion phải có claim/evidence riêng; không dùng mock hoặc seven labels để thay thế.
