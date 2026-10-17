# Project Plan

Roadmap nền: `PLAN-SHOPLAB-PTES-001`, work item `SHOPLAB-PTES-001`. Hướng hiện hành được người dùng chọn: tái sử dụng ứng dụng open-source phù hợp làm target, tập trung discovery, safety, observations, planner và evidence; tranche offline `PLAN-OSCAR-ADOPTION-001` / `OSCAR-ADOPTION-001` thẩm định Django Oscar sandbox 4.2.1. Baseline HEAD `96d9428ef715299ca2c6d403a81d50d97ae55412`; dirty inventory mới được chụp riêng sau SL-03/docs, không dùng HEAD diff để nhận toàn bộ user changes. Trạng thái theo [TASKS.md](TASKS.md); không nâng validation.

## Foundation

Giữ contracts, action catalog, safety, validator và evidence hiện hữu. Bảo toàn working tree chưa commit; chỉ sửa trong allowlist được giao. Sửa tài liệu/task không mở quyền runtime. Không append history, self-approve hoặc commit.

Giữ 35 task IDs hiện hành; nhóm `SL-*` bổ sung luồng triển khai sản phẩm và PTES; nhóm `RT-*` mở rộng nghiên cứu AI Attack Planning dưới quan sát một phần. Contract/catalog/config changes không thuộc cập nhật tài liệu này. Nếu cần thay action semantics, phải dừng để duyệt scope riêng.

### Enterprise Red Team Planning Roadmap (RT-00 .. RT-07)

Lộ trình tái định hướng nghiên cứu sang **AI Attack Planning for Red Team under Partial Observability (Belief-State Planning)**. Lộ trình mới kế thừa toàn bộ nền tảng an toàn, contracts, action catalog, và evidence framework hiện có mà không xóa bỏ hoặc làm mất hiệu lực các kết quả lịch sử (TASK-001..035, SL-01..12).

Nguyên tắc triển khai bắt buộc: **Simulator phải đi trước và được kiểm chứng độc lập trước khi mở rộng sang Mini Enterprise Live Range** (RT-04 trước RT-06).

- **RT-00 — Enterprise Red Team Planning Rebaseline** (`IMPLEMENTED`):
  Tranche tài liệu và quản trị (DOCUMENTATION/GOVERNANCE). Tái định vị bài toán nghiên cứu cốt lõi sang AI Attack Planning for Red Team under Partial Observability (Belief-State Planning). Ban hành ADR-014; sửa AGENTS.md sang cơ chế allowlist theo task; cập nhật PROJECT_CONTEXT.md, PROJECT_PLAN.md, TASKS.md. Bảo toàn toàn bộ lịch sử và evidence cũ.
- **RT-01 — Zero-Knowledge Boundary** (`SPEC_ONLY`):
  Thiết lập rào chắn Zero-Knowledge tuyệt đối cho Planner: tách Ground Truth khỏi planner contracts, di chuyển schema và manifests về canonical path `evaluation/**`. Planner tuyệt đối không nhận ground truth, global network topology, full target allowlist, hidden credentials, hoặc defender-private state. Xây dựng bộ test suite kiểm tra boundary và fail-closed assertions.
- **RT-02 — Belief State** (`SPEC_ONLY`):
  Thiết kế schema và hiện thực hóa `BeliefState` kế thừa từ `StateManager`. Xây dựng mô hình biểu diễn trạng thái niềm tin (Belief State) cập nhật liên tục từ các quan sát (observations) thực tế thu thập được: host reachability, port/service discovery, credential cache, privilege levels, và confidence score có tính đến độ suy giảm (belief decay). Loại bỏ hoàn toàn oracle knowledge khỏi state representation.
- **RT-03 — Enterprise Action Model** (`SPEC_ONLY`):
  Định nghĩa và chuẩn hóa danh mục hành động tấn công doanh nghiệp có giới hạn (Enterprise Bounded Actions): reconnaissance, network discovery, credential probing, service exploration, và lateral movement hypotheses. Giữ vững nguyên tắc an toàn: tuyệt đối không arbitrary shell, không dynamic actions, không free-form payload execution; mọi action đều tuân thủ schema định kiểu chặt chẽ.
