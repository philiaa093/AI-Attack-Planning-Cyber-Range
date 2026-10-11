# SL-06 — Quản trị sản phẩm và hoàn thiện UI

## Status

`IMPLEMENTED`. Đã hoàn thành trên target ShopLab (`cyber-range/targets/ecommerce/app.py`) và kiểm chứng tự động bằng bộ test tích hợp `tests/integration/test_ecommerce_admin.py` (14 tests PASS). Chưa có independent review / approval; không tự nâng `VALIDATED`.

## Purpose

Cung cấp bảng điều khiển quản trị (Admin Backoffice) để quản lý danh mục sản phẩm, điều chỉnh tồn kho, kiểm soát quy trình chuyển đổi trạng thái đơn hàng (order status lifecycle), chính sách hủy đơn, và ghi nhật ký kiểm toán (audit log) có phân quyền server-side nghiêm ngặt.

## Background

Sau SL-03, SL-04 và SL-05, hệ thống đã có xác thực người dùng, giỏ hàng, checkout và lịch sử đơn hàng. SL-06 hoàn thiện giao diện và API quản trị backoffice, yêu cầu quyền `admin` được xác thực server-side, bảo đảm máy trạng thái đơn hàng forward-only, chính sách hủy đơn minh bạch, lưu trữ sản phẩm (product archival) an toàn và ghi log hoạt động quản trị.

## Scope

- Code ứng dụng: `cyber-range/targets/ecommerce/app.py`
- Test suite tích hợp: `tests/integration/test_ecommerce_admin.py`
- Endpoints: `/admin`, `/admin/orders/<id>`, `/admin/orders/status`, `/admin/orders/cancel`, `/admin/products/stock`, `/admin/products/archive`, `/admin/products/create`

## Out of Scope

Không bypass phân quyền, không tài khoản admin mặc định cố định trong code, không quản trị hệ điều hành máy chủ, không xóa vật lý các đơn hàng hay sản phẩm đã có giao dịch.

## Inputs

Identity có role `admin` từ bảng `users`, form POST data cho trạng thái đơn, tồn kho, tạo/lưu trữ sản phẩm, CSRF token.

## Outputs

Giao diện quản trị `/admin`, trang chi tiết quản trị đơn `/admin/orders/<id>`, cập nhật trạng thái đơn hàng, bảng `product_archives`, bảng `admin_activity_log`.

## Interfaces

- `GET /admin`: Dashboard tổng quan sản phẩm, đơn hàng, người dùng và 30 hoạt động audit log gần nhất. Yêu cầu role `admin`.
- `GET /admin/orders/<id>`: Chi tiết quản trị đơn hàng với form chuyển trạng thái và nút hủy đơn nếu đủ điều kiện.
- `POST /admin/orders/status`: Chuyển trạng thái đơn hàng theo máy trạng thái forward-only (order_id, status, csrf_token).
- `POST /admin/orders/cancel`: Hủy đơn hàng (order_id, csrf_token); chỉ áp dụng cho đơn `pending`.
- `POST /admin/products/stock`: Cập nhật tồn kho sản phẩm (product_id, stock, csrf_token).
- `POST /admin/products/archive`: Lưu trữ sản phẩm (product_id, csrf_token).
- `POST /admin/products/create`: Tạo sản phẩm mới (name, description, category_id, price, stock, csrf_token).

## Data Contracts

- Phân quyền: Cột `users.role = 'admin'` trong SQLite; không chấp nhận cookie role tự xưng từ client.
- Order transitions:
  - `pending` -> `processing`, `shipped`, `cancelled`
  - `processing` -> `shipped`
  - `completed` -> `shipped`
  - `shipped` -> `delivered`
  - `delivered` -> terminal (không cho phép chuyển tiếp)
  - `cancelled` -> terminal
- Cancellation policy: Chỉ cho phép hủy khi đơn ở trạng thái `pending`. Đơn đã ở `processing`, `shipped`, `delivered` bị từ chối với 400.
- Product archival: Bảng `product_archives (product_id INTEGER PRIMARY KEY, archived_at TIMESTAMP)`.
- Audit log: Bảng `admin_activity_log (id, user_id, action, target_type, target_id, old_value, new_value, created_at)`.

## Dependencies

SL-03 (Auth/Roles), SL-04 (Checkout/Stock), SL-05 (Orders/Snapshots); liên kết TASK-003 và TASK-011.

## Implementation Requirements

