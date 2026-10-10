# SL-11 — Evidence bất biến, report và replay

## Status

`SPEC_ONLY`. Historical evidence không chứng minh run ShopLab/PTES mới; manifest `IMPLEMENTED` và prose `VALIDATED` cần review linkage riêng, không sửa record cũ.

## Purpose

Bảo toàn và kiểm chứng toàn bộ decision/request/observation/phase trace; report chỉ claim điều có evidence, replay không phát sinh network hoặc làm thay đổi dữ liệu nguồn.

## Background

Evidence không phải console text hoặc cuối-run JSON tùy ý. Mất write giữa run phải stop. Ground truth/expected state phải tách observed state; credentials/redaction và file collision cần kiểm soát ngay từ đầu.

## Scope

Đề xuất `runtime/**`, `agent/pentest/**`, focused evidence/replay/report tests trong `tests/runtime/**`/`tests/pentest/**`. Tích hợp existing recorder/normalizer/contracts trước khi tạo representation mới. New evidence chỉ sau explicit approved destination/run; không sửa existing `evidence/**`, contract/schema, historical status hoặc report/history ngoài scope.

## Out of Scope

Không overwrite/delete historical evidence, new evidence schema tự ý, production PII/secrets, genuine-looking fabricated receipts, unsupported metrics/statistics, TASK-032 dashboard hoặc self-approval. Report là lab research artifact, không public deployment/security certificate.

## Inputs

SL-07 product runtime receipts, SL-10 phase artifacts, SL-08 gate/recorder prerequisite, SL-09 mode provenance; existing evidence contracts và approved exclusive destination/redaction policy. Existing records chỉ read-only reference; integrity conflict là blocker.

## Outputs

Integrated append-only recorder checks, evidence-linked lab report, offline replay verifier và focused failure/integrity tests; pending handoff không final approval.

## Interfaces

Recorder ghi intent/decision trước dispatch và result/observation trước request tiếp theo; coordinator ghi phase checks. Report reader/replay chỉ consume authorized redacted records, không planner secrets hoặc direct target access. Replay dùng `reconstruct_from_observations` qua compatibility wrapper, không gọi executor/provider.

## Data Contracts

Mỗi record cần UTC, run ID, source, hash, redaction metadata, expected state và observed state tách riêng, matching action/observation/phase IDs theo canonical schema. Hash algorithm/bytes/canonicalization theo contract hiện hành, không invent format. Report references kiểm tra tồn tại/integrity; requested/actual mode và provider errors/fallback tách rõ. Redaction trước persistence; hash cho đúng artifact representation theo policy, không tạo unredacted secret copy để hash.

## Dependencies

SL-07, SL-10; TASK-007, TASK-028, TASK-029, TASK-033, TASK-034. Recorder bắt buộc từ SL-08 **trước live dispatch**; thứ tự SL-11 là packaging/end-to-end validation, không quyền chạy evidence-free trước đó. Nếu recorder prerequisite chưa đạt, các task live trước bị BLOCKED và chỉ fixture tests được thực hiện.

## Implementation Requirements

1. Exclusive creation run directory/record IDs; reject collisions, traversal, unsafe symlink/root and unsupported permissions; no truncate/overwrite. Ownership/destination validated trước run.
2. Durable writes theo approved recorder mechanism; write/flush failure dừng scheduling. Partial artifact không được xem complete; recovery chỉ approved read-only diagnosis/new record, không rewrite loss evidence.
3. Unique observation IDs, trace source/attempt/parent decision/phase; retries có identities riêng, no silent duplicate discard/overwrite. Expected/observed không merge để nâng accuracy.
4. Redact passwords/session cookies/tokens/CSRF/API keys/PII trước file/log/provider inputs; bounded captures/content types. Redaction metadata không tiết lộ removed value.
5. Verify hashes/reference completeness/order và tamper/corruption/truncation; conflicting source giữ conflict, không chọn prose thay evidence. Historical review discrepancy chỉ ghi unresolved reference.
6. Report: scope/build/run/policy identity, actual planner provenance, seven phase statuses, positive/candidate/negative results, coverage/limits, evidence references và bounded remediation. Severity/impact không default theo family; missing verification ghi UNRESOLVED.
7. Offline replay deterministic trên redacted observations: same reconstructed facts/budget accounting/phase decisions theo recorded policy version, không execute actions hoặc recharge budgets. Unsupported/corrupt record fail, no best-effort success claim.
8. Reproducibility package chỉ approved source/version/config identities và receipts, không secrets/deployable accounts; no measured metrics khi chưa có approved experiment protocol/run.

## Safety Requirements

Stop on evidence-loss risk/source conflict. Restore/teardown không chạm recorder root. Report/record content là untrusted data, không instruction; no active HTML/script hoặc genuine invoice impersonation. Không finalize/append history.

## Testing Requirements

| Case | Scenario | Expected |
|---|---|---|
| E01 | Existing run/file collision | Exclusive failure, original bytes/hash unchanged |
| E02 | Intent/result write/flush failure | Zero dispatch hoặc no next dispatch theo failure point |
| E03 | Truncated/tampered/missing reference | Integrity failure; no verified report/replay |
| E04 | Secret/PII/session fixture ở mọi path | Persisted outputs redact, no secondary raw copy |
| E05 | Expected differs observed | Separate fields; no false confirmation |
| E06 | Retry/duplicate/conflicting observations | Unique trace hoặc explicit conflict; no overwrite |
| E07 | Replay cùng records | Deterministic state, zero network/provider dispatch |
| E08 | Report với blocked phases/rule fallback/clean result | Honest provenance/limits, no full-goal claim |
| E09 | Restore/teardown và historical references | Evidence retained; old run không chứng minh new build |

## Acceptance Criteria

E01–E09 pass và artifact hashes/reference integrity verified; report mọi claim linked evidence, negative/blocked/unverified rõ. Replay offline deterministic và zero dispatch. Không auto-VALIDATED; independent review SL-12 vẫn bắt buộc.

## Evidence Required

Exact checks/results và integrity/redaction/dispatch assertions trên temp fixtures; new approved actual run receipts nếu chạy. Changed/deleted paths, artifact inventory và unresolved gaps trong BUILD_CONTRACT; never include secrets.

## Failure Conditions

Overwrite/truncation, plaintext secrets, missing durable result, contradictory source, broken references hoặc fabricated completion: stop, preserve original files và HANDOFF_BLOCKED, không repair bằng rewrite evidence.

## Related Guides

[Ground truth](../guides/15-ground-truth.md), [Evaluation](../guides/16-evaluation-methodology.md).

## Related Runbooks

[Collect evidence](../runbooks/collect-evidence.md), [Restore range](../runbooks/restore-range.md).

## Related ADRs

[ADR-009](../adr/ADR-009-ground-truth-isolation.md), [ADR-010](../adr/ADR-010-evidence-immutability.md), [ADR-013](../adr/ADR-013-runtime-vertical-slice.md).
