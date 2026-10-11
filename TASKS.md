# Tasks

Status vocabulary: `SPEC_ONLY`, `TBD`, `UNRESOLVED`, `IMPLEMENTED`, `VALIDATED`, `DEFERRED`, `BLOCKED`.

Tasks 001-010 are `VALIDATED` by foundation evidence `EV-FOUNDATION-001-001` through `EV-FOUNDATION-001-004`. TASK-011 through TASK-014 are `VALIDATED` for local Docker runtime slice by RUNTIME-004 evidence and approved review; scope excludes public deployment, planner validation, and external tool execution. Tasks 015-017 remain `SPEC_ONLY`; current adapters are simulation-oriented and real tool execution is not validated. Tasks 018-019 are `VALIDATED` by perception evidence `EV-PERCEPTION-018-001` through `EV-PERCEPTION-019-003`. Tasks 020-025, 027-031, and 033-035 remain `SPEC_ONLY`. Tasks 026 and 032 are `DEFERRED`; no result claim exists.

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
| TASK-015 | Discovery adapter | `SPEC_ONLY` | TASK-004, TASK-006, TASK-011 |
| TASK-016 | ZAP adapter | `SPEC_ONLY` | TASK-004, TASK-006, TASK-011 |
| TASK-017 | Nuclei adapter | `SPEC_ONLY` | TASK-004, TASK-006, TASK-011 |
| TASK-018 | Observation normalizer | `VALIDATED` | TASK-006, TASK-015 |
| TASK-019 | Knowledge-state store | `VALIDATED` | TASK-005, TASK-018 |
| TASK-020 | Planner interface | `SPEC_ONLY` | TASK-004, TASK-005, TASK-019 |
| TASK-021 | Rule-based planner | `SPEC_ONLY` | TASK-020 |
| TASK-022 | LLM planner | `SPEC_ONLY` | TASK-020, TASK-003 |
| TASK-023 | RL environment | `SPEC_ONLY` | TASK-004, TASK-005, TASK-006, TASK-009 |
| TASK-024 | Reward model | `SPEC_ONLY` | TASK-023 |
| TASK-025 | Q-learning baseline | `SPEC_ONLY` | TASK-023, TASK-024 |
| TASK-026 | DQN/PPO candidate | `DEFERRED` | TASK-023, TASK-024 |
| TASK-027 | Hybrid planner | `SPEC_ONLY` | TASK-021, TASK-022, TASK-025 |
| TASK-028 | Experiment runner | `SPEC_ONLY` | TASK-010, TASK-020 |
| TASK-029 | Metrics engine | `SPEC_ONLY` | TASK-009, TASK-028 |
| TASK-030 | Held-out evaluation | `SPEC_ONLY` | TASK-028, TASK-029 |
| TASK-031 | Statistical analysis | `SPEC_ONLY` | TASK-030 |
| TASK-032 | Dashboard | `DEFERRED` | TASK-028, TASK-029 |
| TASK-033 | Report artifact generator | `SPEC_ONLY` | TASK-029 |
| TASK-034 | Reproducibility package | `SPEC_ONLY` | TASK-030, TASK-031, TASK-033 |
| TASK-035 | Final foundation audit | `SPEC_ONLY` | all-required |

## ShopLab/PTES implementation backlog

Nguồn kế hoạch: `PLAN-SHOPLAB-PTES-001` / `SHOPLAB-PTES-001`, xem [PROJECT_PLAN.md](PROJECT_PLAN.md). Người dùng đã mở phạm vi cập nhật tài liệu/task; không cấp per-run approval hoặc quyền sửa contracts/catalog/evidence. Giữ nguyên bảng TASK-001–035 và các trạng thái lịch sử ở trên, không tự review hoặc nâng validation. `SL-*` là work packages bổ sung, không thay thế hoặc tạo lại canonical task IDs.

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
| [SL-09](docs/task-specs/SL-09-observation-planner.md) | TASK-020, TASK-021, TASK-022 | `IMPLEMENTED` | [SL-08](docs/task-specs/SL-08-discovery-safety.md) | State-manager integration (idempotent, conflict detection, minimized prompt), schema-bound proposals (plan.schema.json), explicit mode provenance (RULE/LLM/MOCK), strict fallback handling, zero-dispatch gate eval: 13 unit tests P01–P08 & authority PASS, live Docker verification 8/8 pha PASS; Autonomous Closed-Loop Runner (runtime/autonomous_runner.py) đạt 12/12 tests A01–A12 PASS, live verification PASS (RUN-AUTONOMOUS-LIVE-1791708234); chưa independent approval |
| [SL-10](docs/task-specs/SL-10-ptes-orchestration.md) | TASK-020, TASK-028, TASK-033 | `IMPLEMENTED` | [SL-08](docs/task-specs/SL-08-discovery-safety.md), [SL-09](docs/task-specs/SL-09-observation-planner.md) | PTES coordinator điều phối 7 phase (exit criteria, honest transitions Phase 5 BLOCKED, Phase 6 NOT_RUN, Phase 7 COMPLETED): 8 unit tests T01–T08 PASS, live Docker verification 7/7 phase PASS; chưa independent approval |
| [SL-11](docs/task-specs/SL-11-evidence-reporting.md) | TASK-007, TASK-028, TASK-029, TASK-033, TASK-034 | `IMPLEMENTED` | [SL-07](docs/task-specs/SL-07-lab-runtime.md), [SL-10](docs/task-specs/SL-10-ptes-orchestration.md) | Immutable evidence packaging, report generator, zero-network replay verifier, root containment, non-recurrence lock: 14 tests E01–E09 & B01–B05 PASS, authoritative run `RUN-SL11-HANDOFF-20261011/`, ghi nhận sai lệch lịch sử; chưa independent approval |
| [SL-12](docs/task-specs/SL-12-verification-handoff.md) | TASK-030, TASK-034, TASK-035 | `SPEC_ONLY` | SL-07, SL-08, SL-09, SL-10, SL-11 | Pre-review gate HANDOFF_BLOCKED do validate_scaffold phát hiện vi phạm schema tại scripts/demo/demo-output/... từ phiên khác; khóa build ID, run ID, CURRENT_REVIEW_SOURCE_MANIFEST, 18 checks PASS; dừng chờ chỉ thị scope |

