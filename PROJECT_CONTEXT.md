# Project Context

## Purpose

Tái sử dụng ứng dụng thương mại điện tử open-source phù hợp làm target trong Web Cyber Range cô lập; dành công sức cho discovery, safety, observations, planner và evidence. Candidate hiện hành là Django Oscar sandbox 4.2.1 với lớp cấu hình lab mỏng, không viết lại auth/cart/order. Giữ ShopLab và kết quả SL-01–03 nguyên trạng; không chuyển validation cũ sang target mới. Không coi việc dựng ba lỗi rồi gọi ba công cụ tương ứng là hoàn thành mục tiêu.

Phạm vi family nghiên cứu MVP theo ADR-003 vẫn là SQL injection, cross-site scripting và path traversal. Giới hạn này không có nghĩa ứng dụng chỉ có ba endpoint hoặc planner được biết trước vị trí lỗi. Planner modes: `RULE`, `LLM`, `RL`, `HYBRID`; chưa mở rộng family hoặc quyền thực thi bằng tài liệu này.

## Architecture

Luồng sản phẩm cần kiểm chứng trên upstream: catalog/search → đăng ký/đăng nhập → giỏ hàng → checkout mô phỏng → đơn hàng → đánh giá; dashboard quản trị theo quyền phía server. Hóa đơn là fit-gap, không giả định Oscar core cung cấp tính năng này và không tự thêm extension. Thanh toán/email không kết nối dịch vụ thật; assets/search phải local. Database, session, media và search cần persistence/restore checks riêng; không ép Oscar dùng schema/routes SQLite của ShopLab.

Luồng assessment: scope và seed được duyệt → discovery observations → state → proposal schema-bound → safety policy và approval → bounded executor → observation → evidence bất biến → replan → report. Mọi request, redirect và request phụ đều cần target/action/rate/order/budget checks. Safety refusal xảy ra trước dispatch.

Planner chỉ nhận observations đã redact; không nhận source code target, vị trí lỗi, ground truth, session token hoặc bí mật. Ground truth chỉ thuộc evaluation. HTTP 200, reflection, error hoặc sự tồn tại của form không tự chứng minh vulnerability hay impact.

## Planner model

- `RULE`: baseline xác định, phải được báo cáo đúng mode.
- `LLM`: đề xuất schema-bound từ observations, không tự cấp quyền hoặc tạo action/command/payload mới.
- `RL`: học trong state/action space hữu hạn; không ưu tiên triển khai trước sản phẩm và safety pipeline.
- `HYBRID`: kết hợp candidates nhưng không bypass policy.

Lỗi provider, malformed output và fallback phải được ghi rõ. Một run chỉ dùng rule không được mô tả là LLM run thành công. Tái dùng StateManager cho state, request/time budget và replay; không thay đổi action ID hoặc contract semantics âm thầm.

## Current state

Nguồn trạng thái task là [TASKS.md](TASKS.md), không phải số lượng file đã tạo. Các trạng thái lịch sử được giữ nguyên trong lần cập nhật tài liệu này, không phải được review hoặc xác nhận lại:

