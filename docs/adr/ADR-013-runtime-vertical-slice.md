# Runtime vertical slice

## Status

`IMPLEMENTED` documentation decision, được cập nhật theo kế hoạch `PLAN-SHOPLAB-PTES-001` và yêu cầu cập nhật tài liệu/task. Không tự approve ADR hoặc nâng runtime thành `VALIDATED`. SL-01 baseline và SL-02 storage có checks/gate/review độc lập được xác minh trong phạm vi offline fixture/mock và SQLite temp; không có product E2E/Docker/provider/PTES evidence mới. Trạng thái và exact receipts tại [TASKS.md](../../TASKS.md#checks-and-observed-implementation-state).

## Context

Foundation và clean-control/target slice hiện có không đủ đáp ứng mục tiêu sản phẩm web hoàn chỉnh và AI đánh giá qua bảy giai đoạn PTES dựa trên khám phá. Prototype ShopLab và orchestrators có code, nhưng nghiệp vụ, safety integration và runtime observations chưa chứng minh goal hoàn thành.

TASKS.md ghi validation lịch sử TASK-011–014 qua RUNTIME-004 cho slice cũ. Manifest RUNTIME-004 ghi `IMPLEMENTED`; review linkage cần đối chiếu trước tái sử dụng claim. Không tự thay trạng thái lịch sử, overwrite evidence hoặc áp dụng evidence cũ cho code gateway/ShopLab vừa sửa.

## Decision

Giữ slice stdlib hiện có và hoàn thiện ShopLab theo thứ tự product-first tại [PROJECT_PLAN.md](../../PROJECT_PLAN.md); backlog `SL-*` tại [TASKS.md](../../TASKS.md). Mở hướng triển khai sản phẩm và bounded assessment theo kế hoạch đã duyệt, không mở unbounded runtime:

- Clean-control in-process boundary hiện hành không tự đổi để chạy ShopLab. Target registration/manifest và executor compatibility cần duyệt/check trước executable run.
- ShopLab nghiệp vụ: persistent SQLite, server-side session/authorization/CSRF, catalog/cart, atomic checkout/stock/idempotency, owned orders/invoices/reviews, protected admin và approved restore. Dữ liệu giả, offline simulated payment/email; không hardcoded credentials.
- Docker targets chỉ trên internal lab network; gateway ingress loopback. Gateway chỉ upstream cố định allowlisted, không follow external redirect/outbound proxy; giữ cookie/status/header cần cho nghiệp vụ và bounded body. Cần isolation receipts, không suy ra từ compose.
- `DRY_RUN=true` giữ default. Runtime chỉ typed allowlisted actions; không shell/command/payload/credential/dynamic-action proposal fields. Không repurpose action ID với semantics khác để qua validator.
- Planner proposals từ observed state vẫn là data tới khi safety policy và approval chấp thuận. Mỗi request, redirect, supplemental request đều gate: identity/target/action/order/rate/budgets/kill switch. Missing approval hoặc malformed input fail closed trước dispatch.
- Discovery từ seed và bề mặt thực sự quan sát, không preset vulnerability locations. Không tự submit side-effect forms. Giữ ground truth/source/secrets/tokens ngoài planner input; explicit rule/LLM/hybrid provenance và fallback.
- Bảy giai đoạn PTES có artifact/exit criterion riêng theo PROJECT_PLAN. Safe verification chỉ trong quyền hiện hành. Active exploitation, new payloads, credential theft, host file reads, persistence và lateral movement không được cấp quyền bởi ADR này. Blocked/not-run/unresolved phases không gọi là completed.
- Evidence mới append-only với UTC/run/source/hash/redaction, expected/observed tách biệt, unique provenance/replay và exclusive creation. Evidence-write failure dừng; restore không xóa evidence.

ADR-003 family restriction vẫn hiệu lực; không thêm auth-bypass/IDOR như family nghiên cứu mới chỉ vì hoàn thiện authorization sản phẩm. Các target khác, action catalog/contracts, scenarios và evidence cũ không thuộc implementation scope nếu chưa có phê duyệt riêng. TASK-026 và TASK-032 giữ `DEFERRED`.

## Alternatives Considered

Không chọn:
- Demo ba lỗi kèm công cụ biết trước đáp án, hoặc chỉ bọc pipeline cũ bằng bảy phase names.
- Thêm lỗi cố ý, arbitrary command execution, public targets, production credentials/data hoặc mở active exploitation không có quyền.
- Bỏ qua product correctness để chạy AI trên session/cart/checkout chưa hoàn thiện.
- Nới safety defaults, tự thêm dynamic actions hoặc dùng default endpoint fallback để hợp thức hóa prototype.
- Dùng mock/rule run, config check hoặc artifact creation làm bằng chứng Docker/LLM/full PTES success.

## Consequences

Cần bổ sung work packages ShopLab/PTES mà không thay 35 canonical task IDs. Product tests và gateway E2E precede assessment. HTTP reset đang bị từ chối để bảo toàn dữ liệu; restore được duyệt vẫn là hạng mục chưa triển khai hoàn chỉnh, không giả health/reset compatibility.

Tệp SQLite giữ dữ liệu qua process restart cùng data directory, không tự chứng minh persistence qua container replacement. Storage lifecycle/connection-locking/transactions và durable Docker storage cần checks/evidence riêng.

Không đưa build sang Review nếu deterministic pre-review gate chưa đạt: matching contract IDs/base head, allowed/forbidden paths, required receipts, no placeholders/blockers và repository checker khi có. Handoff blocked không dùng repair budget. Không self-approve, finalize, append history hoặc commit.

## Risks

- SL-02 đã xử lý shared SQLite connection hazard bằng connection-per-service và explicit transactions; lifecycle/concurrency/schema preservation/process-restart checks, gate và review R1 đã PASS. Checkout/reset nghiệp vụ, restore/session invalidation và runtime concurrency vẫn cần checks riêng trước runtime claim.
- Client-controlled identity, ownership/CSRF thiếu và prototype stored rendering/file access còn cần sửa; code mới không có chứng nhận an toàn ngoài lab.
- Gateway Cookie/Set-Cookie/redirect/header/path/bounds có fixture/mock tests PASS trong SL-01 và regression SL-02 R1; các tests này không chứng minh actual gateway product E2E hoặc network egress/isolation, vẫn cần approved SL-07 runtime checks.
- Target registration/manifest/config-validator assumptions có thể xung đột; cần scope riêng nếu phải sửa contract/catalog hoặc policy semantics.
- Classifier, Docker/provider availability có thể chặn checks. Ghi actual receipt/blocker, không bypass công cụ hoặc retry vô hạn.
- Evidence loss, ground-truth leakage, silent fallback và unsupported severity/impact claims làm sai kết quả nghiên cứu. Dừng khi xung đột nguồn hoặc evidence-write failure.

## Revisit Conditions

Chỉ mở rộng executable scope sau approved source/contract/safety review, image/version provenance, target registry/manifest checks, isolation và product E2E/restore receipts, append-only evidence verification và independent review. Mở active exploitation hoặc research families khác cần quyết định riêng, không suy ra từ mục tiêu bảy giai đoạn.

Validation ShopLab cần đủ product criteria tại PROJECT_PLAN; validation AI/PTES cần actual planner-mode/provider provenance và phase-specific evidence. Tài liệu này không authorizes runtime, không xác nhận goal đã hoàn thành và không thay measured observations.
