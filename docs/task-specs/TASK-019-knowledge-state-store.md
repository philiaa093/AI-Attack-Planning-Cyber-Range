# TASK-019 — Knowledge-state store

## Status

`VALIDATED`.

## Purpose

Giữ knowledge-state store đã có và mô tả compatibility verification khi observations đến từ web target snapshot mới.

## Background

`VALIDATED` chỉ giới hạn perception evidence hiện có; không xác nhận web mới. StateManager hiện có là API tái dùng, không sửa trong scope này; validation cũ không áp dụng tự động cho snapshot mới.

## Scope

Rà facts/provenance, run identity, session/episode isolation, duplicate/replay và một budget owner khi target surfaces thay đổi. Dẫn runtime/safety/provenance/replay acceptance tới [SL-07](SL-07-lab-runtime.md), [SL-08](SL-08-discovery-safety.md), [SL-09](SL-09-observation-planner.md).

## Out of Scope

Không đổi StateManager, state schema, action semantics, target ID, budgets hoặc planner. Không thêm RL, payload, live command, source/ground-truth input hay runtime claim.

## Inputs

Approved snapshot/impact assessment, observations đã redact, StateManager API hiện có, historical perception evidence và approved policy/budget identities.

## Outputs

Compatibility cases và receipts cần thiết để tái dùng state với observation surfaces bị ảnh hưởng; không tạo claim execution hoặc planner validation.

## Interfaces

Tái dùng `apply_observation`, `decrement_requests`, `decrement_seconds`, `get_state` và `reconstruct_from_observations`. Executor/gate theo SL-08 và planner proposal boundary theo SL-09; state không dispatch network.

## Data Contracts

Facts mang source observation identity/provenance; run/session/episode identifiers tách biệt. Budget chỉ có một owner/source of truth; replay/duplicate không được silently double-decrement hoặc overwrite conflict.

## Dependencies

TASK-005, TASK-018

## Implementation Requirements

1. Kiểm tra facts/provenance của links/forms/redirects/auth-response observations tương thích snapshot mới mà không đưa source/ground truth vào state.
2. Kiểm tra identity tách biệt giữa run, session và episode; không merge facts chỉ vì route/UI giống nhau.
3. Kiểm tra duplicate/replay reconstruction, conflict handling và budget accounting theo API hiện có.
4. Không suy finding, severity, impact hoặc completed phase từ state fact; observations vẫn là boundary of truth.

## Safety Requirements

State input là trust boundary: validate/redact trước ingest, preserve lab target/action/approval/refusal constraints ở dispatcher, không log token/credential. Conflict hoặc evidence loss risk phải dừng handoff liên quan.

## Testing Requirements

Sau impact assessment, chạy compatibility cases facts/provenance, identities, session/episode isolation, duplicate/replay và single budget owner. Discovery/refusal/evidence failure theo SL-08; planner replan/provenance theo SL-09, không tự thêm runtime check.

## Acceptance Criteria

Receipts mới chứng minh phần state interaction bị ảnh hưởng có semantics rõ và replay/budget không sai; evidence lịch sử bảo toàn. Không nâng validation của web snapshot mới hoặc planner/provider từ unit/fixture result.

## Evidence Required

Giữ perception evidence hiện có. Check mới cần exact command/result, UTC, run ID, snapshot source/hash, redaction, expected/observed, identity/provenance và budget owner khi execution được duyệt.

## Failure Conditions

Fact without provenance, identity leakage, cross-session/episode contamination, duplicate overwrite, double budget decrement, ground-truth leak, malformed input hoặc evidence mismatch: block affected handoff and preserve records.

## Related Guides

Xem planning, AI-agent fundamentals và safety guides; requirements executable chuẩn ở SL-08/SL-09.

## Related Runbooks

Không có lệnh live hoặc provider run; áp dụng runbook chỉ sau approved runtime scope.

## Related ADRs

ADR-005 giữ separation; ADR-009 giữ ground-truth isolation; ADR-012/ADR-013 giữ policy/runtime boundaries.