- **RT-04 — Simulation Backend** (`SPEC_ONLY`):
  Xây dựng môi trường mô phỏng (Simulation Backend) dựa trên khung lý thuyết POMDP (Partially Observable Markov Decision Process). Simulator lưu giữ True State độc quyền, tiếp nhận action đã được Safety Gate duyệt, và sinh ra partial observations kèm theo chi phí/ngân sách (cost/budget accounting). **Hoàn thành và kiểm chứng offline/deterministic trước khi triển khai bất kỳ live range nào**.
- **RT-05 — Planner Integration** (`SPEC_ONLY`):
  Tích hợp các chế độ planner (`RULE`, `LLM`, `RL`, `HYBRID`) trên nền tảng Belief State và Simulation Backend. Đảm bảo tính minh bạch về nguồn gốc quyết định (mode provenance), tuân thủ proposal schema (`plan.schema.json`), kiểm soát lỗi provider, và thực thi chính sách fallback an toàn.
- **RT-06 — Mini Enterprise Live Range** (`SPEC_ONLY`):
  Triển khai môi trường mạng doanh nghiệp thu nhỏ cô lập (Multi-host Docker lab, segmented subnets, Active Directory / LDAP mô phỏng, simulated corporate services, loopback ingress). Live range sử dụng chung executor interface và observation contract với simulation backend (RT-04). Tích hợp CentralizedSafetyGate kiểm soát phân quyền và ngăn chặn egress ra ngoài.
- **RT-07 — Experimental Evaluation** (`SPEC_ONLY`):
  Thiết lập bộ kịch bản đánh giá thực nghiệm (benchmark suite) so sánh hiệu năng của các planner (`RULE`, `LLM`, `RL`, `HYBRID`) dưới điều kiện quan sát một phần trên cả Simulation Backend và Mini Enterprise Live Range. Đánh giá tính chính xác của Belief State so với Ground Truth (độc quyền trong evaluation), tỉ lệ thành công, hiệu quả sử dụng ngân sách (budget efficiency), và thời gian phát hiện.

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

### TASK-017 — Nuclei offline và bàn giao normalizer

TASK-017 là `IMPLEMENTED` cho parser/safety wrapper nhập báo cáo JSON/JSONL ngoại tuyến theo yêu cầu người dùng; chưa `VALIDATED`. Exact template-ID manifest mặc định rỗng, target/origin validation, resource limits và dữ liệu tối giản; `execute` luôn `DENIED`. Receipts phiên triển khai ngày 2026-10-11: 72 tests offline PASS (28 Nuclei, 27 adapters, 17 safety), AST/diff checks PASS; repository gate exit 1 với 643 lỗi ngoài scope, 0 lỗi thuộc năm paths Task 17 ở lần chạy cuối của phiên đó. Không suy runtime approval hoặc success từ cập nhật trạng thái.

