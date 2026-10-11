# SL-04 — Catalog, giỏ hàng và checkout toàn vẹn

## Status

`IMPLEMENTED`. Triển khai trên ShopLab target (`cyber-range/targets/ecommerce/app.py`), xác minh qua integration suites `test_ecommerce_checkout.py` (13 tests PASS) và `test_ecommerce_storage.py` (28 tests PASS). Tổng 65 tests ecommerce integration PASS. Chưa có independent review / approval; không tự nâng lên `VALIDATED`. Không runtime/Docker validation.

## Purpose

Cung cấp luồng duyệt/tìm kiếm sản phẩm (catalog/search/detail), quản lý giỏ hàng tách biệt theo owner (guest session token digest hoặc user ID), và checkout đơn lẻ trong một transaction atomic không oversell, không duplicate order, không floating-point money drift, và tách rời invoice filesystem generation ra ngoài DB transaction.

## Background

ShopLab là web target thương mại điện tử độc lập của lab cyber-range đang tiếp tục được phát triển và hoàn thiện. SL-01 và SL-02 đã hoàn thành baseline gateway và SQLite storage lifecycle/transactions. SL-03 đã triển khai auth, sessions, CSRF và ownership. SL-04 hoàn thiện các invariants nghiệp vụ cốt lõi: catalog/search, giỏ hàng, atomic stock decrement trong checkout transaction, tách biệt hoàn toàn invoice file generation ra ngoài DB transaction (post-commit action kết hợp on-demand fallback) để đảm bảo ACID, chuẩn hóa idempotency theo logical owner `(key, owner_key)`, và xử lý tiền tệ chính xác bằng integer minor units (USD cents).

## Scope

- Source allowlist: `cyber-range/targets/ecommerce/app.py`, `tests/integration/test_ecommerce_checkout.py`, `tests/integration/test_ecommerce_storage.py`.
- Nghiệp vụ:
  1. Product catalog & search: case-insensitive bounded substring search (`/products?q=...`), category filtering, chi tiết sản phẩm, an toàn 404 cho missing product.
  2. Cart management: guest cart gắn session token digest (`cart_key`), user cart gắn `user_id`. Add, update, remove validate quantity (> 0), kiểm tra stock availability phía server.
  3. Single-transaction checkout: validate owner/session/CSRF, kiểm tra idempotency, load authoritative basket/prices từ DB (bỏ qua client-supplied prices), kiểm tra stock, atomic decrement stock qua `UPDATE products SET stock = stock - ? WHERE id = ? AND stock >= ?`, insert đơn hàng vào `orders`, insert từng dòng vào `order_items`, lưu bản ghi idempotency, xóa giỏ hàng, commit SQLite transaction.
  4. Decoupled invoice filesystem: tách hoàn toàn việc ghi file invoice ra ngoài DB transaction qua cơ chế post-commit action; nếu DB commit thất bại thì không tạo orphan invoice file; nếu filesystem ghi file thất bại thì không rollback order đã commit; route `/download/invoice` có cơ chế fallback tự động tạo hóa đơn on-demand từ DB.
  5. Idempotency owner semantics: bảng `order_idempotency` khóa chính `(key, owner_key)` với `owner_key` phân biệt `user:<uid>` và `guest:<cart_key>`. Retry cùng payload trả về order đã tạo mà không trừ kho lần hai; retry cùng key sau khi user xoay session vẫn nhận diện đúng đơn hàng; retry khác payload trả về 409 Conflict; hai owner khác nhau dùng cùng textual key không bị xung đột.
  6. Money arithmetic: tính toán toàn bộ bằng integer minor units (cents) thông qua `Decimal('0.01')` với rounding `ROUND_HALF_UP`, tránh sai số binary floating-point. Schema SQLite ràng buộc cứng `CHECK(currency = 'USD')`, định nghĩa hằng số `SHOPLAB_CURRENCY = 'USD'`.

## Out of Scope

Không tích hợp cổng thanh toán bên ngoài (không thẻ tín dụng thật, không Stripe/PayPal), không gửi email thật ra ngoài lab, không PII, không chuyển đổi đa tiền tệ ngoài USD, không migrate sang Django Oscar.

## Inputs

Authoritative catalog trong SQLite; session identities (authenticated user ID hoặc opaque guest session HMAC digest); CSRF tokens hợp lệ từ form; idempotency key từ header `Idempotency-Key` / `X-Idempotency-Key` hoặc form payload.

## Outputs

- Bảng dữ liệu: `products` (stock cập nhật nguyên tử), `orders` (bản ghi đơn hàng với status `completed`), `order_items` (snapshot tên sản phẩm, số lượng, đơn giá và currency USD), `order_idempotency` (khóa kép `key, owner_key` lưu `request_hash` và `order_id`).
- File hóa đơn: tệp `INV-[A-F0-9]{32}.txt` tạo ở post-commit hook; endpoint `/download/invoice` an toàn có dynamic on-demand fallback.
- Test suites: `tests/integration/test_ecommerce_checkout.py` (13 tests PASS), `tests/integration/test_ecommerce_storage.py` (28 tests PASS).

## Interfaces

- `GET /products`, `GET /products?q=...`
- `GET /cart`, `POST /cart/add`, `POST /cart/update`, `POST /cart/remove`
- `GET /checkout`, `POST /checkout`
- `GET /download/invoice?file=INV-...`

## Data Contracts

