# TASK-011 — Cyber range network

## Status

`SPEC_ONLY`.

## Purpose

Ghi rõ phạm vi rà soát cyber range khi web target hoàn thiện hoặc đổi upstream, không cấp quyền runtime mới.

## Background

TASKS.md giữ trạng thái lịch sử `VALIDATED` cho local Docker slice qua RUNTIME-004, trong khi spec này giữ `SPEC_ONLY`. Manifest RUNTIME-004 ghi `IMPLEMENTED`; cần review linkage, phạm vi và hash trước khi tái sử dụng. Validation cũ không áp dụng tự động cho snapshot mới.

## Scope

Đánh giá tác động lên topology, service, database, storage, gateway, registry và identity target khi UI, build hoặc upstream thay đổi. Acceptance/runtime/safety/provenance/replay chi tiết tham chiếu [SL-07](SL-07-lab-runtime.md), [SL-08](SL-08-discovery-safety.md) và [SL-09](SL-09-observation-planner.md).

## Out of Scope

Không sửa compose, registry, manifest, safety policy, target ID hay target A/B chỉ vì UI thay đổi. Không public target, scanner, payload, lệnh live, credentials, arbitrary shell hoặc kết luận runtime từ tài liệu.

## Inputs

Target snapshot được duyệt, impact assessment, source/version/image provenance thực có, mapping identity nếu upstream thay thế, và evidence/receipts lịch sử còn nguyên.

## Outputs

Đánh giá phạm vi ảnh hưởng và danh sách receipts mới cần có trước khi snapshot được dùng lại; không tạo runtime approval hoặc evidence mới.

## Interfaces

Network boundary giữ gateway ingress, internal target, registry/manifest và safety target/action allowlist là các authority riêng. Mọi request/redirect tương lai theo gate và recorder của SL-08.

## Data Contracts

Ghi snapshot identity, source/version có chứng cứ, manifest/image reference nếu có và liên kết evidence; không bịa digest hoặc coi image `latest` là immutable pin. Evidence expected/observed, UTC, run ID, hash và redaction vẫn tách biệt.

## Dependencies

TASK-003

## Implementation Requirements

1. So sánh snapshot mới với identity đã duyệt để xác định topology, service, DB, storage, gateway, registry và safety mapping nào bị ảnh hưởng.
2. UI-only change không tự đổi target ID; upstream hoặc target khác cần mapping/identity được duyệt riêng theo SL-07.
3. Kiểm tra product/runtime prerequisites, Linux/DB support, image provenance, loopback/internal isolation và restore theo SL-07, không lặp procedure.
4. Bảo toàn evidence lịch sử; không overwrite receipts hay chuyển claims slice cũ sang snapshot mới.

## Safety Requirements

Lab-only, target/action allowlist, approval, rate/order/budget, refusal, audit và restore vẫn bắt buộc. Thiếu approval, malformed identity hoặc mismatch registry/manifest phải fail closed trước dispatch.

## Testing Requirements

Trước tái sử dụng snapshot, thực hiện impact assessment và receipts mới cho các thành phần bị ảnh hưởng. Kiểm chứng isolation, storage/restore và gateway chỉ theo acceptance có thẩm quyền tại SL-07; discovery/planner theo SL-08/SL-09.

## Acceptance Criteria

Impact assessment liên kết snapshot với thay đổi network/service và nêu receipts mới cần có; historical evidence còn nguyên; không có claim runtime, provenance hoặc validation mới khi thiếu quan sát. Không dùng status lịch sử thay acceptance của snapshot mới.

## Evidence Required

Giữ source record/evidence lịch sử bất biến. Snapshot mới chỉ có evidence sau approved run với UTC, run ID, source, hash, redaction, expected và observed; lỗi ghi evidence phải dừng theo SL-07.

## Failure Conditions

Identity/manifest conflict, missing approval, unsupported provenance, public binding, egress không được duyệt, storage/restore data-loss risk hoặc evidence conflict: chặn handoff runtime và bảo toàn records.

## Related Guides

Xem cyber-range fundamentals và safety guides; requirements chuẩn nằm tại SL-07–SL-09.

## Related Runbooks

Các runbook start, isolation, restore chỉ được dùng khi scope/run được duyệt; spec này không tự ủy quyền runtime.

## Related ADRs

ADR-012 và ADR-013 giữ safety-engine và runtime boundary; ADR-003 không mở rộng vulnerability families.
