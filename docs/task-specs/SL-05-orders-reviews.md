# SL-05 — Đơn hàng, hóa đơn và đánh giá

## Status

`IMPLEMENTED`. Đã hoàn thành trên target ShopLab (`cyber-range/targets/ecommerce/app.py`) và kiểm chứng tự động bằng bộ test tích hợp `tests/integration/test_ecommerce_orders_reviews.py` (16 tests PASS). Chưa có independent review / approval; không tự nâng `VALIDATED`.

## Purpose

Người dùng truy cập lịch sử/chi tiết đơn hàng, tải hóa đơn và gửi đánh giá sản phẩm đúng quyền hạn; bảo đảm an toàn dữ liệu, chống IDOR, bảo vệ stored XSS, phân tách hóa đơn và phản ánh nhãn lab mô phỏng.

## Background

Trước SL-05, luồng checkout SL-04 đã tạo đơn và tách invoice post-commit. SL-05 hoàn thiện việc truy cập lịch sử đơn hàng, xem chi tiết snapshot đơn, chống IDOR đa người dùng, tải file hóa đơn kèm cơ chế fallback tạo hóa đơn từ DB, hiển thị nhãn hóa đơn lab mô phỏng, thu nhỏ dữ liệu API (data minimization), và quản lý đánh giá sản phẩm có escaping chống XSS.

## Scope

- Code ứng dụng: `cyber-range/targets/ecommerce/app.py`
- Test suite tích hợp: `tests/integration/test_ecommerce_orders_reviews.py`
- Endpoint: `/orders`, `/orders/<id>`, `/api/orders/<id>`, `/download/invoice?file=...`, `/reviews`, `/products/<id>`

## Out of Scope

Không thanh toán tiền thật, không gửi email ra ngoài mạng, không arbitrary file download, không upload tệp tùy ý, không bypass CSRF/auth.

## Inputs

User identity từ SL-03, order records và snapshot từ SL-04, review form inputs từ khách hàng.

## Outputs

Trang lịch sử đơn hàng `/orders`, chi tiết đơn `/orders/<id>`, API minimized `/api/orders/<id>`, tệp hóa đơn text/plain kèm disclaimer lab, khối đánh giá khách hàng trên trang chi tiết sản phẩm `/products/<id>`.

## Interfaces

- `GET /orders`: Danh sách đơn hàng thuộc sở hữu của session/user hiện tại.
- `GET /orders/<id>`: Chi tiết snapshot đơn hàng; 404 nếu không sở hữu.
- `GET /api/orders/<id>`: Dữ liệu JSON rút gọn; chỉ chứa thông tin cần thiết, không expose session_id/token/password.
- `GET /download/invoice?file=INV-...txt`: Tải hóa đơn; kiểm tra quyền sở hữu; fallback tạo từ DB nếu file đĩa không còn; reject path traversal với 400.
- `POST /reviews`: Gửi đánh giá sản phẩm (product_id, rating, body, csrf_token); yêu cầu authenticated user.

## Data Contracts

- Order snapshot: `id`, `total`, `currency` (USD), `status`, `invoice_file`, `created_at`, danh sách items (`name`, `quantity`, `unit_price`, `currency`).
- Invoice text: Header invoice, `Notice: ShopLab — Lab / Simulated Order Receipt (No payment charged)`, danh sách mặt hàng và tổng tiền.
- Review data: `product_id`, `user_id`, `username`, `rating` (integer 1..5), `body` (plain text <= 4000 ký tự), `created_at`.
- Data minimization: `/api/orders/<id>` cấm chứa session_id, cart_key, csrf_secret, password_hash, email của user khác.

## Dependencies

SL-03 (Auth/Session/CSRF), SL-04 (Cart/Checkout/Idempotency); liên kết TASK-011.

## Implementation Requirements

