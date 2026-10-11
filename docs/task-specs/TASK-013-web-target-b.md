# TASK-013 — Web target B

## Status

`IMPLEMENTED`.

## Purpose

Duy trì đặc tả target B lịch sử và nêu điều kiện kiểm chứng lại khi web target B hoàn thiện hoặc đổi upstream.

## Background

TASKS.md ghi `VALIDATED` cho slice Docker lịch sử; spec giữ marker `IMPLEMENTED` và target B có identity/evidence riêng, không gộp với target A. TARGETS-013 mô tả coverage target lịch sử, không là image digest hay upstream pin. Linkage RUNTIME-004 cần review riêng về phạm vi/hash trước tái sử dụng. Validation cũ không áp dụng tự động cho snapshot mới.

## Scope

Đánh giá khác biệt UI, build, target snapshot hoặc upstream đối với target B; dẫn product/runtime/safety/provenance/replay tới [SL-07](SL-07-lab-runtime.md), [SL-08](SL-08-discovery-safety.md) và [SL-09](SL-09-observation-planner.md).

## Out of Scope

Không thay target B bằng Oscar mặc định, không đổi target ID cho UI-only change, không thêm vulnerability/payload, workflow khai thác hay lệnh live. Không sửa compose, registry, manifest, policy, contracts hoặc evidence.

## Inputs

Target B lịch sử, snapshot được duyệt, source/version/manifest/image evidence thực có, mapping identity khi replacement và impact assessment.

## Outputs

Phân loại tác động và receipts cần có lại cho target B; không tạo implementation/runtime claim, registry entry hay approval.

## Interfaces

Gateway, registry/manifest và safety gate là boundary có thẩm quyền. Discovery thu links/forms/redirects qua SL-08; planner nhận observations đã redact theo SL-09, không source/ground truth.

## Data Contracts

Liên kết target ID và snapshot identity với source/version/provenance chỉ khi có record. `latest` không chứng minh immutable image; absence of record là unverified, không phải digest suy đoán.

## Dependencies

TASK-011

## Implementation Requirements

1. Giữ B nguyên identity khi UI-only change không tác động runtime boundary; vẫn ghi impact assessment cho thành phần thay đổi.
2. Upstream/target replacement cần approved mapping B → identity mới theo SL-07, không tự thỏa dependency bằng candidate Oscar bị chặn execution.
3. Đối chiếu product flow, auth-response metadata, redirects, DB/storage, gateway và restore impact với acceptance SL-07.
4. Bảo toàn receipts/evidence lịch sử của B, không dùng chúng xác nhận snapshot mới.

## Safety Requirements

Lab-only, approval, target/action allowlist, rate/order/budget, refusal, audit và restore giữ nguyên. Mismatch target/manifest hoặc thiếu approval phải chặn trước network side effect.

## Testing Requirements

Mỗi thay đổi ảnh hưởng phải có receipts mới theo impact assessment; kiểm chứng product/gateway/isolation/restore theo SL-07 và discovery/planner boundaries theo SL-08/SL-09. Không lấy negative UI check làm acceptance tuyệt đối.

## Acceptance Criteria

Có phân biệt B giữ nguyên, B thay đổi và B bị thay thế; baseline/provenance/receipts mới đủ rõ để review. Không có claim validation/runtime/provenance chưa observed, không làm thay đổi historical status/evidence.

## Evidence Required

Giữ evidence lịch sử target B append-only. Snapshot mới chỉ claim observed sau run được duyệt, có UTC, run ID, source, hash, redaction, expected/observed và replay/provenance phù hợp.

## Failure Conditions

Unknown identity, mapping không được duyệt, provenance thiếu, product/runtime prerequisite chưa đạt, isolation/restore risk hoặc evidence conflict: block runtime handoff, không xóa records.

## Related Guides

Xem cyber-range and safety guides; yêu cầu canonical ở SL-07–SL-09 được dẫn chiếu, không sao chép.

## Related Runbooks

Spec không cung cấp lệnh live; áp dụng runbook chỉ sau approval của scope/run hiện hành.

## Related ADRs

ADR-003 giới hạn research families; ADR-012/ADR-013 giữ safety và runtime boundaries.
