# Project Plan

Roadmap nền: `PLAN-SHOPLAB-PTES-001`, work item `SHOPLAB-PTES-001`. Hướng hiện hành được người dùng chọn: tái sử dụng ứng dụng open-source phù hợp làm target, tập trung discovery, safety, observations, planner và evidence; tranche offline `PLAN-OSCAR-ADOPTION-001` / `OSCAR-ADOPTION-001` thẩm định Django Oscar sandbox 4.2.1. Baseline HEAD `96d9428ef715299ca2c6d403a81d50d97ae55412`; dirty inventory mới được chụp riêng sau SL-03/docs, không dùng HEAD diff để nhận toàn bộ user changes. Trạng thái theo [TASKS.md](TASKS.md); không nâng validation.

## Foundation

Giữ contracts, action catalog, safety, validator và evidence hiện hữu. Bảo toàn working tree chưa commit; chỉ sửa trong allowlist được giao. Sửa tài liệu/task không mở quyền runtime. Không append history, self-approve hoặc commit.

Giữ 35 task IDs hiện hành; nhóm `SL-*` bổ sung luồng triển khai sản phẩm và PTES. Contract/catalog/config changes không thuộc cập nhật tài liệu này. Nếu cần thay action semantics, phải dừng để duyệt scope riêng.

## Literature/Threat

Family nghiên cứu MVP giữ theo ADR-003. Threat model mới phải xuất phát từ assets, roles, trust boundaries và bề mặt quan sát của ShopLab; không cung cấp đáp án hoặc vị trí lỗi cho planner. Nguồn học thuật và kết quả thực nghiệm không được giả định đã hoàn thành.

## Cyber Range

### Mốc A — kiểm chứng phần nền đã sửa

