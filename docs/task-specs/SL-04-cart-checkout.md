# SL-04 — Catalog, giỏ hàng và checkout toàn vẹn

## Status

`SPEC_ONLY`. Hướng hiện hành là upstream fit-gap/configuration/acceptance, không tiếp tục tự xây cart/checkout ShopLab. Django Oscar sandbox 4.2.1 chưa chạy; source/dependency/environment gate còn blocker. Trang hoặc source upstream không chứng minh invariants đúng.

## Purpose

Luồng browse/search/detail → cart → order hoạt động như sản phẩm, không oversell, trộn cart, tính tiền sai hoặc tạo đơn trùng.

## Background

ShopLab lịch sử dùng float, chưa có stock/idempotency/checkout acceptance; shared connection đã được SL-02 sửa và search có regression receipts, không suy ra nghiệp vụ hoàn chỉnh. Hướng mới tái sử dụng Oscar, không tiếp tục sửa business app; source inspection chỉ cho thấy khả năng upstream, chưa có execution checks.

## Scope

Đề xuất `cyber-range/targets/oscar-lab/**` và `tests/integration/test_oscar_lab*.py`: tái sử dụng catalog/basket/checkout upstream, cấu hình lab mỏng và acceptance tests. Không sửa ShopLab, không migrate DB cũ hoặc viết lại auth/cart/order. Dependency equivalence với SL-02/SL-03 phải có review riêng; receipts ShopLab không kiểm chứng Oscar. Không triển khai cổng payment thật.

## Out of Scope

Không discount/tax/multi-currency phức tạp, external payment/email, real customer data, frontend framework migration, fixed demo lỗi. Không thay schema contract nghiên cứu hoặc config ngoài task.

## Inputs

SL-02/SL-03 acceptance receipts; product catalog/schema, validated sessions và stock; currency decision/limits được chốt cho lab trước edit.

## Outputs

Upstream capability/fit-gap matrix, cấu hình lab tối thiểu và acceptance receipts cho catalog/basket/checkout/order snapshots; tests transaction/concurrency/idempotency. Không tạo checkout service mới chỉ để khớp prototype; missing equivalence giữ blocker.

## Interfaces

Dùng routes/forms/models upstream đã pin; không adapter routes ShopLab chỉ để tests cũ pass. Product acceptance có thể biết routes, nhưng không đưa route map/source vào discovery/planner. Checkout nhận current validated identity/basket, giá server và shipping giả; mapping idempotency/stock/money phải có fit-gap explicit trước khi claim acceptance.

## Data Contracts

`price_minor`, `unit_price_minor`, `total_minor` integer và currency explicit; quantity positive bounded integer, stock nonnegative. Order items snapshot product label/price/currency/quantity; future catalog edit không thay invoice đơn cũ. Key uniqueness scoped owner + operation; duplicate matching request trả cùng order, different payload với key cũ bị conflict. Shipping chỉ fixture giả trong lab.

## Dependencies

SL-02, SL-03; TASK-011. SL-05 hiển thị/serve order/invoice đã được tạo; không dependency vòng với invoice generation.

## Implementation Requirements

Thẩm định/cấu hình/kiểm chứng upstream theo các invariants bên dưới, không coi đây là yêu cầu tự viết lại services. Source Oscar dùng Decimal và stock allocation; chưa chứng minh tương đương integer minor units/decrement/idempotency/concurrency. Ghi gap và giữ task chưa complete nếu chưa đáp ứng; thay acceptance cần approval riêng. Trước upstream execution phải có dependency lock/license audit và môi trường phù hợp: Windows không được upstream hỗ trợ, PostgreSQL hỗ trợ chính thức, SQLite chỉ development. Không chạy Makefile reset/seed hoặc source build NPM hook.

1. Search/filter bounded, parameterized, cả hai kết hợp; no SQL leak. Product không tồn tại/hết hàng có response rõ.
2. Cart chỉ truy cập validated owner/session; guest migration theo SL-03. Add/update/remove validate product/quantity/availability phía server; row IDs không tự chứng minh ownership.
3. Một transaction checkout: check key/owner → load cart/prices → validate stock/shipping → decrement stock atomically → insert order/items/shipping → clear cart → commit. Error bất kỳ rollback; không tạo file invoice nằm ngoài transaction ở đây.
4. Money integer minor units; chuyển dữ liệu float legacy có migration explicit/test, không round silently hay nhận client price.
5. Idempotency key ràng buộc request và owner; cùng submission/retry không double charge giả lập hoặc decrement hai lần. Empty cart request không tạo order mới.
6. Stock check và update cùng transaction; concurrency two buyers dùng hàng cuối chỉ một successful order. Bounded quantity/total và integer overflow policy rõ.
7. UI forms CSRF, stale-stock messages, quantity update/remove, contact fields validation; không fake email/payment success. Đơn được accepted không mặc định delivered.

## Safety Requirements

Không real payment hoặc PII. Reject before writes với invalid identity/CSRF. Không trust hidden inputs/unit price. Giữ snapshot và ownership khi role/session đổi; không disclose cart người khác. Concurrency tests dùng temp DB, không lab data hiện hữu.

## Testing Requirements

| Case | Scenario | Expected |
|---|---|---|
| C01 | Browse/search + category/detail/missing ID | Kết quả đúng, bounded validation, safe 404 |
| C02 | Hai guest/users add/update/remove cùng product | Carts tách biệt; ownership checked |
| C03 | Zero/negative/noninteger/oversized quantity | Reject, DB không đổi |
| C04 | Client gửi total/price/owner tùy ý | Bỏ qua/reject; giá từ server snapshot |
| C05 | Checkout hợp lệ | Stock/order/items/shipping/cart commit cùng nhau |
| C06 | Failure giữa transaction | Không partial order/decrement/cart loss |
| C07 | Same key retry và key khác payload/owner | Same order hoặc conflict đúng, không double-write |
| C08 | Hai buyers mua hàng cuối và stock stale | Không oversell; một winner, loser rõ lỗi |
| C09 | Restart và catalog price change sau checkout | Đơn và giá snapshot không đổi |

## Acceptance Criteria

Các invariants money/stock/cart/ownership/transaction/idempotency được asserts trong tests, không chỉ response 200. Business flow thật qua in-process HTTP pass và negative cases giữ DB unchanged. Không invoice side effect nửa commit; UI/CSRF compatible gateway. Docker claim để SL-07.

## Evidence Required

Test commands/results và redacted before/after invariant snapshots; transaction strategy/concurrency receipts; không real addresses/emails/tokens. Handoff SL-05 order schema và snapshot rules, unresolved constraints.

## Failure Conditions

Oversell, duplicate order, price mismatch, mixed cart ownership, partial transaction hoặc unreviewed migration: blocker, không complete. Required tests chưa chạy không coi IMPLEMENTED whole package.

## Related Guides

[Web security](../guides/04-web-security-testing.md), [Cyber Range](../guides/03-cyber-range-fundamentals.md).

## Related Runbooks

[Collect evidence](../runbooks/collect-evidence.md), [Restore range](../runbooks/restore-range.md).

## Related ADRs

[ADR-013](../adr/ADR-013-runtime-vertical-slice.md), [Evidence immutability](../adr/ADR-010-evidence-immutability.md).
