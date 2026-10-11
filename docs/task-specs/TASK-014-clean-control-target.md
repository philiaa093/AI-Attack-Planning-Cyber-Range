# TASK-014 — Clean control target

## Status

`IMPLEMENTED`.

## Purpose

Giữ clean control lịch sử và xác định điều kiện so sánh lại khi web target hoặc upstream đổi snapshot.

## Background

TASKS.md ghi `VALIDATED` cho local Docker slice lịch sử; spec giữ `IMPLEMENTED`. TARGETS-014 mô tả coverage clean-control lịch sử, không là image digest hay upstream pin. Linkage RUNTIME-004 cần review riêng về phạm vi/hash trước tái sử dụng. Validation cũ không áp dụng tự động cho snapshot mới, nhưng evidence lịch sử vẫn được bảo toàn.

## Scope

Đánh giá clean control còn tương thích với target snapshot mới, có cùng ràng buộc identity, policy, budgets và observation boundary để so sánh công bằng. Runtime/safety/provenance/replay tham chiếu [SL-07](SL-07-lab-runtime.md), [SL-08](SL-08-discovery-safety.md), [SL-09](SL-09-observation-planner.md).

## Out of Scope

Không kết luận target an toàn tuyệt đối từ negative checks; không sửa control, target ID, registry, contracts, evidence hoặc policy chỉ để tạo comparison. Không thêm payload, exploitation, public target hay lệnh live.

## Inputs

Approved target/control snapshots, policy/action/budget baseline, mapping identity khi target thay thế, changed-surface impact assessment và evidence lịch sử.

## Outputs

Đánh giá comparability cùng danh sách receipts mới cần có; không phải assurance tuyệt đối, runtime authorization hoặc proof rằng không có vulnerability.

## Interfaces

Control và target phải qua cùng safety gate, recorder, gateway boundary và observed-state path. Ground truth chỉ dùng evaluation, không đưa vào planner hoặc dùng để điều hướng control.

## Data Contracts

Lưu reference tới target/control snapshot, policy/budget identity và provenance có chứng cứ. Ghi negative observations như observations có giới hạn, không chuyển chúng thành global safety claim.

## Dependencies

TASK-011

## Implementation Requirements

1. So sánh identity, approved actions, budgets, rate/order, gateway/DB/storage assumptions và observation normalization giữa target mới và control.
2. UI-only change không tự yêu cầu target ID mới; target/upstream replacement cần mapping được duyệt và baseline control phù hợp theo SL-07.
3. Kiểm tra changed routes/forms/redirects/auth-response metadata không làm comparison biết trước đáp án; discovery theo SL-08, planner theo SL-09.
4. Bảo toàn historical control evidence và nêu receipts mới cho phần bị ảnh hưởng.

## Safety Requirements

Control không được là đường bypass: lab mode, approval, target/action allowlist, budgets, refusal, audit và restore áp dụng như target. Mismatch/missing approval hoặc evidence-write failure phải dừng.

## Testing Requirements

Impact assessment xác định checks comparability cần chạy lại; thực thi phải dùng acceptance runtime của SL-07 và safety/observation/replay boundaries SL-08/SL-09. Negative result cần coverage/limitation và không thay runtime evidence.

## Acceptance Criteria

Control cần được chứng minh phù hợp để so sánh trong phạm vi snapshot/policy đã duyệt, với receipts mới bao phủ phần thay đổi; evidence cũ giữ nguyên. Chưa có bằng chứng thì ghi unverified và chưa đạt acceptance cho comparison mới. Negative observations không chứng minh an toàn tuyệt đối; HTTP status/reflection không tự xác nhận finding.

## Evidence Required

Evidence lịch sử append-only. Bất kỳ comparison run mới nào cần run ID, UTC, source, hash, redaction, expected/observed, policy/budget identity và provenance/replay receipts.

## Failure Conditions

Control/target mismatch, unfair budgets, target identity ambiguity, ground-truth leak, evidence loss, unsafe restore hoặc claim vượt coverage: block comparison/runtime handoff và preserve records.

## Related Guides

Xem safety, ground-truth và evaluation guides; detailed runtime/discovery/planner acceptance nằm ở SL-07–SL-09.

## Related Runbooks

Không có procedure live ở đây; runbook chỉ theo approved scope, inventory và restore approval.

## Related ADRs

ADR-009 giữ ground-truth isolation; ADR-012/ADR-013 giữ gate và runtime boundary.