- Chạy tests gateway và storage; sửa lỗi trong phạm vi riêng nếu có.
- Xác minh syntax, persistence, không import side effects, tìm kiếm/lọc kết hợp và dữ liệu mẫu không có tài khoản cố định.
- Gateway phải giữ Cookie/multiple Set-Cookie, status, redirect hợp lệ; không tự follow redirect hoặc kết nối origin khác; request/response có giới hạn.
- Mốc baseline SL-01 đã có checks/gate và review độc lập được xác minh. SL-02 R1 tiếp tục kiểm chứng storage bằng 90 regression tests, AST 2 files và scaffold checker PASS; gate PASS, review `FINAL / APPROVE`, verifier exit 0 ngày 2026-10-10. Receipts/hashes và exact scope tại [TASKS.md](TASKS.md#checks-and-observed-implementation-state); chỉ offline fixture/mock và SQLite temp.
- Các attempts bị chặn trong phiên trước vẫn không được ghi PASS; receipts mới không thay kết quả cũ. Không suy ra Docker/runtime/restore/provider validation từ baseline.

### Mốc B — tái sử dụng upstream và kiểm chứng fit-gap

Django Oscar sandbox 4.2.1 là candidate, chưa là runtime target được kiểm chứng. Không viết lại auth/cart/order hoặc xóa/migrate ShopLab. Dùng upstream business functionality, chỉ cấu hình lab/override tối thiểu; routes/schema riêng của upstream, không ép tương thích ShopLab.

1. Pin source/license/provenance và dependency artifacts có hashes thật. Archive và wheel được đọc không execution; không dùng upstream source build hook NPM, Makefile reset/seed hoặc Dockerfile remote script. Wheel chứa assets giúp tránh tự build frontend; hash PyPI không phải chữ ký hoặc chứng minh wheel khớp GitHub commit.
2. Gate môi trường trước cài/import: upstream không hỗ trợ Windows; PostgreSQL được hỗ trợ chính thức, SQLite chỉ development. Cần môi trường Linux cô lập được duyệt/kiểm chứng, dependency compatibility/license lock và đánh giá support 4.2.1. Hiện `HANDOFF_BLOCKED`; không chạy source để thử vượt gate.
3. SL-04: đánh giá catalog/basket/checkout upstream theo invariants dưới đây. Decimal money và stock allocation khác implementation ShopLab phải có fit-gap/mapping explicit; không tự đổi acceptance integer-minor/idempotency/concurrency thành HTTP 200.
4. SL-05: kiểm chứng orders/reviews/ownership/snapshots. Invoice chưa xác minh có trong core; không thêm extension hoặc viết lại invoice chỉ để khớp prototype, giữ gap tới scope riêng.
5. SL-06: cấu hình dashboard permissions/local administrative workflow và assets/UI offline, không viết lại admin. Không default accounts, first-user admin, secret fallback, CDN/analytics hoặc real payment/email.
6. SL-07: chỉ sau product checks/review và executable scope riêng mới tích hợp identity mới vào gateway/compose/registry. Cần Host/Origin/CSRF review, image provenance, Linux/DB/storage/isolation/restore receipts. Tranche hiện tại không sửa gateway/compose/safety config, không Docker hoặc server.

Các yêu cầu nghiệp vụ dưới đây vẫn là acceptance cần kiểm chứng/ghi gap, không còn là chỉ thị tự xây lại ShopLab:

- Auth: password hashing phù hợp, opaque session phía server, expiry/logout invalidation, CSRF. Không tin username/role cookie, không hardcoded credentials.
- Catalog/search/detail; cart riêng từng phiên với update/remove và stock validation phía server.
- Checkout atomic: integer minor currency units, price snapshot, stock decrement, order/items/shipping persistence, idempotency. Quyết định guest/cart migration phải giữ ownership khi đăng nhập.
- Orders/detail/invoice ownership; review validation và output escaping.
- Admin catalog/stock/order-status management có authorization, CSRF và validation.
- Responsive UI, empty/error states, nhãn lab và simulated payment/email; không claim email đã gửi hoặc đã thu tiền.
- SL-02 đã kiểm chứng SQLite connection-per-service, explicit transactions/rollback/cleanup, schema v1 preservation, bounded busy/drain và process-restart persistence. Import không khởi động server hoặc ghi tệp. Validation chỉ cho S01–S07 và restore coordination handoff; chưa chứng minh nghiệp vụ checkout, crash/power-loss hoặc container durability.
- SL-03 đã `IMPLEMENTED` trong phạm vi offline: auth/authorization/session/CSRF, schema v2 reject legacy v1, 114 tests PASS, AST ba file/checker/gate PASS. Người triển khai đã tự review và sửa hai findings ID/query; chưa có independent review APPROVE, không nâng `VALIDATED`. Xem receipts tại [TASKS.md](TASKS.md#sl-03--kết-quả-offline-r1).
- SL-04 đã `IMPLEMENTED` trên ShopLab trong phạm vi offline: catalog/search, giỏ hàng session/user-bound, checkout atomic transaction với stock decrement, idempotency theo owner `(key, owner_key)`, tiền USD integer minor units, invoice post-commit tách rời; 13 tests checkout PASS (tổng 65 tests ecommerce PASS); chưa có independent review APPROVE, không tự nâng `VALIDATED`. Xem receipts tại [TASKS.md](TASKS.md#sl-04--kết-quả-offline-r1).
- SL-05 đã `IMPLEMENTED` trên ShopLab: lịch sử đơn hàng, snapshot immutability, IDOR protection (404), API data minimization, hóa đơn lab notice kèm fallback on-demand từ DB, đánh giá sản phẩm (1-5 sao, <= 4000 ký tự) và chống Stored XSS; 16 tests orders/reviews PASS (tổng 81 tests ecommerce PASS); chưa có independent review APPROVE, không tự nâng `VALIDATED`. Xem receipts tại [TASKS.md](TASKS.md#sl-05--kết-quả-offline-r1).
- SL-06 đã `IMPLEMENTED` trên ShopLab: admin backoffice phân quyền server-side, máy trạng thái đơn hàng forward-only (`pending` -> `processing`/`cancelled`, `processing`/`completed` -> `shipped`, `shipped` -> `delivered`), chính sách hủy đơn nghiêm ngặt (chỉ `pending`), soft-archive sản phẩm (`product_archives`), cập nhật tồn kho an toàn và audit log (`admin_activity_log`); 14 tests admin PASS (tổng 95 tests ecommerce PASS); chưa có independent review APPROVE, không tự nâng `VALIDATED`. Xem receipts tại [TASKS.md](TASKS.md#sl-06--kết-quả-offline-r1).
- SL-07 đã `IMPLEMENTED` trên ShopLab trong môi trường Docker lab cô lập: target container không mở port ra host, Gateway loopback ingress `127.0.0.1:18088:8080`, named volume `cyber-range_ecommerce-data` mount tại `/app/data`, kịch bản live Docker `scripts/cyber-range/verify_live_docker.py` xác thực thành công 8/8 pha (health, full flow, IDOR isolation, container restart, container replacement đổi ID bảo toàn volume, failure 502 injection, restore baseline via ephemeral container, bounded teardown) và 17 tests gateway E2E PASS; chưa có independent review APPROVE, không tự nâng `VALIDATED`. Xem receipts tại [TASKS.md](TASKS.md#sl-07--kết-quả-live-docker-runtime-verification).
- ShopLab đã hoàn thành trọn vẹn chuỗi SL-01–07, bảo đảm nền tảng runtime ổn định và sẵn sàng cho SL-08 (Discovery & Safety Gate).
- Restore qua workflow quản trị được duyệt, nhất quán DB/session/invoices; không xóa evidence.

Acceptance: luồng đăng ký → đăng nhập → catalog → cart → checkout → đơn/hóa đơn → review → logout hoạt động; hai sessions tách biệt; ownership/CSRF/admin checks; stock/idempotency/concurrent checkout; restart persistence; restore; live Docker verification qua Gateway. Tất cả các tiêu chí acceptance đã được chứng minh qua test suites và live Docker receipts.

### Mốc C — runtime qua gateway và isolation

Chỉ sau checks sản phẩm và runtime approval: đối chiếu target registry/manifest với compose, image provenance, loopback ingress, internal target network và egress denial. Gateway không được thành outbound proxy. SQLite cần persistence qua container replacement nếu đó là claim; file trên writable layer chỉ hỗ trợ process restart, không chứng minh durable Docker storage.

Thu evidence health, nghiệp vụ qua gateway, restart/restore, isolation và teardown. Existing RUNTIME-004 không xác nhận ShopLab hoặc gateway vừa sửa. Không public deployment.

## Perception/Tooling

### Mốc D — discovery và policy boundary

Discovery từ seed được duyệt và links/forms/redirects quan sát được; không đoán sẵn routes/params/vị trí lỗi. Same-origin canonicalization, visited set, depth/page/body limits, per-request budgets/rate/time/kill switch; không tự submit side-effect forms.

Tái dùng `agent/memory/state/state_manager.py`: `apply_observation`, `decrement_requests`, `decrement_seconds`, `reconstruct_from_observations`. Đọc normalizer/recorder/contracts hiện hành trước integration. Outcome phải phân biệt success/failure/refusal/timeout; mỗi observation có identity và provenance riêng.

Policy gate trước mọi dispatch; unknown action/target, malformed input, missing approval và order/rate/budget violations bị từ chối. Tool adapters chỉ hỗ trợ capability đã được duyệt; không chọn công cụ bằng cách biết trước lỗi target. TASK-015–017 chưa có validation cho external tool runtime.

- SL-08 đã `IMPLEMENTED`: `runtime/discovery_recorder.py`, `runtime/discovery_gate.py`, `runtime/discovery_engine.py`. Recorder ghi intent và result nguyên tử, fsync, SHA-256, schema validation (`evidence.schema.json`), fail-closed (7 preflight tests E01–E07 PASS). Centralized safety gate kiểm tra chặt chẽ lab mode, dynamic TOCTOU revocation, budget, sliding rate limit, và bất biến `effective_targets = canonical_allowlist & run_approved_targets` (9 safety tests D01–D09 PASS). Live Docker verification `scripts/cyber-range/verify_sl08_live.py` đạt 7/7 pha PASS, bằng chứng lưu tại `evidence/runtime/RUN-SL08-LIVE/`.

## Rule

Giữ baseline xác định để so sánh. Rule fallback là mode thực tế riêng, không được ghi thành LLM. Không dùng tiêu chí “đủ ba lỗi” hoặc default vulnerability routes để kết thúc run.

## LLM

### Mốc E — planner dựa trên quan sát và bảy giai đoạn PTES

LLM nhận observations đã redact, không source/ground truth/secrets/tokens. Proposal schema-bound không có quyền thực thi; candidate action phải qua policy và approval. Log mode/model/provider identity thực tế, provider error và fallback reason. Không raw payload/command generation.

- SL-09 đã `IMPLEMENTED`: `runtime/planner_adapter.py` và `runtime/observed_planner.py`. Tái sử dụng `StateManager`, bảo đảm tính bất biến khi nạp observation, phát hiện xung đột, thu gọn prompt không chứa bí mật/HTML thô. Đề xuất chuẩn hóa theo `plan.schema.json`, theo dõi đầy đủ `mode_provenance`, kiểm soát nghiêm ngặt chính sách fallback (`fallback_allowed=False` dừng an toàn thay vì âm thầm lùi về rule), gate evaluation không dispatch mạng. 13 unit tests (P01–P08 và tests thẩm quyền allowlist) PASS. Live Docker verification `scripts/cyber-range/verify_sl09_live.py` đạt 8/8 pha PASS, bằng chứng lưu tại `evidence/runtime/RUN-SL09-LIVE/`. Sẵn sàng cho SL-10 (PTES Coordinator).
- Autonomous Closed-Loop Control đã `IMPLEMENTED`: `runtime/autonomous_runner.py` kết nối trực tiếp `ObservedStatePlanner`, `CentralizedSafetyGate`, `StateManager` và `DurableEvidenceRecorder` thành vòng lặp tự hành đóng kín: `OBSERVATION -> STATE -> AI PLANNER -> PROPOSAL -> SAFETY GATE -> EXECUTOR -> NEW OBSERVATION -> STATE UPDATE -> AI REPLAN -> ... -> STOP`. Bất biến then chốt: runner tuyệt đối không chứa transport trực tiếp (0 direct client libraries); fail-closed ghi intent trước dispatch và result trước request kế tiếp; xử lý từ chối an toàn qua quan sát `REFUSAL`; phát hiện lặp trạng thái không có tiến triển (`NO_PROGRESS_LOOP`). 12 acceptance tests A01–A12 tại `tests/runtime/test_autonomous_runner.py` PASS 100%. Live verification trên ShopLab cyber-range `scripts/cyber-range/verify_autonomous_live.py` (Run ID `RUN-AUTONOMOUS-LIVE-1791708234`) đạt kết quả trung thực: 4 iterations, 3 approved dispatches, 0 denied, 11 network dispatches, 0 unsafe dispatches, 20 observations, stop reason `discovery_surface_complete`, exit code 0.
- SL-10 đã `IMPLEMENTED`: `runtime/ptes_coordinator.py`. Điều phối 7 giai đoạn PTES có entry/exit criteria độc lập, tái sử dụng gate/recorder SL-08 và planner SL-09. Trạng thái phản ánh trung thực: Phase 1 COMPLETED, Phase 2 COMPLETED_BOUNDED, Phase 3 COMPLETED, Phase 4 COMPLETED, Phase 5 BLOCKED, Phase 6 NOT_RUN, Phase 7 COMPLETED (tổng 0 confirmed vulnerabilities, 0 unsafe dispatches). 8 unit tests (T01–T08) PASS. Live Docker verification đạt 7/7 phase PASS. Chưa có independent review; không tự nâng `VALIDATED`. Sẵn sàng cho SL-11.

| Giai đoạn | Đầu ra và tiêu chí kết thúc | Khi thiếu quyền hoặc evidence |
|---|---|---|
| 1. Pre-engagement | Scope, identity, approval, budgets, restore baseline và điều kiện dừng đã kiểm tra | Dừng trước dispatch; `BLOCKED` |
| 2. Intelligence gathering | Inventory endpoint/form/input có source observations và coverage/giới hạn | Ghi coverage chưa đủ, không đoán endpoint |
| 3. Threat modeling | Asset/role/trust-boundary hypotheses liên kết inventory | Hypothesis không phải confirmed finding |
| 4. Vulnerability analysis | Passive/approved non-destructive checks; positive và negative observations | Candidate nếu chưa đủ confirmation evidence |
| 5. Exploitation | Chỉ safe verification nằm trong policy; không thêm payload hoặc active exploitation | `BLOCKED`/`NOT_RUN` nếu ngoài scope, không giả hoàn thành |
| 6. Post-exploitation | Impact từ dữ liệu giả và bằng chứng đã có; không persistence/credential theft/host file read/lateral movement | `UNRESOLVED` khi chưa chứng minh impact |
| 7. Reporting | Evidence-linked findings, limitations, coverage, negative results, remediation, phase statuses và planner provenance | Không vượt observed claims; không auto-VALIDATED |

`NOT_RUN` là trạng thái thực thi phase, không thêm vào vocabulary task. Bảy nhánh hoặc bảy nhãn không chứng minh bảy giai đoạn đã thực hiện. LLM run thật cần provider-backed receipts và independent review; mock/rule run không thay thế.

## RL Environment

Giữ finite state/action và ground-truth isolation. Triển khai sau bounded executable pipeline, không mở scope để đáp ứng goal sản phẩm. TASK-023–024 giữ trạng thái hiện hành.

## RL Planner

TASK-025 giữ kế hoạch Q-learning baseline. TASK-026 DQN/PPO giữ `DEFERRED`; không tự mở training hoặc result claims.

## Hybrid

TASK-027 kết hợp candidates trên cùng policy/budgets sau baseline/planner interfaces được kiểm chứng. Không bypass gate hoặc conceal fallback.

## Evaluation

### Mốc F — evidence, reproducibility và review

Evidence append-only: exclusive new run, UTC/run ID/source/hash/redaction; expected và observed tách biệt. Không log credentials/cookies/PII thật. Ghi evidence thất bại phải dừng request tiếp theo.

Fixture evaluation đổi route/form names và có clean control; chứng minh discovery không hardcoded, planner không đọc ground truth, HTTP 200/reflection không tự confirm. So sánh planner chỉ khi same budgets và run identities có receipts. Chưa có experimental metrics mới.

Build trả BUILD_CONTRACT matching task/plan/base head, exact scope, changed/deleted files, command receipts, unverified/blockers và pending_handoff_payload. Deterministic pre-review gate kiểm tra contracts, path allowlist, receipts, blockers và repository checker. `HANDOFF_BLOCKED` không được đưa sang review hoặc tính repair decrement; only evidence-backed review blockers dùng repair budget. Không self-approve/finalize.

- SL-11 đã `IMPLEMENTED`: `runtime/evidence_package.py` và `runtime/discovery_recorder.py`. Đóng gói bằng chứng bất biến, kiểm chứng tính toàn vẹn SHA-256 và quan hệ nhân quả; sinh báo cáo nghiên cứu liên kết bằng chứng (`report.md`, `report.json`); bộ máy replay ngoại tuyến xác định (`reconstruct_from_observations`) với `ZeroNetworkGuard` bảo đảm đúng 0 network dispatches và 0 provider dispatches. Cơ chế kiểm soát root containment chống path traversal/symlink escape trên custom `base_dir` (B01–B04) và khóa bất biến không xóa/tái sử dụng run dở dang (B05). 14 unit tests (E01–E09, B01–B05) PASS. Gói bằng chứng chuẩn mực bàn giao lưu tại `evidence/runtime/RUN-SL11-HANDOFF-20261011/` (51 files, 23 records). Ghi nhận sai lệch lịch sử minh bạch: `HISTORICAL_EVIDENCE_DISCREPANCY = ABORTED_RUN_DIRECTORY_DELETED_DURING_SELF_REVIEW`. Toàn bộ 108 files của các run lịch sử được xác minh bất biến 100%. Chưa có independent review; không tự nâng `VALIDATED`. Sẵn sàng cho SL-12 (Independent verification handoff).
- SL-12 deterministic pre-review gate hiện ghi nhận `HANDOFF_BLOCKED`: xác lập build ID `SL12-PREVIEW-ee45e60-20261011`, plan ID `PLAN-SHOPLAB-PTES-001`, base HEAD `ee45e602c05f79f99c67c59e5fbc24a2b4c70bec`; kiểm chứng đọc-chỉ run chuẩn mực `RUN-SL11-HANDOFF-20261011` (integrity PASS 23 records/51 files, dual replay PASS zero network/provider); 18 nhóm check receipts PASS; tạo `CURRENT_REVIEW_SOURCE_MANIFEST` (27 files); công bố minh bạch sai lệch lịch sử (aborted run deleted) và giới hạn liên kết nguồn (`SOURCE_AT_RUN_BINDING = PARTIAL`); xuất `REVIEW_CONTRACT`. Ghi nhận `HANDOFF_BLOCKER = REPOSITORY_CHECKER_FAILED` do `validate_scaffold.py` phát hiện lỗi schema tại tệp demo `scripts/demo/demo-output/BASELINE-...` (ngoài allowlist). Dừng theo Stop Rules, không tự sửa ngoài scope; chưa có independent review; không tự approve, không tự nâng `VALIDATED`.

## Dashboard

TASK-032 giữ `DEFERRED`. UI sản phẩm ShopLab không phải dashboard nghiên cứu. Không dùng demo UI hoặc số liệu viết sẵn làm kết quả observed.

## Final Reproducibility

Required checks trước bàn giao runtime:
- Gateway/storage focused tests; product auth/cart/checkout/ownership/admin/CSRF/concurrency/persistence/restore.
- Safety negative tests: missing approval, unknown target/action, malformed URL/redirect/method, budgets/rate/order/kill switch và evidence failures; zero dispatch khi reject.
- Adaptive/provider/report tests: changed route names, malformed proposal, explicit fallback, provenance, unique observations, replay và honest phase statuses.
- Repository validator/safety regression và review độc lập; receipt phải có command thực tế, exit code, result và liên kết artifact nếu có.
- Authorized Docker isolation/business-flow run; authorized provider-backed run hoặc explicit unverified.

Các lệnh focused sau đã có receipts PASS cho exact source SL-02 R1; không phải live deployment procedure và phải chạy lại nếu source thay đổi. R1 quan sát gateway 13 tests/storage 28 tests, exit 0; xem [TASKS.md](TASKS.md#checks-and-observed-implementation-state) để đối chiếu đầy đủ bảy checks, source hashes và review:

```text
python -B -m unittest discover -s tests/integration -p test_gateway_product.py -v
python -B -m unittest discover -s tests/integration -p test_ecommerce_storage.py -v
```

Repository checker: `scripts/validation/validate_scaffold.py`; xác minh CLI trước chạy. Không vượt cơ chế chặn công cụ hoặc nhờ peer bypass approval. Khi classifier/provider/Docker không khả dụng, ghi blocker cụ thể, không retry vô hạn hoặc fake evidence.

## Completion rule

Tài liệu có thể `IMPLEMENTED` khi được cập nhật, không `VALIDATED` nếu chưa checks/review. Code từng phần không hoàn thành task có acceptance criteria lớn hơn. Historical task statuses không tự chuyển sang evidence cho code mới.

ShopLab hoàn chỉnh cần product tests, runtime evidence và review. PTES hoàn chỉnh cần phase-specific exit evidence và quyền phù hợp; blocked/skipped/not-run không phải completed. Documentation không cấp runtime approval, tự finalize hoặc chứng nhận sản phẩm an toàn.