1. Server-side ownership enforcement: `owns_order(identity, order)` xác thực quyền sở hữu cho cả HTML view, API view và invoice download. Người dùng khác truy cập nhận 404 (không lộ ID enumeration).
2. Data minimization: endpoint `/api/orders/<id>` loại bỏ toàn bộ trường nhạy cảm nội bộ trước khi trả về client.
3. Invoice lab notice: nội dung hóa đơn bắt buộc chứa dòng `Notice: ShopLab — Lab / Simulated Order Receipt (No payment charged)`.
4. Invoice on-demand synthesis fallback: nếu tệp hóa đơn vật lý trên đĩa bị xóa hoặc không khả dụng, endpoint `/download/invoice` tự động tái tạo nội dung hóa đơn từ bảng `orders` và `order_items`.
5. Invoice security: regex validation `INV-[A-F0-9]{32}\.txt` và `_validate_path` từ chối triệt để path traversal, null bytes, CRLF injection với mã 400.
6. Product review validation: rating bắt buộc là số nguyên 1..5, body bắt buộc không rỗng và không quá 4000 ký tự; từ chối và rollback nếu vi phạm.
7. Stored XSS defense: toàn bộ nội dung review của người dùng được escape HTML ngữ cảnh an toàn bằng `html_escape()` trước khi render ra giao diện.
8. CSRF protection: POST `/reviews` yêu cầu token CSRF hợp lệ.

## Safety Requirements

Lab-only isolation. Không PII, không thông tin thanh toán thật. IDOR check bắt buộc ở server-side. Path traversal check nghiêm ngặt. Escaping an toàn chống XSS.

## Testing Requirements

| Case | Scenario | Expected |
|---|---|---|
| O01 | User authenticated xem đơn hàng của mình | Đúng thông tin snapshot, tổng tiền, items |
| O02 | User B / Anonymous truy cập đơn của User A (IDOR) | Trả về 404 Not Found an toàn |
| O03 | Data minimization trên `/api/orders/<id>` | Không rò rỉ session token, credentials, internal secrets |
| O04 | Snapshot đơn bất biến khi giá catalog đổi | Đơn hàng và hóa đơn giữ nguyên giá snapshot cũ |
| O05 | Tải hóa đơn khi tệp trên đĩa tồn tại và khi bị xóa | Trả về 200 OK với lab notice; fallback tái tạo từ DB |
| O06 | Path traversal / CRLF injection trên invoice download | Trả về 400 Bad Request; không đọc file tùy ý |
| O07 | Gửi đánh giá hợp lệ (rating 1-5, body) | Lưu trữ thành công, render an toàn kèm sao |
| O08 | Gửi đánh giá có rating không hợp lệ / body rỗng / quá dài | Trả về 400 Bad Request, DB không thay đổi |
| O09 | Payload stored XSS trong review (`<script>`, `onerror`) | Render an toàn sau khi escape, không thực thi script |
| O10 | Gửi review không có CSRF token hoặc token sai | Trả về 403 Forbidden |

## Acceptance Criteria

Tất cả các tiêu chí về IDOR protection, API data minimization, invoice lab notice & fallback, review validation & stored XSS escaping được xác minh bằng kiểm thử tự động. Bộ test `tests/integration/test_ecommerce_orders_reviews.py` (16 tests) đạt 100% PASS, exit code 0.

## Evidence Required

Command receipts thực tế:
- `python -B -m unittest discover -s tests/integration -p "test_ecommerce_orders_reviews.py"`: 16 tests PASS, exit 0.
- `python -B -m unittest discover -s tests/integration -p "test_ecommerce_*.py"`: 81+ tests PASS, exit 0.
- `python -B scripts/validation/validate_scaffold.py`: SCAFFOLD VALID, exit 0.
Không ghi token, password hoặc dữ liệu cá nhân trong receipts.

## Failure Conditions

Rò rỉ dữ liệu cross-tenant (IDOR), lộ token hoặc mật khẩu qua order API, path traversal đọc file máy chủ, stored XSS payload không được escape, hoặc hóa đơn thiếu lab notice.

## Related Guides

[Web security](../guides/04-web-security-testing.md), [Safety](../guides/17-cyber-range-safety.md).

## Related Runbooks

[Collect evidence](../runbooks/collect-evidence.md), [Restore range](../runbooks/restore-range.md).

## Related ADRs

[ADR-013](../adr/ADR-013-runtime-vertical-slice.md), [Ground-truth isolation](../adr/ADR-009-ground-truth-isolation.md).