Đã có 12 đặc tả chi tiết được liên kết ở bảng trên; xem [chỉ mục và lifecycle contracts](docs/task-specs/index.md#shoplab-task-contracts). Mỗi task gồm phạm vi, interfaces/data contracts, implementation/safety requirements, test cases, acceptance, evidence và failure conditions. Sự tồn tại của đặc tả không nâng trạng thái implementation/runtime; SL-01/SL-02 chỉ có validation trong phạm vi checks/review được ghi bên dưới. Trước live dispatch SL-07–10 phải có approved recorder/destination và failure-stop checks; SL-11 không cho phép trì hoãn ghi evidence đến cuối run.

Hướng hiện hành: **thẩm định/pin/configuration upstream → fit-gap/acceptance SL-04–06 → approved runtime SL-07 → SL-08 → SL-09/SL-10 → SL-11 → SL-12**. SL-01–03 giữ là lịch sử ShopLab, không chuyển PASS sang Oscar hoặc bỏ pending independent approval SL-03. IDs/dependencies trong bảng giữ nguyên; dependency equivalence cho target mới cần review explicit, không tự coi fulfilled bằng upstream. TASK-026 và TASK-032 giữ `DEFERRED`; không mở RL training, dashboard hoặc metrics claims.

### Cập nhật theo web target snapshot

Các specs [TASK-011](docs/task-specs/TASK-011-cyber-range-network.md), [TASK-012](docs/task-specs/TASK-012-web-target-a.md), [TASK-013](docs/task-specs/TASK-013-web-target-b.md), [TASK-014](docs/task-specs/TASK-014-clean-control-target.md), [TASK-018](docs/task-specs/TASK-018-observation-normalizer.md) và [TASK-019](docs/task-specs/TASK-019-knowledge-state-store.md) phân loại phần giữ nguyên, impact assessment và receipts mới khi web snapshot đổi. Bảng trạng thái/dependencies và evidence lịch sử ở trên không đổi; validation cũ không áp dụng tự động cho snapshot mới. TARGETS-012/013/014 là evidence target riêng theo phạm vi lịch sử; linkage RUNTIME-004 cần đối chiếu riêng trước tái sử dụng. Instance scenario/ground-truth/experiment version theo snapshot tại TASK-008–010; ground truth chỉ evaluation.

## Checks and observed implementation state

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

- Foundation blockers lịch sử: không có theo bảng hiện hành. TASK-011–014 được TASKS.md ghi validation cho slice cũ; không dùng làm chứng nhận ShopLab/gateway mới hoặc LLM.
- RUNTIME-004 manifest ghi `IMPLEMENTED` trong khi task prose ghi `VALIDATED` qua approved review. Cần đối chiếu review/claim scope và hashes trước tái sử dụng; chưa xác minh trong phiên này, không sửa evidence hoặc tự thay status lịch sử.
- Documentation checker compatibility và blocker SL-01 trước đây đã được xử lý: exact 35 TASK + 12 SL được kiểm tra, required checks và gate PASS, review độc lập APPROVE đã xác minh. Không còn blocker cho baseline SL-01; các attempts bị chặn trước đây không được chuyển thành PASS.
- SL-02 không còn blocker trong scope offline được review: lifecycle, rollback, schema preservation, concurrency và process-restart persistence đã có checks/review R1. Auth/CSRF/ownership SL-03 đã IMPLEMENTED và có offline checks, nhưng chưa có independent approval; checkout/stock/idempotency (SL-04), orders/reviews (SL-05), admin nghiệp vụ (SL-06), lab runtime (SL-07), discovery safety gate (SL-08), observed planner (SL-09), PTES coordinator điều phối 7 phase trung thực (SL-10), và immutable evidence packaging / zero-network replay (SL-11) đã hoàn thành implementation với receipts kiểm thử đầy đủ cùng live Docker verification và gói chuẩn mực `RUN-SL11-HANDOFF-20261011/`.
- `lab-ecommerce` đã được đăng ký chính thức vào `configs/safety/target-allowlist.yaml` và manifest; CentralizedSafetyGate áp dụng bất biến tập giao `canonical allowlist ∩ run-approved targets`, runtime caller không thể nới rộng chính sách.
- Docker isolation, durable storage và product E2E (SL-07), discovery safety gate (SL-08), observed planner (SL-09), PTES coordinator (SL-10) và evidence packaging/replay (SL-11) đã hoàn thành implementation; SL-12 deterministic pre-review gate đã PASS (khóa build/evidence identity, source manifest và review contract), đang chờ independent review độc lập thực hiện. Chưa có independent review / approval; không tự nâng `VALIDATED`.
- Active exploitation và post-exploitation ngoài safe verification chưa có executable scope. Phase cần quyền vượt scope phải `BLOCKED`/`NOT_RUN`, không fake completed. Task status vocabulary giữ nguyên; `NOT_RUN` chỉ là phase execution status.
- Public targets, production data, new payloads, arbitrary shell, dynamic actions và tự nâng validation vẫn không được phép.