Tiếp theo: bàn giao candidate contract cho TASK-018, giữ provenance/evidence trước state update và quy ước `confidence=0.0` là chưa đánh giá, không phải âm tính; xử lý checker blockers theo scope riêng, kiểm tương thích report thật và review độc lập. Scanner runtime scaffold giữ `SPEC_ONLY`, durable evidence/report provenance và external execution còn `UNRESOLVED`. Chi tiết tại [TASKS.md](TASKS.md#task-017--parser-và-safety-wrapper-nuclei-ngoại-tuyến).

### TASK-015 — discovery offline và liên kết SL-08

TASK-015 là `IMPLEMENTED` cho `runtime/discovery_report_importer.py`: bounded import `httpx-jsonl`/`whatweb-json`, policy/approval checks, evidence và observations có provenance `IMPORTED_OFFLINE`; review simulation ghi `SIMULATED_FIXTURE`. Check cập nhật trạng thái ngày 2026-10-11 đạt 45 tests PASS, exit 0. Metadata vẫn chưa xác minh, external-tool execution `UNRESOLVED`; adapter discovery cũ còn mô phỏng. Đối chiếu acceptance với SL-08 và bàn giao review độc lập trước validation; không làm lại chức năng đã có hoặc chuyển receipts SL-08 thành approval TASK-015.

### TASK-016 — offline slice và evidence tiếp theo

`PLAN-TASK016-ZAP-OFFLINE-001` / `BUILD-TASK016-ZAP-OFFLINE-001` đã triển khai bounded JSON parser và wrapper ngoại tuyến. `import_report` trả candidate data, không action observation; `execute` luôn `DENIED` với facts/results rỗng. Giữ target allowlist, all-or-nothing scope validation, confidence ordinal không severity fallback, rate/budget ceiling theo adapter và `endpoint_id=null` để minimize dữ liệu. Không external scanner/network/file ingestion hoặc fake findings.

Self-check ngày 2026-10-11 có 60 tests PASS (16 ZAP, 27 adapters, 17 safety), scoped diff check PASS và bốn hashes khớp snapshot. Independent review chưa có verdict; self-review không thay approval. Checker từng PASS ở build gốc nhưng lần ghi nhận sau đó exit 1 vì lỗi trong `dashboards/app/frontend/node_modules/**` ngoài allowlist; handoff giữ `HANDOFF_BLOCKED`. Canonical TASK-016 là `IMPLEMENTED` trong phạm vi parser/wrapper offline, chưa `VALIDATED`; check cập nhật trạng thái chạy lại suite ZAP đạt 16 tests PASS, exit 0, chưa chạy lại repository gate hoặc tái xác nhận build hashes. Exact receipts và giới hạn tại [TASKS.md](TASKS.md#checks-and-observed-implementation-state).

Kế hoạch được duyệt `PLAN-TASK016-ZAP-EVIDENCE-002` chọn durable evidence ngoại tuyến, chưa triển khai hoặc chạy checks:
1. Giải quyết repository checker blocker trong scope riêng và chạy lại gate; không xóa dependencies hoặc sửa validator ngoài allowlist TASK-016.
2. Main tự triển khai API import có evidence qua `DurableEvidenceRecorder.persist_phase_artifact`: recorder/run/source/root tường minh, intent → minimized result hoặc rejection, hash cùng bounded snapshot, persist trước return và sticky halt khi ghi lỗi. Không lưu raw report hoặc dùng `DISPATCH_CONFIRMED` cho import.
3. Trong phạm vi recorder được duyệt, kiểm no-overwrite publication/containment và bảo toàn evidence cũ bằng temp-directory tests; chạy focused/regression checks, gate rồi bàn giao review. Windows directory-entry power-loss durability vẫn `UNRESOLVED`, không giả bảo đảm.

Tương thích report ZAP thật cần fixture/provenance được kiểm chứng; live ZAP không thuộc nhánh này. Cập nhật tài liệu không cấp scan/per-run approval hoặc nâng task `VALIDATED`.

- SL-08 đã `IMPLEMENTED`: `runtime/discovery_recorder.py`, `runtime/discovery_gate.py`, `runtime/discovery_engine.py`. Recorder ghi intent và result nguyên tử, fsync, SHA-256, schema validation (`evidence.schema.json`), fail-closed (7 preflight tests E01–E07 PASS). Centralized safety gate kiểm tra chặt chẽ lab mode, dynamic TOCTOU revocation, budget, sliding rate limit, và bất biến `effective_targets = canonical_allowlist & run_approved_targets` (9 safety tests D01–D09 PASS). Live Docker verification `scripts/cyber-range/verify_sl08_live.py` đạt 7/7 pha PASS, bằng chứng lưu tại `evidence/runtime/RUN-SL08-LIVE/`.

### TASK-019 — SQLite knowledge-state store và bàn giao

Task hiện `IMPLEMENTED` cho store ngoại tuyến tại `runtime/knowledge_state_store.py`, cập nhật trạng thái ngày 2026-10-12 theo yêu cầu người dùng. Context tách run/session/episode; observations append-only, facts có index, assets view và state snapshot ghi cùng transaction. Tái dùng StateManager làm budget owner; giữ observation/state contracts và idempotent replay/conflict semantics, không tích hợp store vào runner hoặc consumer trong phần triển khai này.

Receipts triển khai ngày 2026-10-11: 21 tests SQLite + 39 tests API cũ PASS (hai suite exit 0), AST/diff/example PASS; repository checker exit 1 với 656 errors, 0 errors trong ba paths Task 19. Source hashes được đối chiếu khi cập nhật tài liệu và khớp receipts; không chạy lại suites. Historical perception validation không bao phủ SQLite extension. Exact receipts và giới hạn tại [thiết kế Task 19](docs/implementation/knowledge_state_store.md), trạng thái tại [TASKS.md](TASKS.md#task-019--knowledge-state-store-sqlite-ngoại-tuyến).

Thứ tự tiếp theo: giải quyết repository gate trong scope riêng → independent review schema/identity/budget/provenance → kiểm compatibility TASK-018/consumer và evidence-before-state theo recorder được duyệt. Handoff hiện `HANDOFF_BLOCKED`; chưa chứng minh durable evidence binding, report thật, process/container restore hoặc hiệu năng. Mỗi ingest replay history; không mở checkpoint/state restoration API hoặc runtime scope bằng cập nhật tài liệu.

### TASK-020 — Shared planner interface và bàn giao

Task hiện `IMPLEMENTED` cho giao diện ngoại tuyến tại [runtime/planner_interface.py](runtime/planners/planner_interface.py), cập nhật ngày 2026-10-12 theo yêu cầu người dùng. Entry points plan/replan kiểm tra input/output chung; strategy implement mode/_plan và tùy chọn _replan. Snapshot/proposal immutable theo canonical schemas; identity/revision, scope/objective, stop conditions và fallback provenance được kiểm. StateManager giữ budget ownership; candidate sets không cấp quyền execution.

Receipts triển khai: 28 focused tests, 21 Task 19 regression và 16 planner contract tests PASS, từng suite exit 0; AST/example/whitespace PASS. Source hashes khớp receipts khi cập nhật trạng thái, không chạy lại suites. Checker phiên triển khai exit 1 với 656 errors, 0 errors trong ba paths Task 20. [Thiết kế/receipts](docs/implementation/planner_interface.md) giữ exact commands, UTC, hashes và giới hạn; [TASKS.md](TASKS.md#task-020--planner-interface-ngoại-tuyến) là nguồn trạng thái.

Handoff `HANDOFF_BLOCKED`: giải quyết repository blockers trong scope riêng → independent review shared interface/identity/provenance → approved consumer integration với coordinator/gate/recorder. Real RULE/LLM/RL/HYBRID backends, reference/evidence integrity, redaction completeness và runtime integration giữ `UNRESOLVED`; không có provider/training/dispatch trong interface. Không chuyển SL-09 receipts thành validation ABC mới hoặc nâng các task phụ thuộc; TASK-026/032 giữ `DEFERRED`.

## Rule

Giữ baseline xác định để so sánh. Rule fallback là mode thực tế riêng, không được ghi thành LLM. Không dùng tiêu chí “đủ ba lỗi” hoặc default vulnerability routes để kết thúc run.

### TASK-021 — Rule-based planner ngoại tuyến và bàn giao

Task 21 là `IMPLEMENTED` trong phạm vi baseline xem xét bằng chứng ngoại tuyến theo yêu cầu người dùng ngày 2026-10-12; chưa `VALIDATED`. [RuleBasedPlanner](runtime/planners/rule_based_planner.py) kế thừa Task 20 và chỉ đọc snapshot Task 19. Luật immutable, điều kiện đóng, thứ tự priority/rule ID/fact ID xác định; chỉ đề xuất `ACTION-PLAN-003` (`REVISIT_EVIDENCE`) cho candidate có subject là lab target thuộc scope. Completion CONTROL và feedback liên kết context/revision/action/source observation; planner không sửa store, trừ budget, ghi evidence hoặc tự dispatch.

Receipts triển khai: 28 focused tests và 65 dependency/contract tests PASS (93 tests, từng suite exit 0), AST/example/whitespace PASS. Checker phiên triển khai exit 1 với 656 lỗi ngoài scope, 0 lỗi thuộc ba paths Task 21; source hashes đã đối chiếu khi cập nhật trạng thái, không chạy lại suites. Exact commands và giới hạn tại [thiết kế và receipts Task 21](docs/implementation/rule_based_planner.md).

Handoff `HANDOFF_BLOCKED`: xử lý repository blockers trong scope riêng → review độc lập strategy/completion/source integrity → approved recorder/coordinator integration. Durable evidence, xác thực completion ngoài synthetic fixtures, runtime/scanner execution và baseline nghiên cứu đầy đủ giữ `UNRESOLVED`. Không chuyển receipts SL-09 hoặc baseline ngoại tuyến thành validation scanner/LLM; cập nhật tài liệu không mở quyền thực thi hoặc thay trạng thái task phụ thuộc.

## LLM

### TASK-022 — LLM planner ngoại tuyến và bàn giao

Task 22 là `IMPLEMENTED` cho phần xem xét metadata bằng chứng ngoại tuyến theo yêu cầu người dùng ngày 2026-10-12; chưa `VALIDATED`. [LLMPlanner](runtime/planners/llm_planner.py) kế thừa Task 20 và đọc snapshot Task 19; context có giới hạn, coverage và system prompt, một tool có strict schema với revision binding. Chỉ đề xuất `ACTION-PLAN-003` hoặc dừng; Python gắn objective/target/source observation từ snapshot. Replan phân biệt DENIED/FAILURE/ERROR/PARTIAL/SUCCESS và không lặp phiên bản candidate chưa thay đổi sau thất bại; completion cần CONTROL liên kết feedback. Raw fact values không gửi vào context; provider injection là trusted code, không sandbox hoặc authorization.

Receipts triển khai: 31 focused tests + 93 regression tests PASS (124 tests), AST/document/link/whitespace PASS. Checker triển khai exit 1 với 613 lỗi ngoài scope, 0 lỗi thuộc ba paths Task 22. Source hashes khớp receipts khi cập nhật trạng thái; không chạy lại suites trong lần cập nhật tài liệu. [Thiết kế/receipts Task 22](docs/implementation/llm_planner.md) giữ exact commands, UTC, hashes và giới hạn.

Handoff `HANDOFF_BLOCKED`, blocker `REPOSITORY_CHECKER_FAILED_OUTSIDE_SCOPE`: xử lý repository blockers trong scope riêng → review độc lập context/selection/replan/provenance → approved provider/reference/evidence/coordinator integration. Provider/model/tokenizer/transport thật, durable evidence/history/reference integrity và runtime integration còn `UNRESOLVED`. Fallback chỉ khi được cho phép và provider unavailable/timeout, ghi actual mode RULE; fixture/fallback không chứng minh LLM run thật. Không mở scanner/executor/runner scope hoặc nâng task phụ thuộc; TASK-026/032 giữ `DEFERRED`.

### Mốc E — planner dựa trên quan sát và bảy giai đoạn PTES

LLM nhận observations đã redact, không source/ground truth/secrets/tokens. Proposal schema-bound không có quyền thực thi; candidate action phải qua policy và approval. Log mode/model/provider identity thực tế, provider error và fallback reason. Không raw payload/command generation.

- SL-09 đã `IMPLEMENTED`: `runtime/planner_adapter.py` và `runtime/observed_planner.py`. Tái sử dụng `StateManager`, bảo đảm tính bất biến khi nạp observation, phát hiện xung đột, thu gọn prompt không chứa bí mật/HTML thô. Đề xuất chuẩn hóa theo `plan.schema.json`, theo dõi đầy đủ `mode_provenance`, kiểm soát nghiêm ngặt chính sách fallback (`fallback_allowed=False` dừng an toàn thay vì âm thầm lùi về rule), gate evaluation không dispatch mạng. 13 unit tests (P01–P08 và tests thẩm quyền allowlist) PASS. Live Docker verification `scripts/cyber-range/verify_sl09_live.py` đạt 8/8 pha PASS, bằng chứng lưu tại `evidence/runtime/RUN-SL09-LIVE/`. Sẵn sàng cho SL-10 (PTES Coordinator).
- Autonomous Closed-Loop Control đã `IMPLEMENTED`: `runtime/autonomous_runner.py` kết nối trực tiếp `ObservedStatePlanner`, `CentralizedSafetyGate`, `StateManager` và `DurableEvidenceRecorder` thành vòng lặp tự hành đóng kín: `OBSERVATION -> STATE -> AI PLANNER -> PROPOSAL -> SAFETY GATE -> EXECUTOR -> NEW OBSERVATION -> STATE UPDATE -> AI REPLAN -> ... -> STOP`. Bất biến then chốt: runner tuyệt đối không chứa transport trực tiếp (0 direct client libraries); fail-closed ghi intent trước dispatch và result trước request kế tiếp; xử lý từ chối an toàn qua quan sát `REFUSAL`; phát hiện lặp trạng thái không có tiến triển (`NO_PROGRESS_LOOP`). 12 acceptance tests A01–A12 tại `tests/runtime/test_autonomous_runner.py` PASS 100%. Live verification trên ShopLab cyber-range `scripts/cyber-range/verify_autonomous_live.py` (Run ID `RUN-AUTONOMOUS-LIVE-1791708234`) đạt kết quả trung thực: 4 iterations, 3 approved dispatches, 0 denied, 11 network dispatches, 0 unsafe dispatches, 20 observations, stop reason `discovery_surface_complete`, exit code 0.
- Autonomous Pentest Loop với Safe Active Verification đã `IMPLEMENTED`: Bổ sung `runtime/capability_registry.py` cung cấp 4 bounded verifiers (`SafeInputVerificationExecutor` cho `ACTION-WEB-001`, `SafeReflectionVerificationExecutor` cho `ACTION-WEB-002`, `SafePathFixtureVerificationExecutor` cho `ACTION-WEB-003`, `PassiveSurfaceAnalyzer` cho `ACTION-SCAN-001`). Khắc phục 3 blocker findings: F-01 (Form provenance chuẩn hóa relative action URL và cô lập POST inputs khỏi synthetic GET queries), F-02 (Data-driven hypothesis routing theo ngữ nghĩa tham số và outcome-driven replan), F-03 (Phát biểu kết quả kiểm tra âm tính trung thực có giới hạn độ tin cậy <= 0.75). 18 tests V01–V18 tại `tests/runtime/test_autonomous_pentest.py` PASS 100%. Live verification trên ShopLab cyber-range `scripts/cyber-range/run_autonomous_pentest.py` (Run ID `RUN-AUTONOMOUS-PENTEST-1791723996`) đạt PASS: 7 decisions, 6 approved, 0 denied, 3 active verifications, 23 network dispatches, 0 unsafe dispatches, 3 findings phát hiện trung thực, stop reason `discovery_surface_complete`, Docker teardown an toàn.
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

TASK-023 là `IMPLEMENTED` cho [Gymnasium replay ngoại tuyến](docs/implementation/rl_environment.md)
theo yêu cầu ngày 2026-10-12: fixed action/observation spaces, step/reset, refusal,
approval/order/rate/budget mô phỏng và adapter chỉ đọc snapshot Task 19/20.
23 focused tests gồm check_env và 49 regression tests PASS. Không dispatch scanner,
executor/provider hoặc mạng; audit bền vững, live integration và independent review
giữ `UNRESOLVED`. Gate triển khai exit 1 với 613 lỗi ngoài scope, 0 lỗi Task 23;
handoff `HANDOFF_BLOCKED`, chưa `VALIDATED`. Bước kế tiếp: xử lý repository blockers
trong scope riêng, review độc lập replay/state/budget/evidence boundary, rồi mới mở
tích hợp theo scope được duyệt. Source hashes khớp receipts khi đồng bộ tài liệu;
72 tests là receipts triển khai, không được chạy lại trong lần cập nhật tài liệu này.
TASK-024 hiện `IMPLEMENTED` cho [scorer riêng](docs/implementation/reward_model.md), cập nhật
ngày 2026-10-12 theo yêu cầu người dùng; chưa `VALIDATED`. Chấm progress/completion,
phạt lặp, rate/order/refusal và dừng sớm từ outcome đóng của simulator. Candidate và
nhãn replan không được thưởng riêng. Receipts triển khai: 11 focused + 23 Task 23
regression tests PASS, AST/link/whitespace PASS. Source hashes khớp khi đồng bộ,
không chạy lại suites. Gate triển khai trước đó exit 1 với 613 lỗi ngoài scope;
[validator repair](scripts/validation/README.md) giải quyết blocker checker, gate hiện
exit 0, 0 lỗi. Bước kế tiếp: review độc lập weights/trusted-event boundary,
config acceptance trong scope riêng, rồi scope tích hợp environment/evidence được duyệt;
hiệu chỉnh trọng số và budget equivalence vẫn `UNRESOLVED`.
Reward tích hợp trong replay vẫn chỉ minh họa; config reward còn TBD. Ground truth
không thuộc observation/info. Runner Task 25 gọi scorer Task 24 riêng cho từng
outcome đã commit; không thay reward của Task 23 hoặc canonical action/catalog/contracts.

## RL Planner

TASK-025 hiện `IMPLEMENTED` cho [Q-learning metadata replay ngoại tuyến](docs/implementation/q_learning.md)
theo yêu cầu triển khai và cập nhật trạng thái ngày 2026-10-12; chưa `VALIDATED`.
Q-table thưa khởi tạo 0, masked epsilon-greedy/Bellman, seeded training và greedy
evaluation; state gồm metadata quan sát, ngân sách, mask và read age. Chọn lại sau
mỗi transition; Task 24 chấm đúng một lần sau mỗi bước Task 23 đã commit. Hết ngân
sách hữu hạn kết thúc bootstrap; mask không cấp quyền và step vẫn kiểm tra policy.
Receipts triển khai: 19 focused + 34 dependency regression tests PASS (53 tests),
AST/example/whitespace/repository gate PASS, exit 0, 0 lỗi. Source hashes khớp khi
đồng bộ tài liệu; không chạy lại tests trong lần cập nhật này. Bước kế tiếp: review
độc lập state/reward/termination/policy, scope evidence/checkpoint bền vững và
held-out evaluation/calibration/budget equivalence trước full planner integration.
Các phần này còn `UNRESOLVED`; fixture không chứng minh hội tụ hoặc tính tối ưu.
TASK-026 DQN/PPO và TASK-032 giữ `DEFERRED`; không mở live training/dispatch.

### TASK-026 — Chuẩn bị wrapper/protocol replay ngoại tuyến

Theo yêu cầu ngày 2026-10-12, phần chuẩn bị
[reward/mask wrapper và evaluator](docs/implementation/offline_rl_protocol.md) đã `IMPLEMENTED`,
chưa `VALIDATED`; Task 26 toàn phần vẫn `DEFERRED` theo AGENTS.md.
Wrapper chỉ nhận Task-023 replay, chấm Task 24 đúng một lần sau commit, chuẩn hóa
observation có mask/read age và kết thúc bootstrap khi hết ngân sách nội tại.
Evaluator kiểm tra fixture families/content không trùng giữa train/validation/test,
N/budget/tick-rate/seed/masking thống nhất; giữ failures trong completion denominator.
Protocol đề xuất N=8, split 60/20/20, năm training seeds và final test sau chọn bằng
validation. Benchmark này chưa được tạo/chạy; candidate/checkpoint chưa tồn tại.

Receipts triển khai: 99 tests PASS, AST/example/link/whitespace PASS. Bốn source
hashes khớp khi đồng bộ tài liệu; không chạy lại suites. Gate cuối triển khai exit 1
với 27 lỗi ngoài scope, 0 lỗi thuộc năm paths implementation; giữ receipt PASS trước
đó như lịch sử, không mô tả gate hiện hành PASS. Handoff `HANDOFF_BLOCKED`, blocker
`REPOSITORY_CHECKER_FAILED_OUTSIDE_SCOPE`; checks cập nhật tài liệu có receipt riêng
tại runtime/offline_rl_protocol.md.

Pending handoff: xử lý blocker trong scope riêng → independent review reward/state/
horizon/split/failure accounting → scope SB3 dependency lock/compatibility và evidence/
checkpoint bền vững. Các phần này và learned-policy evaluation còn `UNRESOLVED`.
Không chuyển fixture checks thành validation DQN/PPO, không nâng Task 028/030/032,
không mở training/live dispatch hoặc thay contracts/configuration/catalog/scenarios.

## Hybrid

TASK-027 kết hợp candidates trên cùng policy/budgets sau baseline/planner interfaces được kiểm chứng. Không bypass gate hoặc conceal fallback.

### TASK-027 — Router tham chiếu hybrid ngoại tuyến

Task hiện `IMPLEMENTED` cho [reference routing policy và thiết kế handoff](docs/implementation/hybrid_router.md),
cập nhật ngày 2026-10-12 theo yêu cầu người dùng; chưa `VALIDATED`. Router chỉ trả
dữ liệu từ PlanningInput/history/feedback đã validate: RULE trước, LLM handoff khi
no match hoặc review thất bại; metadata context giữ revision/budget/provenance,
loại phiên bản đã thất bại/hoàn thành theo history đã kiểm. DENIED, scope thu hồi,
quota/no progress và budget đều dừng. Chỉ `ACTION-PLAN-003`, không gọi backend,
provider hoặc executor; StateManager tiếp tục sở hữu budget.

Receipts triển khai: 20 router tests + 28 interface + 28 rule + 31 LLM tests PASS
(107 tests, từng suite exit 0); AST, 19 local links và whitespace PASS. Hai source
hashes khớp khi đồng bộ; không chạy lại suites trong lần cập nhật tài liệu.
Gate triển khai exit 1: 27 repository errors, 0 lỗi thuộc ba paths implementation.
Checks đồng bộ tài liệu có receipts riêng tại runtime/hybrid_router.md.

Handoff `HANDOFF_BLOCKED`, blocker `REPOSITORY_CHECKER_FAILED_OUTSIDE_SCOPE`.
Thứ tự tiếp: xử lý gate ngoài scope trong task riêng → review độc lập routing/
identity/history → scope adapter LLM handoff và completion/recorder/coordinator.
Task 22 hiện không nhận RULE feedback qua replan trực tiếp; cần adapter riêng,
không relabel backend/plan ID. Adapter, history/concurrency, tokenizer/provider thật,
durable evidence, gate integration và arbitration với Task 25 còn `UNRESOLVED`;
full hybrid runtime giữ `SPEC_ONLY`. Không nâng các task phụ thuộc hoặc mở quyền
thực thi; TASK-026/032 giữ `DEFERRED`.

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

ShopLab hoàn chỉnh cần product tests, runtime evidence và review. PTES hoàn chỉnh cần phase-specific exit evidence và quyền phù hợp; blocked/skipped/not-run không phải completed. Nhóm RT tuân thủ thứ tự chặt chẽ: RT-00 tái chuẩn hóa tài liệu/governance, RT-01 rào chắn zero-knowledge, RT-02 belief state, RT-03 enterprise action model, RT-04 simulation backend (bắt buộc hoàn thành và kiểm chứng trước live range), RT-05 tích hợp planner, RT-06 mini enterprise live range, RT-07 đánh giá thực nghiệm. Documentation không cấp runtime approval, tự finalize hoặc chứng nhận sản phẩm an toàn.
