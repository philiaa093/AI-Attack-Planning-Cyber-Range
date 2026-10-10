# SL-02 — Storage lifecycle, transaction và persistence

## Status

`VALIDATED` trong phạm vi đã duyệt: S01–S07 offline/SQLite temp và handoff restore coordination. Build `BUILD-SL02-STORAGE-001` R1, plan `PLAN-SL02-STORAGE-001`: 90 regression tests, AST 2 files/scaffold checker/gate PASS; review độc lập `FINAL / APPROVE` được verifier xác nhận exit 0 ngày 2026-10-10. S08 restore thực tế/replacement/session invalidation và Docker durability chưa chạy; không mở runtime bằng trạng thái này. Exact receipts/hashes tại [TASKS.md](../../TASKS.md#checks-and-observed-implementation-state).

## Purpose

Có storage layer ổn định cho sản phẩm, không import side effects, không mất dữ liệu khi restart và không trộn transactions giữa requests.

## Background

Shared global connection hazard đã được xử lý bằng connection riêng từng service transaction; lifecycle globals chỉ giữ path/admission/active count, không giữ connection chung. `BEGIN IMMEDIATE` cho writes, query-only read transactions, rollback/close trước HTTP response và schema v1 fail closed đã có fixture checks. F01 filter schema bỏ sót user objects vì LIKE underscore wildcard đã được tái hiện và sửa thành literal prefix. HTTP reset vẫn bị chặn, chưa phải restore workflow hoàn chỉnh.

## Scope

Triển khai đề xuất chỉ trong `cyber-range/targets/ecommerce/**`, focused storage/concurrency tests trong `tests/integration/**` hoặc `tests/runtime/**`. Chọn connection-per-request/service transaction; nếu dùng shared connection thì lock phải bao phủ toàn bộ transaction, không chỉ execute. Chốt chiến lược trước edit; không đổi framework vô cớ.

## Out of Scope

Không migrations trên production, không đọc/xóa evidence, không xóa data directory bất kỳ, không Docker deployment trong task này. Không sửa contracts/config/catalog bằng task-spec.

## Inputs

SL-01 receipts; current SQLite schema và data-directory setting; giả định restart/lab restore được duyệt; product routes sẽ tái dùng storage.

## Outputs

Storage lifecycle/transaction API, versioned schema handling cho lab, bounded validation, tests restart/concurrency/rollback, thiết kế restore coordination và receipts. Không coi output design restore là đã chạy restore.

## Interfaces

API đã có `initialize_storage`, `_init_db`, `storage_transaction`, `quiesce_storage`, `close_storage`, `search_products`. `storage_transaction(write=False/True)` sở hữu connection riêng, explicit transaction và rollback/cleanup; server startup/shutdown sở hữu lifecycle, request không tự close global storage. Foreign keys và busy timeout từ `BUSY_SECONDS` được bật trên từng connection. SL-04 tái dùng boundary transaction checkout; SL-07 cần approved restore/replacement/session coordination riêng.

## Data Contracts

SQLite foreign keys bật trên mọi connection; unique constraints/positive quantities/nonnegative stock/currency constraints cho schema mới. Mọi timestamp nghiệp vụ UTC. Giá integer minor units và currency explicit khi SL-04 triển khai, migration không truncate float âm thầm. Schema mismatch phải báo lỗi, không drop/reseed user data.

## Dependencies

SL-01. Liên kết TASK-011. Auth/checkout test integration ở SL-03/SL-04, không tạo dependency vòng.

## Implementation Requirements

1. Import không ghi tệp, mở DB hay server. Config data dir được validate trước startup; không chọn evidence directory hoặc path từ HTTP input.
2. Initialization atomic và idempotent: first run tạo schema/catalog, reopen không reseed; phát hiện partial/incompatible schema có rollback hoặc fail rõ ràng.
3. Transactions explicit, connection/lock lifecycle dễ test, bounded busy handling; rollback mọi exception và close connections đúng lúc.
4. Commit/shutdown giữ data; startup lỗi không để global DB nửa khởi tạo. Close idempotent sau server đã ngừng workers.
5. Storage errors trả safe error, không lộ filesystem/SQL; không tiếp tục checkout sau write failure.
6. Local restore coordination: ngừng new mutations, chờ in-flight transactions, thay state trong phạm vi app data đã duyệt, invalidate sessions phù hợp; không unlink tùy ý hoặc overwrite evidence. SL-07 xác minh workflow thực tế.

## Safety Requirements

Không seeded accounts/secrets. Không migrate/delete khi source không rõ hoặc evidence-loss risk. Phê duyệt restore riêng; giữ data cũ nếu migration fail. Không dùng `.resolve()` như bằng chứng tuyệt đối filesystem safety; xử lý ownership/symlink/configured root theo threat boundary.

## Testing Requirements

| Case | Scenario | Expected |
|---|---|---|
| S01 | Import, initialization/close lặp và reopen | Không import I/O; lifecycle đúng; không reseed |
| S02 | Partial schema hoặc unsupported schema version | Fail rõ ràng; dữ liệu cũ không mất |
| S03 | Exception giữa hai writes trong transaction | Cả hai writes rollback |
| S04 | Hai requests đồng thời trên cùng sản phẩm | Không interleave một transaction; invariants giữ |
| S05 | Foreign-key/quantity/stock violation | Reject/rollback; safe response |
| S06 | DB busy hoặc read-only data dir | Bounded failure, không hang hoặc false success |
| S07 | Restart process với cùng dir | Product/order data giữ đúng; không fixed user accounts |
| S08 | Restore khi mutation đang chạy | Coordination theo policy; evidence untouched; không state nửa cũ/nửa mới |

Dùng temp directory và fixtures giả; không test lên storage của người dùng. S01–S07 có 28 storage tests PASS trong R1, bao gồm version 0 partial/version 1 thêm prefix-lookalike user object bị từ chối và bytes giữ nguyên; hai subprocess kiểm tra product/order/item persistence. S08 chỉ đã kiểm tra admission/drain timeout giữ fail closed và không đóng worker connection; integration restore/replacement/session invalidation cần SL-03/SL-07 approval. Test riêng successful quiesce khi worker active vẫn là gap non-blocking được reviewer ghi nhận.

## Acceptance Criteria

Storage API rõ lifecycle/transaction boundaries; initialization/reopen/rollback/concurrency tests pass; shared global transaction hazard được xử lý; schema failure không mất dữ liệu. Process-restart claim có receipts; container-replacement durability không thuộc acceptance ở đây. Handoff design restore và gaps được nêu rõ; không auto-VALIDATED.

## Evidence Required

Schema/version và chosen transaction strategy; exact test commands/results; before/after expected-observed không chứa identities/secrets; hash/UTC/run/source/redaction theo policy khi lưu receipts.

Đã ghi nhận R1 ngày 2026-10-10: 90 tests PASS (storage 28, gateway 13, validator 31, safety 17, scaffold integration 1), AST 2 files/checker PASS; mọi required command exit 0. Artifacts ngoài repo tại `C:/Users/DELL/AppData/Local/Temp/claude/E--PBL6-FINAL/70d0e679-2bee-4cda-bdbf-4677f16e949e/sl02-goal-20261010-001/`: `plan.json`, `build-r1.json`, `repair1-receipts.json`, `gate-r1.json`, `review-r1.json`, `review-verification-r1.json`, `review-verification-r1-receipt.json`, `F01-reproduction.json`. Đây là operational receipts ở vị trí tạm, không phải kho runtime evidence lâu dài. Exact source hashes/gate/review và command receipts được đối chiếu tại [TASKS.md](../../TASKS.md#checks-and-observed-implementation-state); review chỉ áp dụng source build R1, không bao gồm cập nhật tài liệu này.

Restore design handoff: đóng admission, drain transactions có timeout; timeout không mở admission hoặc đóng worker connection. Actual DB/invoice replacement và session invalidation phải do approved SL-03/SL-07 workflow, không chạm evidence. Invoice filesystem/SQLite chưa atomic chung; orphan reconciliation thuộc SL-04/SL-07. Trusted app-owned parent/ACL là boundary giả định; Windows receipts không chứng minh POSIX ownership, hostile concurrent replacement, crash/power-loss hay container durability.

## Failure Conditions

Concurrent writes sai invariant, data-loss risk, unsupported schema tự reseed, tests dùng user data, unbounded lock wait hoặc restore chạm evidence: blocker, dừng build.

## Related Guides

[Cyber Range](../guides/03-cyber-range-fundamentals.md), [Safety](../guides/17-cyber-range-safety.md).

## Related Runbooks

[Restore range](../runbooks/restore-range.md), [Collect evidence](../runbooks/collect-evidence.md).

## Related ADRs

[ADR-013](../adr/ADR-013-runtime-vertical-slice.md), [Evidence immutability](../adr/ADR-010-evidence-immutability.md).
