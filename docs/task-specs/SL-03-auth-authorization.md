# SL-03 — Xác thực, session, CSRF và phân quyền

## Status

`IMPLEMENTED` trong phạm vi offline fixture/mock và SQLite temp. Build `BUILD-SL03-AUTH-001`, plan `PLAN-SL03-AUTH-001`, revision R1 có 114 tests PASS, AST ba file/scaffold checker PASS và deterministic gate PASS. Người triển khai đã tự review theo yêu cầu người dùng, sửa validation ID 64-bit và query parsing, rồi chạy lại checks. Chưa có independent review `FINAL / APPROVE` được xác minh nên không nâng `VALIDATED` hoặc coi acceptance lifecycle đã hoàn tất. Receipts và giới hạn tại [TASKS.md](../../TASKS.md#sl-03--kết-quả-offline-r1).

## Purpose

Thay client-controlled username/role bằng identity phía server, bảo vệ mọi thao tác mutation và chuẩn hóa ownership cho cart/orders/invoices/admin.

## Background

Prototype lấy session từ username và tin role/username cookies. UI ẩn liên kết không phải authorization. Các chức năng cần identity đáng tin trước khi kiểm thử checkout và đa người dùng.

## Scope

Đề xuất `cyber-range/targets/ecommerce/**`, focused auth/authorization tests trong `tests/integration/**`. Tái dùng gateway cookie support qua tests; không edit gateway trừ allowlist riêng. Middleware/helpers tập trung cho authenticated user, role, resource ownership và CSRF.

## Out of Scope

Không OAuth/social/email thật, production credentials, seeded admin password, brute-force/pentest payload, public deployment hoặc tự cấp quyền cho user đầu tiên. Không sửa safety policy để thay product authorization.

## Inputs

SL-01/SL-02 receipts, user/session schema, routes/forms và current gateway behavior. Giả định local lab HTTP; Secure cookie chỉ khi có verified HTTPS, không đặt flag làm login hỏng trên HTTP rồi bỏ tests.

## Outputs

Password hashing/verification, session lifecycle, CSRF helpers, protected routes, local admin-promotion boundary, negative/authenticated tests và documentation handoff cho SL-04–06.

## Interfaces

Product identity từ opaque session lookup; helpers trả user ID/role server-side hoặc anonymous. Gateway giữ Set-Cookie/Cookie và CSRF header. Local administrative workflow chỉ promote một account đã tạo hợp lệ, không network-exposed bootstrap hoặc mặc định admin đầu tiên; SL-06 triển khai UX/workflow cụ thể.

## Data Contracts

Password hash gồm algorithm/version/salt/work factor; không plain text hoặc raw SHA-256. Session lưu token digest, user/cart association, issued/expiry UTC và CSRF secret; browser cookie opaque, HttpOnly, SameSite, Path scoped. Không đưa token/CSRF/password vào logs/planner/evidence. Username/email/password length/type validation, duplicate identity behavior rõ ràng.

## Dependencies

SL-01, SL-02; liên kết TASK-003/TASK-011. SL-05/SL-06 triển khai resource-specific ownership trên helper này.

## Implementation Requirements

1. Validate registration/login input ở server; store salted slow password hash, constant-time verification where applicable, generic login failure và bounded throttling.
2. Opaque unpredictable session, expiry, rotate khi login/privilege change; logout POST + CSRF invalidate phía server. GET logout không mutate.
3. CSRF token ràng buộc session cho mọi POST/mutation gồm login/register/admin; anonymous session và rotation không mất cart hoặc cho session fixation. Origin checks là defense bổ sung, không thay token.
4. Ignore role/username cookies để xác định quyền. Session không hợp lệ fail anonymous/deny, không tự chuyển thành username lookup.
5. Ownership helpers deny by default cho resource không thuộc current user; không lộ owner/session/PII qua error response. Admin rights đọc từ DB và kiểm tra mỗi mutation.
6. Giữ guest cart tách biệt; login migration chỉ từ validated current guest session, merge theo limits, rotate token, không nhập cart của identity client chỉ định.
7. Local admin promotion/revocation cần quyền quản trị máy lab và quiescent/transaction-safe storage, audit đã redact; không password cố định hoặc auto-admin registration.

## Safety Requirements

Credential handling chỉ bên product, không planner proposal fields hoặc test evidence. Tests tạo fixtures runtime, không hardcoded deployable accounts. Unauthorized/CSRF failure phải trước write. Không trace token trong exception.

## Testing Requirements

| Case | Scenario | Expected |
|---|---|---|
| A01 | Register/login/logout và duplicate account | Identity đúng; generic invalid login; logout invalidates |
| A02 | Client thay role/username cookie | Không đổi quyền, không xem admin/resources người khác |
| A03 | Missing/foreign/expired session | Deny; không user lookup từ raw cookie |
| A04 | Missing/wrong/cross-session CSRF | Reject trước mutation; đúng token cho phép |
| A05 | Login session rotation, old token replay | Old token invalid; cart migration đúng owner |
| A06 | User A/B với cart/orders/admin | Cô lập; user thường deny admin |
| A07 | Password storage, throttle và limits | Không raw password; salted hashes khác nhau; bounded failures |
| A08 | Cookies đi qua gateway | Login/logout/CSRF flow hoạt động; không tokens trong receipts |

## Acceptance Criteria

Không authorization nào tin client role/username; session rotation/expiry/logout/CSRF/ownership fixtures pass; mutations denied không ghi DB; cookie flow verified. Admin bootstrap không tạo fixed credential và không expose network. Threat-sensitive diff cần independent review; code creation không auto validation.

## Evidence Required

Exact test receipts, role/ownership matrix và redaction proof; audit promote/revoke nếu workflow chạy được duyệt. Không đính token/password/hash có thể tái dùng vào report. Expected/observed tách biệt.

## Failure Conditions

Session fixation/cross-user leak/CSRF bypass/first-user auto-admin, fixture credentials trong deploy image, logs lộ secrets hoặc chưa chốt lifecycle strategy: dừng và báo blocker; không claim auth complete.

## Related Guides

[Web security testing](../guides/04-web-security-testing.md), [Safety](../guides/17-cyber-range-safety.md).

## Related Runbooks

[Collect evidence](../runbooks/collect-evidence.md), [Restore range](../runbooks/restore-range.md).

## Related ADRs

[ADR-013](../adr/ADR-013-runtime-vertical-slice.md), [Safety engine control](../adr/ADR-012-safety-engine-control.md).
