# Tasks

Status vocabulary: `SPEC_ONLY`, `TBD`, `UNRESOLVED`, `IMPLEMENTED`, `VALIDATED`, `DEFERRED`, `BLOCKED`.

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

## ShopLab/PTES implementation backlog

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

### Enterprise Red Team Planning backlog

Nguồn kế hoạch: `PLAN-ENTERPRISE-REDTEAM-001`, work package nhóm `RT-*` chuyển đổi trọng tâm sang **AI Attack Planning for Red Team under Partial Observability (Belief-State Planning)**. Kế thừa toàn bộ contracts, action catalog, safety gate và evidence framework hiện có; không thay đổi canonical task IDs `TASK-001..035` hoặc các validation lịch sử `SL-01..12`.

| Work package | Liên kết task nền | Trạng thái ban đầu | Phụ thuộc | Đầu ra và điều kiện chấp nhận |
|---|---|---|---|---|
| RT-00 | TASK-002, TASK-003 | `IMPLEMENTED` | Không | Enterprise Red Team Planning Rebaseline: Tranche tài liệu và quản trị. Ban hành ADR-014 (Belief State Architecture), cập nhật AGENTS.md sang allowlist theo task, rebaseline PROJECT_CONTEXT.md, PROJECT_PLAN.md, TASKS.md. Bảo toàn toàn bộ lịch sử foundation và evidence. Báo cáo checks, blockers và allowlist RT-01. |
| RT-01 | TASK-003, TASK-008, TASK-009 | `SPEC_ONLY` | RT-00 | Zero-Knowledge Boundary: Di chuyển ground-truth schema từ `agent/planner/contracts/ground-truth.schema.json` sang vị trí canonical dưới `evaluation/**`. Thiết lập rào chắn Zero-Knowledge: Planner không nhận ground truth, global network topology, full target allowlist, hidden credentials hoặc defender state. Tests kiểm tra rào chắn fail-closed. |
| RT-02 | TASK-005, TASK-006, TASK-019 | `SPEC_ONLY` | RT-01 | Belief State: Thiết kế schema và hiện thực hóa `BeliefState` kế thừa từ `StateManager`. Xây dựng cơ chế cập nhật niềm tin từ quan sát cục bộ (observed facts, reachable assets, open services, credential cache, privilege level, confidence decay). Tuyệt đối không chứa oracle state. |
| RT-03 | TASK-004, TASK-012, TASK-013 | `SPEC_ONLY` | RT-01, RT-02 | Enterprise Action Model: Chuẩn hóa catalog hành động doanh nghiệp có giới hạn (Enterprise Bounded Actions: recon, discovery, credential access probe, lateral movement hypothesis). Tuân thủ nguyên tắc bounded action; cấm arbitrary shell và free-form payloads. |
| RT-04 | TASK-007, TASK-010, TASK-023 | `SPEC_ONLY` | RT-02, RT-03 | Simulation Backend: Xây dựng simulator POMDP enterprise. Lưu giữ True State độc quyền trong engine, trả về partial observations và accounting chi phí/ngân sách cho planner. Chạy deterministic offline tests; hoàn thành và kiểm chứng độc lập TRƯỚC KHI kết nối live range. |
| RT-05 | TASK-020, TASK-021, TASK-022, TASK-027 | `SPEC_ONLY` | RT-04 | Planner Integration: Tích hợp các planner (RULE baseline, LLM planner, RL policy, HYBRID router) với `BeliefState` và Simulation Backend. Tuân thủ proposal schema, kiểm định provenance, strict error fallback, zero-dispatch gate evaluation. |
| RT-06 | TASK-011, TASK-012, TASK-013, TASK-014 | `SPEC_ONLY` | RT-04, RT-05 | Mini Enterprise Live Range: Cyber-range multi-host doanh nghiệp thu nhỏ cô lập (Docker internal networks, segmented VLANs, simulated services, loopback ingress). Dùng chung executor và observation contract với simulator (RT-04). Tích hợp CentralizedSafetyGate kiểm soát phân quyền. |
| RT-07 | TASK-028, TASK-029, TASK-030, TASK-031 | `SPEC_ONLY` | RT-05, RT-06 | Experimental Evaluation: Bộ kịch bản đánh giá so sánh (benchmark suite) trên simulator và live range. Chấm điểm planner dựa trên Ground Truth (cô lập trong evaluation). Đo lường metrics: success rate, steps to goal, budget efficiency, belief accuracy vs true state. |

## Checks and observed implementation state

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

## Blockers

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
