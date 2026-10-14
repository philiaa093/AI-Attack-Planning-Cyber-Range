# TASK-019 — Knowledge-state store

## Status

`IMPLEMENTED` cho phần bổ sung SQLite ngoại tuyến, cập nhật trạng thái ngày 2026-10-12 theo yêu cầu người dùng; chưa được review độc lập hoặc nâng `VALIDATED`. Subset StateManager/KnowledgeRepository giữ validation lịch sử theo perception evidence, không áp dụng cho SQLite extension.

## Purpose

Lưu observations chuẩn hóa, tài sản/facts đã khám phá và trạng thái mô phỏng qua SQLite; tái dùng StateManager đã có và cung cấp truy vấn indexed projections/snapshot. Giữ compatibility verification khi observations đến từ web target snapshot mới.

## Background

Validation lịch sử chỉ giới hạn perception evidence hiện có; không xác nhận web mới hoặc SQLite extension. StateManager hiện có là API tái dùng, không sửa trong scope này. Extension được triển khai ngoại tuyến theo yêu cầu người dùng; code/tests/schema rationale và receipts tại [thiết kế Task 19](../implementation/knowledge_state_store.md).

## Scope

Store SQLite file hoặc in-memory, observations append-only, indexed facts/assets view và state snapshot; validate input, transaction/rollback, run/session/episode isolation, duplicate/conflict/replay và single budget owner. Implementation ở [knowledge_state_store.py](../../runtime/state/knowledge_state_store.py), focused cases ở [test_knowledge_state_store.py](../../tests/runtime/test_knowledge_state_store.py). Compatibility với snapshot/consumer thực tế còn chờ kiểm chứng; runtime/safety/evidence acceptance theo [SL-07](SL-07-lab-runtime.md), [SL-08](SL-08-discovery-safety.md), [SL-09](SL-09-observation-planner.md).

## Out of Scope

Không đổi StateManager, state/observation schema, action semantics, target ID, budget semantics hoặc planner. Không thêm RL, payload, live command, target source/ground-truth input, runner integration hoặc runtime claim. Không migrate DB có sẵn, thay evidence recorder hoặc claim chữ ký chống giả mạo từ SHA-256.

## Inputs

Observations chuẩn hóa đã redact; run/session/episode, scenario/objective, initial budget, subject/action allowlists đã được caller thu hẹp theo policy; source identity/hash và measured costs. Source hash là metadata caller cung cấp, store không đọc source file hoặc xác minh report. Compatibility tiếp theo cần approved snapshot/impact assessment, historical perception evidence và approved policy/budget identities.

## Outputs

SQLite journal, facts/assets projections, canonical state snapshot, deterministic replay và receipts fixtures/temp DB. Giữ compatibility cases cần thiết để tái dùng state với surfaces bị ảnh hưởng; không tạo claim execution hoặc planner validation.

## Interfaces

Store API: `StoreContext`, `create_context`, `ingest`, `get_state`, `query_facts`, `list_assets`, `observations`, `reconstruct`. Tái dùng `StateManager.apply_observation`, `decrement_requests`, `decrement_seconds`, `set_phase`, `get_state` để replay; giữ API lịch sử `reconstruct_from_observations`. Executor/gate theo SL-08 và planner proposal boundary theo SL-09; store không dispatch network/provider.

## Data Contracts

Observation/state contracts giữ nguyên; metadata session/episode/source/cost/phase thuộc envelope của store. Context key tách run/session/episode; session ID là nhãn mô phỏng, không token/cookie. Facts mang source_observation_id; journal giữ nguồn/hash/redaction/UTC. Cùng observation ID và cùng toàn bộ envelope được bỏ qua idempotently; khác payload/provenance/cost/phase bị từ chối. Cùng fact ID khác type/subject/value bị từ chối, cùng semantics giữ confidence cao nhất theo StateManager. StateManager là budget owner duy nhất; mỗi observation mới giảm actions một lần, kể cả DENIED/ERROR; requests/seconds do caller truyền.