- `products`: `price` REAL/INTEGER >= 0, `stock` INTEGER >= 0, `currency` = 'USD'.
- `orders`: `id` INTEGER PK, `user_id` INTEGER, `session_id` TEXT, `total` REAL >= 0, `currency` = 'USD', `status` TEXT, `invoice_file` TEXT.
- `order_items`: `id` INTEGER PK, `order_id` INTEGER FK, `product_id` INTEGER FK, `quantity` INTEGER > 0, `unit_price` REAL >= 0, `currency` = 'USD'.
- `order_idempotency`: `key` TEXT, `owner_key` TEXT, `user_id` INTEGER, `session_id` TEXT, `order_id` INTEGER, `request_hash` TEXT, `created_at` TEXT, `PRIMARY KEY (key, owner_key)`.

## Dependencies

SL-02, SL-03; TASK-011. SL-05 hiển thị/serve order/invoice đã được tạo; không dependency vòng với invoice generation.

## Implementation Requirements

1. Search/filter: parameterized, bounded, case-insensitive substring; không leak dữ liệu SQL; sản phẩm không tồn tại trả response 404 an toàn.
2. Cart ownership: guest cart gắn opaque token digest, authenticated cart gắn user ID. Add/update/remove validate quantity dương và kiểm tra tồn kho phía server; bỏ qua hoàn toàn unit price gửi từ client.
3. Checkout transaction nguyên tử: kiểm tra idempotency -> nạp authoritative cart items -> kiểm tra stock -> atomic stock decrement (`UPDATE products SET stock = stock - ? WHERE id = ? AND stock >= ?`) -> insert order & order_items -> insert idempotency record -> xóa cart -> commit.
4. Tách biệt invoice filesystem: không ghi tệp filesystem trong DB transaction block. Ghi file ở `_post_commit_action` sau khi DB commit thành công; download route có dynamic fallback tái tạo hóa đơn từ DB nếu file không tồn tại trên đĩa.
5. Idempotency theo owner: khóa chính `(key, owner_key)`; cùng owner + cùng payload trả về order cũ; cùng owner + khác payload trả 409 Conflict; khác owner + cùng key hoạt động độc lập; user sau rotation session vẫn tra cứu được đúng đơn hàng.
6. Xử lý tiền tệ chính xác: chuẩn hóa sang integer minor units (cents) qua helper `_to_minor` và `_from_minor`; SQLite schema ràng buộc `CHECK(currency = 'USD')`. Các giá trị `0.10`, `0.20`, `0.30`, `10.01`, `19.99` và tổng nhiều món round-trip chính xác.
7. Bảo vệ CSRF: form mutation bắt buộc CSRF token hợp lệ; cart rỗng bị từ chối chuyển hướng về `/cart`.

## Safety Requirements

Lab-only isolation. Không thanh toán thật, không thẻ tín dụng, không PII. CSRF validation bắt buộc trước mọi state mutation. Allowlist target và hành động. Path traversal rejection trên endpoint download hóa đơn (`_validate_path` và regex pattern filename).

## Testing Requirements

| Case | Scenario | Expected |
|---|---|---|
| C01 | Browse/search + category/detail/missing ID | Kết quả chính xác, bounded query, safe 404 |
| C02 | Hai guests/users thao tác cart | Carts hoàn toàn độc lập theo owner |
| C03 | Non-positive, non-integer, oversized quantity | Bị từ chối, DB không thay đổi |
| C04 | Client gửi giá/total tùy ý | Bỏ qua; tính toán strictly từ authoritative DB |
| C05 | Checkout hợp lệ | Stock decrement, order, items, idempotency commit đồng thời, cart xóa sạch |
| C06 | Failure giữa transaction (hết stock / DB error) | Rollback toàn bộ, zero orphan invoice file |
| C07 | Idempotency retry (Cases A–E) & conflict | Cùng payload trả cùng order; khác payload trả 409; session rotation nhận đúng order; khác owner độc lập |
| C08 | Hai buyers mua hàng cuối / stock concurrency | Atomic decrement; một người thành công, một người nhận lỗi 409 |
| C09 | Process restart & catalog price thay đổi sau checkout | Đơn hàng và giá snapshot được bảo toàn |

## Acceptance Criteria

Tất cả các business invariants về stock concurrency, cart ownership, single-transaction checkout, post-commit invoice decoupling, idempotency owner semantics, và money minor units USD được kiểm chứng tự động bằng tests. Bộ test `tests/integration/test_ecommerce_checkout.py` (13 tests) và `tests/integration/test_ecommerce_storage.py` (28 tests) đạt 100% PASS. Không tồn tại orphan file khi checkout fail; filesystem failure không rollback order đã commit.

## Evidence Required

Command receipts thực tế:
- `python -B -m unittest discover -s tests/integration -p "test_ecommerce_checkout.py"`: 13 tests PASS, exit 0.
- `python -B -m unittest discover -s tests/integration -p "test_ecommerce_*.py"`: 65 tests PASS, exit 0.
- `python -B scripts/validation/validate_scaffold.py`: SCAFFOLD VALID, exit 0.
Không ghi token, password hoặc dữ liệu cá nhân trong receipts.

## Failure Conditions

Oversell hàng tồn kho, duplicate order khi retry idempotency key, sai số dấu phẩy động tiền tệ, tạo file invoice orphan khi DB rollback, hoặc invoice filesystem error làm rollback DB order đã commit.

## Related Guides

[Web security](../guides/04-web-security-testing.md), [Cyber Range](../guides/03-cyber-range-fundamentals.md).

## Related Runbooks

[Collect evidence](../runbooks/collect-evidence.md), [Restore range](../runbooks/restore-range.md).

## Related ADRs

[ADR-013](../adr/ADR-013-runtime-vertical-slice.md), [Evidence immutability](../adr/ADR-010-evidence-immutability.md).