- Foundation và perception: trạng thái `VALIDATED` được TASKS.md gắn với evidence hiện có.
- TASK-011–014: TASKS.md ghi `VALIDATED` cho local Docker slice qua RUNTIME-004, không bao gồm ShopLab, planner hoặc real external-tool execution. Manifest RUNTIME-004 có status `IMPLEMENTED`; liên kết review và phạm vi validation cần đối chiếu trước khi tái sử dụng claim. Không sửa evidence hoặc tự hạ/nâng trạng thái lịch sử.
- SL-01 baseline và SL-02 storage lifecycle đã được kiểm chứng trong phạm vi offline fixture/mock và SQLite temp. SL-02 dùng connection riêng theo service, explicit transactions, schema version 1 fail closed và bounded admission/drain; hai process restart giữ products/orders/order_items, không reseed accounts. Đây không phải sản phẩm hoàn chỉnh hoặc runtime được kiểm chứng.
- SL-02 R1: 90 tests PASS, AST 2 files/scaffold checker/gate PASS; review độc lập `FINAL / APPROVE` được verifier xác nhận exit 0 ngày 2026-10-10. F01 schema-prefix wildcard đã được tái hiện và sửa, regression giữ nguyên DB bytes khi reject. Exact commands, hashes và artifacts của `PLAN-SL02-STORAGE-001` / `BUILD-SL02-STORAGE-001` được ghi tại [TASKS.md](TASKS.md#checks-and-observed-implementation-state).
- Các attempts gateway/storage từng bị classifier chặn trước thực thi vẫn không có exit code/PASS; receipts SL-01/SL-02 là những lần chạy mới, không chuyển attempts cũ thành thành công. Chưa có Docker/LLM/PTES run chứng minh mục tiêu; actual restore/session invalidation, Docker durability và invoice filesystem/DB atomicity chưa được kiểm chứng.
- SL-03 auth/session/CSRF/ownership hiện `IMPLEMENTED`: revision R1 có 114 tests PASS, AST ba file/scaffold checker/gate PASS. Schema v2 cho DB mới; reject v1 trước writes, không tự migrate. Người triển khai đã tự review và sửa validation ID/query; chưa có independent review APPROVE được xác minh nên không nâng `VALIDATED`. Exact receipts và giới hạn tại [TASKS.md](TASKS.md#sl-03--kết-quả-offline-r1).
- Checkout atomic/stock/idempotency, quản trị nghiệp vụ và restore còn cần hoàn thiện. Orchestrator hiện có chưa đáp ứng yêu cầu discovery-driven, per-request gate và evidence-based phase completion.
- TASK-026 và TASK-032 giữ `DEFERRED`. Metrics, training và kết quả nghiên cứu không được suy ra từ prototype.

Hướng hiện hành theo lựa chọn người dùng và `PLAN-OSCAR-ADOPTION-001`: thẩm định/pin Oscar, cấu hình lab mỏng và chuyển SL-04–07 thành upstream fit-gap/configuration/acceptance trước SL-08–12. SL-01–03 là lịch sử ShopLab; independent approval SL-03 vẫn thiếu, không bị xóa hoặc chuyển sang Oscar. Không tiếp tục tự xây nghiệp vụ ShopLab trong tranche này.

Oscar hiện là candidate bị chặn trước execution: source tag 4.2.1 tại commit `d0a70850abf8e4229d4971aa7e8f4643326ec9f3`; wheel chính thức có assets/LICENSE và hash khớp metadata PyPI, chưa chứng minh khớp commit hay chữ ký. Upstream không hỗ trợ Windows; PostgreSQL là DB được hỗ trợ chính thức, SQLite chỉ development. Security policy không nêu thời hạn support 4.2.1 và README còn bảng support cũ. Chưa có dependency lock/license audit hoàn chỉnh hoặc môi trường Linux cô lập được kiểm chứng; không cài/chạy source, không dùng upstream Makefile/Dockerfile hoặc auth fixtures. Chi tiết tại [TASKS.md](TASKS.md#oscar--thẩm-định-nguồn-offline).

Thứ tự và acceptance: [PROJECT_PLAN.md](PROJECT_PLAN.md). Giữ IDs/dependencies `SL-*`; việc thay implementation không bỏ các yêu cầu ownership, CSRF, money, stock, idempotency, restore hoặc evidence. Chênh lệch upstream phải ghi rõ, không tự hạ acceptance.

## Boundaries

Chỉ local isolated lab với dữ liệu giả. Không public target, Internet scanning, arbitrary shell, dynamic actions, payload mới, credentials cố định, dữ liệu production hoặc deployment claim. Giữ lab mode, target/action allowlists, approval, rate/order/budget checks, kill switch, audit và restore.

`lab-ecommerce` trong compose chưa đồng nghĩa được cho phép trong safety registry. Registration và manifest cần kiểm tra riêng trước runtime. Không nới safety defaults để hợp thức hóa prototype.

Phê duyệt kế hoạch và sửa tài liệu không phải per-run/per-action approval. Giai đoạn PTES ngoài quyền hiện hành phải ghi `BLOCKED` hoặc `NOT_RUN`, thiếu evidence ghi `UNRESOLVED`; không giả completion. Không persistence trên target, credential theft, đọc host files hoặc lateral movement trong post-exploitation.

Evidence mới cần UTC, run ID, source, hash, redaction và expected/observed tách biệt; không overwrite record cũ. Evidence-write failure hoặc xung đột nguồn phải dừng. Phiên bản, image provenance/digest, model identity và measured metrics chỉ được ghi khi có bằng chứng.

## Source hierarchy

User source và approved contracts outrank derivative documents. AGENTS.md quy định governance; PROJECT_PLAN.md quy định roadmap; TASKS.md quy định backlog/status; ADR quy định quyết định kiến trúc; evidence quy định observed claims.

Nguồn roadmap: `PLAN-SHOPLAB-PTES-001` / `SHOPLAB-PTES-001`; tranche hiện hành `PLAN-OSCAR-ADOPTION-001` / `OSCAR-ADOPTION-001` theo lựa chọn tái sử dụng upstream được duyệt. Approval này cho thẩm định/configuration/tests offline và tám tài liệu được liệt kê, không runtime hoặc dependency execution khi gate chưa đạt. Không tự approve, finalize, append history hoặc commit. ADR-013 giữ nguyên như quyết định lịch sử ShopLab; user source/approved plan mới chi phối thay đổi hướng, không giả ADR đã được sửa/re-approved. Khi evidence và prose xung đột, báo blocker thay vì chọn claim có lợi hơn.
