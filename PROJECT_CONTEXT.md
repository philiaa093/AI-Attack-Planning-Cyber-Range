# Project Context

## Purpose

Dự án tái định hướng trọng tâm nghiên cứu sang **AI Attack Planning for Red Team under Partial Observability (Belief-State Planning)** trong môi trường mạng doanh nghiệp mô phỏng và cyber range cô lập. Toàn bộ nền tảng, cơ chế quản trị an toàn (Safety Gate), contracts, và bằng chứng lịch sử của Web Pentest Cyber Range MVP (ShopLab và chuỗi SL-01–SL-11) được bảo toàn nguyên trạng làm baseline kiểm chứng. Không chuyển validation cũ sang kiến trúc mới hoặc coi các bài toán đồ thị biết trước đường đi là hoàn thành mục tiêu.

Trọng tâm nghiên cứu cốt lõi:
- Bài toán hoạch định tấn công của tác tử Red Team dưới điều kiện quan sát một phần (POMDP / belief-state planning). Tác tử không có oracle view, không được biết trước sơ đồ mạng tổng thể (global topology), không có danh sách mục tiêu đầy đủ, mã nguồn, hay vị trí lỗ hổng.
- Planner chỉ được tiếp cận các quan sát thực tế (observations) và trạng thái niềm tin (Belief State) được xây dựng từ quan sát.
- Các chế độ planner tiếp tục bao gồm `RULE`, `LLM`, `RL`, `HYBRID`; hoạch định trên không gian trạng thái niềm tin với danh mục hành động hữu hạn có giới hạn (Enterprise Bounded Actions).
- Cơ chế kiểm soát an toàn (Centralized Safety Gate) giữ thẩm quyền tuyệt đối trước mọi dispatch. Tuyệt đối không mở public targets, không arbitrary shell, và không free-form payload execution.

## Architecture

Kiến trúc phân tách ranh giới niềm tin và ranh giới an toàn (Trust & Belief Boundary Separation):
- **Belief State & Planner Context**: Planner CHỈ được nhận các quan sát (observations) đã redact và cập nhật trạng thái niềm tin (Belief State). Ground truth, global network topology, full target allowlist, target source code, hidden credentials, và defender-private state (nhật ký SIEM, bẫy honeypot, trạng thái ẩn nội bộ phía phòng thủ) TUYỆT ĐỐI KHÔNG xuất hiện trong planner context.
- **True State**: True State toàn cục chỉ thuộc quyền sở hữu của Simulator và Evaluator nhằm duy trì tính chân thực của bài toán quan sát một phần.
- **Ground Truth**: Ground truth chỉ thuộc phân hệ evaluation (vị trí canonical dưới `evaluation/**`). Ground truth dùng để chấm điểm và kiểm chứng độ chính xác của Belief State sau run, không tham gia vào quá trình planning.
- **Safety Scope != Planner-Visible Scope**: Ranh giới an toàn (Safety Scope) do Safety Gate nắm giữ để thực thi chính sách bảo vệ lab (canonical target allowlist, action catalog, rate limits, budgets). Planner tuyệt đối không được nhận full target allowlist nhằm triệt tiêu rò rỉ tri thức oracle. Planner chỉ thấy các thực thể đã quan sát qua discovery từ seed được duyệt.
- **Luồng điều phối tam giác (Planner – Gate – Executor)**:
  `SEED/APPROVAL -> DISCOVERY/ACTION OBSERVATION -> BELIEF STATE -> SCHEMA-BOUND PROPOSAL -> CENTRALIZED SAFETY GATE (AUTHORIZATION) -> BOUNDED EXECUTOR -> OBSERVATION -> IMMUTABLE EVIDENCE -> BELIEF UPDATE -> REPLAN -> REPORT`.
- Mọi request, redirect, auxiliary request đều qua Safety Gate trước khi dispatch. Safety refusal xảy ra trước network/simulator side-effect.
- HTTP 200, reflection, error hoặc banner không tự chứng minh vulnerability hay access level nếu thiếu observed evidence xác thực.
- Simulator (mô phỏng POMDP) và Mini Enterprise Live Range dùng chung executor interface và result/observation contract; simulator hoàn thành và kiểm chứng trước khi kết nối live range.

## Planner model

