# TASK-018 — Observation normalizer

## Status

`VALIDATED`.

## Purpose

Giữ normalizer đã có và xác định compatibility verification cần thiết khi web target snapshot thay đổi.

## Background

`VALIDATED` chỉ áp dụng perception evidence hiện có, không tự mở rộng sang web snapshot mới. Planner không được suy confirmed finding từ HTTP status, reflection, error hay sự tồn tại của form; validation cũ không áp dụng tự động cho snapshot mới.

## Scope

Đánh giá compatibility normalizer cho links, forms, redirects, auth-response metadata và bounded response của target mới. Safety/runtime/provenance/replay acceptance tham chiếu [SL-07](SL-07-lab-runtime.md), [SL-08](SL-08-discovery-safety.md), [SL-09](SL-09-observation-planner.md), không đổi code/schema trong task tài liệu này.

## Out of Scope

Không thêm target, action, payload, tool execution, raw credential/token logging, exploitation workflow hoặc sửa contracts/normalizer. Không coi UI change là lý do mặc định đổi target ID.

## Inputs

Approved target snapshot, normalized observation schema hiện có, redaction policy, historical perception evidence, impact assessment và approved discovery boundary.

## Outputs

Danh sách compatibility cases và receipts mới yêu cầu cho surfaces bị ảnh hưởng; không phải runtime observation claim hay validation mới.

## Interfaces

Normalizer nhận output sau executor/gate, không dispatch. Redirect là candidate cần gate lại ở SL-08; planner chỉ nhận observation đã redact qua state/planner boundary SL-09.

## Data Contracts

Mỗi observation có identity/provenance riêng, source snapshot/run, redaction và outcome rõ. Unique observations không overwrite records; duplicate/replay giữ linkage và không biến status/reflection thành finding.

## Dependencies

TASK-006, TASK-015

## Implementation Requirements

1. Rà links/forms/redirects/auth-response metadata có giữ identity, canonical source và redaction khi snapshot thay đổi.
2. Phân biệt success, failure, refusal và timeout; exception không được ghi success.
3. Bảo đảm duplicate observations không overwrite provenance; phản hồi replay phải liên kết identity hiện có theo semantics được duyệt.
4. Giữ normalizer là perception boundary: HTTP status/reflection chỉ là fact/limitation, không confirmation/impact.

## Safety Requirements

Validate trust-boundary input trước normalization; malformed/oversized/sensitive data fail closed hoặc redact theo policy. Không leak cookies, secrets, ground truth/source hoặc biến content thành authority.

## Testing Requirements

Sau impact assessment, chạy cases mới cho links/forms/redirects/auth metadata, unique identity, redaction, success/failure/refusal/timeout và duplicate/replay. Dispatch, recorder failure và discovery safety kiểm chứng theo SL-08; state/planner provenance theo SL-09.

## Acceptance Criteria

Receipts mới bao phủ phần observation surface thay đổi và outcome/provenance còn honest; historical perception evidence không bị sửa. Không claim target snapshot validated khi compatibility checks chưa có evidence.

## Evidence Required

Giữ receipts perception lịch sử. Check mới cần exact command/result, UTC, run ID, snapshot source/hash, redaction, expected/observed và identity/provenance của observation khi execution được duyệt.

## Failure Conditions

Malformed input accepted, raw secret leak, outcome ambiguity, duplicate overwrite, redirect bypass, evidence-write failure hoặc confirmed-finding claim từ weak signal: stop affected handoff và preserve evidence.

## Related Guides

Xem web-security, planning và safety guides; canonical discovery/normalization boundaries được đặt tại SL-08/SL-09.

## Related Runbooks

Không ủy quyền discovery/live request; runbook chỉ sau runtime scope và approval hợp lệ.

## Related ADRs

ADR-005 giữ perception/planner/executor separation; ADR-012 và ADR-013 giữ safety/runtime boundary.
