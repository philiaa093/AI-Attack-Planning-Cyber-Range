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
- SL-01–03 giữ là lịch sử ShopLab, independent approval SL-03 vẫn thiếu. Ưu tiên hiện hành là source/dependency/environment gate Oscar và upstream acceptance SL-04–07, không chuyển PASS lịch sử hoặc mặc nhiên thay dependency semantics. Không mở runtime/action semantics bằng checks storage/auth offline.
- Restore qua workflow quản trị được duyệt, nhất quán DB/session/invoices; không xóa evidence. Endpoint reset bị từ chối hiện tại không có nghĩa restore đã hoàn thiện.

Acceptance: luồng đăng ký → đăng nhập → catalog → cart → checkout → đơn/hóa đơn → review → logout hoạt động; hai sessions tách biệt; ownership/CSRF/admin checks; stock/idempotency/concurrent checkout; restart persistence; restore. Chưa đạt khi chỉ có các trang HTML.

### Mốc C — runtime qua gateway và isolation

Chỉ sau checks sản phẩm và runtime approval: đối chiếu target registry/manifest với compose, image provenance, loopback ingress, internal target network và egress denial. Gateway không được thành outbound proxy. SQLite cần persistence qua container replacement nếu đó là claim; file trên writable layer chỉ hỗ trợ process restart, không chứng minh durable Docker storage.

Thu evidence health, nghiệp vụ qua gateway, restart/restore, isolation và teardown. Existing RUNTIME-004 không xác nhận ShopLab hoặc gateway vừa sửa. Không public deployment.

## Perception/Tooling

### Mốc D — discovery và policy boundary

Discovery từ seed được duyệt và links/forms/redirects quan sát được; không đoán sẵn routes/params/vị trí lỗi. Same-origin canonicalization, visited set, depth/page/body limits, per-request budgets/rate/time/kill switch; không tự submit side-effect forms.

Tái dùng `agent/memory/state/state_manager.py`: `apply_observation`, `decrement_requests`, `decrement_seconds`, `reconstruct_from_observations`. Đọc normalizer/recorder/contracts hiện hành trước integration. Outcome phải phân biệt success/failure/refusal/timeout; mỗi observation có identity và provenance riêng.

Policy gate trước mọi dispatch; unknown action/target, malformed input, missing approval và order/rate/budget violations bị từ chối. Tool adapters chỉ hỗ trợ capability đã được duyệt; không chọn công cụ bằng cách biết trước lỗi target. TASK-015–017 chưa có validation cho external tool runtime.

## Rule

Giữ baseline xác định để so sánh. Rule fallback là mode thực tế riêng, không được ghi thành LLM. Không dùng tiêu chí “đủ ba lỗi” hoặc default vulnerability routes để kết thúc run.

## LLM

### Mốc E — planner dựa trên quan sát và bảy giai đoạn PTES

LLM nhận observations đã redact, không source/ground truth/secrets/tokens. Proposal schema-bound không có quyền thực thi; candidate action phải qua policy và approval. Log mode/model/provider identity thực tế, provider error và fallback reason. Không raw payload/command generation.

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