- `RULE`: baseline xác định hoạch định trên Belief State, phải được báo cáo đúng mode.
- `LLM`: đề xuất schema-bound từ Belief State và observations, không tự cấp quyền hoặc tạo action/command/payload mới.
- `RL`: học chính sách (policy) trong POMDP / belief MDP với action space hữu hạn; không triển khai trước simulation backend và safety pipeline.
- `HYBRID`: kết hợp candidates trên Belief State nhưng không bypass policy gate.

Lỗi provider, malformed output và fallback phải được ghi rõ. Một run chỉ dùng rule không được mô tả là LLM run thành công. Tái dùng StateManager / mở rộng BeliefStateManager cho state, belief decay/updates, request/time budget và replay; không thay đổi action ID hoặc contract semantics âm thầm.

## Current state

Nguồn trạng thái task là [TASKS.md](TASKS.md), không phải số lượng file đã tạo. Các trạng thái lịch sử được giữ nguyên trong lần cập nhật tài liệu này, không phải được review hoặc xác nhận lại:

- Foundation và perception subset lịch sử: trạng thái `VALIDATED` được TASKS.md gắn với evidence hiện có. TASK-018 hiện `IMPLEMENTED` cho phần mở rộng Nuclei ngoại tuyến theo yêu cầu người dùng; validation cũ không bao phủ extension mới. Receipts phiên triển khai có 141 tests PASS; independent review, durable evidence integration và runtime còn `UNRESOLVED`. Chi tiết tại [TASKS.md](TASKS.md#task-018--observation-normalizer-và-giao-tiếp-nuclei-ngoại-tuyến).
- TASK-011–014: TASKS.md ghi `VALIDATED` cho local Docker slice qua RUNTIME-004, không bao gồm ShopLab, planner hoặc real external-tool execution. Manifest RUNTIME-004 có status `IMPLEMENTED`; liên kết review và phạm vi validation cần đối chiếu trước khi tái sử dụng claim. Không sửa evidence hoặc tự hạ/nâng trạng thái lịch sử.
- SL-01 baseline và SL-02 storage lifecycle đã được kiểm chứng trong phạm vi offline fixture/mock và SQLite temp. SL-02 dùng connection riêng theo service, explicit transactions, schema version 1 fail closed và bounded admission/drain; hai process restart giữ products/orders/order_items, không reseed accounts. Đây không phải sản phẩm hoàn chỉnh hoặc runtime được kiểm chứng.
- SL-02 R1: 90 tests PASS, AST 2 files/scaffold checker/gate PASS; review độc lập `FINAL / APPROVE` được verifier xác nhận exit 0 ngày 2026-10-10. F01 schema-prefix wildcard đã được tái hiện và sửa, regression giữ nguyên DB bytes khi reject. Exact commands, hashes và artifacts của `PLAN-SL02-STORAGE-001` / `BUILD-SL02-STORAGE-001` được ghi tại [TASKS.md](TASKS.md#checks-and-observed-implementation-state).
- Các attempts gateway/storage từng bị classifier chặn trước thực thi vẫn không có exit code/PASS; receipts SL-01/SL-02 là những lần chạy mới, không chuyển attempts cũ thành thành công. Chưa có Docker/LLM/PTES run chứng minh mục tiêu; actual restore/session invalidation, Docker durability và invoice filesystem/DB atomicity chưa được kiểm chứng.
- SL-03 auth/session/CSRF/ownership hiện `IMPLEMENTED`: revision R1 có 114 tests PASS, AST ba file/scaffold checker/gate PASS. Schema v2 cho DB mới; reject v1 trước writes, không tự migrate. Người triển khai đã tự review và sửa validation ID/query; chưa có independent review APPROVE được xác minh nên không nâng `VALIDATED`. Exact receipts và giới hạn tại [TASKS.md](TASKS.md#sl-03--kết-quả-offline-r1).
- SL-04 checkout atomic/stock/idempotency, owner semantics, decoupled invoice và USD integer minor units đã `IMPLEMENTED` trên ShopLab (13 tests checkout PASS, tổng 65 tests ecommerce PASS); chưa có independent review APPROVE.
- SL-05 đơn hàng, snapshot immutability, IDOR protection (404), API data minimization, hóa đơn lab notice kèm fallback on-demand từ DB, đánh giá sản phẩm (1-5 sao, <= 4000 ký tự) và chống Stored XSS đã `IMPLEMENTED` trên ShopLab (16 tests orders/reviews PASS, tổng 81 tests ecommerce PASS); chưa có independent review APPROVE.
- SL-06 admin backoffice phân quyền server-side, máy trạng thái đơn hàng forward-only (`pending` -> `processing`/`cancelled`, `processing`/`completed` -> `shipped`, `shipped` -> `delivered`), chính sách hủy đơn nghiêm ngặt (chỉ `pending`), soft-archive sản phẩm (`product_archives`), cập nhật tồn kho an toàn và audit log (`admin_activity_log`) đã `IMPLEMENTED` trên ShopLab (14 tests admin PASS, tổng 95 tests ecommerce PASS); chưa có independent review APPROVE.
- SL-07 Docker Compose lab cô lập (`internal: true`), Gateway loopback ingress `127.0.0.1:18088:8080`, named volume `cyber-range_ecommerce-data` mount tại `/app/data`, kịch bản live Docker `scripts/cyber-range/verify_live_docker.py` xác thực thành công 8/8 pha (health, full flow, IDOR isolation, container restart, container replacement đổi ID bảo toàn volume, failure 502 injection, restore baseline via ephemeral container, bounded teardown) và 17 tests gateway E2E đã `IMPLEMENTED` trên ShopLab; chưa có independent review APPROVE.
- SL-08 discovery dựa trên quan sát và centralized safety gate đã `IMPLEMENTED`: `runtime/discovery_recorder.py` bảo đảm ghi bền vững intent trước dispatch và result trước request kế tiếp, fsync, SHA-256, schema validation (`evidence.schema.json`) và fail-closed; `runtime/discovery_gate.py` tập trung toàn bộ kiểm tra chính sách (lab mode, budget, sliding rate limit, kill switch, dynamic TOCTOU revocation) với bất biến giao quyền nghiêm ngặt `effective_targets = canonical_allowlist & run_approved_targets`; `runtime/discovery_engine.py` BFS khám phá liên kết từ seed `/` an toàn, chỉ thu thập metadata cho forms (không gửi submit), giới hạn độ sâu/chuyển hướng. 7 preflight tests E01–E07 PASS, 9 safety tests D01–D09 PASS, 7/7 pha live Docker verification `scripts/cyber-range/verify_sl08_live.py` PASS; chưa có independent review APPROVE.
- SL-09 planner dựa trên observed state và replan đã `IMPLEMENTED`: `runtime/planner_adapter.py` tái sử dụng `StateManager`, bảo đảm tính bất biến khi nạp observation, báo lỗi xung đột dữ liệu, cô lập/redact dữ liệu nhạy cảm và HTML, ngân sách do `StateManager` quản lý duy nhất; `runtime/observed_planner.py` tạo đề xuất schema-bound (`plan.schema.json`), theo dõi minh bạch `mode_provenance` (chế độ yêu cầu, chế độ thực thi, lý do fallback, nguồn quyết định), chính sách fallback nghiêm ngặt dừng an toàn khi `fallback_allowed=False`, đánh giá gate không dispatch mạng (`evaluate_proposal_against_gate`). 13 tests (P01–P08 và tests thẩm quyền allowlist 0.4–0.6) PASS, 8/8 pha live Docker verification `scripts/cyber-range/verify_sl09_live.py` PASS; chưa có independent review APPROVE.
- SL-10 PTES Coordinator đã `IMPLEMENTED`: `runtime/ptes_coordinator.py` kết nối trực tiếp với SL-08 safety gate/recorder và SL-09 planner, điều phối 7 giai đoạn PTES có tiêu chí entry/exit độc lập, phản ánh trung thực trạng thái (Phase 1 COMPLETED, Phase 2 COMPLETED_BOUNDED, Phase 3 COMPLETED, Phase 4 COMPLETED, Phase 5 BLOCKED, Phase 6 NOT_RUN, Phase 7 COMPLETED; 0 confirmed vulnerabilities, 0 unsafe dispatches); 8 unit tests T01–T08 PASS, 7/7 phase live Docker verification PASS; chưa có independent review APPROVE.
- SL-11 immutable evidence packaging, reporting và deterministic replay đã `IMPLEMENTED`: `runtime/evidence_package.py` và `runtime/discovery_recorder.py` đóng gói bằng chứng nguyên tử với cơ chế tạo độc quyền (exclusive creation), kiểm chứng root containment chống escape trên custom `base_dir` (B01–B04), khóa bất biến không tái sử dụng run dở dang (B05), khử dữ liệu nhạy cảm (secret redaction), sinh báo cáo lab liên kết bằng chứng (`report.md`, `report.json`), và bộ máy replay ngoại tuyến xác định với `ZeroNetworkGuard` bảo đảm đúng 0 network dispatches và 0 provider dispatches; 14 tests E01–E09 & B01–B05 PASS; gói bằng chứng chuẩn mực bàn giao lưu tại `evidence/runtime/RUN-SL11-HANDOFF-20261011/` (51 files, 23 records); minh bạch ghi nhận sai lệch lịch sử `HISTORICAL_EVIDENCE_DISCREPANCY = ABORTED_RUN_DIRECTORY_DELETED_DURING_SELF_REVIEW`; chưa có independent review APPROVE.
- Autonomous Closed-Loop Runner đã `IMPLEMENTED`: `runtime/autonomous_runner.py` hiện thực hóa vòng lặp điều khiển tự động hoàn chỉnh `OBSERVATION -> STATE -> AI PLANNER -> PROPOSAL -> SAFETY GATE -> EXECUTOR -> NEW OBSERVATION -> STATE UPDATE -> AI REPLAN -> ... -> STOP`. Bất biến zero direct transport: runner không chứa client HTTP/socket trực tiếp, mọi I/O mạng đi qua `CentralizedSafetyGate`. Ghi nhận fail-closed evidence (intent trước dispatch, result trước request kế tiếp), nhận diện chu kỳ bế tắc (`NO_PROGRESS_LOOP`), và phản ứng thích ứng với từ chối an toàn (`REFUSAL`). Bộ kiểm thử chấp nhận 12 tiêu chí (A01–A12) trong `tests/runtime/test_autonomous_runner.py` đạt 12/12 PASS (exit code 0). Live verification trên ShopLab cyber-range `scripts/cyber-range/verify_autonomous_live.py` đạt PASS (Run ID `RUN-AUTONOMOUS-LIVE-1791708234`, 4 iterations, 3 approved dispatches, 0 denied, 11 network dispatches, 0 unsafe dispatches, 20 observations, stop reason `discovery_surface_complete`, exit code 0); bảo toàn volume `ecommerce-data` và tính bất biến của bằng chứng lịch sử; chưa có independent review APPROVE.
- Autonomous Pentest Loop với Safe Active Verification đã `IMPLEMENTED`: `runtime/capability_registry.py` cung cấp các bounded verifiers (`SafeInputVerificationExecutor` cho `ACTION-WEB-001`, `SafeReflectionVerificationExecutor` cho `ACTION-WEB-002`, `SafePathFixtureVerificationExecutor` cho `ACTION-WEB-003`, `PassiveSurfaceAnalyzer` cho `ACTION-SCAN-001`). Khắc phục triệt để 3 blocker findings từ Independent Review: F-01 (Form Provenance — chuẩn hóa relative URL cho form action, cô lập form POST thành candidate metadata mà không tạo synthetic GET query lên trang chứa), F-02 (Data-Driven Hypothesis Affinity — định tuyến giả thuyết theo ngữ nghĩa tham số và outcome-driven replan thay cho fixed sequence ladder), F-03 (Truthful Security Claims — giới hạn độ tin cậy kết quả âm tính <= 0.75, phát biểu trung thực theo quan sát probe thay vì cam đoan kiến trúc hệ thống). 18 tests chấp nhận trong `tests/runtime/test_autonomous_pentest.py` đạt 18/18 PASS. Kịch bản live pentest `scripts/cyber-range/run_autonomous_pentest.py` đạt PASS (Run ID `RUN-AUTONOMOUS-PENTEST-1791723996`: 7 decisions, 6 approved, 0 denied, 3 active verifications, 23 network dispatches, 0 unsafe dispatches, 3 honest negative findings, stop reason `discovery_surface_complete`, Docker teardown sạch sẽ bảo toàn volume dữ liệu); chưa có independent review APPROVE.
- TASK-015 là `IMPLEMENTED` trong phạm vi discovery report importer/observations offline (`runtime/discovery_report_importer.py`), liên quan discovery SL-08; check cập nhật trạng thái ngày 2026-10-11 đạt 45 tests PASS, exit 0. Giữ provenance `IMPORTED_OFFLINE`/`SIMULATED_FIXTURE`; adapter discovery cũ còn mô phỏng, external execution `UNRESOLVED`, acceptance và independent review chưa hoàn tất.
- TASK-016 là `IMPLEMENTED` trong phạm vi parser/safety wrapper ZAP JSON ngoại tuyến, chưa `VALIDATED`. `import_report` chỉ trả candidates đã validate/minimize (`endpoint_id=null`); `execute` luôn `DENIED`, không scanner/network hoặc scan `SUCCESS` giả. Self-check lịch sử ngày 2026-10-11: 16 ZAP + 27 adapters + 17 safety tests PASS, bốn hashes khớp build `BUILD-TASK016-ZAP-OFFLINE-001`; check cập nhật trạng thái chạy lại suite ZAP đạt 16 tests PASS, exit 0, không tái xác nhận hashes/build cũ. Chưa có independent approval. Checker trước đó exit 1 do lỗi tại `dashboards/app/frontend/node_modules/**` ngoài allowlist, handoff `HANDOFF_BLOCKED`; chưa chạy lại gate trong lần cập nhật này. ZAP thật, tương thích report thực tế và durable evidence integration chưa được chứng minh; kế hoạch evidence offline đã duyệt nhưng chưa triển khai. Chi tiết receipts/giới hạn tại [TASKS.md](TASKS.md#checks-and-observed-implementation-state).
- TASK-017 là `IMPLEMENTED` trong phạm vi parser/safety wrapper Nuclei ngoại tuyến theo yêu cầu người dùng, chưa `VALIDATED`. Nhập JSON/JSONL trong bộ nhớ, allowlist template ID cụ thể mặc định rỗng, validate/minimize all-or-nothing; `execute` luôn `DENIED`. Receipts phiên triển khai ngày 2026-10-11: 28 Nuclei + 27 adapters + 17 safety tests PASS, AST/diff checks PASS; repository gate exit 1, 643 lỗi ngoài scope và 0 lỗi thuộc Task 17 ở lần chạy cuối của phiên đó. Scanner runtime scaffold vẫn `SPEC_ONLY`; report thật, durable evidence và independent review `UNRESOLVED`. Chi tiết/handoff tại [TASKS.md](TASKS.md#task-017--parser-và-safety-wrapper-nuclei-ngoại-tuyến).
- TASK-020 hiện `IMPLEMENTED` cho Planner ABC/DTO và adapter đọc snapshot Task 19 ngoại tuyến, cập nhật ngày 2026-10-12 theo yêu cầu người dùng. Receipts triển khai: 28 focused + 21 state-store regression + 16 planner contract tests PASS (65 tests); AST/example/whitespace PASS. Source hashes được đối chiếu khi cập nhật trạng thái, không chạy lại suites. Checker phiên triển khai exit 1 với 656 lỗi ngoài scope, 0 lỗi thuộc ba paths Task 20; handoff `HANDOFF_BLOCKED`. Independent review, real backends, reference/evidence integrity và runtime integration giữ `UNRESOLVED`; proposal không cấp quyền dispatch. Chi tiết tại [TASKS.md](TASKS.md#task-020--planner-interface-ngoại-tuyến).
- TASK-021 hiện `IMPLEMENTED` cho baseline RuleBasedPlanner xem xét bằng chứng ngoại tuyến, cập nhật ngày 2026-10-12 theo yêu cầu người dùng; chưa `VALIDATED`. Kế thừa Task 20, đọc snapshot Task 19, luật immutable có thứ tự xác định và chỉ đề xuất `ACTION-PLAN-003`; completion CONTROL gắn với feedback giúp tránh lặp cùng phiên bản candidate. Receipts triển khai: 28 focused + 65 dependency/contract tests PASS (93 tests, từng suite exit 0), AST/example/whitespace PASS. Source hashes khớp receipts khi cập nhật trạng thái; không chạy lại suites trong lần cập nhật tài liệu. Checker phiên triển khai exit 1 với 656 lỗi ngoài scope, 0 lỗi thuộc ba paths Task 21; handoff `HANDOFF_BLOCKED`. Independent review, durable evidence/coordinator integration, scanner execution và full research baseline giữ `UNRESOLVED`. Chi tiết tại [TASKS.md](TASKS.md#task-021--rule-based-planner-ngoại-tuyến).
- TASK-022 hiện `IMPLEMENTED` cho LLMPlanner xem xét metadata bằng chứng ngoại tuyến, cập nhật ngày 2026-10-12 theo yêu cầu người dùng; chưa `VALIDATED`. Kế thừa Task 20, đọc snapshot Task 19; context có giới hạn, system prompt, strict tool schema và revision binding; chỉ đề xuất `ACTION-PLAN-003` hoặc dừng. Replan theo feedback, completion CONTROL và fallback `LLM` → `RULE` có provenance rõ ràng. Receipts triển khai: 31 focused + 93 regression tests PASS (124 tests), AST/document/link/whitespace PASS. Source hashes khớp receipts khi cập nhật trạng thái; không chạy lại suites trong lần cập nhật tài liệu. Checker triển khai exit 1 với 613 lỗi ngoài scope, 0 lỗi thuộc ba paths Task 22; handoff `HANDOFF_BLOCKED`. Provider/model/tokenizer thật, durable evidence/history/reference integrity, coordinator/gate integration và review độc lập còn `UNRESOLVED`; fixture không chứng minh LLM runtime. Chi tiết tại [TASKS.md](TASKS.md#task-022--llm-planner-xem-xét-bằng-chứng-ngoại-tuyến).
- TASK-023 hiện `IMPLEMENTED` cho [Gymnasium replay ngoại tuyến](docs/implementation/rl_environment.md)
  theo yêu cầu ngày 2026-10-12; chưa `VALIDATED`. Fixed action/observation spaces,
  step/reset, replay approval/order/rate/budget và adapter chỉ đọc snapshot Task 19/20.
  23 focused tests gồm check_env + 49 regression tests PASS. Audit trong bộ nhớ;
  durable evidence, report integrity, independent review và live integration còn
  `UNRESOLVED`. Không scanner/executor/provider/network dispatch; reward chỉ minh họa.
  Repository gate triển khai exit 1: 613 lỗi ngoài scope, 0 lỗi Task 23;
  handoff `HANDOFF_BLOCKED`, blocker `REPOSITORY_CHECKER_FAILED_OUTSIDE_SCOPE`.
  Source hashes đã đối chiếu khớp receipts khi đồng bộ tài liệu; không chạy lại
  72 tests trong lần cập nhật này. Reward trả về từ Task 23 vẫn chỉ minh họa;
  runner Task 25 dùng scorer Task 24 riêng sau mỗi bước đã commit.
- TASK-024 hiện `IMPLEMENTED` cho [scorer đánh giá metadata ngoại tuyến](docs/implementation/reward_model.md),
  cập nhật trạng thái ngày 2026-10-12 theo yêu cầu người dùng; chưa `VALIDATED`.
  Scorer độc lập chấm outcome đóng, phạt lặp/rate/order/refusal và dừng sớm; candidate
  không được coi là confirmed finding. Receipts triển khai: 11 focused + 23 Task 23
  regression tests PASS, AST/link/whitespace PASS; source hashes khớp khi đồng bộ,
  không chạy lại suites. Gate triển khai trước đó exit 1: 613 lỗi ngoài scope;
  [validator repair](scripts/validation/README.md) hiện ghi gate exit 0, 0 lỗi,
  giải quyết blocker checker của Task 24. Review độc lập, config acceptance, tích hợp environment,
  durable evidence và hiệu chỉnh trọng số còn `UNRESOLVED`; reward Task 23 chưa thay.
  Chi tiết tại [TASKS.md](TASKS.md#task-024--bộ-chấm-điểm-đánh-giá-metadata-ngoại-tuyến).
- TASK-025 hiện `IMPLEMENTED` cho [Q-learning replay ngoại tuyến](docs/implementation/q_learning.md),
  cập nhật trạng thái ngày 2026-10-12 theo yêu cầu người dùng; chưa `VALIDATED`.
  Q-table thưa khởi tạo 0, epsilon-greedy theo mask, Bellman với ngân sách hữu hạn,
  replan sau mỗi observation và scorer Task 24 cho outcome đã commit. Receipts triển
  khai: 19 focused + 34 Task 23/24 regression tests PASS (53 tests), AST/example/
  whitespace/repository gate PASS, exit 0, 0 lỗi. Bốn source hashes khớp khi đồng bộ;
  không chạy lại suites trong lần cập nhật tài liệu. Training/audit trong bộ nhớ;
  review độc lập, durable evidence, held-out evaluation, calibration, budget equivalence
  và full planner integration còn `UNRESOLVED`. Không suy hội tụ, tính tối ưu hoặc
  runtime success từ fixture; chi tiết tại [TASKS.md](TASKS.md#task-025--q-learning-replay-ngoại-tuyến).
- TASK-026 giữ `DEFERRED` cho DQN/PPO candidate. Phần chuẩn bị
  [wrapper reward/mask và protocol đánh giá replay ngoại tuyến](docs/implementation/offline_rl_protocol.md)
  đã `IMPLEMENTED`, chưa `VALIDATED`: chấm Task 24 sau transition đã commit,
  observation chuẩn hóa có mask/read age, horizon hữu hạn và kiểm tra split/budget/seed.
  Receipts triển khai: 29 focused + 53 Task 23–25 regression + 17 safety tests PASS
  (99 tests). Bốn source hashes vẫn khớp khi đồng bộ ngày 2026-10-12; không chạy lại
  tests trong lần cập nhật tài liệu. Gate cuối phiên triển khai exit 1: 27 lỗi ngoài
  năm paths implementation, 0 lỗi trong scope; gate PASS trước đó không thay receipt
  FAIL mới hơn. Handoff `HANDOFF_BLOCKED`; DQN/PPO training/checkpoint, SB3/PyTorch
  compatibility, benchmark thực tế, durable evidence và review độc lập còn
  `UNRESOLVED`. Chi tiết và pending handoff tại
  [TASKS.md](TASKS.md#task-026--chuẩn-bị-wrapperprotocol-replay-ngoại-tuyến).
- TASK-027 hiện `IMPLEMENTED` cho [thiết kế và router tham chiếu hybrid ngoại tuyến](docs/implementation/hybrid_router.md),
  cập nhật ngày 2026-10-12 theo yêu cầu người dùng; chưa `VALIDATED`. Router trả dữ liệu
  điều hướng rule-first, metadata handoff khi review thất bại/no match, exclusion theo
  candidate version và dừng khi DENIED/hết budget/quota/no progress. Chỉ hỗ trợ
  `ACTION-PLAN-003`; không gọi backend/provider hoặc tự dispatch. Receipts triển khai:
  20 focused + 87 Task 20–22 regression tests PASS (107 tests), AST/19 links/whitespace
  PASS; hai source hashes khớp khi đồng bộ, không chạy lại suites. Repository gate
  triển khai exit 1: 27 lỗi ngoài scope, 0 lỗi thuộc ba files; `HANDOFF_BLOCKED`.
  LLM handoff adapter, completion liên backend, history/concurrency, tokenizer/provider
  thật, durable evidence, Task 25 arbitration và review độc lập còn `UNRESOLVED`;
  full hybrid runtime vẫn `SPEC_ONLY`. Chi tiết tại
  [TASKS.md](TASKS.md#task-027--router-tham-chiếu-hybrid-ngoại-tuyến).
- TASK-032 giữ `DEFERRED`. Metrics, training và kết quả nghiên cứu không được suy ra từ prototype.
- TASK-019 hiện `IMPLEMENTED` cho SQLite knowledge-state store ngoại tuyến, tái dùng StateManager và giữ contract hiện có. Receipts triển khai ngày 2026-10-11: 21 tests mới + 39 tests API cũ PASS; checker exit 1 với 656 lỗi ngoài scope, 0 lỗi thuộc ba paths Task 19. Cập nhật trạng thái ngày 2026-10-12 đối chiếu source hashes khớp receipts, không chạy lại suites hoặc chuyển validation lịch sử sang extension. Handoff `HANDOFF_BLOCKED`; review độc lập, consumer/evidence integration, process/container restore và performance còn `UNRESOLVED`. Chi tiết tại [TASKS.md](TASKS.md#task-019--knowledge-state-store-sqlite-ngoại-tuyến).

Hiện trạng và chuyển tiếp: Tranche tái chuẩn hóa hiện hành là `RT-00 — Enterprise Red Team Planning Rebaseline` (`IMPLEMENTED`), mở ra lộ trình nghiên cứu AI Attack Planning under Partial Observability gồm các mốc: RT-01 (Zero-Knowledge Boundary), RT-02 (Belief State), RT-03 (Enterprise Action Model), RT-04 (Simulation Backend), RT-05 (Planner Integration), RT-06 (Mini Enterprise Live Range), RT-07 (Experimental Evaluation). Simulator bắt buộc hoàn thành và kiểm chứng trước live range. Toàn bộ chuỗi sản phẩm và PTES lịch sử SL-01–SL-11 trên ShopLab (với toàn bộ ecommerce tests, gateway E2E tests, discovery safety tests, planner tests, PTES coordinator tests, evidence packaging/replay tests và live Docker runtime receipts PASS) được bảo toàn nguyên trạng làm nền tảng kiểm chứng. SL-12 (Independent verification handoff) giữ `HANDOFF_BLOCKED` chờ giải quyết repository blockers ngoài scope.

Thứ tự và acceptance: [PROJECT_PLAN.md](PROJECT_PLAN.md). Giữ IDs/dependencies `TASK-001..035`, `SL-*` và các validation lịch sử. Không tự hạ acceptance hoặc nâng validation khi chưa có checks và review độc lập.

## Boundaries

Chỉ local isolated lab hoặc simulation backend cô lập với dữ liệu giả. Không public target, Internet scanning, arbitrary shell, dynamic actions, free-form payload mới, credentials cố định, dữ liệu production hoặc deployment claim. Giữ lab mode, target/action allowlists, approval, rate/order/budget checks, kill switch, audit và restore.

CentralizedSafetyGate áp dụng bất biến tập giao `canonical allowlist ∩ run-approved targets`; runtime caller không được nới rộng chính sách. Planner tuyệt đối không nhận full target allowlist, global topology, credentials, source code hay defender-private state; ranh giới an toàn không đồng nhất với phạm vi quan sát của tác tử.

Phê duyệt kế hoạch và sửa tài liệu không phải per-run/per-action approval. Giai đoạn thực thi ngoài quyền hiện hành phải ghi `BLOCKED` hoặc `NOT_RUN`, thiếu evidence ghi `UNRESOLVED`; không giả completion. Không persistence ngoài scope trên target, credential theft, đọc host files hoặc lateral movement ngoài bounded actions đã duyệt.

Evidence mới cần UTC, run ID, source, hash, redaction và expected/observed tách biệt; không overwrite record cũ. Evidence-write failure hoặc xung đột nguồn phải dừng. Phiên bản, image provenance/digest, model identity và measured metrics chỉ được ghi khi có bằng chứng.

## Source hierarchy

User source và approved contracts outrank derivative documents. AGENTS.md quy định governance; PROJECT_PLAN.md quy định roadmap; TASKS.md quy định backlog/status; ADR quy định quyết định kiến trúc (bao gồm ADR-014 cho kiến trúc Enterprise Red Team Belief State); evidence quy định observed claims.

Nguồn roadmap: `PLAN-ENTERPRISE-REDTEAM-001`, bắt đầu bằng tranche `RT-00 — Enterprise Red Team Planning Rebaseline`. Lịch sử roadmap nền `PLAN-SHOPLAB-PTES-001` / `SHOPLAB-PTES-001` và `PLAN-OSCAR-ADOPTION-001` được lưu giữ nguyên vẹn. Approval hiện tại chỉ áp dụng cho tài liệu và governance của RT-00, không cấp quyền runtime, dependency execution hoặc sửa mã nguồn ngoài scope. Không tự approve, finalize, append history hoặc commit. ADR-014 xác lập quyết định kiến trúc phân tách ranh giới True State, Belief State, Ground Truth, Safety Gate và Executor. Khi evidence và prose xung đột, báo blocker thay vì chọn claim có lợi hơn.
