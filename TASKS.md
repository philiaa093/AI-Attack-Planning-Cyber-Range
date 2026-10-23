# Tasks

Status vocabulary: `SPEC_ONLY`, `TBD`, `UNRESOLVED`, `IMPLEMENTED`, `VALIDATED`, `DEFERRED`, `BLOCKED`.

Ưu tiên hiện hành: **nền tảng nghiên cứu AI Red Team bằng mô phỏng và benchmark tái lập**, theo [context](PROJECT_CONTEXT.md) và [plan](PROJECT_PLAN.md). Đợt tài liệu chỉ chỉnh ba file governance; không đổi task IDs/status/dependencies, không cấp runtime approval.

### Việc cần làm tiếp

1. Hoàn thiện episode mô phỏng nhỏ và nối RULE/random đối chứng qua cùng observation/action/gate/evidence boundary (RT-04, phần tích hợp RT-05).
2. Tái lập bảng so sánh bằng scenario splits, seeds và budgets cố định; tái dùng log/hash/metrics/report hiện có. Chưa đóng RT-07 toàn phần khi thiếu RT-06.
3. Thêm từng LLM/RL/HYBRID sau baseline. Tạm ngừng mở rộng ecommerce, Oscar, dashboard và live range; giữ acceptance/pending work lịch sử.

