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
| [SL-04](docs/task-specs/SL-04-cart-checkout.md) | TASK-011 | `SPEC_ONLY` | SL-02, SL-03 | Upstream catalog/basket/checkout fit-gap và acceptance; không viết lại nghiệp vụ. Giữ money/snapshot/stock/transaction/idempotency/concurrency invariants, ghi rõ chênh lệch Decimal và stock allocation |
| [SL-05](docs/task-specs/SL-05-orders-reviews.md) | TASK-011 | `SPEC_ONLY` | SL-03, SL-04 | Upstream orders/reviews ownership, snapshots, escaping và offline communication acceptance; invoice là gap chưa xác minh, không tự thêm extension |
| [SL-06](docs/task-specs/SL-06-product-admin.md) | TASK-003, TASK-011 | `SPEC_ONLY` | SL-03, SL-04, SL-05 | Cấu hình/kiểm chứng upstream dashboard permissions, local role workflow, stock/status invariants và UI/assets offline; không viết lại admin hoặc seed credentials |
| [SL-07](docs/task-specs/SL-07-lab-runtime.md) | TASK-011, TASK-014 | `SPEC_ONLY` | SL-02, SL-03, SL-04, SL-05, SL-06 | Scope riêng cho target identity mới, Linux/DB/image provenance, gateway Host/Origin/CSRF, registry, isolation/storage/restore/E2E receipts; không thuộc quyền execution hiện hành |
| [SL-08](docs/task-specs/SL-08-discovery-safety.md) | TASK-003, TASK-004, TASK-015, TASK-018, TASK-019 | `SPEC_ONLY` | [SL-07](docs/task-specs/SL-07-lab-runtime.md) | Seed/links/forms/redirect discovery, canonicalization và limits; per-request gate, rate/order/budgets/kill switch; reject tests chứng minh zero dispatch |
| [SL-09](docs/task-specs/SL-09-observation-planner.md) | TASK-020, TASK-021, TASK-022 | `SPEC_ONLY` | [SL-08](docs/task-specs/SL-08-discovery-safety.md) | Schema-bound observed-state planning và replan; no ground-truth/source/token leak; explicit actual mode/model/provider/fallback; changed-route fixture tests |
| [SL-10](docs/task-specs/SL-10-ptes-orchestration.md) | TASK-020, TASK-028, TASK-033 | `SPEC_ONLY` | SL-08, SL-09 | Bảy phase-specific PTES outputs/exit checks theo PROJECT_PLAN; blocked/not-run/unresolved không giả completed; không mở active exploitation |
| [SL-11](docs/task-specs/SL-11-evidence-reporting.md) | TASK-007, TASK-028, TASK-029, TASK-033, TASK-034 | `SPEC_ONLY` | SL-07, SL-10 | Append-only redacted evidence, source/hash/UTC/expected-observed, unique observations/replay; evidence failure dừng; evidence-linked reports với negative results/coverage/limitations |
| [SL-12](docs/task-specs/SL-12-verification-handoff.md) | TASK-030, TASK-034, TASK-035 | `SPEC_ONLY` | SL-07, SL-08, SL-09, SL-10, SL-11 | Focused tests và validator receipts, authorized Docker/provider observations, deterministic contract pre-review gate, independent review và pending handoff; không self-approve |

Đã có 12 đặc tả chi tiết được liên kết ở bảng trên; xem [chỉ mục và lifecycle contracts](docs/task-specs/index.md#shoplab-task-contracts). Mỗi task gồm phạm vi, interfaces/data contracts, implementation/safety requirements, test cases, acceptance, evidence và failure conditions. Sự tồn tại của đặc tả không nâng trạng thái implementation/runtime; SL-01/SL-02 chỉ có validation trong phạm vi checks/review được ghi bên dưới. Trước live dispatch SL-07–10 phải có approved recorder/destination và failure-stop checks; SL-11 không cho phép trì hoãn ghi evidence đến cuối run.

Hướng hiện hành: **thẩm định/pin/configuration upstream → fit-gap/acceptance SL-04–06 → approved runtime SL-07 → SL-08 → SL-09/SL-10 → SL-11 → SL-12**. SL-01–03 giữ là lịch sử ShopLab, không chuyển PASS sang Oscar hoặc bỏ pending independent approval SL-03. IDs/dependencies trong bảng giữ nguyên; dependency equivalence cho target mới cần review explicit, không tự coi fulfilled bằng upstream. TASK-026 và TASK-032 giữ `DEFERRED`; không mở RL training, dashboard hoặc metrics claims.

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

Chưa xác minh: independent approval, legacy migration, Docker/browser/HTTPS, transport confidentiality của current valid bearer token, actual restore/invalidate-all/container durability, chống hostile filesystem/external-process writers, checkout money/stock/idempotency/file-DB atomicity (SL-04), full SL-05/06 và provider/PTES runtime. Handoff lịch sử SL-03 vẫn cần review độc lập exact build để đóng acceptance lifecycle, không được coi SL-03 đã VALIDATED. Lựa chọn mới chuyển công việc hiện hành sang upstream Oscar fit-gap/configuration/acceptance; không tiếp tục tự xây SL-04 ShopLab và không bỏ pending approval lịch sử.

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
- SL-02 không còn blocker trong scope offline được review: lifecycle, rollback, schema preservation, concurrency và process-restart persistence đã có checks/review R1. Auth/CSRF/ownership SL-03 đã IMPLEMENTED và có offline checks, nhưng chưa có independent approval; checkout/stock/idempotency, admin nghiệp vụ và approved restore vẫn chưa hoàn thiện. Không áp dụng validation SL-02 cho các luồng này.
- `lab-ecommerce` chưa được đối chiếu registration trong safety target allowlist/manifest; compose entry không tự cấp quyền.
- Docker isolation, durable storage, product E2E và provider-backed AI run chưa được kiểm chứng cho code mới. Thiếu per-run approval và evidence destination được chốt.
- Active exploitation và post-exploitation ngoài safe verification chưa có executable scope. Phase cần quyền vượt scope phải `BLOCKED`/`NOT_RUN`, không fake completed. Task status vocabulary giữ nguyên; `NOT_RUN` chỉ là phase execution status.
- Public targets, production data, new payloads, arbitrary shell, dynamic actions và tự nâng validation vẫn không được phép.