## Dependencies

TASK-005, TASK-018

## Implementation Requirements

1. Kiểm tra facts/provenance của links/forms/redirects/auth-response observations tương thích snapshot mới mà không đưa source/ground truth vào state.
2. Kiểm tra identity tách biệt giữa run, session và episode; không merge facts chỉ vì route/UI giống nhau.
3. Kiểm tra duplicate/replay reconstruction, conflict handling và budget accounting theo API hiện có.
4. Không suy finding, severity, impact hoặc completed phase từ state fact; observations vẫn là boundary of truth.
5. Commit journal/facts/snapshot trong một transaction; reject schema DB không phù hợp trước writes, không tự migrate. Query facts có index và phân trang, replay kiểm envelope hashes và snapshot.

## Safety Requirements

State input là trust boundary: validate/redact trước ingest, preserve lab target/action/approval/refusal constraints ở dispatcher, không log token/credential. Conflict hoặc evidence loss risk phải dừng handoff liên quan.

## Testing Requirements

Receipts triển khai ngày 2026-10-11: `python -B -m unittest discover -s tests/runtime -p test_knowledge_state_store.py -v` exit 0, 21 tests PASS; `python -B -m unittest discover -s tests/unit -p test_knowledge_state_store.py -v` exit 0, 39 tests PASS. Cases gồm scope/schema/redaction, identity isolation, duplicate/conflict, budget/replay, SQL append-only guards, write rollback, connection reopen và hai writers trong cùng process. AST/diff/example checks PASS. Hash hai file Python khớp receipts khi đối chiếu ngày 2026-10-12; không chạy lại suites trong lần sửa tài liệu này.

Sau impact assessment, kiểm consumer/snapshot compatibility riêng. Discovery/refusal/evidence failure theo SL-08; planner replan/provenance theo SL-09, không tự thêm runtime check. Checks fixtures/connection reopen không chứng minh process restart hoặc container restore.

## Acceptance Criteria

Offline subset đã có receipts cho semantics state/replay/budget; task chưa đóng acceptance toàn bộ. Repository gate và independent review còn chờ; consumer/Normalizer integration, durable evidence binding, report thật, process/container restore và hiệu năng dữ liệu lớn `UNRESOLVED`. Evidence lịch sử bảo toàn. Không nâng validation của snapshot mới hoặc planner/provider từ unit/fixture result.

## Evidence Required

Giữ perception evidence hiện có. [Receipts Task 19](../implementation/knowledge_state_store.md) ghi exact commands/results, source SHA-256, receipt UTC và synthetic run IDs RUN-019/RUN-020 cùng expected/observed assertions. Checker triển khai exit 1, 656 repository errors và 0 errors thuộc ba paths Task 19; handoff `HANDOFF_BLOCKED`, blocker `REPOSITORY_CHECKER_FAILED`. SQLite journal là dữ liệu vận hành, không thay immutable evidence recorder. Check compatibility mới cần source/snapshot hash, redaction, identities và budget owner khi scope được duyệt.

## Failure Conditions

Fact without provenance, identity leakage, cross-session/episode contamination, duplicate overwrite, double budget decrement, ground-truth leak, malformed input, journal hash/snapshot mismatch hoặc evidence mismatch: block affected handoff and preserve records. Pending handoff: repository blockers xử lý theo scope riêng → independent review → approved consumer/evidence compatibility checks; không self-approve/finalize hoặc claim runtime success.

## Related Guides

Xem planning, AI-agent fundamentals và safety guides; requirements executable chuẩn ở SL-08/SL-09.

## Related Runbooks

Không có lệnh live hoặc provider run; áp dụng runbook chỉ sau approved runtime scope.

## Related ADRs

ADR-005 giữ separation; ADR-009 giữ ground-truth isolation; ADR-012/ADR-013 giữ policy/runtime boundaries.