Các trạng thái bên dưới là ledger đã ghi, gồm thay đổi đang có trong working tree; không phải chứng nhận mọi phần đã commit/review. `IMPLEMENTED` không đồng nghĩa `VALIDATED`. Không chép receipts sang context/plan. Xem [blockers hiện hành](#blockers) trước khi tái dùng claim cũ.

### Enterprise Red Team Planning backlog

Bảng RT là nguồn trạng thái/dependencies cho hướng nghiên cứu; mở khi cần chi tiết. Không nâng trạng thái trong đợt chuẩn hóa.

<details>
<summary>Trạng thái và acceptance RT-00–RT-07</summary>


Nguồn kế hoạch: `PLAN-ENTERPRISE-REDTEAM-001`, work package nhóm `RT-*` chuyển đổi trọng tâm sang **AI Attack Planning for Red Team under Partial Observability (Belief-State Planning)**. Kế thừa toàn bộ contracts, action catalog, safety gate và evidence framework hiện có; không thay đổi canonical task IDs `TASK-001..035` hoặc các validation lịch sử `SL-01..12`.

| Work package | Liên kết task nền | Trạng thái ban đầu | Phụ thuộc | Đầu ra và điều kiện chấp nhận |
|---|---|---|---|---|
| RT-00 | TASK-002, TASK-003 | `IMPLEMENTED` | Không | Enterprise Red Team Planning Rebaseline: Tranche tài liệu và quản trị. Ban hành ADR-014 (Belief State Architecture), cập nhật AGENTS.md sang allowlist theo task, rebaseline PROJECT_CONTEXT.md, PROJECT_PLAN.md, TASKS.md. Bảo toàn toàn bộ lịch sử foundation và evidence. Báo cáo checks, blockers và allowlist RT-01. |
| RT-01 | TASK-003, TASK-008, TASK-009 | `IMPLEMENTED` | RT-00 | Zero-Knowledge Boundary: Hoàn tất cả RT-01A (Ground Truth Physical Isolation) và RT-01B (Planner Visibility Boundary / Fog-of-War). Phân tách tuyệt đối Safety Scope khỏi Planner-Visible Scope. Automated boundary suites tests/boundary/ (16/16 tests PASS). |
| RT-02 | TASK-005, TASK-006, TASK-019 | `IMPLEMENTED` | RT-01 | Belief State: Hoàn tất cả RT-02A (Enterprise Observation Model: 15 fact types, provenance, credential/session opaque redaction) và RT-02B (Belief State Projection: deterministic projection, facts vs hypotheses hard boundary, access monotonicity, zero-knowledge isolation, tích hợp StateManager/KnowledgeStateStore/PlannerStateAdapter/StateSnapshot). Chưa review độc lập / VALIDATED. |
| RT-03 | TASK-004, TASK-012, TASK-013 | `IMPLEMENTED` | RT-01, RT-02 | Enterprise Action Model: Hoàn tất cả RT-03A (Generic TTP Action Contract) và RT-03B (Action Constraint Evaluator). Single canonical ActionConstraintEvaluator tại runtime/evaluators/action_evaluator.py. Thống nhất canonical access: NONE < FOOTHOLD < USER < PRIVILEGED < SYSTEM. Quarantined hypotheses. Historical access != active capability. Eligibility != Authorization. Chưa review độc lập / VALIDATED. |
| RT-04 | TASK-007, TASK-010, TASK-023 | `IMPLEMENTED` | RT-02, RT-03 | Simulation Backend: Hoàn tất cả RT-04A (Hidden Scenario & True-State Model), RT-04B (Transition & Observation Simulator), và RT-04C (Unified Episode Environment & Gymnasium Adapter: canonical EpisodeEnvironment lifecycle loop, Farama Gymnasium adapter, action masking, 16D belief state encoding, replay bit-for-bit determinism, legacy RL coexistence). Chưa review độc lập / VALIDATED. |
| RT-05 | TASK-020, TASK-021, TASK-022, TASK-027 | `IMPLEMENTED` | RT-04 | Planner Integration: Lớp tích hợp tập hoạch định chuẩn mực (Planner-Neutral Episode Integration Layer). Hoàn tất toàn bộ gói RT-05 gồm RT-05A (Common Planner Episode Interface & Rule Baseline), RT-05A1 (Benchmark Action-Space Normalization: 9 canonical generic benchmark actions), RT-05B (Pure LLM Belief-State Planner Baseline), RT-05C (Hybrid Belief-State Planner — Proposed Method: LLM semantic ranking + deterministic symbolic scoring -> fusion, HYBRID_SCORING_V1, SYMBOLIC_ONLY fallback, ablation readiness), và RT-05D (Benchmark Protocol & Methodology Freeze: đóng băng RULE_POLICY_V1, LLM_ATTACK_PLANNER_PROMPT_V1, HYBRID_SCORING_V1_FROZEN, weights hash, 12 kịch bản held-out H1–H12 độc lập với S1–S4 dev, seed manifest cố định, primary/secondary metrics machine-computable, tests/runtime/test_benchmark_protocol.py 14/14 PASS). Chưa review độc lập / VALIDATED. |
| RT-06 | TASK-011, TASK-012, TASK-013, TASK-014 | `IMPLEMENTED` | RT-04, RT-05 | Mini Enterprise Live Range & Docker Wire-Level Validation (RT-06 + RT-06V): Cyber-range multi-host doanh nghiệp thu nhỏ cô lập trên Docker Compose (4 bridge networks, internal: true segmentation, loopback ingress). Dùng chung executor, observation normalizer và belief projection với simulator. Tích hợp CentralizedSafetyGate, KillSwitch, pivot relay. Automated suites tests/runtime/test_live_validation_range.py (21 tests PASS) và tests/runtime/test_enterprise_docker_range.py (9 tests PASS). Chưa review độc lập / VALIDATED. |
| RT-07 | TASK-028, TASK-029, TASK-030, TASK-031 | `SPEC_ONLY` | RT-05, RT-06 | Experimental Evaluation: Bộ kịch bản đánh giá so sánh (benchmark suite) trên simulator và live range. Chấm điểm planner dựa trên Ground Truth (cô lập trong evaluation). Đo lường metrics: success rate, steps to goal, budget efficiency, belief accuracy vs true state. |

</details>

<details>
<summary>Bảng TASK-001–TASK-035 và phạm vi baseline đã ghi</summary>

Tasks 001-010 are `VALIDATED` by foundation evidence `EV-FOUNDATION-001-001` through `EV-FOUNDATION-001-004`. TASK-011 through TASK-014 are `VALIDATED` for local Docker runtime slice by RUNTIME-004 evidence and approved review; scope excludes public deployment, planner validation, and external tool execution. TASK-015 is `IMPLEMENTED` for offline discovery report import/observations, with related discovery implementation in SL-08; TASK-016 is `IMPLEMENTED` for the offline JSON parser/safety wrapper; TASK-017 is `IMPLEMENTED` for the offline Nuclei report parser/safety wrapper. These statuses do not close acceptance/review or validate external-tool execution. See the TASK-015/016/017 implementation states below. TASK-018 is `IMPLEMENTED` for the current offline Nuclei normalization extension, pending independent review and durable evidence integration. TASK-019 is `IMPLEMENTED` for the offline SQLite knowledge-state store, pending repository gate, independent review and consumer/evidence integration. Earlier TASK-018/019 subsets retain historical `VALIDATED` scope under perception evidence `EV-PERCEPTION-018-001` through `EV-PERCEPTION-019-003`; those receipts do not validate either new extension. TASK-020 is `IMPLEMENTED` for the offline Planner ABC/DTO/state-read adapter, pending repository gate, independent review and consumer/evidence integration. TASK-021 is `IMPLEMENTED` for the offline evidence-review rule baseline, pending repository gate, independent review and durable evidence/coordinator integration; full research baseline and scanner execution remain `UNRESOLVED`. TASK-022 is `IMPLEMENTED` for the offline LLM metadata evidence-review strategy, pending repository gate, independent review and provider/evidence/coordinator integration; real provider/model/tokenizer and runtime behavior remain `UNRESOLVED`. TASK-023 is `IMPLEMENTED` for offline Gymnasium replay only, pending repository gate, independent review and durable evidence/live integration. TASK-024 is `IMPLEMENTED` for the standalone offline metadata-review reward scorer and tests, pending independent review, config acceptance and environment/evidence integration; the repository-checker blocker is resolved by the validator repair below. TASK-025 is `IMPLEMENTED` for offline Q-learning replay as recorded in its table row and receipts below. TASK-027 is `IMPLEMENTED` for the offline hybrid routing reference and metadata handoff design, pending repository gate, independent review and adapter/history/evidence integration; full hybrid runtime remains `SPEC_ONLY`. Tasks 028-031 and 033-035 remain `SPEC_ONLY`. Tasks 026 and 032 remain `DEFERRED`; the Task-026 preparatory reward/mask wrapper and offline evaluation protocol are `IMPLEMENTED` as a subset, pending repository gate, independent review and learned-model/evidence integration. No DQN/PPO result claim exists.

| ID | Descriptive name | Status | Dependencies |
|---|---|---|---|
| TASK-001 | Foundation validator | `VALIDATED` | none |
| TASK-002 | Root governance docs | `VALIDATED` | TASK-001 |
| TASK-003 | Safety contracts | `VALIDATED` | TASK-001 |
| TASK-004 | Action catalog | `VALIDATED` | TASK-003 |
| TASK-005 | State contract | `VALIDATED` | TASK-001 |
| TASK-006 | Observation contract | `VALIDATED` | TASK-001 |
| TASK-007 | Evidence contract | `VALIDATED` | TASK-001 |
| TASK-008 | Scenario contract | `VALIDATED` | TASK-001, TASK-003 |
| TASK-009 | Ground-truth contract | `VALIDATED` | TASK-008 |
| TASK-010 | Experiment contract | `VALIDATED` | TASK-007, TASK-008 |
| TASK-011 | Cyber range network | `VALIDATED` | TASK-003 |
| TASK-012 | Web target A | `VALIDATED` | TASK-011 |
| TASK-013 | Web target B | `VALIDATED` | TASK-011 |
| TASK-014 | Clean control target | `VALIDATED` | TASK-011 |
| TASK-015 | Discovery adapter | `IMPLEMENTED` | TASK-004, TASK-006, TASK-011 |
| TASK-016 | ZAP adapter | `IMPLEMENTED` | TASK-004, TASK-006, TASK-011 |
| TASK-017 | Nuclei adapter | `IMPLEMENTED` | TASK-004, TASK-006, TASK-011 |
| TASK-018 | Observation normalizer | `IMPLEMENTED` | TASK-006, TASK-015 |
| TASK-019 | Knowledge-state store | `IMPLEMENTED` | TASK-005, TASK-018 |
| TASK-020 | Planner interface | `IMPLEMENTED` | TASK-004, TASK-005, TASK-019 |
| TASK-021 | Rule-based planner | `IMPLEMENTED` | TASK-020 |
| TASK-022 | LLM planner | `IMPLEMENTED` | TASK-020, TASK-003 |
| TASK-023 | RL environment | `IMPLEMENTED` | TASK-004, TASK-005, TASK-006, TASK-009 |
| TASK-024 | Reward model | `IMPLEMENTED` | TASK-023 |
| TASK-025 | Q-learning baseline | `IMPLEMENTED` | TASK-023, TASK-024 |
| TASK-026 | DQN/PPO candidate | `DEFERRED` | TASK-023, TASK-024 |
| TASK-027 | Hybrid planner | `IMPLEMENTED` | TASK-021, TASK-022, TASK-025 |
| TASK-028 | Experiment runner | `SPEC_ONLY` | TASK-010, TASK-020 |
| TASK-029 | Metrics engine | `SPEC_ONLY` | TASK-009, TASK-028 |
| TASK-030 | Held-out evaluation | `SPEC_ONLY` | TASK-028, TASK-029 |
| TASK-031 | Statistical analysis | `SPEC_ONLY` | TASK-030 |
| TASK-032 | Dashboard | `DEFERRED` | TASK-028, TASK-029 |
| TASK-033 | Report artifact generator | `SPEC_ONLY` | TASK-029 |
| TASK-034 | Reproducibility package | `SPEC_ONLY` | TASK-030, TASK-031, TASK-033 |
| TASK-035 | Final foundation audit | `SPEC_ONLY` | all-required |

</details>

## ShopLab/PTES implementation backlog

Baseline Web/ShopLab/Oscar được giữ để tra cứu. Các chỉ dẫn “hướng hiện hành” trong khối lưu giữ sau thuộc roadmap cũ; ưu tiên hiện tại theo plan ở trên. Không chuyển validation giữa source/target hoặc tự đóng acceptance còn thiếu.

<details>
<summary>Bảng SL-01–SL-12, acceptance và hướng Web/Oscar trước tái định hướng</summary>


Nguồn kế hoạch: `PLAN-SHOPLAB-PTES-001` / `SHOPLAB-PTES-001`, xem [PROJECT_PLAN.md](PROJECT_PLAN.md). Người dùng đã mở phạm vi cập nhật tài liệu/task; không cấp per-run approval hoặc quyền sửa contracts/catalog/evidence. Giữ TASK-001–035 IDs/dependencies và các validation lịch sử; theo yêu cầu người dùng, cập nhật TASK-015/016/017 thành `IMPLEMENTED` trong phạm vi mô tả bên dưới, không tự review hoặc nâng validation. `SL-*` là work packages bổ sung, không thay thế hoặc tạo lại canonical task IDs.

SL-01 đã đạt acceptance criteria cho baseline fixture/mock; SL-02 đã đạt acceptance S01–S07 và handoff restore coordination trong phạm vi offline/SQLite temp được duyệt. Cả hai có required checks PASS, deterministic gate PASS và review độc lập `FINAL / APPROVE` đã được xác minh. SL-02 dùng connection riêng theo service, explicit transactions và schema version 1 fail closed. Các kết quả này không chứng nhận runtime, restore thực tế, sản phẩm hoàn chỉnh hoặc SL-03–SL-12. Trạng thái work package dựa trên acceptance và phạm vi review, không chỉ có file hoặc một phần code.

| Work package | Liên kết task nền | Trạng thái | Phụ thuộc | Đầu ra và điều kiện chấp nhận |
|---|---|---|---|---|
| [SL-01](docs/task-specs/SL-01-baseline-checks.md) | TASK-011, TASK-014 | `VALIDATED` | Không | Baseline checks: 70 tests PASS, AST 6 files PASS, scaffold checker/gate PASS; review độc lập FINAL / APPROVE đã xác minh; chỉ fixture/mock và SQLite temp, không runtime evidence |
| [SL-02](docs/task-specs/SL-02-storage-lifecycle.md) | TASK-011 | `VALIDATED` | [SL-01](docs/task-specs/SL-01-baseline-checks.md) | S01–S07 offline/SQLite temp và restore coordination handoff: 90 regression tests PASS, AST 2 files/checker/gate PASS; review R1 FINAL / APPROVE đã xác minh. S08 restore thực tế/session invalidation và Docker durability chưa chạy, thuộc SL-03/SL-07 |
| [SL-03](docs/task-specs/SL-03-auth-authorization.md) | TASK-003, TASK-011 | `IMPLEMENTED` | SL-01, SL-02 | Auth/session/CSRF/ownership offline: 114 tests PASS, AST 3 files/checker/gate PASS; đã tự review và sửa hai findings, chưa có independent review APPROVE, không runtime validation |
| [SL-04](docs/task-specs/SL-04-cart-checkout.md) | TASK-011 | `IMPLEMENTED` | SL-02, SL-03 | Catalog/cart/checkout atomic transaction, stock decrement, owner-scoped idempotency, USD integer minor units, decoupled post-commit invoice: 13 checkout tests PASS, 65 ecommerce tests PASS; offline fixture/mock, chưa independent approval |
| [SL-05](docs/task-specs/SL-05-orders-reviews.md) | TASK-011 | `IMPLEMENTED` | SL-03, SL-04 | Đơn hàng, chi tiết snapshot, IDOR protection (404), data minimization trên order API, hóa đơn lab notice kèm fallback tạo on-demand từ DB, đánh giá sản phẩm (1-5 sao, plain text <= 4000 ký tự), stored XSS HTML escaping: 16 orders/reviews tests PASS; offline fixture/mock, chưa independent approval |
| [SL-06](docs/task-specs/SL-06-product-admin.md) | TASK-003, TASK-011 | `IMPLEMENTED` | SL-03, SL-04, SL-05 | Admin backoffice phân quyền server-side (403 regular user), máy trạng thái forward-only (pending -> processing/cancelled, processing/completed -> shipped, shipped -> delivered, delivered terminal), chính sách hủy đơn nghiêm ngặt (chỉ pending), soft-archive sản phẩm (product_archives), audit log (admin_activity_log): 14 admin tests PASS; offline fixture/mock, chưa independent approval |
| [SL-07](docs/task-specs/SL-07-lab-runtime.md) | TASK-011, TASK-014 | `IMPLEMENTED` | SL-02, SL-03, SL-04, SL-05, SL-06 | Docker Compose lab cô lập (internal: true, không publish port target), Gateway reverse proxy loopback ingress (127.0.0.1:18088:8080), named volume persistence (/app/data), live Docker runtime verification (verify_live_docker.py: health, full flow, IDOR isolation, restart, replacement, failure 502, baseline restore, bounded teardown) ALL 8/8 PASS; 17 gateway E2E tests PASS; chưa independent approval |
| [SL-08](docs/task-specs/SL-08-discovery-safety.md) | TASK-003, TASK-004, TASK-015, TASK-018, TASK-019 | `IMPLEMENTED` | [SL-07](docs/task-specs/SL-07-lab-runtime.md) | Observation-driven discovery (BFS links, forms metadata-only), centralized safety gate (allowlist intersection, budget, rate, kill switch, dynamic TOCTOU revocation), durable recorder (atomic write, fsync, fail-closed): 7 preflight tests E01–E07 PASS, 9 safety tests D01–D09 PASS, live Docker verification 7/7 pha PASS; chưa independent approval |
| [SL-09](docs/task-specs/SL-09-observation-planner.md) | TASK-020, TASK-021, TASK-022 | `IMPLEMENTED` | [SL-08](docs/task-specs/SL-08-discovery-safety.md) | State-manager integration (idempotent, conflict detection, minimized prompt), schema-bound proposals (plan.schema.json), explicit mode provenance (RULE/LLM/MOCK), strict fallback handling, zero-dispatch gate eval: 13 unit tests P01–P08 & authority PASS, live Docker verification 8/8 pha PASS; Autonomous Closed-Loop Runner (runtime/autonomous_runner.py) đạt 12/12 tests A01–A12 PASS, live verification PASS (RUN-AUTONOMOUS-LIVE-1791708234); Autonomous Pentest Loop với Bounded Safe Verification (runtime/capability_registry.py) khắc phục 3 review blockers F-01/F-02/F-03 đạt 18/18 tests V01–V18 PASS, live pentest PASS (RUN-AUTONOMOUS-PENTEST-1791723996); chưa independent approval |
| [SL-10](docs/task-specs/SL-10-ptes-orchestration.md) | TASK-020, TASK-028, TASK-033 | `IMPLEMENTED` | [SL-08](docs/task-specs/SL-08-discovery-safety.md), [SL-09](docs/task-specs/SL-09-observation-planner.md) | PTES coordinator điều phối 7 phase (exit criteria, honest transitions Phase 5 BLOCKED, Phase 6 NOT_RUN, Phase 7 COMPLETED): 8 unit tests T01–T08 PASS, live Docker verification 7/7 phase PASS; chưa independent approval |
| [SL-11](docs/task-specs/SL-11-evidence-reporting.md) | TASK-007, TASK-028, TASK-029, TASK-033, TASK-034 | `IMPLEMENTED` | [SL-07](docs/task-specs/SL-07-lab-runtime.md), [SL-10](docs/task-specs/SL-10-ptes-orchestration.md) | Immutable evidence packaging, report generator, zero-network replay verifier, root containment, non-recurrence lock: 14 tests E01–E09 & B01–B05 PASS, authoritative run `RUN-SL11-HANDOFF-20261011/`, ghi nhận sai lệch lịch sử; chưa independent approval |
| [SL-12](docs/task-specs/SL-12-verification-handoff.md) | TASK-030, TASK-034, TASK-035 | `SPEC_ONLY` | SL-07, SL-08, SL-09, SL-10, SL-11 | Pre-review gate HANDOFF_BLOCKED do validate_scaffold phát hiện vi phạm schema tại scripts/demo/demo-output/... từ phiên khác; khóa build ID, run ID, CURRENT_REVIEW_SOURCE_MANIFEST, 18 checks PASS; dừng chờ chỉ thị scope |

Đã có 12 đặc tả chi tiết được liên kết ở bảng trên; xem [chỉ mục và lifecycle contracts](docs/task-specs/index.md#shoplab-task-contracts). Mỗi task gồm phạm vi, interfaces/data contracts, implementation/safety requirements, test cases, acceptance, evidence và failure conditions. Sự tồn tại của đặc tả không nâng trạng thái implementation/runtime; SL-01/SL-02 chỉ có validation trong phạm vi checks/review được ghi bên dưới. Trước live dispatch SL-07–10 phải có approved recorder/destination và failure-stop checks; SL-11 không cho phép trì hoãn ghi evidence đến cuối run.

Hướng hiện hành: **thẩm định/pin/configuration upstream → fit-gap/acceptance SL-04–06 → approved runtime SL-07 → SL-08 → SL-09/SL-10 → SL-11 → SL-12**. SL-01–03 giữ là lịch sử ShopLab, không chuyển PASS sang Oscar hoặc bỏ pending independent approval SL-03. IDs/dependencies trong bảng giữ nguyên; dependency equivalence cho target mới cần review explicit, không tự coi fulfilled bằng upstream. TASK-026 và TASK-032 giữ `DEFERRED`; không mở RL training, dashboard hoặc metrics claims.

### Cập nhật theo web target snapshot

Các specs [TASK-011](docs/task-specs/TASK-011-cyber-range-network.md), [TASK-012](docs/task-specs/TASK-012-web-target-a.md), [TASK-013](docs/task-specs/TASK-013-web-target-b.md), [TASK-014](docs/task-specs/TASK-014-clean-control-target.md), [TASK-018](docs/task-specs/TASK-018-observation-normalizer.md) và [TASK-019](docs/task-specs/TASK-019-knowledge-state-store.md) phân loại phần giữ nguyên, impact assessment và receipts mới khi web snapshot đổi. Bảng trạng thái/dependencies và evidence lịch sử ở trên không đổi; validation cũ không áp dụng tự động cho snapshot mới. TARGETS-012/013/014 là evidence target riêng theo phạm vi lịch sử; linkage RUNTIME-004 cần đối chiếu riêng trước tái sử dụng. Instance scenario/ground-truth/experiment version theo snapshot tại TASK-008–010; ground truth chỉ evaluation.

</details>

## Checks and observed implementation state

Giữ nguyên receipts đã ghi, gồm phần RT đang triển khai, để bảo toàn commands, hashes, limitations và các liên kết cũ. Từ “hiện tại/tiếp theo” trong receipt áp dụng cho snapshot lúc ghi; không thay kết quả gate/review của source mới. Không tái xác nhận receipts lịch sử trong đợt tài liệu này.

<details>
<summary>Receipts, kiểm chứng và handoff đã ghi trước đợt chuẩn hóa</summary>


### RT-00 — Enterprise Red Team Planning Rebaseline

`IMPLEMENTED` cho tranche tài liệu và quản trị theo yêu cầu tái chuẩn hóa kiến trúc Red Team sang **AI Attack Planning under Partial Observability (Belief-State Planning)**; chưa `VALIDATED`.
- Cập nhật `AGENTS.md`: Chuyển từ cơ chế fixed global code allowlist cũ sang cơ chế khai báo explicit allowed paths riêng theo từng task/tranche; cấm sửa ngoài scope được giao.
- Cập nhật `PROJECT_CONTEXT.md`: Tái định vị bài toán nghiên cứu cốt lõi sang AI Attack Planning under Partial Observability / Belief-State Planning. Xác lập ranh giới Zero-Knowledge Boundary (Planner không nhận ground truth, global topology, full target allowlist, source code, hidden credentials, defender state). Khẳng định Safety Gate giữ thẩm quyền tối cao.
- Cập nhật `PROJECT_PLAN.md`: Bổ sung lộ trình `RT-01` .. `RT-07` kế thừa toàn bộ nền tảng hiện có; nhấn mạnh quy tắc bắt buộc: Simulation Backend (`RT-04`) phải đi trước và được kiểm chứng độc lập trước khi mở rộng sang Mini Enterprise Live Range (`RT-06`).
- Tạo mới `ADR-014`: `docs/adr/ADR-014-enterprise-red-team-belief-state.md` quyết định kiến trúc phân tách ranh giới True State (chỉ thuộc simulator/evaluator), Belief State (chỉ từ observations), Ground Truth (chỉ thuộc evaluation), Safety Scope != Planner-Visible Scope (Planner không nhận full target allowlist), mô hình điều khiển tam giác (Planner proposal -> Safety Gate authorization -> Bounded Executor execution), và thống nhất contract giữa simulator và live range.
- Cập nhật `TASKS.md`: Khởi tạo backlog nhóm `Enterprise Red Team Planning` (`RT-00` .. `RT-07`) với đầy đủ dependencies, initial statuses, và acceptance criteria; bảo toàn toàn bộ mã định danh, trạng thái và bằng chứng lịch sử (`TASK-001..035`, `SL-01..12`).

### RT-00A — Governance Validator Alignment

`IMPLEMENTED` cho tranche đồng bộ validator governance; chưa `VALIDATED`.
- Refactor ADR validation trong `scripts/validation/validate_scaffold.py`: thay thế hardcoded set `ADRS` (trước đây giới hạn ở 13 ADRs) bằng kiểm tra invariant tổng quát:
  1. Tên tệp ADR phải tuân thủ định dạng `ADR-NNN-<slug>.md` (`ADR_FILENAME_PATTERN`).
  2. Mã số ADR phải là duy nhất (phát hiện và chặn duplicate ADR IDs).
  3. Dãy số ADR phải liên tục (contiguous) bắt đầu từ `ADR-001` tới ID lớn nhất hiện có mà không hard-code giới hạn trên.
  4. Bắt buộc phát hiện malformed filenames, missing IDs trong chuỗi, và duy trì các kiểm tra cấu trúc H1/H2 template (`ADR_HEADINGS`).
- Cập nhật bộ unit test `tests/scaffold/test_validator.py`: thay thế `test_exact_adr_manifest` bằng 5 unit tests toàn diện (`test_adr_filename_pattern`, `test_adr_invariants_contiguous_and_unique`, `test_adr_invariants_detect_duplicates`, `test_adr_invariants_detect_missing_sequence`, `test_adr_invariants_detect_malformed_filename`) đạt 5/5 PASS.
- Xác thực: `ADR-014` không còn bị báo `extraneous`; không tạo regression cho `ADR-001..013`. Toàn bộ 52/53 unit tests của scaffold suite PASS (1 fail duy nhất do pre-existing blockers của workspace).

### RT-01A — Ground Truth Physical Isolation

`IMPLEMENTED` cho tranche tách ly vật lý Ground Truth và thiết lập rào chắn Zero-Knowledge tự động; chưa `VALIDATED`.
- Di chuyển canonical Ground Truth schema từ `agent/planner/contracts/ground-truth.schema.json` sang vị trí canonical trong Evaluation domain: `evaluation/ground_truth/ground-truth.schema.json`. Xóa hoàn toàn file schema khỏi `agent/planner/contracts/` để bảo đảm zero copies trong Planner domain.
- Cập nhật manifest liên kết `evaluation/ground-truth/schema-link.json`: trỏ `ground_truth_schema` tới `evaluation/ground_truth/ground-truth.schema.json` và duy trì `runtime_consumers: []`.
- Cập nhật validator `scripts/validation/validate_scaffold.py`: khai báo `GROUND_TRUTH_SCHEMA_PATH`, tải 9 schemas planner từ `agent/planner/contracts` cùng 1 schema evaluation ground-truth; loại bỏ ngoại lệ miễn trừ `path.name == "ground-truth.schema.json"` khỏi kiểm tra `runtime_roots` để fail-closed nếu có bất kỳ file ground-truth nào xuất hiện trong runtime/agent; kiểm tra ràng buộc `schema-link.json` trỏ đúng schema canonical.
- Cập nhật `tests/contracts/test_contracts.py` (đã được phê duyệt mở rộng allowlist): kiểm tra 9 planner schemas trong `agent/planner/contracts`, 1 canonical schema trong `evaluation/ground_truth/`, xác nhận `agent/planner/contracts/ground-truth.schema.json` không tồn tại, và kiểm tra tính toàn vẹn closed Draft 2020-12 object trên toàn bộ 10 contracts (12/12 tests PASS).
- Xây dựng bộ test suite boundary tự động `tests/boundary/test_ground_truth_boundary.py` (8/8 tests PASS) chứng minh các bất biến:
  1. *Physical Isolation*: Schema Ground Truth chỉ nằm ở Evaluation domain, không còn ở Planner contracts.
  2. *Planner Boundary*: `runtime/planners/**` và `agent/planner/**` không import, load hoặc reference Ground Truth (AST scan).
  3. *State Boundary*: `agent/memory/**` và `runtime/state/**` không đọc hoặc lưu trữ Ground Truth; `StateSnapshot.from_state` từ chối fail-closed mọi state chứa truth keys.
  4. *Runtime Orchestration Boundary*: `runtime/orchestration/**` không đưa ground truth vào planner input; `PlanningInput` không chứa accessors/thuộc tính ground truth.
  5. *Evaluation Exception*: Evaluation domain được phép load canonical schema và validate dữ liệu `sample.json` sạch sẽ.
  6. *No Source Leakage*: Các lớp planner không chứa bất kỳ API/helper nào để truy vấn ground truth hoặc oracle ngầm.
  7. *Active Regression Detection*: Bộ quét AST chủ động phát hiện và chặn đứng các vi phạm import/call mới trong mã nguồn planner/state.
- Receipts kiểm thử:
  - `tests/boundary/test_ground_truth_boundary.py`: 8 tests PASS (exit code 0).
  - `tests/contracts/test_contracts.py`: 12 tests PASS (exit code 0).
  - `tests/safety/test_root_types.py`: 13 tests PASS (exit code 0).
  - `tests/evaluation/test_metrics.py`: 8 tests PASS (exit code 0).
  - `tests/runtime/test_planner_interface.py`: 16 tests PASS (exit code 0).
  - `tests/runtime/test_observed_planner.py`: 13 tests PASS (exit code 0).
  - `tests/runtime/test_rule_based_planner.py`: 28 tests PASS (exit code 0).
  - `tests/runtime/test_llm_planner.py`: 31 tests PASS (exit code 0).
  - `tests/runtime/test_hybrid_router.py`: 20 tests PASS (exit code 0).
  - `tests/runtime/test_autonomous_runner.py` & `test_autonomous_pentest.py`: 34 tests PASS (exit code 0).
  - `git diff --check`: PASS (exit code 0).
  - `scripts/validation/validate_scaffold.py`: không tạo thêm lỗi mới (0 regressions); bảo toàn nguyên trạng các blocker pre-existing của workspace (.demo-session.json, missing fixtures, .pyc artifacts).

### TASK-027 — Router tham chiếu hybrid ngoại tuyến

`IMPLEMENTED` cho reference routing policy và bản thiết kế handoff, cập nhật ngày
2026-10-12 theo yêu cầu người dùng; chưa `VALIDATED`.
[Router](runtime/planners/hybrid_router.py), [thiết kế và receipts](docs/implementation/hybrid_router.md),
[tests](tests/runtime/test_hybrid_router.py) chỉ xử lý metadata review với
`ACTION-PLAN-003`. Rule-first, handoff khi no match/FAILURE/ERROR/PARTIAL,
fingerprint candidate và context-bound history chống lặp; DENIED, missing feedback
evidence, scope thu hồi, budget/quota/no progress đều dừng. Snapshot/history không
bị router sửa, budget không trừ lần hai. Router trả dữ liệu, không gọi strategy,
provider, executor hoặc sửa evidence.

Receipts triển khai: 20 focused + 28 Task 20 + 28 Task 21 + 31 Task 22 tests PASS
(107 tests, từng suite exit 0); AST 2 files, 19 links và whitespace PASS. Source
SHA-256 của router/tests khớp receipts khi đồng bộ; không chạy lại suites trong
lần cập nhật tài liệu. Gate triển khai exit 1 với 27 lỗi ngoài scope, 0 lỗi thuộc
ba files implementation. Checks đồng bộ tài liệu/gate có receipts riêng tại
runtime/hybrid_router.md; không chuyển focused PASS thành repository PASS.

Handoff `HANDOFF_BLOCKED`, blocker `REPOSITORY_CHECKER_FAILED_OUTSIDE_SCOPE`.
Pending: xử lý repository blockers trong scope riêng → review độc lập → scope
LLM handoff adapter, cross-backend completion, history/audit concurrency và
recorder/coordinator/gate integration. Task 22 hiện dừng khi nhận RULE feedback
qua replan trực tiếp; không relabel để vượt kiểm tra. Adapter/provider/tokenizer,
durable evidence/reference integrity, Task 25 arbitration và full hybrid backend
còn `UNRESOLVED`; full hybrid runtime giữ `SPEC_ONLY`. Status/dependencies của
34 task khác giữ nguyên, TASK-026/032 vẫn `DEFERRED`. Không self-approve/finalize.

### TASK-026 — Chuẩn bị wrapper/protocol replay ngoại tuyến

Task toàn phần giữ `DEFERRED` theo AGENTS.md; cập nhật tài liệu/trạng thái chi tiết
ngày 2026-10-12 không mở DQN/PPO training. Phần chuẩn bị đã `IMPLEMENTED`, chưa
`VALIDATED`: [wrapper](runtime/evaluation/replay_wrappers.py) và
[evaluator](runtime/evaluation/offline_evaluation.py), cùng
[protocol/receipts](docs/implementation/offline_rl_protocol.md),
[wrapper tests](tests/runtime/test_replay_wrappers.py) và
[evaluation tests](tests/runtime/test_offline_evaluation.py).
Wrapper chấm Task 24 một lần sau commit, mask boolean không thay quyền của step,
normalization cố định và read age từ outcome đã quan sát. Hết ngân sách nội tại
được adapter coi terminal; cờ Task 23 gốc giữ trong info, source base không đổi.
Evaluator giữ failures trong denominator, từ chối split families/content trùng và
khóa N/budget/rate/seed/masking bằng protocol fingerprint.

Receipts phiên triển khai: 15 wrapper + 14 evaluator + 23 environment + 11 reward
và 19 Q-learning + 17 safety tests PASS (99 tests, mỗi suite exit 0);
AST/example/document/link/whitespace PASS. Bốn source SHA-256 khớp receipts khi
đồng bộ; không chạy lại tests trong lần cập nhật này. Gate cuối phiên triển khai
exit 1: 27 lỗi ngoài năm paths implementation, 0 lỗi thuộc scope, gồm status READY
tại .demo-session.json và forbidden bytecode. Gate PASS trước đó được giữ như
receipt lịch sử. Kiểm tra docs/status/links và gate đồng bộ có receipt riêng tại
runtime/offline_rl_protocol.md; không chuyển 99 tests thành observed learned-policy
evaluation hoặc chứng minh runtime.

Handoff `HANDOFF_BLOCKED`, blocker `REPOSITORY_CHECKER_FAILED_OUTSIDE_SCOPE`.
Pending: xử lý artifacts ngoài scope trong task riêng → independent review reward
provenance/state/horizon/split/error denominator → scope dependency lock/SB3
compatibility và durable evidence/checkpoint. DQN/PPO model/training/checkpoint,
benchmark N=8/split 60/20/20 thực tế, library compatibility và evidence integration
còn `UNRESOLVED`; protocol đề xuất không phải benchmark đã chạy. Không nâng Task
028/030/032, không thay task IDs/dependencies, không self-approve/finalize.

### TASK-025 — Q-learning replay ngoại tuyến

`IMPLEMENTED` trong phạm vi baseline metadata replay, cập nhật theo yêu cầu người
dùng ngày 2026-10-12; chưa `VALIDATED`. [Agent/runner](runtime/evaluation/q_learning.py) dùng
Q-table thưa khởi tạo 0, epsilon-greedy theo action mask và cập nhật Bellman trên
state quan sát có ngân sách hữu hạn/read age. Chọn lại sau mỗi transition; scorer
Task 24 nhận đúng một outcome đã commit từ Task 23 cho mỗi bước. Không thay reward
trả về của Task 23. Empty mask dừng trước step; policy/audit của simulator giữ nguyên.

Receipts triển khai tại [runtime/q_learning.md](docs/implementation/q_learning.md): 19 focused
+ 23 environment + 11 reward regression tests PASS (53 tests, mỗi suite exit 0);
AST/example/whitespace/repository gate PASS, exit 0, 0 repository errors và 0 Task 25
errors. Bốn SHA-256 source hashes khớp khi đồng bộ tài liệu; không chạy lại suites
trong lần cập nhật này. Kiểm tra tài liệu/status/links và gate mới có receipt riêng.
Fixture một slot học được inventory → report → finish trong ba bước, return 1.27;
đây là kiểm thử tổng hợp, không phải held-out evaluation hoặc chứng minh tính tối ưu.

Pending handoff: review độc lập state encoding/reward provenance/finite-horizon
boundary/proposal policy; durable training evidence/checkpoint; calibration,
held-out evaluation, budget equivalence và full Task 20 planner integration.
Các phần này `UNRESOLVED`; không có checker blocker trong receipt triển khai này.
Task IDs/dependencies giữ nguyên; Task 26/32 giữ `DEFERRED`. Không tự approve,
finalize hoặc nâng `VALIDATED`; không cấp live training/dispatch approval.

### TASK-024 — Bộ chấm điểm đánh giá metadata ngoại tuyến

`IMPLEMENTED` trong phạm vi scorer độc lập theo yêu cầu cập nhật tài liệu/trạng thái
ngày 2026-10-12; chưa `VALIDATED`. [Hàm Python](runtime/evaluation/reward_model.py) chấm outcome
đóng do simulator tin cậy cung cấp, tách step/progress/penalty/completion. Phạt lặp,
rate/order/refusal và dừng sớm; không thưởng theo candidate, severity hoặc nhãn replan.
Scorer không thay reward trong Task 23. Runner Task 25 hiện gọi scorer riêng cho
replay training; full planner/executor và durable evidence integration còn chờ.

Receipts triển khai tại [runtime/reward_model.md](docs/implementation/reward_model.md): 11 focused
+ 23 Task 23 regression tests PASS (34 tests, mỗi suite exit 0); AST hai files,
local links và whitespace PASS. Source SHA-256 của scorer/tests đã đối chiếu khớp
khi cập nhật tài liệu; không chạy lại suites trong lần đồng bộ này. Gate triển khai
exit 1 với 613 lỗi ngoài scope, 0 lỗi thuộc ba paths Task 24; không suy runtime success.

Blocker `REPOSITORY_CHECKER_FAILED_OUTSIDE_SCOPE` đã được xử lý theo yêu cầu người dùng:
[validator repair và receipts](scripts/validation/README.md) ghi gate exit 0,
`SCAFFOLD VALID`, 0 lỗi. Receipt 613 lỗi ở trên là kết quả trước khi sửa, được giữ
nguyên; gate PASS không tự đóng acceptance hoặc nâng `VALIDATED`.
Pending: review độc lập trọng số/trusted-event boundary, scope tích hợp Task 23 và
config acceptance, evidence bền vững, hiệu chỉnh thực nghiệm và budget equivalence.
`configs/rl/reward.yaml` còn TBD, chưa được sửa hoặc chấp nhận; acceptance config/tests
của spec chưa đóng. Bộ phân loại báo cáo có nhãn chỉ là đề xuất, chưa triển khai.
Ground truth không thuộc planner observation/info; Task 25 `IMPLEMENTED` cho replay, Task 26/32
`DEFERRED`. Không tự approve/finalize hoặc nâng `VALIDATED`.

### TASK-023 — Gymnasium replay ngoại tuyến

`IMPLEMENTED` theo yêu cầu người dùng ngày 2026-10-12; chưa `VALIDATED`. Khung tại
[runtime/rl_environment.py](runtime/evaluation/rl_environment.py) có Discrete actions, Dict
observations, step/reset đúng Gymnasium, approval/allowlist/order/rate/budget mô phỏng,
refusal và audit metadata trong bộ nhớ giữ qua reset. Adapter đọc snapshot Task 19/20
không ghi store hoặc trừ lại StateManager budget. Chỉ replay metadata; không gọi scanner,
provider, executor hoặc mạng. Candidate không phải confirmed vulnerability; thiếu báo cáo
giữ unknown. Reward tích hợp trong Task 23 vẫn chỉ minh họa; Task 24 có scorer riêng
`IMPLEMENTED`; runner Task 25 dùng scorer riêng, không thay reward của environment.
Task 25 `IMPLEMENTED` cho replay ngoại tuyến, Task 26/32 giữ `DEFERRED`.

Receipts: 23 focused tests gồm check_env + 21 state-store + 28 planner-interface
regressions PASS (72 tests), mỗi suite exit 0. Dependency Python user site có Gymnasium
1.4.0; không đổi contracts/configuration/catalog/scenarios/evidence hoặc lịch sử.
Chi tiết, gate và pending handoff tại [runtime/rl_environment.md](docs/implementation/rl_environment.md).
Independent review, durable evidence, report authenticity/reference integrity và live
scanner/gate/executor/restore integration giữ `UNRESOLVED`; không suy runtime success.

Gate validate() exit 1 với 613 lỗi ngoài scope, 0 lỗi thuộc tám paths Task 23;
scoped AST/example/headings/82 local links/whitespace PASS. Handoff `HANDOFF_BLOCKED`,
blocker `REPOSITORY_CHECKER_FAILED_OUTSIDE_SCOPE`. Pending: xử lý repository blockers
trong scope riêng → independent review replay/state/budget/evidence boundary → scope
tích hợp được duyệt. Không tự approve/finalize hoặc nâng VALIDATED.

Đồng bộ tài liệu: source SHA-256 của environment, focused tests và dependency
declaration khớp receipts triển khai. Bảng 35 task IDs/status/dependencies giữ nguyên
trong lần đồng bộ Task 23; khi đó Task 23 `IMPLEMENTED`, Task 24 có scorer riêng,
Task 25 `SPEC_ONLY`, Task 26/32 `DEFERRED`. Hiện Task 25 `IMPLEMENTED` cho replay
như mục riêng ở trên; receipt đồng bộ Task 23 vẫn giữ nguyên phạm vi lịch sử.
Không chạy lại 72 tests, không chuyển receipt offline thành validation runtime.
Checks lần đồng bộ: scoped headings và 89 local links PASS, source hashes khớp,
whitespace/git diff --check PASS; mỗi check exit 0. Repository gate không chạy lại;
613 lỗi ngoài scope là receipt triển khai được giữ nguyên, không phải đo mới.


### TASK-015 — discovery report import và observations ngoại tuyến

`IMPLEMENTED` trong phạm vi importer/observations offline; chưa `VALIDATED` hoặc hoàn tất acceptance/handoff. `runtime/discovery_report_importer.py` nhập báo cáo `httpx-jsonl`/`whatweb-json`, kiểm tra input root, identity, bounds, target/action approval và canonical policy; ghi evidence và tạo observations tùy chọn với provenance `IMPORTED_OFFLINE`. Metadata khai báo vẫn chưa xác minh; external-tool execution giữ `UNRESOLVED`. Các bước review mô phỏng có provenance `SIMULATED_FIXTURE`, không phải planner/provider/executor runtime.

SL-08 cung cấp discovery engine/gate/recorder liên quan; trạng thái và receipts riêng của SL-08 không tự nghiệm thu toàn TASK-015. `tools/adapters/discovery/adapter.py` còn trả dữ liệu mô phỏng, không dùng output `SUCCESS` của adapter này để chứng minh discovery thật. Chưa xác minh report từ công cụ thật hoặc independent approval cho snapshot importer hiện tại.

| Command/check cập nhật trạng thái ngày 2026-10-11 | Exit code | Observed result |
|---|---|---|
| `python -B -m unittest discover -s tests/runtime -p test_discovery_report_importer.py -v` | 0 | 45 tests PASS; fixtures/temp directories, policy/evidence failures, no network/process/gate dispatch và observations/review simulation offline |

Pending handoff: đối chiếu acceptance TASK-015 với importer và SL-08, khóa source/receipts và review độc lập; external-tool execution vẫn chưa xác minh. Lần cập nhật này chỉ sửa tài liệu, không chạy live discovery hoặc công cụ ngoài.

### TASK-017 — parser và safety wrapper Nuclei ngoại tuyến

`IMPLEMENTED` theo yêu cầu người dùng trong phạm vi nhập báo cáo ngoại tuyến; chưa `VALIDATED`. Các file triển khai là `tools/adapters/nuclei/adapter.py`, `tools/parsers/nuclei_parser.py`, `tools/adapters/nuclei/README.md`, `tests/unit/test_nuclei_adapter_offline.py` và phần Nuclei trong `tests/unit/test_tool_adapters.py`.

`import_report` nhận JSON list hoặc JSONL đã nạp vào bộ nhớ, kiểm target/HTTP origin và template ID cụ thể bằng manifest ngoại tuyến mặc định rỗng; validate all-or-nothing, giới hạn byte/depth/records và quota/rate theo instance. Trả candidates theo scanner-result contract với `endpoint_id=null`, `confidence=0.0` nghĩa là chưa đánh giá độ tin cậy. Không suy confidence từ severity, không tạo confirmed finding hoặc scan observation từ import. `execute` luôn `DENIED` với facts/results rỗng; không scanner/process/network hoặc ghi evidence.

Receipts thực tế ngày 2026-10-11 của phiên triển khai, không phải checks mới của lần sửa trạng thái:

| Command/check | Exit code | Observed result |
|---|---|---|
| `python -B -m unittest discover -s tests/unit -p test_nuclei_adapter_offline.py -v` | 0 | 28 tests PASS |
| `python -B -m unittest discover -s tests/unit -p test_tool_adapters.py -v` | 0 | 27 tests PASS |
| `python -B -m unittest discover -s tests/safety -p test_safety.py -v` | 0 | 17 tests PASS |
| `python -B scripts/validation/validate_scaffold.py` | 1 | Lần cuối của phiên triển khai: 643 repository errors, 0 errors thuộc năm paths TASK-017 |

AST bốn Python files và scoped diff check PASS trong phiên triển khai. Repository gate vẫn blocked do normalizer schemas, dashboard/dependencies, forbidden artifacts và report fields/statuses ngoài scope. Tương thích report scanner thật, version/provenance, durable evidence và independent review còn `UNRESOLVED`; không dùng 72 tests offline làm bằng chứng runtime success. Pending handoff TASK-018: nhận candidates theo contract, giữ evidence riêng trước cập nhật state; không diễn giải confidence chưa đánh giá hoặc report rỗng thành kết quả âm tính. Chi tiết tại [README](tools/adapters/nuclei/README.md). Không xóa file, đổi contract hoặc mở quyền thực thi khi cập nhật trạng thái.

### TASK-018 — Observation Normalizer và giao tiếp Nuclei ngoại tuyến

`IMPLEMENTED` cho phạm vi hiện hành theo yêu cầu người dùng chuyển lại trạng thái. Phần normalizer trước đây giữ ghi nhận `VALIDATED` trong phạm vi perception evidence lịch sử; không sửa evidence hoặc áp dụng validation cũ cho phần mở rộng Nuclei.

API `ObservationNormalizer.normalize_nuclei` nhận candidates tối giản của TASK-017 hoặc raw JSON/JSONL, tái sử dụng parser TASK-017, kiểm canonical target và trusted origin/template manifest, redact và coalesce facts nhưng giữ record hashes/linkage trong provenance. Đầu ra dùng observation contract hiện có và hai schema giao tiếp riêng; chỉ tạo `CANDIDATE_FINDING`, giữ `confidence=0.0` là chưa đánh giá. Import thành công tạo observation `PARTIAL`, không chứng minh scanner execution hoặc absence of vulnerabilities.

Receipts phiên triển khai ngày 2026-10-11: 141 tests PASS, gồm 24 integration TASK-017/018, 33 normalizer, 28 Nuclei adapter, 27 shared adapters, 12 contracts và 17 safety; mỗi suite exit 0. AST/JSON Schema/scoped whitespace checks PASS. Lần checker cuối của phiên triển khai exit 1 với 652 repository errors, 0 errors thuộc TASK-018; đây là receipts đã quan sát, không phải lần chạy lại khi sửa trạng thái. Exact commands, source hashes và giới hạn tại [Interface Contract](agent/perception/normalizers/NUCLEI_INTERFACE.md).

Handoff vẫn chờ repository gate và independent review. Pinned report Nuclei thật, durable evidence-before-state integration, replay/conflict handling ở state và runtime giữ `UNRESOLVED`. Cập nhật trạng thái không tự approve, finalize, đổi contracts/catalog/configuration hoặc mở scanner execution. Pending handoff: review giao tiếp và source snapshot, xử lý checker blockers trong scope riêng, rồi tích hợp recorder đã được duyệt trước state update. Không xóa file hoặc sửa evidence lịch sử.

### TASK-019 — Knowledge-state store SQLite ngoại tuyến

Trạng thái hiện hành cập nhật ngày 2026-10-12 là `IMPLEMENTED` cho phần bổ sung SQLite theo yêu cầu người dùng; chưa `VALIDATED`. StateManager/KnowledgeRepository và perception evidence lịch sử giữ nguyên phạm vi validation cũ, không áp dụng cho extension mới.

Ba file triển khai: `runtime/knowledge_state_store.py`, `runtime/knowledge_state_store.md`, `tests/runtime/test_knowledge_state_store.py`. Store lưu observations append-only và cập nhật facts/state snapshot trong cùng transaction; index hỗ trợ truy vấn theo subject/type/confidence, assets là view. Context tách run/session/episode; ingest validate UTC/schema/scope/redaction, idempotent retry không double-decrement, conflicting identities bị từ chối. StateManager là budget owner duy nhất; `reconstruct` kiểm hash và so snapshot với replay. Không nối store vào runner/planner/executor hoặc cấp quyền dispatch.

Receipts phiên triển khai ngày 2026-10-11: hai suite exit 0 với 21 tests SQLite mới và 39 tests API hiện có PASS; AST/diff/example checks PASS. Lượt checker cuối exit 1 với 656 repository errors, 0 errors thuộc ba paths Task 19. Đây là receipts lịch sử của phiên triển khai, không phải checks chạy lại khi cập nhật trạng thái. Ngày 2026-10-12, source SHA-256 của hai file Python được đối chiếu và khớp receipts. Exact commands, hashes, nguồn fixture/UTC, expected/observed và giới hạn tại [thiết kế và receipts Task 19](docs/implementation/knowledge_state_store.md).

Kiểm tra đồng bộ tài liệu ngày 2026-10-12: repository `validate()` exit 1, 656 errors và 0 errors thuộc năm tài liệu đã sửa; scoped document/link check exit 0, 59 local links hợp lệ; status/source hashes/whitespace check và scoped `git diff --check` PASS. Giữ riêng các receipts cập nhật này với suites triển khai ngày 2026-10-11; exact commands tại tài liệu thiết kế.

Handoff giữ `HANDOFF_BLOCKED` với blocker `REPOSITORY_CHECKER_FAILED`; chưa có independent review. Consumer/Normalizer integration, durable evidence binding, report thật, process/container restore và hiệu năng dữ liệu lớn giữ `UNRESOLVED`. Mỗi ingest còn replay history để tái dùng API StateManager; query đọc indexed projections/snapshot. Pending handoff: xử lý repository blockers trong scope riêng, review schema/identity/budget/provenance và compatibility trước integration. Cập nhật tài liệu không self-approve/finalize, thay contract/action semantics hoặc chứng minh runtime success.

### TASK-020 — Planner interface ngoại tuyến

Trạng thái cập nhật ngày 2026-10-12 là `IMPLEMENTED` cho ABC/DTO/state-read adapter theo yêu cầu người dùng; chưa `VALIDATED`. Ba artifacts: [planner_interface.py](runtime/planners/planner_interface.py), [thiết kế và receipts](docs/implementation/planner_interface.md), [focused tests](tests/runtime/test_planner_interface.py). plan/replan kiểm input/output chung; subclass implement strategy hooks. Snapshot/proposal immutable, identity theo run/session/episode và revision; schema/scope/objective, stop conditions và fallback provenance được kiểm. StateManager vẫn là budget owner duy nhất.

Receipts phiên triển khai ngày địa phương 2026-10-12: 28 focused tests + 21 Task 19 regression + 16 planner contract tests PASS (65 tests, từng suite exit 0); AST/example/whitespace checks PASS. Repository checker exit 1 với 656 errors, 0 errors trong ba paths Task 20. Source HEAD/hashes, UTC, exact commands và expected/observed tại tài liệu receipts. Cập nhật trạng thái chỉ đối chiếu source SHA-256 khớp receipts, không chạy lại suites hoặc tự review/approve.

Handoff `HANDOFF_BLOCKED`, blocker `REPOSITORY_CHECKER_FAILED`. Real RULE/LLM/RL/HYBRID backends, redaction completeness, reference/evidence integrity, durable evidence binding, coordinator/gate/recorder integration và independent approval giữ `UNRESOLVED`. Candidate sets không cấp quyền execution; không có provider/training/dispatch trong interface. Pending handoff: xử lý repository blockers theo scope riêng → independent review shared boundary/identity/provenance → approved consumer integration. Các task phụ thuộc giữ trạng thái hiện hành; TASK-026/032 giữ `DEFERRED`.

Checks đồng bộ tài liệu ngày 2026-10-12: scoped headings/link/whitespace và status/dependencies/source-hashes PASS (exit 0, 75 local links hợp lệ); scoped git diff --check exit 0. Repository validate() exit 1 với 656 errors và 0 errors thuộc năm tài liệu đã sửa. Exact commands và phạm vi thay đổi tại receipts Task 20; đây là checks tài liệu, không phải chạy lại suites hoặc independent approval.

### TASK-021 — Rule-based planner ngoại tuyến

Trạng thái cập nhật ngày 2026-10-12 là `IMPLEMENTED` cho baseline xem xét bằng chứng ngoại tuyến theo yêu cầu người dùng; chưa `VALIDATED` hoặc hoàn tất acceptance/handoff. Ba artifacts: [rule_based_planner.py](runtime/planners/rule_based_planner.py), [thiết kế và receipts](docs/implementation/rule_based_planner.md), [focused tests](tests/runtime/test_rule_based_planner.py). RuleBasedPlanner kế thừa giao diện Task 20, đọc StateSnapshot Task 19; luật immutable với priority và điều kiện đóng, phase ANALYSIS/REPLAN, candidate scope rõ ràng. Chỉ đề xuất `ACTION-PLAN-003`; không gọi scanner, provider, executor hoặc sửa state/budget/evidence.

Receipts triển khai ngày địa phương 2026-10-12: 28 focused tests + 28 Task 20 + 21 Task 19 + 16 planner contracts PASS (93 tests, từng suite exit 0); AST/example/whitespace checks PASS. Thứ tự lựa chọn xác định; completion gắn với phiên bản candidate và context tránh lặp qua instance mới; feedback không thành công, thiếu completion hoặc đổi state không liên quan dừng an toàn; snapshot/store/journal giữ nguyên sau planner calls. Source HEAD, SHA-256, UTC, nguồn fixture, exact commands và expected/observed tại tài liệu receipts. Cập nhật trạng thái chỉ đối chiếu hai source hashes khớp receipts; không chạy lại suites hoặc tự review/approve.

Repository checker phiên triển khai exit 1 với 656 errors, 0 errors thuộc ba paths Task 21. Handoff giữ `HANDOFF_BLOCKED`, blocker `REPOSITORY_CHECKER_FAILED_OUTSIDE_SCOPE`. Independent review, durable evidence/source integrity, coordinator/gate/recorder integration, scanner/runtime execution và full research baseline giữ `UNRESOLVED`; không chuyển synthetic fixtures thành evidence runtime. Pending handoff: xử lý repository blockers theo scope riêng → independent review rule/completion/provenance → approved consumer integration. Task phụ thuộc không tự nâng trạng thái; TASK-026/032 giữ `DEFERRED`.

Checks đồng bộ tài liệu ngày 2026-10-12: scoped headings/link/anchor/whitespace, status/dependency và source-hash checks PASS (exit 0, 92 local links); scoped git diff --check exit 0. Repository validate() exit 1 với 656 errors, 0 errors thuộc năm tài liệu Task 21 đã sửa. Exact commands, UTC và phạm vi cập nhật tại tài liệu receipts Task 21; đây là checks tài liệu, không phải chạy lại 93 tests hoặc review độc lập.

### TASK-022 — LLM planner xem xét bằng chứng ngoại tuyến

Trạng thái cập nhật ngày 2026-10-12 là `IMPLEMENTED` cho phần xem xét metadata bằng chứng ngoại tuyến theo yêu cầu người dùng; chưa `VALIDATED` hoặc đóng acceptance. Ba artifacts: [llm_planner.py](runtime/planners/llm_planner.py), [thiết kế và receipts](docs/implementation/llm_planner.md), [focused tests](tests/runtime/test_llm_planner.py). LLMPlanner kế thừa Task 20, đọc snapshot Task 19; context có giới hạn/coverage, system prompt, strict tool schema và revision binding. Chỉ đề xuất `ACTION-PLAN-003` hoặc dừng; raw fact values không gửi cho provider, planner không ghi store/evidence, trừ budget hoặc dispatch scanner/executor.

Replan kiểm context/revision/action/objective, phân biệt DENIED/FAILURE/ERROR/PARTIAL/SUCCESS, loại phiên bản candidate chưa thay đổi sau thất bại và yêu cầu completion CONTROL liên kết observation trong feedback trước tiếp tục sau SUCCESS. Provider output malformed/refusal/incomplete không fallback. Provider unavailable/timeout chỉ fallback khi được cho phép, ghi requested mode LLM, actual mode RULE và reason rõ ràng; không phải gọi backend Task 21. Mode labels/counters/providers trong tests là synthetic fixtures.

Receipts triển khai ngày địa phương 2026-10-12: 31 focused tests + 28 Task 20 + 21 Task 19 + 28 Task 21 + 16 planner contracts PASS (124 tests, từng suite exit 0), AST/document/link/whitespace PASS. Receipt UTC 2026-10-11T20:57:12.3960969Z, build BUILD-TASK022-REVIEW-OFFLINE-20261012, source HEAD/hashes và exact commands tại tài liệu receipts. Lần focused ban đầu exit 1 do fixture gọi sai Task 19 API được giữ riêng; không tính lại các lần chạy 29 tests vào tổng 124. Cập nhật trạng thái chỉ đối chiếu hai source hashes khớp receipts, không chạy lại suites hoặc tự review/approve.

Checker triển khai exit 1 với 613 lỗi ngoài scope, 0 lỗi thuộc ba paths Task 22; handoff `HANDOFF_BLOCKED`, blocker `REPOSITORY_CHECKER_FAILED_OUTSIDE_SCOPE`. Provider/model/tokenizer/transport thật, durable evidence/history/reference integrity, coordinator/gate integration và independent review giữ `UNRESOLVED`; không coi strict schema hoặc fixture PASS là LLM runtime success. Pending handoff: xử lý repository blockers theo scope riêng → independent review context/selection/replan/provenance → approved provider/reference/evidence/coordinator integration. Giữ nguyên task IDs/dependencies và trạng thái task phụ thuộc; TASK-026/032 giữ `DEFERRED`.

Checks đồng bộ tài liệu ngày 2026-10-12: scoped headings/link/anchor/whitespace PASS (exit 0, 81 local links, 21 anchors); status/dependencies/source-hashes và scoped git diff --check PASS. Đối chiếu bảng trước/sau: chỉ TASK-022 đổi trạng thái, toàn bộ dependency IDs và 34 trạng thái khác giữ nguyên. Repository validate() exit 1 với 613 lỗi ngoài scope, 0 lỗi thuộc năm tài liệu cập nhật. Exact commands/UTC và phạm vi thay đổi tại receipts Task 22; không chạy lại 124 tests hoặc review độc lập trong lần sửa tài liệu này.

### TASK-016 — parser và safety wrapper ZAP ngoại tuyến

Canonical task là `IMPLEMENTED` trong phạm vi parser/wrapper offline; chưa hoàn tất acceptance/handoff và chưa `VALIDATED`. Source HEAD của build trước `d9ae6ca0d5bb03ce381d7249665237f272eeddc9`; plan `PLAN-TASK016-ZAP-OFFLINE-001`; build `BUILD-TASK016-ZAP-OFFLINE-001`. Trạng thái handoff sau self-check ngày 2026-10-11: `HANDOFF_BLOCKED`. Khi cập nhật trạng thái đã chạy lại `python -B -m unittest discover -s tests/unit -p test_zap_adapter_offline.py -v`: exit 0, 16 tests PASS trên working tree hiện tại. Check này không thay thế build binding, independent review hoặc repository gate; receipts lịch sử dưới đây giữ nguyên phạm vi cũ.

Bốn file triển khai/kiểm thử: `tools/parsers/zap_parser.py`, `tools/adapters/zap/adapter.py`, `tests/unit/test_zap_adapter_offline.py`, `tests/unit/test_tool_adapters.py` (chỉ hai lớp ZAP). Không xóa file; không sửa TASK-015 hoặc BaseAdapter.

- `import_report(report, *, target_id)` nhận JSON object đã nạp, validate all-or-nothing và trả candidate scanner results; không chạy scanner, đọc file hoặc ghi evidence. `execute` cho `ACTION-SCAN-001` luôn trả `DENIED`, facts/results rỗng; không dùng import để giả scan `SUCCESS`.
- Kiểm target allowlist, host/HTTP origin và metadata nhất quán, kể cả alerts bị bỏ qua. Giới hạn 1 MiB JSON, depth 16, 1 site, 1.000 alerts, 2.000 instances/results, URI 2.048 ký tự; rate/budget theo adapter trong process, không phải global runtime quota.
- Confidence ZAP code 0–4 được chuẩn hóa thứ bậc thành 0–1, không suy từ severity hoặc coi là xác suất đã hiệu chuẩn. Chỉ mapping các finding families được hỗ trợ; `endpoint_id=null`, không đưa raw URL/path/query, secrets hoặc alert name tùy ý vào results/errors. Candidate không phải confirmed vulnerability.

| Command/check self-check ngày 2026-10-11 | Exit code | Observed result |
|---|---|---|
| `python -B -m unittest discover -s tests/unit -p test_zap_adapter_offline.py -v` | 0 | 16 tests PASS, gồm zero network/process/write guards |
| `python -B -m unittest discover -s tests/unit -p test_tool_adapters.py -v` | 0 | 27 tests PASS |
| `python -B -m unittest discover -s tests/safety -p test_safety.py -v` | 0 | 17 tests PASS |
| `git diff --check -- tools/parsers/zap_parser.py tools/adapters/zap/adapter.py tests/unit/test_tool_adapters.py` | 0 | Không whitespace errors |
| `python -B scripts/validation/validate_scaffold.py` | 1 | SCAFFOLD INVALID; lỗi quan sát tại `dashboards/app/frontend/node_modules/**`, ngoài allowlist TASK-016 |

Tổng 60 tests PASS. Asserts offline bổ sung PASS cho 13 malformed inputs, hai canonical origins và giới hạn alerts/instances thực tế; bốn source hashes khớp build snapshot. Checker từng PASS ở build gốc (6.008 files), nhưng không thay thế lần FAIL mới nhất. Không sửa/xóa dependencies ngoài scope hoặc bypass checker.

Independent reviewer không trả kết luận do lỗi API; các attempts thay thế đã dừng. Người dùng sau đó yêu cầu main tự review: chưa phát hiện code finding được xác nhận trong checks đã chạy, nhưng đây không phải independent approval hoặc `FINAL / APPROVE`. Không có REVIEW_CONTRACT được xác minh; repair budget chưa tiêu. Receipts chỉ áp dụng snapshot code trước lần sửa tài liệu này.

Artifacts vận hành ngoài repo tại `C:/Users/DELL/AppData/Local/Temp/claude/E--PBL6-FINAL/c5a7c178-4de8-4acd-bb86-a719d7c47856/`: `task016-plan.json`, `task016-build.json`, `task016-self-check.json`. Receipts chứa UTC, commands, expected/observed và exit codes; build chứa source hashes. Vị trí tạm không phải kho evidence lâu dài.

Chưa xác minh/triển khai: tương thích fixture report do ZAP thật tạo, live ZAP, XML/file ingestion, durable evidence/provenance integration và runtime completion. Nhánh evidence offline `PLAN-TASK016-ZAP-EVIDENCE-002` đã được duyệt kế hoạch nhưng chưa viết code/chạy checks; không claim evidence-before-return, no-overwrite publication hoặc Windows crash durability đã đạt. Bước tiếp theo: giải quyết checker blocker theo scope riêng, chạy lại gate và tiếp tục evidence offline trong allowlist được duyệt; không mở scan runtime bằng cập nhật tài liệu.

- Phiên triển khai trước đã sửa `cyber-range/runtime/gateway.py`, `cyber-range/targets/ecommerce/app.py`, `cyber-range/targets/ecommerce/Dockerfile` và thêm hai integration suites. Hai lệnh test từng bị classifier chặn trước thực thi; các attempts đó không có exit code và không được ghi PASS/FAIL. Blocker này đã được xử lý trong phiên SL-01; receipts mới bên dưới là các lần thực sự thực thi, không thay thế kết quả attempts cũ.
- Build SL-01 chỉ sửa `scripts/validation/validate_scaffold.py`, `tests/scaffold/test_validator.py`, `tests/integration/test_gateway_product.py`, `tests/integration/test_ecommerce_storage.py`. Assertion literal `%` đã sửa; import guards áp dụng ngay tại bootstrap/setUp và negative controls đi qua cùng loader. Validator giữ canonical/safety checks và nhận diện exact 12 SL specs.
- Không xóa file: đúng 7 cache baseline đã được di chuyển ra repo và giữ bản gốc cùng backup có SHA256 khớp, theo `quarantine.json`. User changes ngoài allowlist được bảo toàn.
- Source HEAD: `96d9428ef715299ca2c6d403a81d50d97ae55412`; plan `PLAN-SL01-FINAL-003`; build `BUILD-SL01-FINAL-003`. Required-check receipts ghi UTC ngày 2026-10-09, expected/observed, exit code, source/run ID, artifact hash và redaction.

| Command/check thực tế | Exit code | Observed result |
|---|---|---|
| `python -B -m unittest discover -s tests/integration -p test_gateway_product.py -v` | 0 | 13 tests PASS |
| `python -B -m unittest discover -s tests/integration -p test_ecommerce_storage.py -v` | 0 | 8 tests PASS |
| `python -B -m unittest discover -s tests/scaffold -p test_validator.py -v` | 0 | 31 tests PASS |
| `python -B -m unittest discover -s tests/safety -p test_safety.py -v` | 0 | 17 tests PASS |
| `python -B -m unittest discover -s tests -p test_scaffold.py -v` | 0 | 1 test PASS |
| AST parse bằng `python -B -c` (argv đầy đủ trong receipts) | 0 | AST OK: 6 files |
| `python -B scripts/validation/validate_scaffold.py` | 0 | SCAFFOLD VALID |

Tổng 70 tests PASS. Deterministic `gate-r1.json` PASS; review độc lập `review.json` trả `FINAL / APPROVE`, không còn blockers hoặc required actions. `verify_review.py` chạy với `python -I -B`, exit 0, xác minh matching IDs/HEAD và hashes của reviewed sources, contracts, diff và receipts không đổi.

Artifacts vận hành nằm ngoài repo tại `C:/Users/DELL/AppData/Local/Temp/claude/E--PBL6-FINAL/70d0e679-2bee-4cda-bdbf-4677f16e949e/sl01-final-003/`: `plan.json`, `build-r1.json`, `build-r1.diff`, `receipts-r1.json`, `gate-r1.json`, `review.json`, `quarantine.json`. Đây là receipts baseline, không phải runtime evidence; vị trí tạm không phải kho evidence lâu dài. Approval chỉ áp dụng exact build SL-01, không bao gồm lần cập nhật trạng thái tài liệu này.

SL-02 đã được bàn giao trên source HEAD `96d9428ef715299ca2c6d403a81d50d97ae55412`, plan `PLAN-SL02-STORAGE-001`, build `BUILD-SL02-STORAGE-001`, revision R1. Required-check receipts ghi UTC ngày 2026-10-10, exact argv/command, expected/observed, exit code, source/run ID, artifact SHA256 và redaction; chỉ fixture/mock và SQLite trong temp directory.

| Command/check SL-02 R1 thực tế | Exit code | Observed result |
|---|---|---|
| `python -B -m unittest discover -s tests/integration -p test_ecommerce_storage.py -v` | 0 | 28 tests PASS |
| `python -B -m unittest discover -s tests/integration -p test_gateway_product.py -v` | 0 | 13 tests PASS |
| `python -B -m unittest discover -s tests/scaffold -p test_validator.py -v` | 0 | 31 tests PASS |
| `python -B -m unittest discover -s tests/safety -p test_safety.py -v` | 0 | 17 tests PASS |
| `python -B -m unittest discover -s tests -p test_scaffold.py -v` | 0 | 1 test PASS |
| AST parse bằng `python -B -c` (exact argv trong receipts) | 0 | AST OK: 2 files |
| `python -B scripts/validation/validate_scaffold.py` | 0 | SCAFFOLD VALID |

Tổng 90 tests PASS. `gate-r1.json` PASS; `review-r1.json` trả `FINAL / APPROVE`, không còn blockers hoặc required actions. Verifier chạy bằng `python -I -B`, exit 0; `review-verification-r1.json` ghi UTC `2026-10-10T08:32:58.159074+00:00`, xác minh matching IDs/HEAD, hashes contracts/source/receipts/diff, inventory và baseline ngoài hai allowlisted paths được bảo toàn. Reviewer đọc snapshots độc lập nhưng không tự chạy tests hoặc tái tính hashes; các observed execution claims dựa trên receipts được gate và verifier chấp nhận.

Hai file source được review: `cyber-range/targets/ecommerce/app.py` SHA256 `4adb1da2f3c8a71e8a6b9a891a6b91093b5eca0f50d643c6cb1da13c35957781`; `tests/integration/test_ecommerce_storage.py` SHA256 `1ede88e04755b1a0621707dea208dab7e28420ae22b013d3cc1257d80f653019`. Không xóa file. Delta phiên bàn giao: busy timeout dùng một nguồn `BUSY_SECONDS`; test FK/timeout trên từng connection, uncommitted-read isolation và order-item restart persistence; sửa schema filter thành literal prefix `NOT GLOB 'sqlite_*'`.

Review R0 phát hiện F01: `LIKE 'sqlite_%'` bỏ sót user objects có tên giống internal prefix. Regression version 0/1 đã thực thi trước sửa, exit 1 với hai failures `StorageError not raised`; R1 từ chối cả hai và giữ nguyên DB bytes/lifecycle state chưa publish. Một evidence-backed repair đã dùng, không thay receipts hoặc review cũ.

Artifacts ngoài repo: `C:/Users/DELL/AppData/Local/Temp/claude/E--PBL6-FINAL/70d0e679-2bee-4cda-bdbf-4677f16e949e/sl02-goal-20261010-001/`, gồm `plan.json`, `baseline.json`, `build-r1.json`, `build-r1.diff`, `repair1-receipts.json`, `gate-r1.json`, `review-r1.json`, `review-verification-r1.json`, `review-verification-r1-receipt.json` và `F01-reproduction.json`. Gate SHA256 `30584e0fbb57aca08c6b0b1ed824342039ee127b8e0c90843755d2907ab12ff3`; review SHA256 `805caec2c44a0155aefec1d76103c0a53ce93de8948d67488785b14ad2834d9a`. Đây là operational receipts ở vị trí tạm, không phải runtime evidence hoặc kho lưu trữ lâu dài. Approval chỉ cho exact source build R1, không bao gồm lần cập nhật tài liệu này.

Restore handoff: đóng admission rồi drain in-flight transactions với timeout; timeout giữ admission đóng và không đóng connection của worker khác. Actual replacement/session invalidation thuộc SL-03/SL-07 và chưa chạy. Invoice file và SQLite chưa atomic chung; commit failure có thể giữ orphan, reconciliation thuộc SL-04/SL-07. Filesystem boundary giả định trusted app-owned parent/ACL, không chứng minh chống concurrent replacement; POSIX ownership và khả năng tạo symlink thực tế chưa được bảo đảm bởi receipts Windows. Test successful quiesce riêng khi worker active vẫn là gap non-blocking.

Handoff SL-02 không có Docker/LLM/PTES receipts mới và không chứng nhận auth/session/CSRF. Kết quả triển khai SL-03 tiếp theo được tách riêng bên dưới; reset HTTP bị từ chối không hoàn thành restore, không suy ra runtime approval hoặc commit permission.

### SL-03 — kết quả offline R1

SL-03 hiện `IMPLEMENTED`, chưa `VALIDATED`. Source HEAD `96d9428ef715299ca2c6d403a81d50d97ae55412`; plan `PLAN-SL03-AUTH-001`; build `BUILD-SL03-AUTH-001`, revision R1. Phạm vi chỉ offline fixture/mock và SQLite temp, không socket/live dispatch.

Ba file triển khai: `cyber-range/targets/ecommerce/app.py`, `tests/integration/test_ecommerce_storage.py`, `tests/integration/test_ecommerce_auth.py`. Không xóa file. Gate R1 xác nhận delta đúng ba allowlisted paths và bảo toàn baseline ngoài scope, trước lần cập nhật tài liệu này.

Đã triển khai PBKDF2 có salt/work factor, opaque digest-backed sessions, expiry/rotation/logout POST, session-bound CSRF, DB-backed role và ownership, bounded cart merge/throttle/session quotas, local role promotion/revocation với audit và transaction. Schema v2 cho DB mới; schema v1 bị từ chối trước writes, không tự migration. Guest orders không được claim khi login; chỉ cart được merge. Tests gateway dùng mock nối actual Handler, không phải browser/runtime E2E.

| Command/check SL-03 R1 thực tế | Exit code | Observed result |
|---|---|---|
| `python -B -m unittest discover -s tests/integration -p test_ecommerce_auth.py -v` | 0 | 24 tests PASS |
| `python -B -m unittest discover -s tests/integration -p test_ecommerce_storage.py -v` | 0 | 28 tests PASS |
| `python -B -m unittest discover -s tests/integration -p test_gateway_product.py -v` | 0 | 13 tests PASS |
| `python -B -m unittest discover -s tests/scaffold -p test_validator.py -v` | 0 | 31 tests PASS |
| `python -B -m unittest discover -s tests/safety -p test_safety.py -v` | 0 | 17 tests PASS |
| `python -B -m unittest discover -s tests -p test_scaffold.py -v` | 0 | 1 test PASS |
| AST parse bằng `python -B -c` (exact argv trong receipts) | 0 | AST OK: 3 files |
| `python -B scripts/validation/validate_scaffold.py` | 0 | SCAFFOLD VALID |

Tổng 114 tests PASS, không skip; `gate-r1.json` PASS. Các attempts trước có lỗi fixtures được sửa và chạy lại; không ghi các attempts lỗi thành PASS. Review độc lập bị lỗi API/model và không trả verdict. Sau đó người dùng yêu cầu người triển khai tự review: hai findings về ID vượt miền SQLite và query parameters mơ hồ đã được sửa, có regression test mới và chạy lại đủ tám checks. Đây không phải independent review hoặc `FINAL / APPROVE`; chưa có REVIEW_CONTRACT được xác minh. Build status `READY_FOR_REVIEW` không đồng nghĩa task đã được phê duyệt.

Artifacts vận hành ngoài repository: `C:/Users/DELL/AppData/Local/Temp/claude/E--PBL6-FINAL/70d0e679-2bee-4cda-bdbf-4677f16e949e/sl03-auth-20261010-001/`, gồm `plan.json`, `baseline.json`, `build-r1.json`, `build-r1.diff`, `receipts-r1.json`, `gate-r1.json`, `check-r1-*.log` và `source-r1-*.py`. Receipts có exact argv, UTC, run/source, expected/observed, exit/result, artifact/source hashes và redaction. Vị trí tạm không phải kho evidence lâu dài. Contracts/gate này chỉ áp dụng source build trước cập nhật tài liệu; không sửa hoặc tái sử dụng chúng để chứng nhận docs mới.

Chưa xác minh: independent approval, legacy migration, Docker/browser/HTTPS, transport confidentiality của current valid bearer token, actual restore/invalidate-all/container durability, chống hostile filesystem/external-process writers, full SL-05/06 và provider/PTES runtime. Handoff lịch sử SL-03 vẫn cần review độc lập exact build để đóng acceptance lifecycle, không được coi SL-03 đã VALIDATED.

### SL-04 — kết quả offline R1

SL-04 hiện `IMPLEMENTED`, chưa `VALIDATED`. Hoàn thiện trên target ShopLab hiện hữu (`cyber-range/targets/ecommerce/app.py`) theo quyết định tiếp tục phát triển và hoàn thiện ShopLab. Phạm vi chỉ offline fixture/mock, in-memory/temp SQLite và integration test harness; không socket/live dispatch hay Docker deployment.

Ba file triển khai: `cyber-range/targets/ecommerce/app.py`, `tests/integration/test_ecommerce_storage.py`, `tests/integration/test_ecommerce_checkout.py`. Không xóa file.

Đã triển khai và xác minh các invariants cốt lõi:
1. Catalog search/detail: tìm kiếm case-insensitive bounded substring qua `/products?q=...`, an toàn 404 cho missing product.
2. Quản lý cart: giỏ hàng guest gắn opaque token HMAC digest (`cart_key`), giỏ hàng authenticated user gắn `user_id`. Add/update/remove validate quantity > 0 và tồn kho.
3. Transaction checkout đơn lẻ: kiểm tra idempotency -> nạp authoritative cart/prices -> kiểm tra stock -> atomic stock decrement (`UPDATE products SET stock = stock - ? WHERE id = ? AND stock >= ?`) -> insert order & order_items -> insert idempotency -> xóa cart -> commit.
4. Tách biệt invoice filesystem khỏi DB transaction: invoice generation được tách hoàn toàn ra khỏi transaction SQLite qua hook post-commit `_post_commit_action`. Lỗi commit DB rollback sạch và không để lại orphan invoice file; lỗi ghi filesystem post-commit không làm rollback đơn hàng đã commit. Endpoint `/download/invoice` có fallback tạo hóa đơn on-demand từ DB.
5. Idempotency theo logical owner: bảng `order_idempotency` có `PRIMARY KEY (key, owner_key)` với `owner_key` là `user:<uid>` hoặc `guest:<cart_key>`. Retry cùng payload trả về đơn hàng đã tạo mà không double-decrement hay duplicate order; retry sau session rotation của user vẫn nhận diện đúng đơn hàng; retry khác payload trả về 409 Conflict; hai owner khác nhau dùng cùng key hoạt động độc lập.
6. Tiền tệ integer minor units (USD): toàn bộ tính toán tiền tệ chuyển sang integer minor units (cents) qua helper `_to_minor` và `_from_minor` với `Decimal('0.01')` ROUND_HALF_UP. Schema SQLite ràng buộc cứng `CHECK(currency = 'USD')`, hằng số `SHOPLAB_CURRENCY = 'USD'`. Không có sai số floating-point drift cho 0.10, 0.20, 0.30, 10.01, 19.99 và tổng nhiều mặt hàng. Bỏ qua hoàn toàn client-supplied prices.
7. Form CSRF: kiểm tra CSRF token hợp lệ trước mọi state mutation.

| Command/check SL-04 R1 thực tế | Exit code | Observed result |
|---|---|---|
| `python -B -m unittest discover -s tests/integration -p test_ecommerce_checkout.py -v` | 0 | 13 tests PASS |
| `python -B -m unittest discover -s tests/integration -p test_ecommerce_storage.py -v` | 0 | 28 tests PASS |
| `python -B -m unittest discover -s tests/integration -p test_ecommerce_auth.py -v` | 0 | 24 tests PASS |
| `python -B -m unittest discover -s tests/integration -p "test_ecommerce_*.py" -v` | 0 | 65 tests PASS |
| `python -B -m unittest tests/scaffold/test_validator.py` | 0 | 31 tests PASS |
| `python -B scripts/validation/validate_scaffold.py` | 0 | SCAFFOLD VALID |

Tổng 65 tests ecommerce integration PASS, không skip. Chưa có independent review / approval; không nâng `VALIDATED`. Chưa xác minh: Docker runtime containerization, external payment provider, email delivery, SL-05 orders/reviews mở rộng, SL-06 admin quản trị.

### SL-05 — kết quả offline R1

SL-05 hiện `IMPLEMENTED`, chưa `VALIDATED`. Hoàn thiện trên target ShopLab hiện hữu (`cyber-range/targets/ecommerce/app.py`).

File triển khai: `cyber-range/targets/ecommerce/app.py`, `tests/integration/test_ecommerce_orders_reviews.py`.

Đã triển khai và xác minh các invariants cốt lõi:
1. Ownership enforcement (IDOR protection): `owns_order(identity, order)` xác thực quyền sở hữu cho cả HTML view, JSON API và invoice download. User B hoặc anonymous truy cập đơn của User A nhận 404 Not Found an toàn (không để lộ enumeration).
2. Data minimization: endpoint `/api/orders/<id>` loại bỏ toàn bộ các trường nhạy cảm (`session_id`, `cart_key`, `csrf_secret`, `password_hash`, email của user khác).
3. Hóa đơn lab notice & on-demand synthesis fallback: hóa đơn chứa nhãn bắt buộc `Notice: ShopLab — Lab / Simulated Order Receipt (No payment charged)`. Khi tệp hóa đơn vật lý bị xóa trên đĩa, endpoint tự động tái tạo nội dung từ dữ liệu đơn hàng trong SQLite.
4. Chống path traversal / injection trên hóa đơn: regex validation `INV-[A-F0-9]{32}\.txt` và `_validate_path` từ chối các chuỗi `..`, encoded traversal, null bytes, CRLF injection với mã 400.
5. Review validation: rating bắt buộc là số nguyên 1..5; nội dung body bắt buộc không rỗng và không quá 4000 ký tự.
6. Chống Stored XSS: toàn bộ nội dung đánh giá được escape HTML ngữ cảnh an toàn bằng `html_escape()` trước khi render ra giao diện chi tiết sản phẩm.
7. CSRF protection: POST `/reviews` yêu cầu CSRF token hợp lệ.

| Command/check SL-05 R1 thực tế | Exit code | Observed result |
|---|---|---|
| `python -B -m unittest discover -s tests/integration -p test_ecommerce_orders_reviews.py -v` | 0 | 16 tests PASS |
| `python -B -m unittest discover -s tests/integration -p "test_ecommerce_*.py" -v` | 0 | 81 tests PASS |
| `python -B scripts/validation/validate_scaffold.py` | 0 | SCAFFOLD VALID |

### SL-06 — kết quả offline R1

SL-06 hiện `IMPLEMENTED`, chưa `VALIDATED`. Hoàn thiện trên target ShopLab hiện hữu (`cyber-range/targets/ecommerce/app.py`).

File triển khai: `cyber-range/targets/ecommerce/app.py`, `tests/integration/test_ecommerce_admin.py`.

Đã triển khai và xác minh các invariants cốt lõi:
1. Server-side role enforcement: phân quyền `admin` lưu trong DB `users.role`, không tin cậy cookie `role` từ client. Người dùng thông thường và khách truy cập `/admin` hoặc gửi POST mutations bị từ chối với 403 Forbidden.
2. Máy trạng thái đơn hàng forward-only (`ORDER_TRANSITIONS`):
   - `pending` -> `processing`, `shipped`, `cancelled`
   - `processing` -> `shipped`
   - `completed` -> `shipped`
   - `shipped` -> `delivered`
   - `delivered` -> terminal (không cho phép chuyển tiếp)
   - `cancelled` -> terminal
   Từ chối các chuyển đổi trạng thái ngược như `completed -> processing` hay `delivered -> processing` với 400 Bad Request.
3. Chính sách hủy đơn nghiêm ngặt: chỉ cho phép hủy đơn khi trạng thái là `pending`. Đơn đã ở `processing`, `shipped`, `delivered` bị từ chối hủy.
4. Product soft-archival (`product_archives`): sản phẩm bị archive không bị xóa khỏi DB nhằm bảo toàn snapshot đơn cũ, bị ẩn khỏi form mua hàng và hiển thị huy hiệu Archived.
5. Điều chỉnh tồn kho an toàn: xác thực số lượng nguyên không âm, bảo đảm tính toàn vẹn dữ liệu.
6. Audit logging (`admin_activity_log`): toàn bộ các thao tác thay đổi trạng thái, hủy đơn, cập nhật tồn kho, archive hoặc tạo sản phẩm đều được ghi vết đầy đủ.
7. CSRF protection: kiểm tra CSRF token trên toàn bộ các endpoint quản trị.

| Command/check SL-06 R1 thực tế | Exit code | Observed result |
|---|---|---|
| `python -B -m unittest discover -s tests/integration -p test_ecommerce_admin.py -v` | 0 | 14 tests PASS |
| `python -B -m unittest discover -s tests/integration -p "test_ecommerce_*.py" -v` | 0 | 95 tests PASS |
| `python -B scripts/validation/validate_scaffold.py` | 0 | SCAFFOLD VALID |

### SL-07 — kết quả live Docker runtime verification

SL-07 hiện `IMPLEMENTED`, chưa `VALIDATED`. Hoàn thiện trên Compose stack ShopLab cô lập (`cyber-range/compose.yaml`).

File triển khai và kiểm thử: `cyber-range/compose.yaml`, `cyber-range/runtime/gateway.py`, `cyber-range/targets/ecommerce/Dockerfile`, `cyber-range/targets/ecommerce/app.py`, `scripts/cyber-range/verify_live_docker.py`, `tests/integration/test_ecommerce_gateway_e2e.py`.

Đã triển khai và xác minh trực tiếp trên Docker daemon qua 8/8 pha:
1. Health check: Gateway loopback `http://127.0.0.1:18088/health` trả về 200 OK (`{"status": "ok", "target_id": "lab-ecommerce"}`).
2. Full product flow: Client A đăng ký, đăng nhập, duyệt catalog, thêm vào giỏ, checkout, xem đơn hàng, tải hóa đơn và gửi review qua gateway thành công 100%.
3. Two client sessions & IDOR isolation: Client B có session riêng, giỏ hàng rỗng; Client B gọi đơn và hóa đơn của Client A nhận 404 Not Found; truy cập `/admin` nhận 403 Forbidden; thiếu CSRF nhận 403 Forbidden.
4. Container restart persistence: lệnh `docker restart cyber-range-lab-ecommerce-1` thực thi; đơn hàng, review và hóa đơn tồn tại nguyên vẹn sau restart.
5. Container replacement persistence: lệnh `docker rm -f cyber-range-lab-ecommerce-1` và `docker compose up -d --no-deps lab-ecommerce` thực thi; container ID thay đổi (`1144d2dcae55` -> `c73f1dc41337`), cùng gắn named volume `cyber-range_ecommerce-data`; toàn bộ dữ liệu đơn hàng, review và hóa đơn được bảo toàn.
6. Failure injection (target down): lệnh `docker stop cyber-range-lab-ecommerce-1` thực thi; Gateway trả về 502 Bad Gateway an toàn, không rò rỉ hostname hay IP mạng nội bộ; sau khi target start lại, Gateway phục hồi 200 OK.
7. Restore to baseline & session revocation: thực thi `restore_baseline("/app/data")` qua ephemeral container; toàn bộ session cũ của Client A và B bị thu hồi (403); đơn hàng và review thử nghiệm được reset sạch; catalog sản phẩm gốc được phục hồi.
8. Bounded teardown: lệnh `docker compose stop lab-ecommerce gateway-ecommerce` thực thi; cả hai container chuyển sang trạng thái Exited; volume `cyber-range_ecommerce-data` được bảo toàn nguyên vẹn.

| Command/check SL-07 thực tế | Exit code | Observed result |
|---|---|---|
| `python -B scripts/cyber-range/verify_live_docker.py` | 0 | ALL LIVE DOCKER RUNTIME VERIFICATIONS PASSED (8/8 pha PASS) |
| `python -B -m unittest discover -s tests/integration -p test_ecommerce_gateway_e2e.py -v` | 0 | 17 tests PASS |
| `python -B -m unittest discover -s tests/integration -p "test_ecommerce_*.py" -v` | 0 | 95 tests PASS |
| `python -B -m unittest discover -s tests/integration -p test_gateway_product.py -v` | 0 | 13 tests PASS |
| `python -B -m unittest discover -s tests/integration -p test_network_isolation.py -v` | 0 | 5 tests PASS |
| `python -B scripts/validation/validate_scaffold.py` | 0 | SCAFFOLD VALID (3,725 files checked) |

Tổng 95 tests ecommerce integration PASS, 17 gateway E2E tests PASS, 8 pha live Docker runtime PASS. Chưa có independent review / approval; không nâng `VALIDATED`.

### SL-08 — kết quả discovery safety gate và live Docker verification

SL-08 hiện `IMPLEMENTED`, chưa `VALIDATED`. Triển khai kiến trúc observation-driven discovery kết hợp cổng an toàn tập trung (CentralizedSafetyGate) và bộ ghi bằng chứng bền vững (DurableDiscoveryRecorder) trên nền runtime ShopLab SL-07.

File triển khai và kiểm thử: `runtime/discovery_recorder.py`, `runtime/discovery_gate.py`, `runtime/discovery_engine.py`, `tests/runtime/test_recorder_preflight.py`, `tests/runtime/test_discovery_safety.py`, `scripts/cyber-range/verify_sl08_live.py`.

Đã triển khai và xác minh các invariants cốt lõi:
1. Recorder trước điều phối (pre-dispatch): ghi bền vững intent/decision trước khi gửi request mạng; ghi kết quả (result) trước khi lên lịch request tiếp theo. Ghi nguyên tử qua file tạm + fsync + SHA-256; validate schema JSON Draft 2020-12 (`evidence.schema.json`); fail-closed: lỗi ghi intent -> 0 network dispatch; lỗi ghi result -> dừng ngay lập tức, không retry âm thầm.
2. Centralized safety gate: duy nhất một điểm chốt chặn (bottleneck) cho toàn bộ dispatch. Nạp canonical target allowlist, action allowlist và target registry. Bất biến tập giao nghiêm ngặt: `effective_targets = canonical_allowlist ∩ run_approved_targets`; runtime caller chỉ có thể thu hẹp, không thể nới rộng phạm vi được phép.
3. Chuẩn hóa URL an toàn (URL Canonicalizer): ép chữ thường scheme/host, bỏ port mặc định (:80, :443), chuẩn hóa trailing slash, sắp xếp query parameters, loại bỏ fragment, từ chối URL chứa credentials, URL ngoài origin hoặc format mơ hồ.
4. Kiểm soát ngân sách và tốc độ: BudgetTracker theo dõi request budget và time budget; RateLimiter triển khai sliding window kiểm soát rps; tích hợp KillSwitch; hỗ trợ thu hồi quyền động (TOCTOU revocation) dừng request kế tiếp ngay khi chính sách thay đổi.
5. Observation-driven discovery engine: thuật toán duyệt bề rộng (BFS) từ seed được duyệt (`/`), trích xuất link `<a href>` và form `<form action>`. Biểu mẫu mutation chỉ trích xuất metadata (phương thức, tham số, action), tuyệt đối không tự động submit form. Giới hạn số bước nhảy redirect (tối đa 3), độ sâu tìm kiếm và số lượng request.
6. Trạng thái dừng có kiểm soát: trả về `COMPLETED_BOUNDED` khi hết ngân sách hoặc cạn kiệt bề mặt khám phá hợp lệ.

| Command/check SL-08 thực tế | Exit code | Observed result |
|---|---|---|
| `python -B -m unittest discover -s tests/runtime -p test_recorder_preflight.py -v` | 0 | 7 tests PASS (E01–E07 preflight recorder) |
| `python -B -m unittest discover -s tests/runtime -p test_discovery_safety.py -v` | 0 | 9 tests PASS (D01–D09 safety & discovery) |
| `python -B scripts/cyber-range/verify_sl08_live.py` | 0 | ALL LIVE SL-08 DISCOVERY & SAFETY GATE VERIFICATIONS PASSED (7/7 pha PASS) |

7/7 pha live Docker verification SL-08 trên Gateway `http://127.0.0.1:18088`:
- Pha 1: Preflight recorder ghi intent và result bền vững, băm SHA-256 hợp lệ.
- Pha 2: Centralized gate từ chối off-origin, unknown target, unallowlisted action -> đúng 0 network dispatches.
- Pha 3: Khám phá bounded từ seed `/` qua Gateway; thu thập catalog, chi tiết sản phẩm, đăng nhập, đăng ký.
- Pha 4: Kiểm tra form metadata-only, xác nhận 0 mutation submissions được gửi tới target.
- Pha 5: Giới hạn redirect và dừng an toàn trong phạm vi cho phép.
- Pha 6: Ngân sách cạn kiệt dừng có kiểm soát với mã `COMPLETED_BOUNDED`.
- Pha 7: Fail-closed khi thư mục evidence chỉ đọc -> 0 dispatches mạng.
Bằng chứng thực thi live được lưu trữ bất biến tại `evidence/runtime/RUN-SL08-LIVE/`. Chưa có independent review; không nâng `VALIDATED`.

### SL-09 — kết quả observed-state planner và live Docker verification

SL-09 hiện `IMPLEMENTED`, chưa `VALIDATED`. Triển khai bộ lập kế hoạch dựa trên trạng thái quan sát thực tế (ObservedStatePlanner) và lớp tương thích StateManager (PlannerAdapter).

File triển khai và kiểm thử: `runtime/planner_adapter.py`, `runtime/observed_planner.py`, `tests/runtime/test_observed_planner.py`, `scripts/cyber-range/verify_sl09_live.py`.

Đã triển khai và xác minh các invariants cốt lõi:
1. PlannerAdapter tích hợp StateManager: nạp quan sát bảo đảm tính bất biến (idempotent ingestion), phát hiện và báo lỗi xung đột dữ liệu (`ValueError`) nếu cùng observation ID nhưng khác nội dung payload. Thu gọn prompt (state minimization): loại bỏ toàn bộ token nhạy cảm, cookies, mật khẩu và HTML thô, chỉ trích xuất facts có cấu trúc. Phân định ranh giới ngân sách duy nhất: chỉ `StateManager` sở hữu quyền trừ ngân sách (không double-decrement).
2. ObservedStatePlanner schema-bound: sinh đề xuất tuân thủ nghiêm ngặt schema JSON Draft 2020-12 (`plan.schema.json`, `additionalProperties: false`). Hỗ trợ các chế độ `RULE`, `LLM`, `LLM_MOCK`, `HYBRID`.
3. Nguồn gốc chế độ thực thi minh bạch (`mode_provenance`): ghi nhận chính xác chế độ yêu cầu (`requested_mode`), chế độ thực thi (`actual_mode`), nhà cung cấp/mô hình thực tế, lý do fallback (`fallback_reason`), và nguồn quyết định (`decision_origin`).
4. Chính sách fallback nghiêm ngặt: khi `fallback_allowed=False` và nhà cung cấp gặp lỗi hoặc phản hồi sai định dạng, planner lập tức dừng an toàn (`ACTION-END-003`), tuyệt đối không âm thầm lùi về `RULE` mode. Khi fallback được phép, ghi rõ lý do chuyển đổi trong `mode_provenance`.
5. Đánh giá đề xuất không dispatch mạng (`evaluate_proposal_against_gate`): kiểm tra trước tính hợp lệ của đề xuất với gate mà không gửi bất kỳ gói tin mạng nào tới target.
6. Thẩm quyền chính sách allowlist nghiêm ngặt: kiểm tra tập giao target allowlist và thu hồi quyền động TOCTOU revocation trước khi hành động được thực thi.

| Command/check SL-09 thực tế | Exit code | Observed result |
|---|---|---|
| `python -B -m unittest discover -s tests/runtime -p test_observed_planner.py -v` | 0 | 13 tests PASS (P01–P08 và tests thẩm quyền allowlist 0.4–0.6) |
| `python -B scripts/cyber-range/verify_sl09_live.py` | 0 | ALL LIVE SL-09 OBSERVED PLANNER VERIFICATIONS PASSED (8/8 pha PASS) |

8/8 pha live Docker verification SL-09 trên Gateway `http://127.0.0.1:18088`:
- Pha 1: Thẩm quyền allowlist tập giao (`canonical & run_approved`) và dynamic TOCTOU revocation hoạt động chính xác.
- Pha 2: Planner nạp trọn vẹn tập quan sát discovery từ SL-08 vào StateManager an toàn.
- Pha 3: Sinh đề xuất kế hoạch từ trạng thái quan sát thực tế (Rule mode) khớp schema.
- Pha 4: Đánh giá đề xuất qua CentralizedSafetyGate bảo đảm 0 network dispatch.
- Pha 5: Điều phối hành động trinh sát đã lập kế hoạch qua Gate + Recorder tới Gateway thành công.
- Pha 6: Replan với quan sát mới ghi nhận từ target, cập nhật kế hoạch theo trạng thái.
- Pha 7: Xử lý lỗi provider khi `fallback_allowed=False` dừng an toàn với `ACTION-END-003`, không fallback âm thầm.
- Pha 8: Kiểm tra idempotency và phát hiện xung đột dữ liệu trên live state.
Bằng chứng thực thi live được lưu trữ bất biến tại `evidence/runtime/RUN-SL09-LIVE/`. Chưa có independent review; không nâng `VALIDATED`. Sẵn sàng cho SL-10 (PTES Coordinator).

### SL-10 — kết quả PTES Coordinator và live Docker verification

SL-10 hiện `IMPLEMENTED`, chưa `VALIDATED`. Triển khai bộ điều phối 7 giai đoạn PTES (`runtime/ptes_coordinator.py`) kết nối trực tiếp với SL-08 CentralizedSafetyGate, DurableEvidenceRecorder và SL-09 ObservedStatePlanner / PlannerAdapter.

File triển khai và kiểm thử: `runtime/ptes_coordinator.py`, `tests/runtime/test_ptes_coordinator.py`, `scripts/cyber-range/verify_sl10_live.py`.

Đã triển khai và xác minh các invariants cốt lõi:
1. Bảy giai đoạn PTES có tiêu chí kiểm tra đầu vào (entry) và đầu ra (exit) độc lập:
   - Phase 1 (Pre-engagement): kiểm tra phê duyệt, danh tính target, ngân sách, baseline và recorder; vi phạm lập tức chặn dừng (`BLOCKED`) trước khi phát sinh bất kỳ dispatch mạng nào.
   - Phase 2 (Intelligence Gathering): thu thập bề mặt quan sát thực tế (endpoints, forms metadata-only), giới hạn ngân sách và dừng an toàn (`COMPLETED_BOUNDED`).
   - Phase 3 (Threat Modeling): giả thuyết tấn công (hypotheses) phải liên kết chặt chẽ với observations nguồn từ Phase 2; từ chối mọi giả thuyết suy diễn không có nguồn quan sát.
   - Phase 4 (Vulnerability Analysis): phân tích thụ động/không phá hủy, phân loại trung thực tín hiệu thành `CANDIDATE` hoặc `NEGATIVE_RESULT`; nghiêm cấm tự động xác nhận lỗ hổng chỉ qua phản hồi HTTP 200, reflection đơn lẻ hay lỗi cơ sở dữ liệu giả lập.
   - Phase 5 (Exploitation): chỉ cho phép các năng lực kiểm chứng an toàn trong phạm vi chính sách; khi không có quyền/payload cho phép, chuyển trạng thái `BLOCKED`, tuyệt đối không giả lập hoàn thành và không gửi exploit dispatch nào (0 unsafe dispatches).
   - Phase 6 (Post-exploitation): phụ thuộc kết quả khai thác từ Phase 5; do Phase 5 bị chặn, Phase 6 chuyển trạng thái `NOT_RUN` (hoặc `UNRESOLVED`), không thực hiện bất kỳ hành vi persistence, credential dumping hay host file reading.
   - Phase 7 (Reporting): tổng hợp báo cáo chẩn đoán trung thực liên kết bằng chứng; phản ánh chính xác các pha bị chặn (`BLOCKED`), chưa chạy (`NOT_RUN`), và kết quả âm tính (`NEGATIVE_RESULT`).
2. Tách biệt rành mạch giữa hoàn thành điều khiển pipeline (`pipeline_control_completed = True`) và hoàn thành đánh giá toàn diện 7 giai đoạn PTES (`full_ptes_assessment_completed = False`).
3. Truyền lỗi trung thực giữa các pha: lỗi ghi evidence hoặc cạn kiệt ngân sách lập tức dừng quy trình, không nuốt ngoại lệ thành hoàn thành trong khối `finally`.

| Command/check SL-10 thực tế | Exit code | Observed result |
|---|---|---|
| `python -B -m unittest discover -s tests/runtime -p test_ptes_coordinator.py -v` | 0 | 8 tests PASS (T01–T08 PTES Coordinator invariants) |
| `python -B scripts/cyber-range/verify_sl10_live.py` | 0 | ALL LIVE PTES COORDINATOR VERIFICATIONS PASSED (7/7 phase PASS) |

Xác minh live Docker ShopLab: Phase 1 COMPLETED, Phase 2 COMPLETED_BOUNDED (8 endpoints, 2 forms metadata-only), Phase 3 COMPLETED (3 hypotheses liên kết nguồn), Phase 4 COMPLETED (0 confirmed vulnerabilities), Phase 5 BLOCKED (0 exploit dispatches), Phase 6 NOT_RUN, Phase 7 COMPLETED. Tổng confirmed vulnerabilities = 0, unsafe dispatches = 0. Chưa có independent review; không nâng `VALIDATED`.

### SL-11 — kết quả immutable evidence packaging, report, replay và handoff package

SL-11 hiện `IMPLEMENTED`, chưa `VALIDATED`. Hoàn thiện bộ đóng gói bằng chứng bất biến, kiểm chứng tính toàn vẹn hash/reference, sinh báo cáo lab liên kết bằng chứng, và bộ máy replay offline xác định với bảo vệ mạng nghiêm ngặt (`ZeroNetworkGuard`).

File triển khai và kiểm thử: `runtime/evidence_package.py`, `runtime/discovery_recorder.py`, `tests/runtime/test_evidence_reporting.py`, `scripts/cyber-range/verify_sl11_live.py`.

Đã triển khai và xác minh các invariants cốt lõi:
1. Tạo thư mục run và bản ghi độc quyền (`exclusive creation`): sử dụng `os.O_CREAT | os.O_EXCL`, từ chối ghi đè nếu run ID đã tồn tại; bản ghi gốc được bảo toàn 100% byte và hash SHA-256.
2. Kiểm soát ranh giới thư mục bằng chứng (Root Containment): kiểm tra nghiêm ngặt `resolved_destination.relative_to(approved_root)` áp dụng cho cả `base_dir=None` và custom `base_dir`; từ chối đường dẫn tuyệt đối ra ngoài root (B01), escape `..` (B02) và symlink escape trỏ ra ngoài root (B03); cho phép thư mục con hợp lệ (B04).
3. Khóa bảo tồn run thất bại / dở dang (Non-recurrence lock): run directory đã khởi tạo và ghi ít nhất một artifact sẽ không bị xóa hay tái sử dụng lại run ID (B05); nỗ lực chạy lại với cùng run ID thất bại do xung đột (collision).
4. Khử dữ liệu nhạy cảm (Secret Redaction): tự động làm sạch mật khẩu, session cookies, CSRF tokens, API keys trước khi lưu trữ bền vững; trường redaction metadata ghi nhận trường bị loại bỏ mà không tiết lộ giá trị gốc.
5. Kiểm chứng tính toàn vẹn và thứ tự nhân quả: đọc manifest, xác minh SHA-256 từng file, kiểm tra quan hệ nhân quả (mỗi action decision/observation liên kết đúng parent ID, timestamp UTC đơn điệu tăng dần); phát hiện và báo lỗi ngay khi có dấu hiệu cắt xén hoặc giả mạo.
6. Offline Replay xác định với ZeroNetworkGuard: tái hiện toàn bộ facts, ngân sách và quyết định pha từ các bản ghi observation ngoại tuyến mà không phát sinh bất kỳ kết nối mạng hoặc lời gọi provider nào (`network_dispatches = 0`, `provider_dispatches = 0`).
7. Báo cáo nghiên cứu liên kết bằng chứng (`report.md`, `report.json`): ghi nhận nguồn gốc planner thực tế, trạng thái trung thực của 7 phase, các phát hiện âm tính và phạm vi giới hạn.
8. Ghi nhận minh bạch sai lệch lịch sử (Historical Discrepancy Disclosure):
   `HISTORICAL_EVIDENCE_DISCREPANCY = ABORTED_RUN_DIRECTORY_DELETED_DURING_SELF_REVIEW`
   (Một thư mục dở dang `RUN-SL11-LIVE` đã bị xóa trong self-review trước khi quy trình khóa bất biến được kích hoạt; run `RUN-SL11-LIVE` hiện tại không được dùng làm bằng chứng lịch sử hoàn hảo, và toàn bộ 108 files của các run lịch sử `RUN-SL08-LIVE`, `RUN-SL09-LIVE`, `RUN-SL11-LIVE` được xác minh bất biến 100% byte-for-byte).
9. Gói bàn giao chuẩn mực độc quyền mới: tạo thành công run `evidence/runtime/RUN-SL11-HANDOFF-20261011/` với đầy đủ 51 files, 23 records, `manifest.json`, `report.md`, `report.json`, dual `replay_receipt.json` và `integrity_receipt.json`.

| Command/check SL-11 thực tế | Exit code | Observed result |
|---|---|---|
| `python -B -m unittest discover -s tests/runtime -p test_evidence_reporting.py -v` | 0 | 14 tests PASS (E01–E09 evidence invariants, B01–B05 containment & non-recurrence) |
| `python -B scripts/cyber-range/verify_sl11_live.py` | 0 | ALL LIVE SL-11 VERIFICATIONS PASSED (Live run, Manifest, Report, Dual Replay, Historical Immutability) |

Tổng 56 runtime unit tests PASS (`tests/runtime/test_*.py`), 31 scaffold unit tests PASS, `validate_scaffold.py` PASS (`SCAFFOLD VALID`). Gói bàn giao đã sẵn sàng tại `evidence/runtime/RUN-SL11-HANDOFF-20261011/`. Chưa có independent review; không tự nâng `VALIDATED`. Sẵn sàng cho SL-12 (Independent Verification & Handoff).

### SL-12 — kết quả deterministic pre-review gate và pending review contract

Deterministic pre-review gate hiện ghi nhận: **HANDOFF_BLOCKED**. Đã khóa chính xác định danh build, định danh evidence, ma trận kiểm chứng các nhóm checks, bộ nguồn đánh giá và hợp đồng bàn giao cho reviewer độc lập.

Thông số định danh:
- `TASK_ID = SL-12`
- `PLAN_ID = PLAN-SHOPLAB-PTES-001`
- `BUILD_ID = SL12-PREVIEW-ee45e60-20261011`
- `BASE_HEAD = ee45e602c05f79f99c67c59e5fbc24a2b4c70bec`
- `BRANCH = main`
- `DIRTY = true`
- `AUTHORITATIVE_RUN_ID = RUN-SL11-HANDOFF-20261011`

Giới hạn liên kết nguồn (Source-Binding Limitation):
- `SOURCE_AT_RUN_BINDING = PARTIAL`: Không có source manifest nào được lưu trữ bền vững trước khi chạy `RUN-SL11-HANDOFF-20261011`. Không thể truy thu chứng minh trạng thái byte mã nguồn tại thời điểm bắt đầu chạy run.
- `CURRENT_REVIEW_SOURCE_MANIFEST`: Đã tính toán SHA-256 cho 27 tệp triển khai và kiểm thử cốt lõi phục vụ so sánh độc lập của reviewer.

Công bố sai lệch lịch sử và tính bất biến:
- `HISTORICAL_PROCESS_DISCREPANCY`: `prior_aborted_run_deleted: YES`, `recoverable: NO`, `disclosed: YES` (sự cố xóa thư mục dở dang `RUN-SL11-LIVE` trong self-review là không thể khôi phục và đã được công bố minh bạch).
- `POST_DISCLOSURE_IMMUTABILITY`: `RUN-SL08-LIVE`, `RUN-SL09-LIVE`, `RUN-SL11-LIVE` hiện tại và `RUN-SL11-HANDOFF-20261011` bất biến 100%.

Kiểm tra đọc-chỉ Authoritative Run (`RUN-SL11-HANDOFF-20261011`):
- Toàn vẹn gói bằng chứng: 23/23 bản ghi bền vững, 51 package files, SHA-256 khớp 100%, đồ thị tham chiếu hợp lệ, thứ tự UTC đơn điệu tăng dần, quét bí mật sạch sẽ (0 conflicts, 0 errors).
- Offline Replay xác định: 2 lần replay độc lập thành công (`success = True`), đúng 8 observations replayed, 16 facts reconstructed, proposal matched, `network_dispatches = 0`, `provider_calls = 0`.
- Báo cáo PTES trung thực: Phase 5 `BLOCKED` (0 exploit dispatches), Phase 6 `NOT_RUN` (0 post-exploit dispatches), `full_ptes_assessment_completed = False`, `confirmed_vulnerabilities = 0`.

| Command/check SL-12 thực tế | Exit code | Observed result |
|---|---|---|
| `python -B -m unittest discover -s tests/integration -p test_gateway_product.py -v` | 0 | 13 tests PASS (Gateway boundary & forwarding) |
| `python -B -m unittest discover -s tests/integration -p test_ecommerce_storage.py -v` | 0 | 28 tests PASS (ACID, isolation, busy timeout) |
| `python -B -m unittest discover -s tests/integration -p test_ecommerce_auth.py -v` | 0 | 24 tests PASS (Auth, session, CSRF, roles) |
| `python -B -m unittest discover -s tests/integration -p test_ecommerce_checkout.py -v` | 0 | 15 tests PASS (Checkout atomicity, stock, idempotency) |
| `python -B -m unittest discover -s tests/integration -p test_ecommerce_orders_reviews.py -v` | 0 | 14 tests PASS (Orders, IDOR, invoice, reviews XSS) |
| `python -B -m unittest discover -s tests/integration -p test_ecommerce_admin.py -v` | 0 | 9 tests PASS (Admin RBAC, state machine, audit) |
| `python -B -m unittest discover -s tests/integration -p test_ecommerce_gateway_e2e.py -v` | 0 | 5 tests PASS (Gateway E2E, restart, restore) |
| `python -B -m unittest discover -s tests/integration -p test_network_isolation.py -v` | 0 | 5 tests PASS (Internal network & loopback) |
| `python -B -m unittest discover -s tests/integration -p test_executor.py -v` | 0 | 5 tests PASS (Allowlisted DNS & bounds) |
| `python -B -m unittest discover -s tests/runtime -p test_recorder_preflight.py -v` | 0 | 7 tests PASS (Durable recorder fail-closed) |
| `python -B -m unittest discover -s tests/runtime -p test_discovery_safety.py -v` | 0 | 9 tests PASS (Safety gate D01–D09, zero mutation) |
| `python -B -m unittest discover -s tests/runtime -p test_observed_planner.py -v` | 0 | 14 tests PASS (Observed planner P01–P08, replan) |
| `python -B -m unittest discover -s tests/planner -v` | 0 | 16 tests PASS (Planner contracts & catalogs) |
| `python -B -m unittest discover -s tests/runtime -p test_ptes_coordinator.py -v` | 0 | 8 tests PASS (PTES 7-phase coordinator T01–T08) |
| `python -B -m unittest discover -s tests/runtime -p test_evidence_reporting.py -v` | 0 | 14 tests PASS (Evidence packaging & replay) |
| `python -B -c "...EvidenceVerifier().verify_directory(...)..."` | 0 | Package integrity PASS (23 records / 51 files) |
| `python -B -c "...OfflineEvidenceReplayer().replay_run(...)..."` | 0 | Dual replay PASS (deterministic, 0 net, 0 prov) |
| `python -B scripts/validation/validate_scaffold.py` | 1 | SCAFFOLD INVALID (phát hiện vi phạm schema tại tệp demo `scripts/demo/demo-output/BASELINE-...`) |
| `python -B -m unittest discover -s tests/scaffold -p test_validator.py -v` | 1 | 30 tests PASS, 1 FAIL (`test_current_repo_validates` do lỗi tại tệp demo `scripts/demo/demo-output/BASELINE-...`) |
| `python -B -m unittest discover -s tests/safety -v` | 0 | 31 tests PASS (Safety regression tests) |
| `git diff --check` | 0 | Clean diff (0 conflict markers, 0 whitespace errors) |

Trạng thái Docker & Provider:
- `DOCKER_RERUN = NOT_RUN` (lý do: `EXISTING_RECEIPTS_UNDER_REVIEW`, đã có receipts live Docker SL-07–11 đầy đủ).
- `PROVIDER`: Rule engine PASS, Mock provider PASS, `REAL_LLM_PROVIDER_VERIFIED = NO` (không có kết nối API mô hình ngoài nào được cấp phép trong lab).


### Autonomous Closed-Loop Control — kết quả triển khai và live verification

Triển khai hoàn chỉnh bộ điều khiển tự động khép kín `runtime/autonomous_runner.py` theo đúng kiến trúc chỉ thị:
`OBSERVATION -> STATE -> AI PLANNER -> PROPOSAL -> SAFETY GATE -> EXECUTOR -> NEW OBSERVATION -> STATE UPDATE -> AI REPLAN -> ... -> STOP`.

1. **Bất biến an toàn then chốt**:
   - **Zero Direct Transport**: `AutonomousRunner` hoàn toàn không chứa bất kỳ thư viện client HTTP/socket trực tiếp nào (`http.client`, `urllib`, `requests`, `socket`). Mọi tương tác mạng tới mục tiêu đều bắt buộc định tuyến qua `CentralizedSafetyGate`.
   - **Fail-Closed Evidence Persistence**: Ghi nhận intent trước khi dispatch và ghi nhận result trước khi thực hiện request/action kế tiếp; dừng ngay lập tức nếu bộ ghi evidence gặp lỗi (`EVIDENCE_FAILURE`).
   - **Adaptive Refusal Replan**: Khi Safety Gate từ chối đề xuất (do action/target không thuộc allowlist, thiếu approval hoặc vượt budget), hệ thống tạo `REFUSAL` observation nạp vào `StateManager`. Bộ lập kế hoạch replan dựa trên quan sát từ chối, tránh lặp lại hành động bị cấm.
   - **No-Progress Loop Detection**: Tính toán semantic state fingerprint (`state_fingerprint`) độc lập với thứ tự quan sát, theo dõi số lượng fact. Khi lặp lại trạng thái ngữ nghĩa mà không phát sinh quan sát mới, vòng lặp dừng an toàn với lý do `NO_PROGRESS_LOOP`.

2. **Bộ kiểm thử chấp nhận (Acceptance Tests A01–A12)**:
   Triển khai tại `tests/runtime/test_autonomous_runner.py` kiểm chứng toàn diện 12 kịch bản:
   - A01: Observation thay đổi quyết định planner động, không dùng step counter cứng.
   - A02: Gate từ chối tạo quan sát REFUSAL; replan không lặp vô hạn hành động bị từ chối.
   - A03: Hành động được phê duyệt thực thi -> kết quả được chuẩn hóa -> StateManager cập nhật -> planner nhận diện trạng thái mới.
   - A04: Unknown action ID bị Safety Gate từ chối; đúng 0 network dispatch.
   - A05: Target ngoài allowlist bị Safety Gate từ chối; đúng 0 network dispatch.
   - A06: Thu hồi approval token giữa chừng dừng ngay network dispatch kế tiếp.
   - A07: Kích hoạt Kill switch dừng vòng lặp ngay lập tức; 0 network dispatch sau đó.
   - A08: Lỗi ghi evidence kích hoạt cơ chế fail-closed tức thì; 0 network dispatch.
   - A09: Lặp trạng thái ngữ nghĩa dừng an toàn với `NO_PROGRESS_LOOP`.
   - A10: Prompt injection trong nội dung trang đích được cô lập thành passive data; zero policy/target bypass.
   - A11: Theo dõi minh bạch mode provenance (RULE, LLM_MOCK, LLM->RULE fallback, fallback denied).
   - A12: Kiểm tra cấu trúc mã nguồn xác nhận 0 client HTTP/socket trực tiếp trong runner.

3. **Live Verification trên ShopLab cyber-range**:
   Thực thi thành công qua script `scripts/cyber-range/verify_autonomous_live.py`:
   - Dịch vụ Docker: `lab-ecommerce` và `gateway-ecommerce` khởi động trên loopback `http://127.0.0.1:18088`.
   - Bằng chứng lưu tại run ID độc quyền mới: `evidence/runtime/RUN-AUTONOMOUS-LIVE-1791708234` (toàn bộ run lịch sử `RUN-SL08-LIVE`, `RUN-SL09-LIVE`, `RUN-SL11-LIVE` được bảo toàn bất biến).
   - Tiến trình thực thi:
     - Iteration 1: `ACTION-RECON-001` -> Gate APPROVED -> Dispatched True -> 1 observation (1 fact) -> SUCCESS.
     - Iteration 2: `ACTION-RECON-002` -> Gate APPROVED -> Dispatched True -> 10 observations (10 facts) -> SUCCESS.
     - Iteration 3: `ACTION-SCAN-001` -> Gate APPROVED -> Dispatched False (passive scan) -> 1 observation (9 facts) -> SUCCESS.
     - Iteration 4: `ACTION-END-001` -> Gate STOP (`discovery_surface_complete`) -> Dispatched False -> STOP.
   - Tổng kết: 4 decisions (3 approved, 0 denied), 11 network dispatches qua gateway, 0 unsafe dispatches, 20 observations, stop reason `discovery_surface_complete`.
   - Bounded teardown: Dừng an toàn dịch vụ Docker, bảo toàn volume `ecommerce-data`.

| Command / Check kiểm chứng thực tế | Exit code | Observed result |
|---|---|---|
| `python -B -m unittest discover -s tests/runtime -p test_autonomous_runner.py -v` | 0 | 12 tests PASS (A01–A12 acceptance suite) |
| `python -B -m unittest discover -s tests/runtime -p "test_*.py" -v` | 0 | 68 tests PASS (Full runtime test suite) |
| `python -B -m unittest discover -s tests/safety -p "test_*.py" -v` | 0 | 31 tests PASS (Full safety test suite) |
| `python -B -m unittest discover -s tests/integration -p "test_ecommerce_*.py" -v` | 0 | 95 tests PASS (Full ecommerce integration suite) |
| `python -B scripts/validation/validate_scaffold.py` | 0 | SCAFFOLD VALID (5451 files checked) |
| `git diff --check` | 0 | Clean diff (0 whitespace/conflict errors) |
| `python -B scripts/cyber-range/verify_autonomous_live.py` | 0 | Autonomous Closed-Loop Live Verification PASS |

### Autonomous Pentest Loop — Bổ sung Safe Verification và Khắc phục Review Findings (F-01, F-02, F-03)

Bổ sung bộ năng lực kiểm thử an toàn có giới hạn (Bounded Safe Verification Capabilities) và khắc phục toàn diện 3 blocker findings từ Independent Review:
1. **Kiến trúc Bounded Verifiers (`runtime/capability_registry.py`)**:
   - `SafeInputVerificationExecutor` (`ACTION-WEB-001`): Bounded SQL syntax probe (`probe_test'`, `probe_test''`) kiểm tra bất thường cú pháp (syntax error / status deviation) mà không khai thác payload tùy ý.
   - `SafeReflectionVerificationExecutor` (`ACTION-WEB-002`): Bounded script reflection probe với inert alphanumeric marker (`refprobe...`), kiểm tra phản chiếu ngữ cảnh HTML và mã hóa an toàn (`&lt;...&gt;`).
   - `SafePathFixtureVerificationExecutor` (`ACTION-WEB-003`): Bounded path traversal probe sử dụng fixture sentinel (`LAB_TRAVERSAL_SENTINEL`), kiểm tra đọc file ngoài namespace cho phép.
   - `PassiveSurfaceAnalyzer` (`ACTION-SCAN-001`): Quét thụ động bề mặt quan sát, phát hiện tham số form và liên kết mà không phát sinh thêm I/O mạng.

2. **Khắc phục 3 Blocker Findings (`F-01`, `F-02`, `F-03`)**:
   - **`F-01` (Form & Parameter Provenance Broken)**:
     - `PassiveSurfaceAnalyzer` giải quyết relative URL cho form `action` so với URL trang chứa.
     - Các form `POST` được cô lập thành `CANDIDATE_FINDING` metadata, tuyệt đối không tạo ra các `PARAMETER` query giả trên trang chứa (`/`).
     - `AutonomousPentestRunner._evaluate_safety` xác thực chặt chẽ: chỉ cho phép probe nếu tham số thực sự thuộc về endpoint GET tương ứng (`UNOBSERVED_INPUT` nếu vi phạm).
   - **`F-02` (Fixed Sequence Ladder)**:
     - Loại bỏ hoàn toàn chuỗi thử nghiệm cố định (SQLi -> XSS -> Traversal).
     - Triển khai `Hypothesis Affinity` trong `ObservedStatePlanner._derive_rule_proposal`: phân bổ giả thuyết ưu tiên theo ngữ nghĩa tham số (`path_keywords` -> `ACTION-WEB-003` trước; `reflection_keywords` -> `ACTION-WEB-002` trước; injection candidate -> `ACTION-WEB-001` trước).
     - Điều phối replan thích ứng dựa trên kết quả: nếu phát hiện `SIGNAL`, tăng độ ưu tiên điều tra tiếp.
   - **`F-03` (Unsupported Negative Security Claims)**:
     - Loại bỏ các tuyên bố bảo đảm kiến trúc thiếu căn cứ ("Input parameter handled safely with parameterized queries" với độ tin cậy 95%).
     - Thay thế bằng các khẳng định trung thực, giới hạn chặt chẽ theo bằng chứng quan sát được với độ tin cậy thực tế (confidence <= 0.75):
       - SQL: *"No SQL syntax anomaly observed for bounded syntax probe vectors (probe_test', probe_test'')"* (confidence: 0.60).
       - XSS: *"Inert sentinel is properly HTML-escaped (&lt;...&gt;) in observed response body context"* (confidence: 0.75) hoặc *"Inert probe marker was not reflected in observed target response body"* (confidence: 0.60).
       - Traversal: *"No sentinel disclosure observed for bounded LAB_TRAVERSAL_SENTINEL fixture probe"* (confidence: 0.60).

3. **Live Cyber Range Pentest Execution (`RUN-AUTONOMOUS-PENTEST-1791723996`)**:
   - Thực thi kịch bản `scripts/cyber-range/run_autonomous_pentest.py` trên Cyber Range ShopLab cô lập (`http://127.0.0.1:18088`).
   - Kết quả: 7 decisions (6 approved, 0 denied), 3 active verifications (`ACTION-WEB-001` trên `/products?q=`, `/products?category=`; `ACTION-WEB-002` trên `/products?q=`).
   - Đúng 0 synthetic query gửi tới trang chủ `/`, 23 network dispatches qua gateway, 0 unsafe dispatches.
   - Thu thập 3 kết luận trung thực (Negative findings, confidence 0.60 - 0.75).
   - Gói bằng chứng bất biến được lưu trữ tại `evidence/runtime/RUN-AUTONOMOUS-PENTEST-1791723996/` (report `EV-AUTONOMOUS_PENTEST_REPORT-d193d02dfcf8`). Dọn dẹp Docker container sạch sẽ.

| Command / Check kiểm chứng thực tế | Exit code | Observed result |
|---|---|---|
| `python -B -m unittest discover -s tests/runtime -p test_autonomous_pentest.py -v` | 0 | 18 tests PASS (V01–V18 acceptance & regression suite, F-01/F-02/F-03 verified) |
| `python -B -m unittest discover -s tests/runtime -p test_autonomous_runner.py -v` | 0 | 12 tests PASS (A01–A12 runner acceptance suite) |
| `python -B -m unittest discover -s tests/runtime -p test_ptes_coordinator.py -v` | 0 | 11 tests PASS (PTES 7-phase coordinator suite) |
| `python -B -m unittest discover -s tests/runtime -p test_observed_planner.py -v` | 0 | 14 tests PASS (Observed planner suite) |
| `python -B scripts/validation/validate_scaffold.py` | 0 | SCAFFOLD VALID (5681 files checked) |
| `git diff --check` | 0 | Clean diff (0 whitespace/conflict errors) |
| `python -B scripts/cyber-range/run_autonomous_pentest.py` | 0 | Live Cyber Range Pentest Run PASS (RUN-AUTONOMOUS-PENTEST-1791723996) |

### RT-01 — Zero-Knowledge Boundary receipts

Tranche `RT-01` (Zero-Knowledge Boundary) gồm hai tiểu tranche:
- `RT-01A` (Ground Truth Physical Isolation): Di chuyển canonical Ground Truth schema ra khỏi Planner domain sang `evaluation/ground_truth/ground-truth.schema.json`. Cập nhật `schema-link.json` và `validate_scaffold.py`. Xây dựng bộ kiểm thử biên tự động `tests/boundary/test_ground_truth_boundary.py` (8/8 PASS).
- `RT-01B` (Planner Visibility Boundary / Fog-of-War): Tách biệt hoàn toàn Safety Target Scope (do `CentralizedSafetyGate` sở hữu) khỏi Planner-Visible Target Scope (do `PlanningInput` và `AutonomousRunner` sở hữu).
  - Thuộc tính canonical `visible_target_ids: frozenset[str]` trên `PlanningInput`, cung cấp `@property allowed_target_ids` tương thích ngược (phát cảnh báo `DeprecationWarning`).
  - Hàm chiếu `project_visible_targets(state, initial_seed)` chỉ đưa target vào visibility khi có sự kiện quan sát chuẩn tắc (`fact_type == "TARGET"` hoặc host trong `SERVICE`/`ENDPOINT`).
  - `ObservedStatePlanner` mặc định visibility là `{self.target_id}`, loại bỏ hoàn toàn việc nạp ngầm toàn bộ allowlist an toàn.
  - `AutonomousRunner` tại $t=0$ chỉ cấp target seed (`self.target_id`) cho planner, tự động cập nhật tầm nhìn khi quan sát thấy target mới qua `_ingest_and_update_visibility`.
  - Bộ kiểm thử biên tự động `tests/boundary/test_planner_visibility_boundary.py` (8/8 PASS).

| Command / Check kiểm chứng thực tế | Exit code | Observed result |
|---|---|---|
| `python -m unittest tests/boundary/test_ground_truth_boundary.py` | 0 | 8 tests PASS (Ground Truth physical isolation & non-leakage) |
| `python -m unittest tests/boundary/test_planner_visibility_boundary.py` | 0 | 8 tests PASS (Planner visibility boundary & fog-of-war) |
| `python -m unittest discover -s tests/boundary` | 0 | 16 tests PASS (Full boundary test suite) |
| `python -m unittest tests/runtime/test_planner_interface.py` | 0 | 28 tests PASS (Planner interface & visible_target_ids contract) |
| `python -m unittest tests/runtime/test_observed_planner.py` | 0 | 16 tests PASS (Observed planner without allowlist leakage) |
| `python -m unittest tests/runtime/test_rule_based_planner.py` | 0 | 29 tests PASS (Rule planner visibility candidate loop) |
| `python -m unittest tests/runtime/test_llm_planner.py` | 0 | 30 tests PASS (LLM planner zero hidden target leakage) |
| `python -m unittest tests/runtime/test_hybrid_router.py` | 0 | 20 tests PASS (Hybrid router backward compatibility) |
| `python -m unittest tests/runtime/test_autonomous_runner.py` | 0 | 14 tests PASS (Autonomous runner fog-of-war lifecycle) |
| `python -m unittest tests/contracts/test_contracts.py` | 0 | 12 tests PASS (Canonical contract schema validation) |
| `git diff --check` | 0 | Clean diff (0 whitespace/conflict errors) |

### RT-02A — Enterprise Observation Model receipts

Tranche `RT-02A` (Enterprise Observation Model) hoàn thành việc mở rộng canonical Observation Model cho Enterprise Red Team Planning và thiết lập rào chắn tin cậy (Trust Boundary) giữa Execution/Perception và Planning mà tuyệt đối không cho raw executor/tool output đi trực tiếp vào Planner:
- Mở rộng canonical vocabulary trong `agent/planner/contracts/observation.schema.json` từ 8 lên 15 fact types: `TARGET`, `HOST`, `SERVICE`, `ENDPOINT`, `PARAMETER`, `CANDIDATE_FINDING`, `CONFIRMED_FINDING`, `ACCESS`, `CREDENTIAL`, `SESSION`, `REACHABILITY`, `ACTION_OUTCOME`, `DETECTION_SIGNAL`, `OBJECTIVE`, `CONTROL`. Bảo toàn 100% tương thích ngược với vocabulary cũ.
- Bổ sung các trường provenance trên Observation envelope: `source_kind`, `source_target`, `source_session`, `confidence`, `sequence_num`, `evidence_refs`.
- Xây dựng `EnterpriseObservationNormalizer` (`agent/perception/normalizers/enterprise_normalizer.py`):
  - Khử bí mật credentials: chỉ xuất hiện handle mờ (`credential_id`, `principal`, `credential_kind`, `observed_scope`, `validity_state`), loại bỏ hoàn toàn plaintext password/secret khỏi Planner-facing context.
  - Vô trùng sessions: chỉ xuất hiện opaque handle (`session_id`, `target_id`, `access_level`, `state`), không để lộ raw subprocess, socket hay shell internals.
  - Cách ly reachability: chỉ sinh từ kết quả thăm dò/hành động hợp lệ có evidence; cấm tổng hợp từ cấu hình đồ thị toàn cục (Docker Compose, target-allowlist).
  - Giới hạn detection signal: chỉ chấp nhận các tín hiệu quan sát được từ phía attacker (`BLOCKED`, `THROTTLED`, `SESSION_LOST`, `AUTH_LOCKOUT`, `WAF_REJECTION`, `RATE_LIMITED`); cấm nuốt trường Ground Truth hay SIEM riêng của defender.
  - Xác thực objective: chỉ sinh khi objective đạt được qua action hợp lệ kèm evidence reference; không leak metadata flag ẩn.
  - Phân tách fact vs hypothesis: giả thuyết suy diễn mang `source_kind="PLANNER_INFERENCE"` và không mở khóa tầm nhìn mục tiêu (`visible_target_ids`).
- Enforce Trust Boundary: `PlannerStateAdapter` và `AutonomousRunner._ingest_and_update_visibility` từ chối fail-closed mọi object thô/untrusted nếu chưa qua canonical normalizer; bảo toàn fog-of-war.
- Tạo đặc tả nhiệm vụ chi tiết tại `docs/task-specs/RT-02-enterprise-observation-model.md`.

| Command / Check kiểm chứng thực tế | Exit code | Observed result |
|---|---|---|
| `python -B -m unittest tests/perception/test_enterprise_observation.py` | 0 | 10 tests PASS (Enterprise observation fixtures, provenance, credential/session redaction, reachability & detection isolation) |
| `python -B -m unittest tests/contracts/test_contracts.py` | 0 | 13 tests PASS (Canonical contract schema validation including 15-fact vocabulary & provenance) |
| `python -B -m unittest tests/boundary/test_observation_boundary.py` | 0 | 5 tests PASS (Observation model trust boundary, raw output rejection, hypothesis non-expansion) |
| `python -B -m unittest discover -s tests/boundary` | 0 | 21 tests PASS (Full boundary test suite: RT-01A 8 tests, RT-01B 8 tests, RT-02A 5 tests) |
| `python -B -m unittest tests/unit/test_observation_normalizer.py tests/integration/test_nuclei_normalizer.py` | 0 | 57 tests PASS (Normalizer backwards compatibility & regression suite) |
| `python -B -m unittest tests/runtime/test_observed_planner.py tests/runtime/test_rule_based_planner.py tests/runtime/test_llm_planner.py tests/runtime/test_hybrid_router.py tests/runtime/test_planner_interface.py tests/runtime/test_autonomous_runner.py` | 0 | 137 tests PASS (Runtime planners & autonomous runner regression suite, 0 regressions) |
| `git diff --check` | 0 | Clean diff (0 whitespace/conflict errors) |

### RT-02B — Belief State Projection receipts

Tranche `RT-02B` (Belief State Projection) hoàn thành việc xây dựng cơ chế chiếu trạng thái niềm tin tất định (deterministic Belief State Projection) từ canonical observations/knowledge store mà không tạo nguồn sự thật độc lập, không rò rỉ Ground Truth, không lộ full safety allowlist, và phân tách triệt để giả thuyết khỏi sự thật:
- Source of truth invariant: Kiến tạo mô hình `BeliefState` và hàm chiếu `project_belief_state` (`agent/memory/state/belief_state.py`) dẫn xuất 100% từ chuỗi quan sát chuẩn tắc (`observed_facts`). Cấm Planner chỉnh sửa trực tiếp Belief State.
- Facts vs Hypotheses Hard Boundary: Mọi quan sát mang `source_kind="PLANNER_INFERENCE"` bị cách ly hoàn toàn vào `belief.hypotheses`; tuyệt đối không tự thêm máy chủ (`known_hosts`), không mở rộng tầm nhìn (`visible_target_ids`), không tạo thông tin xác thực (`known_credentials`), không nâng quyền hạn (`access_state`), không tạo phiên (`sessions`), không tạo liên kết mạng (`observed_reachability`), không xác nhận lỗ hổng, và không hoàn thành mục tiêu.
- Monotonicity & State Transitions:
  - Máy chủ (`known_hosts`): Khám phá đơn điệu kèm địa chỉ IP và mức quyền cao nhất đã xác nhận.
  - Quyền hạn (`access_state`): Chuyển trạng thái thứ bậc `NONE` -> `FOOTHOLD` -> `USER` -> `PRIVILEGED` -> `SYSTEM`; ghi nhận mức quyền đỉnh đã chứng minh.
  - Thông tin xác thực (`known_credentials`): Khử triệt để plaintext password/secret; handle mờ không suy ngược được từ digest của secret; chuyển trạng thái hợp lệ (`VALID` -> `REVOKED` / `INVALID` là trạng thái cuối).
  - Phiên kết nối (`sessions`): Khử sạch raw shell, subprocess hay socket handle; chuyển trạng thái `ACTIVE` -> `CLOSED` không thể mở lại.
  - Khả năng tiếp cận mạng (`observed_reachability`): Cung có hướng sinh độc quyền từ các sự kiện probe/reachability thực nghiệm; cấm đoán mò từ Docker Compose hay allowlist an toàn.
  - Tín hiệu phòng thủ (`detection_signals`): Chỉ ghi nhận các sự kiện quan sát được từ phía attacker; loại bỏ toàn bộ dữ liệu SIEM/điểm phát hiện riêng của defender.
  - Mục tiêu (`objective_status`): Chỉ cập nhật trạng thái `DISCOVERED` / `ACHIEVED` khi có quan sát tin cậy gắn kèm bằng chứng (`evidence_refs`).
- Tích hợp chuẩn tắc:
  - `StateManager`: bổ sung `get_belief_state() -> BeliefState`, bảo toàn tính tương thích của `get_state()`.
  - `KnowledgeStateStore`: bổ sung `get_belief_state(context) -> BeliefState`.
  - `PlannerStateAdapter`: bổ sung `get_belief_state()` và nạp cấu trúc `belief_state` trong `get_minimized_planner_state()`; pre-seed cache quan sát tránh duplicate replay.
  - `StateSnapshot`: bổ sung `get_belief_state() -> BeliefState` từ danh sách facts đã xác thực.
  - `project_visible_targets`: chặn đứng hoàn toàn `PLANNER_INFERENCE` facts mở khóa `visible_target_ids`.
  - `scripts/validation/validate_scaffold.py`: tổng quát hóa quy ước kiểm định task spec với pattern `RT_SPEC_PATTERN = re.compile(r"^RT-([0-9]{2}[A-Za-z]?)-([a-z0-9]+(?:-[a-z0-9]+)*)\.md$")`.

| Command / Check kiểm chứng thực tế | Exit code | Observed result |
|---|---|---|
| `python -B -m unittest tests/runtime/test_belief_state_projection.py` | 0 | 16 tests PASS (A–R requirements: hosts, services, endpoints, access monotonicity, credential/session redaction, reachability, detection signals, hypotheses quarantine, zero GT, replay determinism) |
| `python -B -m unittest tests/boundary/test_belief_state_boundary.py` | 0 | 5 tests PASS (Belief State immutability, self-confirming attack regression, hypothesis visibility isolation, safety allowlist isolation, ground-truth rejection) |
| `python -B -m unittest discover -s tests/boundary` | 0 | 26 tests PASS (Toàn bộ boundary test suite: RT-01A 10 tests, RT-01B 6 tests, RT-02A 5 tests, RT-02B 5 tests) |
| `python -B -m unittest discover -s tests/contracts` | 0 | 13 tests PASS (Toàn bộ contracts schemas bao gồm 15-fact vocabulary, Draft 2020-12 closed object validation) |
| `python -B -m unittest discover -s tests/perception` | 0 | 10 tests PASS (Enterprise observation normalizer suite) |
| `python -B -m unittest tests/unit/test_knowledge_state_store.py` | 0 | 39 tests PASS (StateManager & KnowledgeStateStore unit suite) |
| `python -B -m unittest discover -s tests/runtime` | 0 | 478 tests PASS (Toàn bộ runtime test suite, 0 regressions) |
| `git diff --check` | 0 | Clean diff (0 whitespace/conflict errors) |

### RT-03A — Generic TTP Action Contract receipts

Tranche `RT-03A` (Generic TTP Action Contract) hoàn thành việc chuyển đổi Action Model từ các action gắn chặt với target/vulnerability cụ thể sang **generic bounded TTP capabilities** có contract rõ ràng, bảo đảm các bất biến:
- Source of truth & Schema: Cập nhật `agent/planner/contracts/action.schema.json` thành Draft 2020-12 closed object (`additionalProperties: false`) biểu diễn đầy đủ năng lực TTP tổng quát: `action_id`, `action_class`, `name`, `description`, `target_kind`, `preconditions`, `expected_effects`, `step_cost`, `noise_cost`, `required_capability`, `argument_schema`, `mitre_attack`, `classification`.
- Danh mục năng lực TTP doanh nghiệp MVP (8 capabilities):
  1. `RECON` / `DISCOVERY` (`ACTION-DISCOVERY-001`): Khám phá mạng và dịch vụ mở trên subnet (`T1018`).
  2. `INITIAL_ACCESS` / `FOOTHOLD` (`ACTION-FOOTHOLD-001`): Thiết lập phiên foothold ban đầu qua dịch vụ mở có lỗ hổng (`T1190`).
  3. `HOST_RECON` (`ACTION-HOSTRECON-001`): Thu thập cấu hình hệ điều hành và giao diện nội bộ từ active session (`T1082`).
  4. `CREDENTIAL_ACCESS` / `CREDENTIAL_DISCOVERY` (`ACTION-CREDS-001`): Khám phá và thu thập credential handle hợp lệ (`T1552`).
  5. `LATERAL_MOVEMENT` / `PIVOT` (`ACTION-PIVOT-001`): Mở rộng phiên tấn công sang máy chủ nội bộ qua thông tin xác thực (`T1021`).
  6. `PRIVILEGE_ESCALATION` (`ACTION-PRIVESC-001`): Nâng đặc quyền thực thi cục bộ từ unprivileged lên privileged (`T1068`).
  7. `OBJECTIVE_ACCESS` (`ACTION-OBJECTIVE-001`): Truy cập và xác thực mục tiêu crown-jewel (`T1565`).
  8. `STOP` (`ACTION-STOP-001`): Kết thúc hoạch định khi hoàn thành mục tiêu hoặc cạn ngân sách.
- Target Independence: Định nghĩa năng lực hoàn toàn độc lập với mục tiêu cụ thể; không chứa IP, hostname, lab target ID, hoặc vulnerability fixture name. Target được lựa chọn tại planning/proposal time từ `visible_target_ids`.
- Structured Preconditions: Điều kiện tiên quyết có cấu trúc, định kiểu chặt chẽ; cấm hoàn toàn eval strings hoặc mã thực thi tùy ý.
- Current vs Historical Access: Phân biệt rạch ròi `proven_access_level` với `active_execution_capability`; các hành động yêu cầu quyền thực thi bắt buộc có `require_active_session: true`. Toàn bộ phiên `CLOSED` không thể thỏa mãn năng lực thực thi dù mức quyền đỉnh trong quá khứ là `PRIVILEGED` hay `SYSTEM`.
- Hard Invariant: `expected_effects` tuyệt đối không được trực tiếp đột biến Belief State; mọi biến đổi trạng thái phải đi qua chuỗi sống: Proposal -> Safety Gate -> Executor -> Canonical Observation -> Belief Projection.
- Bounded Costs: `step_cost` là số nguyên không âm; `noise_cost` (Operational Noise Cost) là số thực không âm.
- Backward Compatibility: Giữ nguyên vẹn 100% các action Web Pentest hiện hữu (`LEGACY_WEB_COMPAT` và `PLANNER_INTERNAL`) trong `actions/catalog/action-catalog.json`.
- Canonical Registry: Hiện thực hóa `actions/catalog/action_registry.py` cung cấp API nạp, kiểm tra schema, quét rò rỉ mục tiêu và thẩm định hợp đồng điều kiện tiên quyết.
- Trạng thái: RT-03A là `IMPLEMENTED`; RT-03B (Action Constraint Evaluator) giữ nguyên `SPEC_ONLY`.

| Command / Check kiểm chứng thực tế | Exit code | Observed result |
|---|---|---|
| `python -B -m unittest tests/contracts/test_action_contract.py` | 0 | 8 tests PASS (A, B, D, E, F: Draft 2020-12 closed schema, generic enterprise actions, legacy web compat, structured preconditions, non-negative step/noise cost, MITRE ATT&CK schema) |
| `python -B -m unittest tests/boundary/test_action_boundary.py` | 0 | 6 tests PASS (C, G, H, I, J, K: zero target/IP leakage, expected_effects zero mutation invariant, closed session rejection for active execution, zero ground truth references, target-neutral metadata) |
| `python -B -m unittest discover -s tests/contracts` | 0 | 21 tests PASS (Toàn bộ contract test suite: 13 foundation/enterprise schemas + 8 action contract tests) |
| `python -B -m unittest discover -s tests/boundary` | 0 | 32 tests PASS (Toàn bộ boundary test suite: 26 baseline + 6 action boundary tests) |
| `python -B -m unittest discover -s tests/perception` | 0 | 10 tests PASS (Enterprise observation normalizer suite) |
| `python -B -m unittest tests/runtime/test_belief_state_projection.py` | 0 | 16 tests PASS (Belief State projection suite) |
| `python -B -m unittest discover -s tests/planner` | 0 | 16 tests PASS (Planner contract suite) |
| `python -B -m unittest tests/unit/test_knowledge_state_store.py` | 0 | 39 tests PASS (StateManager & KnowledgeStateStore unit suite) |
| `git diff --check` | 0 | Clean diff (0 whitespace/conflict errors) |

### RT-03B — Action Constraint Evaluator receipts

Tranche `RT-03B` (Action Constraint Evaluator) hoàn thành việc triển khai một **single canonical Constraint Evaluator** duy nhất xác định action nào khả thi dựa trên Planner-visible Belief State hiện tại, bảo đảm:
- Single Canonical Evaluator: Hiện thực hóa `ActionConstraintEvaluator` tại `runtime/evaluators/action_evaluator.py`; `evaluate_precondition_contract` tại `actions/catalog/action_registry.py` được tinh gọn thành thin wrapper ủy nhiệm hoàn toàn sang canonical evaluator mà không nhân đôi logic.
- Rich Evaluation Outcome: Trả về dataclass `EvaluationResult` gồm `eligible: bool`, `action_id: str`, `target_id: str | None`, `satisfied_conditions`, `failed_conditions`, `reason_codes`, `relevant_fact_ids`, `reasons`, `step_cost`, `noise_cost`, `action_class`, `target_kind`.
- Canonical Reason Codes Vocabulary:
  - `ACTIVE_SESSION_REQUIRED`: Thiếu phiên ACTIVE unclosed trên target.
  - `TARGET_NOT_VISIBLE`: Target không nằm trong planner-visible scope (RT-01 boundary).
  - `HOST_NOT_OBSERVED`: Host chưa được quan sát authoritatively trong Belief State.
  - `SERVICE_NOT_OBSERVED`: Chưa có dịch vụ được quan sát trên target.
  - `SERVICE_TYPE_MISMATCH`: Loại dịch vụ quan sát không khớp required_service_type.
  - `CONFIRMED_FINDING_REQUIRED`: Thiếu phát hiện được xác nhận (CANDIDATE_FINDING không được pass).
  - `INSUFFICIENT_ACCESS`: Mức quyền hiện thời thấp hơn min_access_level yêu cầu.
  - `NO_VALID_CREDENTIAL`: Thiếu credential hợp lệ ở trạng thái VALID.
  - `REACHABILITY_NOT_OBSERVED`: Thiếu cạnh reachability được quan sát đến target.
  - `OBJECTIVE_ALREADY_ACHIEVED`: Mục tiêu đã đạt trạng thái ACHIEVED.
  - `PHASE_NOT_ALLOWED`: Phase hiện tại không nằm trong allowed_phases.
  - `INVALID_TARGET_KIND`: Target không tương thích với target_kind của action.
- Unified Access Hierarchy: Thống nhất thang đo quyền truy cập `NONE < FOOTHOLD < USER < PRIVILEGED < SYSTEM` trên schema, catalog và evaluator; tự động chuẩn hóa `UNPRIVILEGED` sang `USER` tại parser compatibility layer.
- Quarantined Hypotheses: Các fact từ `PLANNER_INFERENCE` hoặc có cờ `hypothesis=True` bị cô lập hoàn toàn, tuyệt đối không được thỏa mãn các điều kiện tiên quyết mang tính authoritative.
- Current vs Historical Access: Quyền lịch sử (`access_level = PRIVILEGED`) với toàn bộ phiên `CLOSED` bị evaluator đánh giá `INELIGIBLE` (`ACTIVE_SESSION_REQUIRED`).
- Purity & Determinism: Evaluator hoàn toàn read-only, zero state mutation, zero network dispatch, zero Ground Truth inspection; 10 lần chạy cùng input cho ra kết quả bit-for-bit đồng nhất.
- Eligibility != Authorization: `eligible=True` chỉ xác nhận tính khả thi logic; `CentralizedSafetyGate` giữ thẩm quyền tối cao từ chối lệnh dispatch nếu target không được cấp quyền (`DISALLOWED_TARGET`).
- STOP Semantics: `ACTION-STOP-001` có `target_kind="ENVIRONMENT"`, không yêu cầu network target hay active session, đánh giá `eligible=True` an toàn.
- Trạng thái: RT-03B là `IMPLEMENTED` (cả RT-03A và RT-03B đạt `IMPLEMENTED`; chưa `VALIDATED` khi chưa qua independent review).

| Command / Check kiểm chứng thực tế | Exit code | Observed result |
|---|---|---|
| `python -B -m unittest tests/runtime/test_action_evaluator.py` | 0 | 22 tests PASS (A–T requirements: target visibility, host/service observation, confirmed vs candidate findings, canonical access ordering, closed vs active session, historical access vs active capability, valid credential, reachability, objective status, determinism, zero mutation, safety gate independence, target neutrality, delegation compatibility, STOP semantics, evaluate_all) |
| `python -B -m unittest discover -s tests/contracts` | 0 | 21 tests PASS (Draft 2020-12 closed schemas, canonical access enum, action catalog validity) |
| `python -B -m unittest discover -s tests/boundary` | 0 | 32 tests PASS (Toàn bộ boundary test suite: RT-01 Zero-Knowledge, RT-02 Observation/Belief, RT-03 Action boundaries) |
| `python -B -m unittest discover -s tests/perception` | 0 | 10 tests PASS (Enterprise normalizer suite) |
| `python -B -m unittest discover -s tests/planner` | 0 | 16 tests PASS (Planner interface & contracts) |
| `python -B -m unittest tests/runtime/test_belief_state_projection.py` | 0 | 16 tests PASS (Deterministic belief projection suite) |
| `python -B -m unittest discover -s tests/runtime` | 0 | 478 tests PASS (Toàn bộ runtime test suite, 0 regressions) |
| `git diff --check` | 0 | Clean diff (0 whitespace/conflict errors) |
| `python -B scripts/validation/validate_scaffold.py` | 1 | Expected exit 1 duy nhất do pre-existing untracked `.demo-session.json` backend/frontend PID blocker |

### RT-04A — Hidden Scenario & True-State Model receipts

Tranche `RT-04A` (Hidden Scenario & True-State Model) hoàn thành việc định nghĩa hợp đồng kịch bản ẩn (Hidden Scenario Contract) và mô hình trạng thái thực (True State Contract) làm nền tảng cho Enterprise Attack Simulator, bảo đảm:
- Phân tách vật lý ranh giới chân lý (Ground Truth Physical Isolation): True State và Hidden Scenario thuộc độc quyền miền `runtime/simulation` và môi trường Evaluation. Planner domain (`runtime/planners/**`, `agent/planner/**`, `agent/memory/**`) tuyệt đối không được đọc hay import scenario manifest, topology ẩn, lỗ hổng ẩn, credentials ẩn, vị trí crown jewel hay trạng thái phòng thủ ẩn.
- Draft 2020-12 Closed Schema:
  - `runtime/simulation/contracts/scenario.schema.json`: Closed schema mô tả `scenario_id`, `entry_seed`, `hidden_nodes`, `hidden_topology`, `hidden_credentials`, `objective`, `detection_model`, `transitions`.
  - `runtime/simulation/contracts/true-state.schema.json`: Closed schema mô tả `scenario_id`, `run_id`, `current_step`, `random_seed`, `node_states`, `active_sessions`, `credentials_truth`, `reachability_truth`, `objective_truth`, `defender_state`, `action_history`.
- Mô hình độc lập: `TrueState` là dataclass độc lập tại `runtime/simulation/models/true_state.py`, hoàn toàn tách biệt và không subclass hay chia sẻ state representation với `BeliefState`.
- Initial Fog-of-War tại t=0: Chỉ có node `entry_seed` duy nhất được công bố cho planner tại thời điểm ban đầu; toàn bộ topology và node nội bộ còn lại ẩn hoàn toàn.
- Cấu trúc khai báo (Declarative): Không chứa mã thực thi tùy ý, eval string, shell command hoặc payload trong kịch bản.
- Tính tất định (Determinism): Tuần tự hóa JSON và tính toán băm SHA-256 hoàn toàn tất định và có thể tái lập qua `random_seed`.
- 4 kịch bản mẫu chuẩn mực (MVP Scenarios S1–S4):
  1. `scenario_s1_straight.json`: Tiến trình 3 tầng thẳng (Entry foothold -> Internal pivot -> Crown DB).
  2. `scenario_s2_decoy.json`: Tiến trình có nhánh bẫy honeypot và honey-token (`validity_state: HONEY_TOKEN`).
  3. `scenario_s3_blocked.json`: Đường trực tiếp bị chặn firewall (`is_blocked: true`), có đường phụ qua jump-box.
  4. `scenario_s4_clean.json`: Hệ thống clean baseline không có lỗ hổng khả thi, kiểm chứng hành vi dừng an toàn.
- Read-only Evaluator Interface: `ScenarioEvaluationView` tại `runtime/simulation/models/evaluator_view.py` cung cấp giao diện chấm điểm chỉ đọc kết hợp True State, Belief State và Action History.
- Trạng thái: RT-04A là `IMPLEMENTED`; RT-04B (Transition & Observation Simulator) và RT-04C (Gymnasium Simulator Wrapper) giữ nguyên `SPEC_ONLY`.

| Command / Check kiểm chứng thực tế | Exit code | Observed result |
|---|---|---|
| `python -B -m unittest discover -s tests/simulation` | 0 | 27 tests PASS (Draft 2020-12 closed schemas, S1–S4 validation, fail-closed loader, TrueState model separation, deterministic serialization, evaluator view) |
| `python -B -m unittest tests/boundary/test_simulation_boundary.py` | 0 | 7 tests PASS (Zero simulation imports in planner domain, PlannerStateAdapter isolation, Evaluator isolation, t=0 fog-of-war, zero leakage of hidden inventory/topology/credentials/objective) |
| `python -B -m unittest discover -s tests/boundary` | 0 | 39 tests PASS (Toàn bộ boundary test suite: 26 baseline + 6 action boundary + 7 simulation boundary) |
| `python -B -m unittest discover -s tests/contracts` | 0 | 21 tests PASS (Toàn bộ contract test suite: 13 foundation/enterprise schemas + 8 action contract tests) |
| `python -B -m unittest tests/perception/test_enterprise_observation.py` | 0 | 10 tests PASS (Enterprise observation normalizer suite) |
| `python -B -m unittest tests/runtime/test_action_evaluator.py tests/runtime/test_belief_state_projection.py` | 0 | 38 tests PASS (Action constraint evaluator & belief state projection suites) |
| `python -B scripts/validation/validate_scaffold.py` | 1 | Expected exit 1 duy nhất do pre-existing untracked `.demo-session.json` backend/frontend PID blocker |
| `git diff --check` | 0 | Clean diff (0 whitespace/conflict errors) |

### RT-04B — Transition & Observation Simulator receipts

Tranche `RT-04B` (Transition & Observation Simulator) hoàn thành việc triển khai Transition Engine và Observation Generator chuẩn mực (canonical) biến action được Planner đề xuất, Constraint Evaluator chấp thuận và Safety Gate cho phép thành: (1) hidden True-State transition; (2) attacker-observable result; (3) canonical Observation hợp thức hóa với `observation.schema.json` dùng để cập nhật Belief State.

Bảo đảm các bất biến cốt lõi:
- Hard Invariant: `Eligible != Successful`. ActionConstraintEvaluator chỉ đánh giá logic trên Planner-visible Belief State; TransitionEngine thẩm định điều kiện thực tế trên hidden Scenario + TrueState. Một hành động có thể eligible=True nhưng environment outcome=FAILURE (ví dụ do firewall chặn trong S3, honeypot trong S2, hoặc hệ thống an toàn trong S4).
- Pipeline thực thi chuẩn mực (End-to-end Execution Pipeline):
  `Planner Proposal -> ActionConstraintEvaluator -> CentralizedSafetyGate -> Simulation Executor / Transition Engine -> Hidden True-State Transition -> Observation Generator -> Canonical Observation -> StateManager Ingestion -> Belief Projection`.
  Không có đường thực thi nào bypass Safety Gate hay Constraint Evaluator.
- Canonical Transition Engine (`runtime/simulation/engine/transition_engine.py`):
  - Phương thức `transition(true_state, scenario, action, target, rng, proposal_parameters, authorized)` trả về dataclass `TransitionResult`.
  - Functional / Copy-on-write semantics: không mutate TrueState gốc, tạo bản sao mới với các biến đổi (access level, session creation, credential reveal, reachability edges, objective completion).
  - Tích lũy tiếng ồn hoạt động (`accumulated_noise += noise_delta`) và cập nhật trạng thái phòng thủ (`QUIET < MONITORING < ALERTED < CONTAINED`) theo ngưỡng kịch bản.
  - Fail-closed khi hành động chưa được cấp quyền (`authorized=False`).
- Canonical Observation Generator (`runtime/simulation/engine/observation_generator.py`):
  - Phương thức `generate_observation(...)` tạo envelope quan sát canonical tuân thủ 100% JSON Schema Draft 2020-12 closed object qua `validate_canonical_observation`.
  - Sinh fact ID tất định (`FACT-SIM-...`), source kind `SIMULATED`, timestamp UTC chuẩn.
  - Tẩy xóa triệt để (fail-closed sanitization) các khóa cấm rò rỉ Ground Truth (`hidden_nodes`, `topology_graph`, `raw_token`, `cleartext_secret`, `is_decoy`, `is_blocked`).
  - Tự động phát sinh fact fallback `ACTION_OUTCOME` failure khi transition thất bại mà kịch bản không định nghĩa template tương ứng.
- Simulation Executor (`runtime/simulation/engine/simulation_executor.py`):
  - Tích hợp điều phối khép kín: kiểm định điều kiện tiên quyết (`ActionConstraintEvaluator`), kiểm soát an toàn (`CentralizedSafetyGate`), thực hiện transition ẩn (`TransitionEngine`), sinh quan sát chuẩn (`ObservationGenerator`), và cập nhật trạng thái (`StateManager.apply_observation`).
- Trạng thái: RT-04B là `IMPLEMENTED` (cả RT-04A và RT-04B đạt `IMPLEMENTED`; RT-04C Gymnasium Simulator Wrapper giữ nguyên `SPEC_ONLY`).

| Command / Check kiểm chứng thực tế | Exit code | Observed result |
|---|---|---|
| `python -B -m unittest tests/simulation/test_transition_engine.py` | 0 | 7 tests PASS (S1 progression, S2 honey-token alert, S3 firewall blockage failure, S4 clean control failure, copy-on-write immutability, unauthorized rejection, deterministic replay) |
| `python -B -m unittest tests/simulation/test_observation_generator.py` | 0 | 4 tests PASS (Draft 2020-12 schema conformance, secret/ground-truth leakage sanitization, fallback failure fact, deterministic fact IDs) |
| `python -B -m unittest tests/simulation/test_simulation_executor.py` | 0 | 5 tests PASS (Precondition rejection, safety gate rejection, kill switch enforcement, S1 end-to-end progression to objective, S3 partial observability & replan) |
| `python -B -m unittest discover -s tests/simulation` | 0 | 43 tests PASS (Toàn bộ simulation test suite: 27 RT-04A + 16 RT-04B tests) |
| `python -B -m unittest discover -s tests/boundary` | 0 | 41 tests PASS (Toàn bộ boundary test suite bao gồm simulation boundary AST scan engine classes) |
| `python -B -m unittest tests/perception/test_enterprise_observation.py tests/runtime/test_action_evaluator.py tests/runtime/test_belief_state_projection.py tests/contracts/test_action_contract.py` | 0 | 56 tests PASS (Perception, evaluator, belief projection, action contracts suites, 0 regressions) |

### RT-05A — Common Planner Episode Interface & Rule Baseline

- Triển khai thành công Planner-Neutral Episode Integration Layer và Rule-Based Planner Baseline cho Enterprise Red Team Planning theo kế hoạch RT-05A.
- Bề mặt thông tin an toàn duy nhất (`runtime/planners/planner_context.py`):
  - `PlannerDecisionContext`: Dataclass bất biến (`frozen=True`) chứa thông tin an toàn cho planner: `run_id`, `step_index`, `max_steps`, `current_phase`, `remaining_budget`, `max_budget`, `visible_target_ids`, `belief_state`, `candidate_proposals`, `eligible_proposals`, `rejected_proposals`, `previous_outcome`, `objective_statement`, `action_history`.
  - Quét đệ quy thời gian chạy (`_scan_for_forbidden_data`) bảo đảm tuyệt đối không rò rỉ Ground Truth (`true_state`, `hidden_scenario`, `evaluator_view`, topology ẩn, credentials ẩn, defender state ẩn) và numeric Gym reward.
  - Vết quyết định chuẩn tắc (`PlannerDecisionTrace`): ghi nhận đầy đủ `step_index`, `visible_targets`, `candidate_action_ids`, `eligible_candidates`, `chosen_proposal`, `rationale`, `reason_code`, `observable_prior_outcome`, `planning_latency_ms`.
- Bộ sinh đề xuất chuẩn tắc (`runtime/planners/candidate_generator.py`):
  - `CandidateGenerator`: Tái sử dụng thống nhất bởi mọi Planner và `SimulationGymEnv`.
  - Sinh candidate proposals thuần túy từ `belief_state.visible_target_ids` và `ActionRegistry`. Tuyệt đối không đọc danh mục node của `HiddenScenario`.
  - Không đọc danh sách target allowlist của `CentralizedSafetyGate`.
  - Đánh giá tính hợp lệ logic qua `ActionConstraintEvaluator`, gán chi phí `step_cost` và `noise_cost`.
  - Ưu tiên credential hợp lệ cho pivot và objective access; chỉ sinh đề xuất không xác thực khi chưa có credential khớp.
- Gym Action-Mask Non-Leakage (`runtime/simulation/gym_adapter.py`):
  - `SimulationGymEnv._generate_admissible_proposals` ủy quyền trực tiếp cho `CandidateGenerator`.
  - Đảm bảo tại $t=0$, không gian hành động và action mask không tiết lộ số lượng hoặc định danh của các node ẩn.
- Rule-Based Planner Baseline (`runtime/planners/rule_based_planner.py`):
  - Triển khai `_plan_context(context: PlannerDecisionContext) -> PlannerDecision`.
  - Bảo lưu 100% tính tương thích ngược với các kiểm thử evidence-review cũ (`PlanningInput`).
  - Phân cấp ưu tiên ngữ nghĩa chuẩn mực (Semantic Priority Hierarchy):
    1. `OBJECTIVE_COMPLETE` -> STOP
    2. `BUDGET_EXHAUSTED` -> STOP
    3. `NETWORK_RECON` (`ACTION-RECON-001`, `ACTION-DISCOVERY-001`)
    4. `SERVICE_SCAN` (`ACTION-SCAN-001`)
    5. `INITIAL_ACCESS_FOOTHOLD` (`ACTION-WEB-001`)
    6. `HOST_RECON` (`ACTION-HOSTRECON-001`)
    7. `CREDENTIAL_DISCOVERY` (`ACTION-AUTH-001`, `ACTION-CREDS-001`)
    8. `LATERAL_PIVOT` (`ACTION-FLOW-001`, `ACTION-PIVOT-001`)
    9. `PRIVILEGE_ESCALATION` (`ACTION-PRIVESC-001`)
    10. `PURSUING_MISSION_OBJECTIVE` (`ACTION-FLOW-002`, `ACTION-OBJECTIVE-001`)
    11. `NO_VALID_CANDIDATE` -> STOP
  - Tính tất định: Sắp xếp tie-breaking ổn định theo `(target_id, from_node_id, has_credential, credential_id, action_id)`.
  - Tránh lặp lại hành động/đường pivot đã thất bại trên host.
- Common Episode Runner (`runtime/orchestration/planner_runner.py`):
  - `PlannerEpisodeRunner(env, planner, candidate_generator)`: Điều phối vòng lặp tập hoạch định qua `PlannerDecisionContext`.
- Kết quả thực nghiệm Rule Baseline trên S1–S4:
  - **S1 (Straight)**: 12 bước, kết thúc `OBJECTIVE_ACHIEVED`, `obj_achieved=True`.
  - **S2 (Decoy)**: 10 bước, kết thúc `CONTAINED` (tiến vào honeypot do không biết trước là decoy, kích hoạt báo động phòng thủ).
  - **S3 (Blocked)**: 19 bước, kết thúc `OBJECTIVE_ACHIEVED` (bị firewall chặn đường trực tiếp sang crown jewel, tự động replan qua jump-box và hoàn thành mục tiêu).
  - **S4 (Clean)**: 4 bước, kết thúc `PLANNER_STOP` với lý do `NO_VALID_CANDIDATE` (không có lỗ hổng khả thi, dừng sạch sẽ, không bịa đặt thành công).
- Trạng thái: RT-05A là `IMPLEMENTED` (RT-05B LLM Planner và RT-05C Hybrid Planner giữ nguyên `SPEC_ONLY`).

| Command / Check kiểm chứng thực tế | Exit code | Observed result |
|---|---|---|
| `python -B -m pytest tests/runtime/test_planner_context.py -v -o pythonpath=". tests/runtime"` | 0 | 6 tests PASS (A, B, C, K, immutability, to_dict, deterministic hash) |
| `python -B -m pytest tests/runtime/test_candidate_generator.py -v -o pythonpath=". tests/runtime"` | 0 | 4 tests PASS (D, F, I, candidate universe from visible targets, no safety bypass, determinism) |
| `python -B -m pytest tests/boundary/test_planner_boundary.py -v -o pythonpath=". tests/runtime"` | 0 | 1 test PASS (G, AST import boundary scan: runtime/planners does not import runtime/simulation) |
| `python -B -m pytest tests/runtime/test_rule_planner_baseline.py -v -o pythonpath=". tests/runtime"` | 0 | 8 tests PASS (H, I, J, L, M, N, O, P, determinism, S1-S4 baseline execution, safety denial handling) |
| `python -B -m pytest tests/simulation/test_gym_adapter.py -v -o pythonpath=". tests/runtime"` | 0 | 8 tests PASS (E, Farama Gym env_checker, action mask non-leakage at t=0) |
| `python -B -m pytest tests/runtime -o pythonpath=". tests/runtime"` | 0 | 525 passed, 2 skipped in 66.88s (Full runtime regression suite PASS) |
| `python -B -m pytest tests/simulation -o pythonpath=". tests/runtime"` | 0 | 73 passed in 1.49s (Full simulation test suite PASS) |
| `python -B -m pytest tests/boundary -o pythonpath=". tests/runtime"` | 0 | 42 passed in 1.36s (Full boundary test suite PASS) |
| `python -B scripts/validation/validate_scaffold.py` | 1 | Expected exit 1 duy nhất do pre-existing untracked `.demo-session.json` (backend/frontend PID blocker ngoài scope) |
| `git diff --check` | 0 | Clean diff (0 whitespace/conflict errors) |

### RT-05B — LLM Belief-State Planner Baseline

- Triển khai thành công Pure LLM Belief-State Planner Baseline tích hợp trực tiếp vào `PlannerEpisodeRunner(env, planner)` theo kế hoạch RT-05B.
- Tái sử dụng trọn vẹn kiến trúc và abstractions hiện có của `LLMPlanner`:
  - Thừa hưởng `LLMProvider` Protocol, `count_tokens`, và `TokenUsage`.
  - Không tạo tệp v2 thừa thãi; giữ 100% tương thích ngược với các kiểm thử offline metadata review cũ (`tests/runtime/test_llm_planner.py` 48/48 checks PASS).
- Bộ tuần tự hóa ngữ cảnh LLM-safe (`serialize_llm_context`):
  - Strict allowlist: `step_index`, `current_phase`, `remaining_budget`, `max_budget`, `visible_target_ids`, `belief_summary` (access levels, sessions, observed credentials, reachability edges), `observable_prior_outcome` (sanitized failure/success), `eligible_candidates`, `public_objective_statement`.
  - Tuyệt đối cấm và đệ quy phát hiện/chặn: numeric Gym reward, TrueState, HiddenScenario, ScenarioEvaluationView, topology ẩn, credentials ẩn, defender state, detection thresholds, transition probabilities, scenario identifiers (S1/S2/S3/S4), decoy labels, transition IDs.
  - Tạo mã băm SHA-256 bất biến: `context_hash`, `prompt_hash`.
- Ổn định khóa ứng viên và Server-Side Membership Validation:
  - Sinh khóa ứng viên tất định `CAND-001`, `CAND-002`, ... trong `CandidateGenerator` và prompt.
  - Bắt buộc LLM phản hồi JSON thuần tuý: `{"selected_candidate_key": "CAND-001", "reason_code": "...", "brief_justification": "..."}`.
  - Server-side membership validation đối chiếu `selected_candidate_key` trong `candidate_map` nội bộ của bước hiện tại và phục hồi proposal gốc; các tham số mục tiêu hoặc action ID do mô hình tự ý gửi bị phớt lờ, loại bỏ nguy cơ hallucination hoặc vượt quyền.
- Hard Invariant: Fail-Closed Invalid Decision Handling:
  - `fallback_to_rule = False` mặc định cho toàn bộ các lần chạy benchmark.
  - Khi LLM trả về JSON lỗi, sai khóa ứng viên, timeout hoặc từ chối, quyết định lập tức fail-closed với reason `INVALID_LLM_DECISION` (`valid=False`), không tự ý fallback sang `RuleBasedPlanner`.
  - Cơ chế fallback sang Rule chỉ kích hoạt khi được cấu hình tường minh (`fallback_to_rule=True`), ghi nhận cờ `fallback_used=True` và reason `LLM_FALLBACK_TO_RULE`.
- Phân cách an toàn dữ liệu quan sát (Prompt Injection Resilience):
  - Toàn bộ kết quả/quan sát từ môi trường được đóng gói trong khối dữ liệu `### CURRENT OPERATIONAL CONTEXT` với format JSON chuẩn, không thể tác động lên hệ thống chỉ dẫn hoặc vượt qua rào kiểm tra membership.
- Theo dõi số liệu và đo lường (Benchmarking Metrics):
  - Thu thập metadata chi tiết cho từng quyết định: `planner_type`, `model`, `prompt_version`, `prompt_hash`, `context_hash`, `response_hash`, `selected_candidate_key`, `canonical_action_id`, `execution_alias_id`, `target_id`, `reason_code`, `brief_justification`, `fallback_used`, `retry_count`, `valid`, `latency_ms`, `tokens_used`.
  - Bộ đếm metrics: `total_decisions`, `valid_decisions`, `invalid_decisions`, `malformed_decisions`, `unknown_candidate_decisions`, `provider_errors`, `fallback_count`.
- Kết quả thực nghiệm Scripted LLM Baseline trên S1–S4:
  - **S1 (Straight)**: Kết thúc `OBJECTIVE_ACHIEVED`, `obj_achieved=True`.
  - **S2 (Decoy)**: Prompt không chứa bất kỳ decoy oracle nào; LLM tiến vào decoy theo dữ liệu quan sát và kích hoạt containment.
  - **S3 (Blocked)**: Phản ứng thuần túy trước thất bại quan sát được của kết nối trực tiếp, tự động replan sang jump-box và hoàn thành mục tiêu.
  - **S4 (Clean)**: Thực hiện `ACTION-STOP-001` sạch sẽ, kết thúc `PLANNER_STOP`, không bịa đặt thành công mục tiêu.
- Trạng thái: RT-05B là `IMPLEMENTED` (RT-05C Hybrid Planner giữ nguyên `SPEC_ONLY`).

| Command / Check kiểm chứng thực tế | Exit code | Observed result |
|---|---|---|
| `python -B -m pytest tests/runtime/test_llm_planner_baseline.py -v -o pythonpath=". tests/runtime"` | 0 | 18 tests PASS (Invariants A-X: context serialization, leakage prevention, candidate validation, fail-closed handling, token/latency metrics, S1-S4 baseline) |
| `python -B -m pytest tests/runtime/test_llm_planner.py tests/runtime/test_evaluation_operations.py -v -o pythonpath=". tests/runtime"` | 0 | 48 tests PASS (48 subtests PASS, zero regressions on existing LLM planner & evaluation suites) |
| `python -B -m pytest tests/runtime/test_action_space_normalization.py tests/runtime/test_rule_planner_baseline.py -v -o pythonpath=". tests/runtime"` | 0 | 18 tests PASS (Action normalization and rule baseline regression suites PASS) |
| `python -B -m pytest tests/simulation -v -o pythonpath=". tests/simulation"` | 0 | 73 tests PASS (8 subtests PASS, full simulation test suite PASS) |
| `python -B -m pytest tests/boundary -v -o pythonpath=". tests/boundary"` | 0 | 42 tests PASS (51 subtests PASS, full boundary test suite PASS) |
| `python -B -m pytest tests/runtime tests/perception tests/contracts -q -o pythonpath=". tests/runtime"` | 0 | 590 passed, 2 skipped, 529 subtests passed in 350.52s (Full runtime test suite PASS) |
| `python -B scripts/validation/validate_scaffold.py` | 1 | Expected exit 1 duy nhất do pre-existing untracked `.demo-session.json` và bytecode artifacts ngoài scope |
| `git diff --check` | 0 | Clean diff (0 whitespace/conflict errors) |

### RT-05C — Hybrid Belief-State Planner (Proposed Method)

- Triển khai thành công Hybrid Belief-State Planner — phương pháp nghiên cứu đề xuất (proposed research method), kết hợp LLM semantic ranking và deterministic symbolic scoring thành mô hình hợp nhất (fusion ranking) theo kế hoạch RT-05C.
- Kiến trúc Hybrid Planner (`runtime/planners/hybrid_planner.py` & `runtime/planners/symbolic_scorer.py`):
  - Nhận cùng `PlannerDecisionContext`, `CandidateGenerator`, và 9 canonical actions như Rule và LLM baseline; không có quyền truy cập hay quan sát ẩn nào ngoài baseline.
  - LLM Semantic Component: yêu cầu xếp hạng có cấu trúc (`ranked_candidate_keys: ["CAND-001", ...]`), kiểm tra membership chặt chẽ trên máy chủ (loại bỏ unknown/invented/duplicate keys), phục hồi proposal gốc, chuyển đổi tất định sang điểm thứ hạng tuyến tính trong đoạn $[0.0, 1.0]$.
  - Tự động short-circuit khi chỉ có 1 ứng viên hợp lệ (`semantic_call_skipped_reason = SINGLE_CANDIDATE`), gán điểm ngữ nghĩa $1.0$ mà không gọi provider.
  - Deterministic Symbolic Scorer (`SymbolicScorer`): tính toán các thành phần chuẩn tắc từ dữ liệu nhìn thấy được:
    - Heuristic tiến trình generic `progress_score` dựa trên `BeliefState` và họ năng lực (scale $[0.0, 1.0]$).
    - Chuẩn hóa chi phí công khai: `noise_cost_norm` và `step_cost_norm` trong $[0.0, 1.0]$.
    - Hình phạt lặp lại: `repeat_penalty` từ `action_history` (scale $[0.0, 1.0]$).
    - Hình phạt thất bại quan sát được: `failure_penalty` từ `previous_outcome` và `action_history` (scale $[0.0, 1.0]$); tuyệt đối không đọc nguyên nhân thất bại ẩn trong simulator.
  - Mô hình hợp nhất phiên bản hóa `HYBRID_SCORING_V1`:
    $$HybridScore(c) = w_{sem} \cdot S_{sem}(c) + w_{prog} \cdot S_{prog}(c) - w_{noise} \cdot C_{noise}(c) - w_{step} \cdot C_{step}(c) - w_{rep} \cdot P_{rep}(c) - w_{fail} \cdot P_{fail}(c)$$
    với trọng số cố định ban đầu: $w_{sem}=0.40, w_{prog}=0.30, w_{noise}=0.10, w_{step}=0.05, w_{rep}=0.15, w_{fail}=0.20$.
  - Tie-breaking tất định: giải quyết đồng điểm bằng thứ tự ổn định `(-fused_score, canonical_action_id, target_id, from_node_id, credential_id, candidate_signature)`.
  - Fallback an toàn: Khi phản hồi của LLM bị lỗi cấu trúc/khóa lạ/timeout/từ chối, planner tự động hạ cấp sang chế độ `SYMBOLIC_ONLY` (`fallback_used=True`, `semantic_component_valid=False`, $w_{sem}=0.0$), tuyệt đối KHÔNG gọi `RuleBasedPlanner`.
  - Sẵn sàng cho nghiên cứu phân rã (Ablation Readiness): `HybridScoringConfig` cung cấp các preset cho phép bật/tắt độc lập các trọng số (Full, without_noise, without_penalties, semantic_only, symbolic_only).
  - Vết quyết định toàn diện (`HybridDecisionTrace`): ghi lại đầy đủ các điểm thành phần, thứ hạng ngữ nghĩa, thứ hạng cuối, mã băm trọng số, băm ngữ cảnh/prompt/phản hồi, độ trễ và số token tiêu thụ.
- Kết quả thực nghiệm Scripted Hybrid Baseline trên S1–S4:
  - **S1 (Straight)**: Kết thúc `OBJECTIVE_ACHIEVED`, `obj_achieved=True`.
  - **S2 (Decoy)**: Prompt không chứa bất kỳ nhãn bẫy decoy/honeypot nào; Hybrid tiến vào decoy dựa trên dịch vụ quan sát được và kích hoạt containment.
  - **S3 (Blocked)**: Thất bại quan sát được của kết nối trực tiếp làm tăng `failure_penalty`, giúp đường rẽ qua jump-box vươn lên dẫn đầu điểm hợp nhất và hoàn thành mục tiêu.
  - **S4 (Clean)**: Các hành động quét lặp đi lặp lại bị phạt, đưa `ACTION-STOP-001` lên vị trí cao nhất; kết thúc sạch sẽ `PLANNER_STOP`, không tạo mục tiêu giả mạo.
- Trạng thái: RT-05C là `IMPLEMENTED` -> Gói RT-05 chuyển sang trạng thái `IMPLEMENTED` toàn phần (Validation pending independent review).

| Command / Check kiểm chứng thực tế | Exit code | Observed result |
|---|---|---|
| `python -B -m pytest tests/runtime/test_hybrid_planner_baseline.py -v -o pythonpath=". tests/runtime"` | 0 | 24 tests PASS (Invariants A-X: candidate equality, Zero-Knowledge context, ranking validation, signature stability, deterministic scoring, noise/step/repeat/failure penalties, fusion formula, tie-break, symbolic fallback, STOP semantics, S1-S4 baseline execution) |
| `python -B -m pytest tests/runtime/test_hybrid_router.py -v -o pythonpath=". tests/runtime"` | 0 | 20 tests PASS (16 subtests PASS, zero regressions on existing Task-027 hybrid router suite) |
| `python -B -m pytest tests/runtime/test_action_space_normalization.py tests/runtime/test_rule_planner_baseline.py tests/runtime/test_llm_planner_baseline.py tests/runtime/test_hybrid_planner_baseline.py tests/runtime/test_hybrid_router.py -v -o pythonpath=". tests/runtime"` | 0 | 80 tests PASS (Toàn bộ 4 bộ kiểm thử planner baseline và router đạt 80/80 PASS) |
| `python -B -m pytest tests/simulation tests/boundary -q -o pythonpath=". tests/runtime"` | 0 | 115 tests PASS (59 subtests PASS, full simulation + boundary suites PASS) |
| `python -B -m pytest tests/runtime tests/perception tests/contracts -q -o pythonpath=". tests/runtime"` | 0 | 614 passed, 2 skipped, 529 subtests passed in 70.18s (Full runtime test suite PASS) |
| `python -B scripts/validation/validate_scaffold.py` | 1 | Expected exit 1 duy nhất do pre-existing untracked `.demo-session.json` và bytecode artifacts ngoài scope |
| `git diff --check` | 0 | Clean diff (0 whitespace/conflict errors) |

### RT-05D — Benchmark Protocol & Methodology Freeze

Tranche `RT-05D`, plan `PLAN-RT05D-BENCHMARK-FREEZE-001`, build `BUILD-RT05D-001`:
- **Đóng băng phương pháp luận và giao thức đánh giá trước khi chạy comparative benchmark**:
  - Xác lập ranh giới cứng: Kịch bản S1–S4 được sử dụng trong suốt quá trình phát triển hệ thống và kiểm thử tích hợp, do đó được định danh chuẩn tắc là `development / engineering validation scenarios`; tuyệt đối không được báo cáo là tập kiểm thử held-out.
  - Bộ 12 kịch bản held-out chuẩn hóa (`SCN-HELD-001` đến `SCN-HELD-012`) tại `evaluation/datasets/held_out/` và manifest `manifest.json` được dành riêng cho comparative evaluation (H1–H3 Straight, H4–H6 Decoy, H7–H9 Blocked/Replan, H10–H12 Clean Control).
  - Xác thực 100% schema đóng Draft 2020-12 và toàn vẹn tham chiếu ngữ nghĩa qua `ScenarioLoader`.
  - Khử nhiễm benchmark (Non-contamination): Tuyệt đối không chứa ID kịch bản held-out, ID node, IP, hay nhãn họ kịch bản trong mã nguồn production của các planner (`rule_based_planner.py`, `llm_planner.py`, `hybrid_planner.py`, `symbolic_scorer.py`, `candidate_generator.py`).
- **Đóng băng phiên bản và hàm băm bất biến của các Planner**:
  - **RULE**: `RULE_POLICY_VERSION = "RULE_POLICY_V1"`, phân cấp 9 bước ưu tiên, tie-breaking tất định.
  - **LLM**: `LLM_ATTACK_PLANNER_PROMPT_V1`, prompt hash `1d35855b6167b0ce151f400c4fb2b292d3e57779689da4a0273fed8a51ac3533`, `LLM_OUTPUT_SCHEMA_VERSION = "LLM_OUTPUT_SCHEMA_V1"`, `LLM_CONTEXT_SERIALIZER_VERSION = "LLM_CONTEXT_SERIALIZER_V1"`.
  - **HYBRID**: `HYBRID_SCORING_V1_FROZEN`, `HYBRID_PLANNER_PROMPT_V1` (hash `d1280d0b3329c261344f8206fb2a9f61218b55262b0bf9d121c511d83a9e6ec1`), `HYBRID_OUTPUT_SCHEMA_VERSION = "HYBRID_OUTPUT_SCHEMA_V1"`, trọng số đông lạnh ($0.40, 0.30, 0.10, 0.05, 0.15, 0.20$), frozen hash `0e595f7294af58a8f635376e8beedb6688cee6784479ae2eb39c21f5c7213aa8`, V1 canonical hash `68e55385e064cb2867d07207022b665a9660b87938318efa355488d67bc2c799`.
- **Minh bạch việc chọn trọng số**: Tuyên bố trung thực: *"Fixed heuristic weights selected during engineering development and frozen before held-out evaluation."* Tuyệt đối không tinh chỉnh trọng số trên tập held-out.
- **Hình thức hóa định lượng các chỉ số chính (Primary Metrics)**:
  - **Goal Completion Rate (GCR)**: Tỷ lệ hoàn thành mục tiêu chỉ tính trên các kịch bản tấn công ($E_{attack}$); các kịch bản Clean-Control hoàn toàn bị loại khỏi mẫu số.
  - **Dead-End Recovery Rate (DERR)**: Mẫu số tính nghiêm ngặt trên các tập có xuất hiện thất bại quan sát được / ngõ cụt mà vẫn tồn tại đường tiến công thay thế hợp lệ.
  - **Clean-Control Restraint (CCR)**: Đánh giá trên tập Clean-Control; yêu cầu lệnh `ACTION-STOP-001` sạch sẽ mà không kiệt quệ ngân sách, không tạo vòng lặp vô tận, không báo cáo mục tiêu giả, và không kích hoạt containment.
- **Hình thức hóa các chỉ số phụ & chẩn đoán**: Steps to Goal, Operational Noise Cost (tuyệt đối không gọi là evasion/detection probability), Invalid Decision Rate, Replanning Success Rate, Planning Latency, Token/Cost metrics, LLM & Hybrid diagnostics.
- **Quy tắc tổng hợp hành động chuẩn tắc**: Tổng hợp viễn trắc hành động luôn gom nhóm theo canonical benchmark action ID; các alias lịch sử (như `ACTION-FLOW-001`) được ghi nhận `execution_alias_id` riêng nhưng báo cáo dưới ID chuẩn tắc `ACTION-PIVOT-001`.
- **Tiền đăng ký ma trận thực nghiệm và seed manifest**:
  - `evaluation/experiments/seed_manifest.json`: Khóa 5 paired replicates ($R01..R05$: sim seeds `[1001..1005]`, provider seeds `[42..46]`) dưới `CONTROLLED_INFERENCE_CONFIG_V1`.
  - `evaluation/experiments/benchmark_matrix.json`: Khóa 3 baseline (RULE, LLM, HYBRID_FULL) và 4 ablations (NO_NOISE, NO_PENALTIES, SEMANTIC_ONLY, SYMBOLIC_ONLY), tổng cộng chính xác 420 planned episodes (12 held-out $\times$ 5 paired replicates $\times$ 7 configs) với deterministic `experiment_id` — bảo lưu thực thi sang RT-07.
  - `evaluation/datasets/held_out/manifest.json`: Khóa toàn bộ 12 kịch bản held-out với mã băm SHA-256 cố định; xác lập bất biến `evaluation uses manifest-pinned scenario bytes`.
  - `docs/evaluation/benchmark-protocol.md`: Tài liệu đặc tả đóng băng toàn diện giao thức (`BENCHMARK_PROTOCOL_FREEZE_V1 = SEALED`).

| Command / Check kiểm chứng thực tế | Exit code | Observed result |
|---|---|---|
| `python -B -m pytest tests/runtime/test_benchmark_protocol.py -v` | 0 | 20 tests PASS (Invariants A-N & Reqs: Exactly 5 paired replicates, 420 cardinality, non-Cartesian invariant, unambiguous provider seed semantics, manifest hash integrity, pinned scenario bytes, held-out token absence in planner code, family label isolation, evaluator-only recovery opportunity, clean-control error failures, frozen weights hash stability, prompt version/hashes, deterministic experiment_id, ablation isolation, GCR/DERR/CCR metrics) |
| `python -B -m pytest tests/runtime/test_rule_planner_baseline.py tests/runtime/test_llm_planner_baseline.py tests/runtime/test_hybrid_planner_baseline.py -q` | 0 | 50 tests PASS (Rule 16 PASS, LLM 10 PASS, Hybrid 24 PASS — zero regression) |
| `python -B -m pytest tests/simulation tests/boundary -q` | 0 | 115 tests PASS (59 subtests PASS, simulator & boundary contracts intact) |
| `python -B -m pytest tests/runtime tests/perception tests/contracts` | 0 | 628 tests PASS, 2 skipped, zero failures |
| `python -B scripts/validation/validate_scaffold.py` | 1 | Validator contract/schema checks pass; process exit remains 1 due documented pre-existing workspace blockers (`.demo-session.json` PIDs and cached bytecode outside task scope). |

### RT-06 — Mini Enterprise Live Validation Range

- Triển khai thành công Mini Enterprise Live Cyber Range theo kế hoạch RT-06, chứng minh tính tương đương kiến trúc (Simulation-to-Live Architectural Parity) của toàn bộ pipeline tác tử hoạch định tấn công (`PlannerDecisionContext`, canonical action model, `ActionConstraintEvaluator`, `CentralizedSafetyGate`, Planner, `EnterpriseObservationNormalizer`, `BeliefState`).
- Bảo toàn tuyệt đối Hard Invariant:
  - `BENCHMARK_PROTOCOL_FREEZE_V1 = SEALED` nguyên vẹn 100%; không thay đổi Rule policy, LLM prompt/schema, Hybrid weights, held-out scenarios, seed manifest, hay metric semantics.
  - Zero bypass: Tác tử hoạch định tuyệt đối không gọi shell/socket/Docker trực tiếp, không nhìn thấy topology Compose hay địa chỉ IP ẩn.
  - Bí mật tổng hợp (synthetic secrets) được cô lập hoàn toàn ở phía container/harness; Planner và `BeliefState` chỉ tiếp nhận opaque handles (`CRED-OPAQ-*`, `SESS-OPAQ-*`).
  - ShopLab / e-commerce lab hiện hữu được bảo toàn nguyên vẹn; không gây phá vỡ baseline.
  - Không bắt đầu benchmark held-out RT-07.
- Kiến trúc thành phần RT-06:
  - **Phân vùng mạng 4 Zone (`runtime/lab/enterprise_range/topology.py`)**: DMZ (`10.0.1.0/24`), Internal Corporate (`10.0.2.0/24`), Restricted Crown-Jewel Vault (`10.0.3.0/24`), Decoy Honeypot (`10.0.4.0/24`) và Clean Baseline (`lab-enterprise-clean`). Bộ kiểm tra rào chắn mạng fail-closed `validate_network_transition`.
  - **Micro-Services Doanh Nghiệp Thu Nhỏ (`runtime/lab/enterprise_range/services.py`)**: `DMZServiceHandler`, `InternalServiceHandler`, `RestrictedServiceHandler`, `DecoyServiceHandler`, `CleanControlServiceHandler` hỗ trợ discovery, foothold, host recon, synthetic credential discovery, lateral pivot, privilege escalation và objective access.
  - **Harness Quản Lý Cyber Range (`runtime/lab/enterprise_range/harness.py`)**: Quản lý vòng đời HTTP endpoints trên loopback ephemeral ports, tường lửa biên, cô lập route (`block_route`/`unblock_route`) và health checks.
  - **Docker Compose Topology (`cyber-range/enterprise_range/compose.enterprise.yaml`, `Dockerfile`)**: Cấu hình 4 mạng bridge cô lập không có internet outbound (`internal: true`).
  - **Live Executor Adapter (`runtime/lab/live_executor_adapter.py`)**: Bộ điều hợp thực thi live có pipeline tương đương hoàn toàn với `SimulationExecutor`: Proposal -> Precondition Evaluation -> Safety Gate -> Live Dispatch -> Enterprise Normalization -> State Ingestion -> Sanitized Evidence Bundle.
  - **Live Episode Environment (`runtime/lab/live_environment.py`)**: Cung cấp giao diện tương thích hoàn toàn với `EpisodeEnvironment` cho `PlannerEpisodeRunner`, quản lý chu trình POMDP, ngân sách và điều kiện kết thúc.
- Xác thực 4 Ca Kiểm Chứng Thực Địa (Live Validation Cases):
  - **L1 Straight**: `RuleBasedPlanner` hoàn thành chuỗi thâm nhập xuyên suốt 3 zone (DMZ -> Internal -> Restricted) trong 21 bước, chiếm cờ mục tiêu tối thượng và kết thúc với `TerminationReason.OBJECTIVE_ACHIEVED`.
  - **L2 Blocked/Replan**: Khi route chính bị chặn, hệ thống sinh tín hiệu phòng vệ (`WAF_REJECTION`), tác tử ghi nhận vào `BeliefState` và tái hoạch định qua route phụ thành công.
  - **L3 Clean Control**: Tác tử tương tác với mục tiêu sạch không có lỗ hổng, kiềm chế hành vi và kết thúc sạch sẽ qua `ACTION-STOP-001`.
  - **L4 Decoy Defense**: Tác tử tương tác với honeypot và nhận diện tín hiệu cảnh báo phòng thủ chuẩn mực.
- Trạng thái: RT-06 là `IMPLEMENTED` (Validation pending review).

| Command / Check kiểm chứng thực tế | Exit code | Observed result |
|---|---|---|
| `python -B -m pytest tests/runtime/test_live_validation_range.py -v` | 0 | 21 tests PASS, 6 subtests PASS (Invariants A-W: explicit isolation, no compose leak, no socket access, canonical bounded actions, fail-closed unknown action/target, safety gate veto, kill switch veto, shell injection rejection, secret redaction, discovery/foothold/pivot/objective canonical normalization, belief ingestion, zero-dispatch STOP, protocol freeze hashes, L1/L2/L3/L4 live validation) |
| `python -B -m pytest tests/runtime/test_benchmark_protocol.py -v` | 0 | 20 tests PASS (BENCHMARK_PROTOCOL_FREEZE_V1 = SEALED confirmed intact) |
| `python -B -m pytest tests/runtime/ -q` | 0 | 618 passed, 2 skipped, 387 subtests passed in 71.50s (Zero runtime regressions) |
| `python -B scripts/validation/validate_scaffold.py` | 1 | Validator checks pass; process exit remains 1 due documented pre-existing workspace blockers (`.demo-session.json` PIDs outside task scope) |
| `git diff --check` | 0 | Clean diff (0 whitespace/conflict errors) |

### RT-06V — Docker Deployment & Wire-Level Validation

- Triển khai và xác thực toàn diện cụm Docker Compose thực tế (`cyber-range/enterprise_range/compose.enterprise.yaml`, `cyber-range/enterprise_range/Dockerfile`) cho Mini Enterprise Live Range, chuyển đổi từ host loopback harness sang môi trường container độc lập có phân đoạn mạng wire-level thực tế.
- Bảo toàn tuyệt đối Hard Invariant:
  - `BENCHMARK_PROTOCOL_FREEZE_V1 = SEALED` nguyên vẹn 100%; không thay đổi Rule policy, LLM prompt/schema, Hybrid weights, held-out scenarios, seed manifest, hay metric semantics.
  - Zero bypass: CentralizedSafetyGate và KillSwitch chặn hoàn toàn mọi lệnh vi phạm lab scope / target allowlist trước khi chạm tới tầng mạng Docker (`zero_docker_dispatch`).
  - Kiến trúc phân tách mạng vật lý (Wire-Level Physical Segmentation):
    - `dmz_net` (172.28.10.0/24): Ingress bridge cho DMZ web application và Clean control target, chỉ publish loopback `127.0.0.1:18081` và `127.0.0.1:18085` lên host.
    - `internal_net` (172.28.20.0/24): Mạng nội bộ với cờ `internal: true`, ngăn chặn hoàn toàn kết nối trực tiếp từ host hoặc internet outbound. Chỉ DMZ và Internal services được gắn kết.
    - `restricted_net` (172.28.30.0/24): Mạng chứa crown-jewel vault với cờ `internal: true`. Chỉ Internal service được kết nối; DMZ không thể kết nối trực tiếp tới Restricted (thất bại wire-level fail-closed `NETWORK_ISOLATION_BARRIER`).
    - `decoy_net` (172.28.40.0/24): Mạng honeypot decoy với cờ `internal: true`. DMZ không thể kết nối trực tiếp (thất bại wire-level fail-closed `NETWORK_ISOLATION_BARRIER`).
- Các cải tiến kỹ thuật chính:
  - **JSON-Compatible Compose (`cyber-range/enterprise_range/compose.enterprise.yaml`)**: Soạn thảo dưới định dạng JSON-compatible YAML 1.2 tương thích hoàn toàn với trình kiểm tra cấu trúc kho mã `validate_scaffold.py` và Docker Compose v2.
  - **Tối ưu hóa Container Runtime (`runtime/lab/__init__.py`)**: Sử dụng PEP 562 lazy module `__getattr__` cho các import cấp agent, đảm bảo container chỉ chạy lightweight HTTP server với standard library mà không cần copy module agent vào container.
  - **Relay Dispatch & Foothold Enforcement (`runtime/lab/enterprise_range/services.py`)**: DMZ và Internal services xử lý `/api/v1/relay` yêu cầu active session (foothold) hợp lệ trước khi cho phép pivot tấn công sang zone tiếp theo, đồng thời cho phép admin lifecycle (`/health`, `/reset`, `/api/v1/admin/block_route`) phục vụ điều phối episode.
  - **Docker Enterprise Range Harness (`runtime/lab/enterprise_range/harness.py`)**: `DockerEnterpriseRangeHarness` theo dõi trạng thái compromised hosts, thực thi rào chắn mạng logic và vật lý, dispatch qua ingress và pivot relay, hỗ trợ teardown sạch và reset route.
  - **Integration Test Suite (`tests/runtime/test_enterprise_docker_range.py`)**: 9 integration tests tự động quản lý vòng đời Docker Compose (up/down), xác minh:
    1. Container health và readiness trên toàn bộ 5 services.
    2. Wire-level isolation: Host truy cập trực tiếp Internal bị từ chối fail-closed.
    3. Wire-level isolation: DMZ không thể tiếp cận Restricted trực tiếp.
    4. Wire-level isolation: DMZ không thể tiếp cận Decoy trực tiếp.
    5. Live Episode Validation L1 (DMZ -> Internal -> Restricted -> STOP) đạt mục tiêu tối thượng trên Docker.
    6. Live Episode Validation L2 (WAF route block -> Replan qua backup route) trên Docker.
    7. Live Episode Validation L3 (Clean control target kiềm chế hành vi) trên Docker.
    8. Live Episode Validation L4 (Decoy honeypot alert) trên Docker.
    9. CentralizedSafetyGate và KillSwitch chặn hoàn toàn dispatch xuống Docker.
- Vòng đời Docker sạch: Sau khi hoàn thành kiểm thử, `docker compose down` dọn dẹp sạch sẽ toàn bộ container và network, không để lại tài nguyên mồ côi (orphan).
- Trạng thái: RT-06V là `IMPLEMENTED` (Validation pending review).

| Command / Check kiểm chứng thực tế | Exit code | Observed result |
|---|---|---|
| `docker compose -f cyber-range/enterprise_range/compose.enterprise.yaml config -q` | 0 | Valid Compose configuration; valid JSON-compatible YAML; no host network mode; no Docker socket mount |
| `python -B -m pytest -p no:cacheprovider -v tests/runtime/test_enterprise_docker_range.py` | 0 | 9 passed in 32.53s (All 9 Docker integration & wire-level isolation tests PASS) |
| `python -B -m pytest -p no:cacheprovider tests/runtime tests/perception tests/contracts` | 0 | 664 passed, 2 skipped in 99.13s (Zero regressions across 666 test items) |
| `python -B -m pytest -p no:cacheprovider tests/simulation tests/boundary` | 0 | 115 passed in 1.80s |
| `python -B -m pytest -p no:cacheprovider tests/runtime/test_benchmark_protocol.py` | 0 | 20 passed in 0.59s (BENCHMARK_PROTOCOL_FREEZE_V1 = SEALED confirmed intact) |
| `python -B scripts/validation/validate_scaffold.py` | 1 | Compose enterprise YAML accepted without error; exit 1 due only to documented pre-existing workspace items (.demo-session.json PIDs and pycache) |
| `git diff --check` | 0 | Clean diff (0 whitespace/conflict errors) |

### Oscar — thẩm định nguồn offline

Tranche `OSCAR-ADOPTION-001`, plan `PLAN-OSCAR-ADOPTION-001`, build `BUILD-OSCAR-ADOPTION-001`: candidate **HANDOFF_BLOCKED**, chưa là target đã cấu hình/test. Người dùng chọn tái sử dụng open-source để tập trung discovery, safety, observations, planner và evidence. Giữ ShopLab/source/tests và lịch sử SL-01–03; không sửa compose/gateway/registry hoặc chuyển validation cũ sang Oscar.

Nguồn đã đọc không import/execution:
- Official repository `django-oscar`, tag 4.2.1 tại commit `d0a70850abf8e4229d4971aa7e8f4643326ec9f3`.
- Archive GitHub SHA256 `04d59d94f9fe2583a7c6916c08f2d49da47dbaceb9f22e11376fc00969830ece`: 26.240.436 bytes, 1.993 members; inspection không thấy entry nguy hiểm theo checks paths/types/size đã chạy. Chưa extract; scan này không chứng nhận source an toàn.
- Official PyPI release: wheel `django_oscar-4.2.1-py3-none-any.whl`, SHA256 `adbb95ea0130859c204cc6fb221052d6d437ecbaa90800e8418a809f72645e9c`, 8.984.805 bytes, 1.071 members, 135 static asset entries và BSD LICENSE/AUTHORS. Hash khớp metadata PyPI qua HTTPS, không chứng minh chữ ký hoặc wheel khớp commit GitHub. Chưa extract/cài/import.
- Release notes 4.2 upstream ghi Django 6.0/treebeard 5.0 compatibility; 4.2.1 giữ compatibility 4.2. Đây là tuyên bố upstream, không phải local compatibility test.
- Platform/database support upstream: không hỗ trợ Windows; PostgreSQL hỗ trợ chính thức, SQLite chỉ development. WSL có Ubuntu nhưng chưa kiểm chứng dependency/environment isolation. Không chọn DB/runtime thay acceptance âm thầm.
- Upstream `SECURITY.md` có private reporting, không nêu thời hạn support 4.2.1; README còn bảng support cũ. Chưa đủ bằng chứng để claim security-supported.

Source-review gaps: setup.py build hook chạy NPM; Dockerfile tải script remote rồi pipe vào shell; Makefile reset DB/media và nạp auth/orders fixtures. Không chạy hoặc dùng nguyên trạng. Wheel base template gọi CDN jQuery, analytics template gọi Google; cần local override/disable và runtime egress tests. Invoice là extension được README liệt kê, chưa có evidence cho core capability; money Decimal/stock allocation/idempotency/concurrency cần fit-gap, không tự coi đạt acceptance ShopLab.

Artifacts exclusive ngoài repo: `C:/Users/DELL/AppData/Local/Temp/claude/E--PBL6-FINAL/2c00e22a-b129-46e8-aafc-333c2615eda3/oscar-adoption-001/`, gồm baseline/plan, quarantined archive/wheel, archive/wheel inspection và selected-text records. Wheel inspection đã ghi records nhưng command exit 1 khi in Unicode ra console cp1252; không ghi command đó PASS hoặc chạy lại ghi đè artifact. Dependency lock/license audit và môi trường execution chưa đạt, nên product suite/configuration/execution NOT_RUN; không Docker/server/assessment/commit. Tài liệu roadmap được cập nhật, không nâng SL-04–07 `SPEC_ONLY` hoặc tự review/approve target.

Bước an toàn tiếp theo: kiểm chứng môi trường Linux cô lập và dependency lock/license/support; chỉ sau gate đạt mới cấu hình/test upstream offline. Nếu không đáp ứng, báo fit-gap và giữ blocked, không âm thầm đổi ứng dụng hoặc hạ safety.

</details>

## Blockers

- **SL-12 gate state: `UNRESOLVED`.** [Receipt SL-12](#sl-12--kết-quả-deterministic-pre-review-gate-và-pending-review-contract) ghi `HANDOFF_BLOCKED`, trong khi tổng kết cũ bên dưới ghi PASS. Chưa đối chiếu matching build/source/gate receipt; giữ nguyên task row `SPEC_ONLY`, chưa có independent approval. Không dùng một trong hai claim để chứng nhận handoff hiện hành.
- RT extensions và simulator trong working tree cần checks/evidence/review theo scope; có model/loader hoặc test files không đóng RT-04/RT-05. Offline metadata replay không chứng minh benchmark enterprise.
- README và một số canonical guides/specs vẫn phản ánh hướng Web hoặc validation claims khác ledger. Chúng ngoài allowlist đợt này; cần scope tài liệu riêng trước khi sửa. Context/plan hiện hành không coi các claims đó là bằng chứng mới.
- Gate/checker errors trong receipts cũ không tự là blocker của source hôm nay. Mỗi handoff cần kết quả check mới và matching source; lỗi ngoài allowlist phải báo, không tự sửa hoặc chuyển attempts bị chặn thành PASS.
- Review linkage RUNTIME-004, source binding, durable integration và các pending handoff chưa được giải quyết bằng việc thu gọn tài liệu; tra receipts đúng task. `TASK-026` và `TASK-032` giữ `DEFERRED`.

<details>
<summary>Các blocker/tổng kết đã ghi trước tái chuẩn hóa; không dùng làm trạng thái gate hiện hành</summary>


- TASK-027 offline routing reference: `HANDOFF_BLOCKED`, gate triển khai exit 1
  với 27 lỗi ngoài scope và 0 lỗi thuộc router/docs/tests. [Receipts và handoff](docs/implementation/hybrid_router.md)
  giữ checks đồng bộ riêng. Review độc lập, adapter LLM handoff, cross-backend
  completion/history integrity, real provider/tokenizer, durable audit/evidence
  và Task 25 arbitration còn `UNRESOLVED`; full hybrid runtime giữ `SPEC_ONLY`.
- TASK-026 preparatory replay wrapper/protocol: `HANDOFF_BLOCKED` do final gate triển
  khai exit 1 với 27 lỗi ngoài scope (.demo-session.json READY và forbidden bytecode),
  sau gate PASS trước đó. [Receipts và handoff](docs/implementation/offline_rl_protocol.md) tách
  kết quả gate đồng bộ mới khỏi receipt này. SB3/PyTorch compatibility, actual model/
  benchmark/checkpoint, durable evidence và independent review còn `UNRESOLVED`;
  Task 26 toàn phần giữ `DEFERRED`.
- Foundation blockers lịch sử: không có theo bảng hiện hành. TASK-011–014 được TASKS.md ghi validation cho slice cũ; không dùng làm chứng nhận ShopLab/gateway mới hoặc LLM.
- RUNTIME-004 manifest ghi `IMPLEMENTED` trong khi task prose ghi `VALIDATED` qua approved review. Cần đối chiếu review/claim scope và hashes trước tái sử dụng; chưa xác minh trong phiên này, không sửa evidence hoặc tự thay status lịch sử.
- Documentation checker compatibility và blocker SL-01 trước đây đã được xử lý: exact 35 TASK + 12 SL được kiểm tra, required checks và gate PASS, review độc lập APPROVE đã xác minh. Không còn blocker cho baseline SL-01; các attempts bị chặn trước đây không được chuyển thành PASS.
- SL-02 không còn blocker trong scope offline được review: lifecycle, rollback, schema preservation, concurrency và process-restart persistence đã có checks/review R1. Auth/CSRF/ownership SL-03 đã IMPLEMENTED và có offline checks, nhưng chưa có independent approval; checkout/stock/idempotency (SL-04), orders/reviews (SL-05), admin nghiệp vụ (SL-06), lab runtime (SL-07), discovery safety gate (SL-08), observed planner (SL-09), PTES coordinator điều phối 7 phase trung thực (SL-10), và immutable evidence packaging / zero-network replay (SL-11) đã hoàn thành implementation với receipts kiểm thử đầy đủ cùng live Docker verification và gói chuẩn mực `RUN-SL11-HANDOFF-20261011/`.
- `lab-ecommerce` đã được đăng ký chính thức vào `configs/safety/target-allowlist.yaml` và manifest; CentralizedSafetyGate áp dụng bất biến tập giao `canonical allowlist ∩ run-approved targets`, runtime caller không thể nới rộng chính sách.
- Docker isolation, durable storage và product E2E (SL-07), discovery safety gate (SL-08), observed planner (SL-09), PTES coordinator (SL-10) và evidence packaging/replay (SL-11) đã hoàn thành implementation; SL-12 deterministic pre-review gate đã PASS (khóa build/evidence identity, source manifest và review contract), đang chờ independent review độc lập thực hiện. Chưa có independent review / approval; không tự nâng `VALIDATED`.
- Active exploitation và post-exploitation ngoài safe verification chưa có executable scope. Phase cần quyền vượt scope phải `BLOCKED`/`NOT_RUN`, không fake completed. Task status vocabulary giữ nguyên; `NOT_RUN` chỉ là phase execution status.
- Public targets, production data, new payloads, arbitrary shell, dynamic actions và tự nâng validation vẫn không được phép.

</details>
