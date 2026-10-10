# SL-01 — Kiểm chứng baseline gateway và storage

## Status

`BLOCKED` theo TASKS.md: các lệnh kiểm thử trước đây bị chặn trước thực thi bởi classifier không khả dụng. Cần kiểm tra lại availability khi bắt đầu, không giả định blocker vĩnh viễn. Đặc tả được viết không hoàn thành work package.

## Purpose

Có baseline có thể tin cậy trước khi mở rộng ShopLab: biết đúng phiên bản, diff của người dùng, tests thực sự chạy hay bị chặn, lỗi nào thuộc code và lỗi nào thuộc môi trường.

## Background

Gateway đã sửa cookie/redirect/limits; ShopLab đã có storage lifecycle và parameterized search. Tests mới chưa có pass/fail receipts. Những thay đổi này không được chứng nhận bằng evidence của target slice cũ.

## Scope

Phạm vi triển khai đề xuất: đọc baseline toàn repo; sửa tối thiểu `cyber-range/runtime/gateway.py`, `cyber-range/targets/ecommerce/app.py`, `cyber-range/targets/ecommerce/Dockerfile` và hai tests hiện hữu `tests/integration/test_gateway_product.py`, `tests/integration/test_ecommerce_storage.py` khi có lỗi được tái hiện. Mỗi build phải được giao allowlist cụ thể; task-spec không tự cấp quyền sửa mã.

## Out of Scope

Không bổ sung nghiệp vụ lớn, không thay config/contracts/catalog/targets khác; không chạy pentest hoặc Docker không có approval; không restore/reset/stash/commit để làm sạch baseline. Không credentials, payload hoặc measured claims mới.

## Inputs

AGENTS.md, PROJECT_CONTEXT.md, PROJECT_PLAN.md, TASKS.md; plan `PLAN-SHOPLAB-PTES-001`; current HEAD/status/diff và các file untracked sẽ sửa. Base head kế hoạch là `96d9428ef715299ca2c6d403a81d50d97ae55412`; xác minh lại thay vì mặc định.

## Outputs

Baseline inventory; danh sách checks thực tế; từng lỗi có input/expected/observed và minimal repair; BUILD_CONTRACT; pending handoff tới SL-02/SL-03. Nếu tools bị chặn, output `HANDOFF_BLOCKED`, không exit code giả.

## Interfaces

`gateway.validate_upstream`, `validate_path`, `safe_location`, `Gateway._proxy`; `app.initialize_storage`, `close_storage`, `_init_db`, `search_products`. Import modules bằng fixture không chạy service. Dùng test runner hiện hữu, không xây runner mới để bypass permissions.

## Data Contracts

Receipt gồm command, working directory, source HEAD, exit code nếu thực thi, kết quả và artifact reference nếu có. `BLOCKED_BEFORE_EXECUTION` khác test `FAIL`; `exit_code=null` khi không chạy. Snapshot/diff không được chứa secrets. Theo lifecycle contract tại [index](index.md#shoplab-task-contracts).

## Dependencies

Không có dependency SL. Liên kết TASK-011/TASK-014 chỉ là foundation scope, không chứng nhận code mới.

## Implementation Requirements

1. Đọc relevant sources và ghi current baseline; giữ nguyên user changes ngoài diff được giao.
2. Kiểm tra imports không ghi DB/file hoặc khởi động network; kiểm tra syntax với checker được phép.
3. Chạy hai commands hiện hữu: `python -m unittest discover -s tests/integration -p test_gateway_product.py -v` và `python -m unittest discover -s tests/integration -p test_ecommerce_storage.py -v`.
4. Nếu test fails, sửa smallest diff dựa trên failure; rerun cả bộ liên quan, ghi các attempts. Không mở rộng auth/checkout trong repair này.
5. Kiểm tra regression và documentation links; chạy repository checker theo CLI được xác minh. Existing repository failures phải ghi rõ, không sửa ngoài allowlist.

## Safety Requirements

Không bypass tool denial/classifier hoặc nhờ worker khác thực hiện lệnh bị chặn. Không log cookies/passwords thật. Mock dùng để test dispatch boundary, không là runtime proof. Không overwrite evidence cũ.

## Testing Requirements

| Case | Input/trạng thái | Expected |
|---|---|---|
| B01 | Import ShopLab/gateway với fixture | Không filesystem/network side effects |
| B02 | Login redirect qua mock upstream có nhiều Set-Cookie | Cookie/status/Location giữ đúng, chỉ một upstream request |
| B03 | Unknown upstream, malformed path/framing, oversized body | Reject trước connect; bounded errors |
| B04 | Reopen SQLite cùng thư mục | Stock/count giữ nguyên; không reseed |
| B05 | Search/category và literal wildcard characters | Filter kết hợp, không diễn giải thành SQL/wildcard ngoài ý định |
| B06 | Runtime command bị chặn | Receipt blocked, không báo PASS/FAIL |

Các case B01–B05 phải gắn với test thực tế hoặc nêu gap; không tự tuyên bố test có coverage đầy đủ.

## Acceptance Criteria

- Baseline và build diff phân biệt được user changes.
- Hai focused suites thực sự pass sau minimal repairs; checker/regression không có new attributable failures.
- Không import side effects hoặc hidden fallback trong check execution.
- Independent review xem exact diff/receipts. Chưa review thì không `VALIDATED`; unresolved required checks giữ handoff blocked.

## Evidence Required

Command receipts với expected/observed, baseline scope và nguồn lỗi; nếu lưu evidence phải exclusive new destination đã duyệt, UTC/run/source/hash/redaction. Check pass không xác nhận Docker isolation hoặc web product E2E.

## Failure Conditions

Tool unavailable, base head đổi, sửa file ngoài scope, malformed receipt, không tái hiện lỗi, schema/source conflict hoặc evidence-loss risk: dừng và báo blocker. Handoff không có proof không được review gate thông qua.

## Related Guides

[Cyber Range](../guides/03-cyber-range-fundamentals.md), [Safety](../guides/17-cyber-range-safety.md).

## Related Runbooks

[Validate isolation](../runbooks/validate-isolation.md), [Collect evidence](../runbooks/collect-evidence.md). Chỉ tham khảo; không runtime authorization.

## Related ADRs

[ADR-013](../adr/ADR-013-runtime-vertical-slice.md), [Evidence immutability](../adr/ADR-010-evidence-immutability.md).
