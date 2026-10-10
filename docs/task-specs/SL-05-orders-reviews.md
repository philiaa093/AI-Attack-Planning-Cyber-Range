# SL-05 — Đơn hàng, hóa đơn và đánh giá

## Status

`SPEC_ONLY`. Chuyển sang upstream orders/reviews fit-gap và acceptance; chưa có execution receipts Oscar. SL-03 đã sửa ownership/escaping cơ bản trong ShopLab nhưng chưa có independent approval, không phải validation target mới. Invoice chưa xác minh có trong Oscar core.

## Purpose

Người dùng truy cập lịch sử/chi tiết đơn, hóa đơn và đánh giá của luồng mua hàng đúng quyền; dữ liệu đơn cũ bất biến với catalog edits.

## Background

ShopLab lịch sử có owner/file/rendering gaps; SL-03 đã triển khai owner gates và escaping cơ bản với offline receipts, chưa independent approval hoặc full SL-05 acceptance. Hướng mới tái sử dụng Oscar orders/reviews, không kế thừa validation ShopLab; invoice capability vẫn chưa xác minh.

## Scope

Đề xuất `cyber-range/targets/oscar-lab/**` và `tests/integration/test_oscar_lab*.py`: cấu hình/kiểm chứng orders/reviews/communication upstream, không viết lại business services hoặc sửa ShopLab. Invoice/API thiếu phải ghi fit-gap; không tự thêm invoice extension hoặc file-download route. Dependency equivalence với SL-03/SL-04 cần review, không kế thừa receipts ShopLab.

## Out of Scope

Không file arbitrary download, upload arbitrary content, invoice/receipt giả như genuine payment record, email/payment thật, host files/secret reading hoặc new exploit payload. Không dùng review content làm planner instruction.

## Inputs

SL-03 identity/ownership/CSRF, SL-04 order snapshot/schema và completed checkout receipts; fake product/users/order fixtures.

## Outputs

Orders list/detail/API và invoice representation, bounded escaped review flows, ownership tests, reproducible redacted receipts. Mọi invoice ghi rõ là đơn lab mô phỏng, không payment proof.

## Interfaces

Dùng upstream customer/order/review interfaces đã pin, không ép routes ShopLab. Ownership và projection phải kiểm chứng trên HTML và mọi API/download thực sự được bật. Invoice requirements bên dưới chỉ áp dụng nếu capability được duyệt và có thật; nếu thiếu thì ghi gap, không claim SL-05 hoàn tất hoặc tự mở scope extension. Không chuyển route map/source/PII vào planner.

## Data Contracts

Order responses chỉ fields cần cho current user; không session IDs/other-user contact. Snapshot item label/quantity/unit_price_minor/total/currency và lab notice. Reviews: current server user, existing product ID, rating integer 1–5, body plain text bounded và timestamp UTC; API không serialize user/token internals.

## Dependencies

SL-03, SL-04; liên kết TASK-011. SL-06 quản trị status với transition policy riêng.

## Implementation Requirements

Ưu tiên upstream functionality và cấu hình tối thiểu; các invariants bên dưới không được tự hạ để khớp candidate. Review rating/rules/snapshot fields khác ShopLab phải được map explicit; không giả định rating 1–5 hoặc invoice feature chỉ từ prototype. Thiếu capability hoặc môi trường execution là gap/blocker, không yêu cầu tự xây lại ứng dụng. Email backend không gửi mạng hoặc ghi token/link xác thực; labels không claim giao dịch thật.

1. Owned orders list/detail/API; validate IDs; consistent 403/404 policy không lộ owner enumeration. Admin access chỉ khi expressly permitted role helper.
2. Invoice được derive từ committed snapshot, không current price; require owner/admin trước generation/serve. Bounded content, safe download headers/filename không CRLF.
3. Nếu invoice cần stored files: generated basename do server, root containment, symlink/permissions policy; creation failure/retry không phá committed order. Không đọc path từ user hoặc file ngoài app-owned store.
4. Review form POST + CSRF + authenticated identity; validate product/rating/body; escaping ở rendering HTML và attribute/title. Lưu raw plain text là data; render text không execute.
5. Xác định review eligibility từ confirmed ownership/purchase nếu yêu cầu verified-purchase badge; không gắn badge mặc định. Duplicate review/update policy explicit.
6. Views có empty/missing/error states, order detail/shipping/status, lab-only invoice/payment notice; không mô tả gửi email nếu chưa gửi.
7. Không đưa review/user content vào logs hoặc LLM raw nếu chưa redact; treats content as untrusted data.

## Safety Requirements

Resource ownership checked cho cả HTML/API/download. Encoding/escaping phải theo context, không chỉ ở một view. Fixtures không real PII hoặc active scripts. Không arbitrary file-read verification để test path policy.

## Testing Requirements

| Case | Scenario | Expected |
|---|---|---|
| O01 | User A own list/detail/API/invoice | Đúng fields và snapshot; không token/session leak |
| O02 | User B/anonymous truy cập đơn/hóa đơn A | Deny consistent; không file read hoặc data leak |
| O03 | Invalid/missing invoice/order mapping | Safe error, không arbitrary path access |
| O04 | Giá/tên catalog thay đổi | Old invoice/order snapshot giữ nguyên |
| O05 | Review plain text có ký tự markup thông thường | HTML escaped; không active content trong fixture |
| O06 | Invalid rating/product/body/CSRF/identity | Reject trước writes |
| O07 | Restart và invoice generation lỗi | Persisted orders/reviews giữ; safe bounded retry/error |
| O08 | HTML/API fields và lab notice | Không email/payment claim giả hoặc internal IDs nhạy cảm |

## Acceptance Criteria

HTML/API/invoice đều ownership-protected; invoices reflect committed snapshots và explicit lab notice; reviews plain-text bounded/context-escaped; negative operations không đổi DB/read arbitrary files. Tests pass với hai sessions; gaps/rules verified-purchase được handoff rõ, không auto-VALIDATED.

## Evidence Required

Exact suite receipts, ownership matrix, redacted output comparisons và snapshot invariants; không genuine-looking fabricated records/PII. Evidence UTC/run/source/hash, không overwrite.

## Failure Conditions

Cross-user response, arbitrary filename access, active rendering, status/payment claim vượt evidence, invoice snapshot mismatch hoặc tests chưa chạy: blocker, không claim complete.

## Related Guides

[Web security](../guides/04-web-security-testing.md), [Safety](../guides/17-cyber-range-safety.md).

## Related Runbooks

[Collect evidence](../runbooks/collect-evidence.md), [Restore range](../runbooks/restore-range.md).

## Related ADRs

[ADR-013](../adr/ADR-013-runtime-vertical-slice.md), [Ground-truth isolation](../adr/ADR-009-ground-truth-isolation.md).
