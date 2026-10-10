# SL-06 — Quản trị sản phẩm và hoàn thiện UI

## Status

`SPEC_ONLY`. Chuyển sang upstream dashboard permission/configuration/UI acceptance; chưa có execution receipts Oscar. Không tiếp tục tự xây admin ShopLab hoặc coi upstream dashboard là đã được kiểm chứng.

## Purpose

Quản trị được catalog/tồn kho/trạng thái đơn đúng quyền và có UI sản phẩm sử dụng được trên desktop/mobile, không chỉ các endpoints demo.

## Background

SL-03–05 cung cấp identity, cart/checkout và order/review. Admin phải dùng server-side roles, không cookie. UI sản phẩm không phải dashboard nghiên cứu TASK-032.

## Scope

Đề xuất `cyber-range/targets/oscar-lab/**` và `tests/integration/test_oscar_lab*.py`: cấu hình/kiểm chứng upstream dashboard, permissions, local administrative workflow và assets/UI. Không viết lại catalog/admin/order services hoặc sửa ShopLab. Sandbox Django `/admin/` chỉ developer convenience và upstream ghi unsupported; không bật mặc định thay dashboard được kiểm chứng.

## Out of Scope

Không public admin, fixed admin credential, first-registration auto-admin, external CDN/payment/email, dashboard/analytics TASK-032, quản trị target OS hoặc free-form commands.

## Inputs

SL-03 auth/CSRF/role helpers, SL-04 money/stock transactions, SL-05 order snapshots/status; approved local administrative authority và fake fixtures.

## Outputs

Upstream dashboard permission/operation fit-gap matrix, lab configuration tối thiểu và role/CSRF/stock/status/UI acceptance receipts. Local role workflow cần authority riêng; không viết services mới hoặc claim screenshots/browser pass nếu chưa chạy tooling. Không deployed claim.

## Interfaces

Dùng upstream dashboard URL/permission model, không map `/admin` ShopLab. Mutations cần server authorization và CSRF được kiểm chứng. Local administrative provisioning cần scope/authority riêng, không HTTP bootstrap, không default admin/first-user privilege, không upstream auth fixtures hoặc password command-line. Tái sử dụng template/form escaping upstream; kiểm chứng mỗi context thay vì giả định an toàn.

## Data Contracts

Product fields bounded: name/description/category existing ID, integer price_minor/currency và nonnegative stock. Stock updates không làm mất invariants với checkout. Order state transition map chốt trước edit; accepted → processing → shipped → completed là ví dụ proposal, không value catalog đã duyệt. Không arbitrary status text hoặc cho sửa totals/items đã commit. Admin audit redact actor/action/resource/UTC/old/new state, không secret.

## Dependencies

SL-03, SL-04, SL-05; TASK-003/TASK-011. Local bootstrap quyền riêng không tự cấp bởi task-spec.

## Implementation Requirements

Đây là fit-gap/configuration/acceptance trên upstream, không chỉ thị viết lại admin. Map Decimal/stock allocation/permission/status semantics tới invariants dưới đây; thiếu equivalence thì giữ gap và không tự hạ acceptance. Override CDN jQuery bằng bundled local asset, tắt analytics và integrations ngoài lab; secret thiếu fail closed, DEBUG=False. Static source scan không chứng minh browser/network isolation; visual và egress cần receipts riêng.

1. Check role từ server mỗi admin GET/mutation; revoke/expired session có effect, không cached role cookie.
2. Catalog create/update/archive, category selection, price/stock validation; referenced products không delete gây lỗi order snapshot. Archived item không mua mới, đơn cũ vẫn đọc được.
3. Stock change trong transaction cùng checkout semantics; stale version/conflict behavior rõ, không lost update khi hai admin/checkout đồng thời.
4. Order-status transitions bounded và audit; reject invalid state, duplicate transition idempotent; cancellation/refund không implement inventory/payment reversal âm thầm. Nếu chưa có reversal policy thì không expose operation.
5. Local role promotion/revocation deny unknown identities và không tự đăng ký credential. Authority/confirmation và session invalidation rõ; no web bootstrap endpoint.
6. UI navigation/cart badges/order detail/forms/error/empty states, labels, keyboard/focus và mobile gutters/no page overflow. Product prices/stock/status phản ánh server data, không KPI giả.
7. Lab notice xuyên suốt và offline assets. Content escaped; forms CSRF; render lỗi không expose DB/paths.

## Safety Requirements

Không tài khoản mặc định. Admin workflow không arbitrary command runner, không reset/evidence deletion. Không public artifact imitation hoặc genuine payment records; screenshots lab-only redact identities.

## Testing Requirements

| Case | Scenario | Expected |
|---|---|---|
| M01 | Anonymous/user thường truy cập admin mutations | Deny trước DB write |
| M02 | Admin với đúng/sai/missing CSRF | Valid write hoặc reject; no cookie-role trust |
| M03 | Invalid price/stock/category/text limits | Safe validation; no partial changes |
| M04 | Archive product referenced bởi order | New purchase deny; old snapshot còn |
| M05 | Concurrent stock edits/checkout | Conflict/serialization đúng, no oversell/lost update |
| M06 | Valid/invalid/repeated order-status transition | Map được enforced; audit đúng; không totals rewrite |
| M07 | Local promote/revoke existing/unknown account | Correct identity, no fixed credential; revoke effect |
| M08 | Mobile/desktop, keyboard và empty/error views | No horizontal page scroll; usable forms/lab notice |

Nếu chưa có browser tooling, M08 ghi unverified và dùng render/HTML assertions phần có thể test; không bịa screenshots hoặc visual pass.

## Acceptance Criteria

Admin làm được các operations đã chốt, negative authorization/CSRF tests pass; stock/order invariants giữ; role workflow không credentials mặc định; product flow UI hoàn chỉnh và evidence-linked accessibility/browser checks. TASK-032 vẫn DEFERRED, không claim production-ready.

## Evidence Required

Exact commands/results, role matrix, state transition map, redacted audit/UI receipts; screenshots chỉ observed với tooling thật. Handoff SL-07 routes/forms/role setup và gaps rõ.

## Failure Conditions

Unprotected bootstrap/mutation, hardcoded credentials, invalid stock/state writes, UI report giả hoặc browser checks thiếu mà claim pass: blocker; dừng khi conflict source/permissions.

## Related Guides

[Web security](../guides/04-web-security-testing.md), [Cyber Range](../guides/03-cyber-range-fundamentals.md).

## Related Runbooks

[Collect evidence](../runbooks/collect-evidence.md), [Restore range](../runbooks/restore-range.md).

## Related ADRs

[ADR-013](../adr/ADR-013-runtime-vertical-slice.md), [Safety engine control](../adr/ADR-012-safety-engine-control.md).