1. Server-side role verification: `self._require_admin()` kiểm tra identity trong DB; từ chối người dùng thường và khách với `403 Forbidden`. Bỏ qua hoàn toàn cookie `role` từ client.
2. Máy trạng thái đơn hàng nghiêm ngặt (Forward-only state machine): chỉ cho phép các bước chuyển trạng thái có nghĩa nghiệp vụ theo map `ORDER_TRANSITIONS`. Từ chối chuyển ngược (ví dụ: `completed -> processing` hay `delivered -> processing`).
3. Chính sách hủy đơn rõ ràng: chỉ đơn `pending` mới có thể hủy. Đơn đã vào khâu xử lý hoặc giao hàng không thể hủy trực tiếp qua endpoint cancel.
4. Product soft-archival: sản phẩm bị archive không bị xóa khỏi DB để bảo toàn snapshot của các đơn hàng cũ; sản phẩm archived bị ẩn khỏi form mua hàng và hiển thị huy hiệu Archived.
5. Cập nhật tồn kho an toàn: validate số lượng nguyên không âm; ghi nhận hoạt động thay đổi tồn kho vào audit log.
6. Audit logging đầy đủ: mọi hành vi thay đổi trạng thái đơn, hủy đơn, điều chỉnh tồn kho, lưu trữ hoặc tạo sản phẩm đều được ghi vào bảng `admin_activity_log`.
7. CSRF validation: kiểm tra CSRF token trên toàn bộ các mutation endpoints của admin.

## Safety Requirements

Lab-only isolation. Không cho phép privilege escalation từ regular user lên admin qua request headers/cookies. Không rò rỉ stack trace khi gặp lỗi tham số. CSRF enforcement tuyệt đối trên mọi POST.

## Testing Requirements

| Case | Scenario | Expected |
|---|---|---|
| M01 | Anonymous / Regular user truy cập `/admin` và POST actions | Trả về 403 Forbidden |
| M02 | Cookie giả mạo `role=admin` của regular user | Bị từ chối với 403 Forbidden (kiểm tra DB authoritative) |
| M03 | POST actions admin thiếu hoặc sai CSRF token | Trả về 403 Forbidden |
| M04 | Chuyển trạng thái đơn hợp lệ (`pending -> processing -> shipped -> delivered`) | Chuyển thành công, ghi audit log |
| M05 | Chuyển trạng thái đơn trái phép (`delivered -> processing`, `shipped -> pending`) | Trả về 400 Bad Request |
| M06 | Hủy đơn hàng ở trạng thái `pending` | Chuyển thành `cancelled`, ghi audit log |
| M07 | Hủy đơn hàng ở trạng thái `processing` hoặc `shipped` | Trả về 400 Bad Request, giữ nguyên trạng thái |
| M08 | Soft-archive sản phẩm | Lưu vào `product_archives`, cấm mua mới, đơn cũ giữ nguyên snapshot |
| M09 | Điều chỉnh tồn kho sản phẩm | Cập nhật chính xác, ghi log `stock_update` |
| M10 | Tạo sản phẩm mới với dữ liệu hợp lệ và không hợp lệ | Tạo thành công khi hợp lệ, 400 khi sai giá/tồn kho |

## Acceptance Criteria

Tất cả các tiêu chí về phân quyền admin, forward-only state machine, chính sách hủy đơn, product soft-archival và audit logging được xác minh bằng kiểm thử tự động. Bộ test `tests/integration/test_ecommerce_admin.py` (14 tests) đạt 100% PASS, exit code 0.

## Evidence Required

Command receipts thực tế:
- `python -B -m unittest discover -s tests/integration -p "test_ecommerce_admin.py"`: 14 tests PASS, exit 0.
- `python -B -m unittest discover -s tests/integration -p "test_ecommerce_*.py"`: 95 tests PASS, exit 0.
- `python -B scripts/validation/validate_scaffold.py`: SCAFFOLD VALID, exit 0.
Không ghi token, password hoặc dữ liệu cá nhân trong receipts.

## Failure Conditions

Regular user truy cập được trang admin, chuyển ngược trạng thái đơn hàng từ `delivered`/`completed` về `processing`, hủy đơn hàng khi đã vận chuyển mà không có chính sách hoàn tiền, hoặc ghi đè/xóa vĩnh viễn sản phẩm đã có đơn hàng.

## Related Guides

[Web security](../guides/04-web-security-testing.md), [Cyber Range](../guides/03-cyber-range-fundamentals.md).

## Related Runbooks

[Collect evidence](../runbooks/collect-evidence.md), [Restore range](../runbooks/restore-range.md).

## Related ADRs

[ADR-013](../adr/ADR-013-runtime-vertical-slice.md), [Safety engine control](../adr/ADR-012-safety-engine-control.md).
