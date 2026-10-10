# SL-07 — Product E2E, Docker lab và restore

## Status

`SPEC_ONLY`. Runtime target Oscar cần scope/approval riêng; tranche `OSCAR-ADOPTION-001` chỉ thẩm định/configuration/tests offline, không Docker/server/live dispatch. Evidence slice cũ và ShopLab không xác nhận Oscar hoặc container durability.

## Purpose

Chứng minh sản phẩm chạy đúng qua gateway trong isolated lab, có durable storage/restore và receipts đủ để phân biệt config correctness với observed runtime.

## Background

Compose có ShopLab lab-ecommerce/gateway-ecommerce, chưa có Oscar identity và safety mapping được duyệt. Candidate mới cần Linux/DB/dependency/product gate trước runtime scope riêng. Dockerfile/data dir hoặc wheel assets không chứng minh durability/isolation; Host/Origin/CSRF, local static/media và egress cần actual receipts.

## Scope

Scope runtime tương lai đề xuất `cyber-range/compose.yaml`, `cyber-range/runtime/**`, `cyber-range/targets/oscar-lab/**`, `cyber-range/targets/manifests/**`, focused `tests/integration/**`/`tests/runtime/**`; không phải allowlist tranche offline hiện hành. Target identity mới, không repurpose `lab-ecommerce`, không sửa/migrate ShopLab. Registration chỉ khi giao rõ `configs/safety/target-allowlist.yaml`; không implicit config permission. Cần approved Linux/DB/executable scope, per-run approval và evidence destination trước Docker/server/dispatch.

## Out of Scope

Không public deploy, Internet scanning, sửa target khác để pass, open outbound gateway, host-wide restore/delete, production data hoặc cài real scanners/LLM. Không fake image pinning/digests hoặc dùng evidence cũ cho build mới.

## Inputs

SL-02–06 product/storage/auth/admin tests/review; baseline/current image build context; target/manifest/policy exact identities; approved start/test/restore/teardown scope. Historical RUNTIME-004 chỉ reference cần review linkage, không acceptance cho ShopLab.

## Outputs

Registered bounded target khi approved, runtime configuration và focused integration tests; observed product E2E/isolation/persistence/restore/teardown receipts; handoff ready/not-ready cho bounded assessment.

## Interfaces

Host chỉ qua loopback gateway; target chỉ internal network. Registry/manifest mapping target ID → internal host/port/approved action capability không suy ra từ prefix lab-. Gateway không tự follow redirect hoặc forward user authority. Startup/health/restore interface giữ consistent product identity; health không đọc credentials/source/ground truth.

## Data Contracts

Run identity, image/version/digest observed, source HEAD/diff/build identity, policy approval IDs, mount/volume ownership và lab data location. Data dir không evidence root. Readiness/health false hoặc identity mismatch không thành PASS. Evidence receipts expected/observed/UTC/hash/source/redaction; new exclusive run không overwrite.

## Dependencies

SL-02, SL-03, SL-04, SL-05, SL-06; TASK-011/TASK-014. Nếu product approval chưa đạt thì handoff blocked. SL-11 đánh giá recorder integration cho AI; task này chỉ chạy product checks với recorder/receipt mechanism hiện có đã duyệt, nếu không có thì block chứ không trì hoãn ghi evidence.

## Implementation Requirements

Tái sử dụng upstream app và gateway, không viết lại nghiệp vụ để đạt runtime demo. Oscar không hỗ trợ Windows; PostgreSQL hỗ trợ chính thức và SQLite chỉ development, nên DB/runtime claims cần chọn/kiểm chứng phù hợp qua scope riêng. Pin wheel/dependencies/image thật; không dùng upstream Dockerfile remote script, Makefile reset/seed hoặc source build NPM hook. Review Host/Origin/CSRF/redirect/static-media serving với DEBUG=False trước integration. Invoice/stock allocation/idempotency gaps phải giải quyết explicit, không bypass acceptance.

1. Đối chiếu registry/manifest/compose/validator restrictions. Mismatch action semantics hoặc schema cần scope riêng; không nới policy cho prototype.
2. Pin/record image identity/provenance theo approved sources; không bịa digest hoặc kết luận reproducible từ `latest` tag.
3. Persistent storage mount với least privilege, correct app user access; distinguish process restart/container replacement; không bind sensitive host paths.
4. Gateway loopback ingress/internal upstream, bounded Cookie/Set-Cookie/status/redirect/error flow; không public proxy hoặc external redirect dispatch.
5. Product E2E bằng fake accounts tạo runtime: browse → register/login → cart → checkout → orders/invoice/review → logout; admin operations bằng approved local existing-account workflow.
6. Observe internal-only target topology và egress denial; config inspect không thay actual checks. Gateway ingress attachment không tự chứng minh egress safe; constraints/checks riêng.
7. Restore: approved local operation, stop mutations/wait in-flight, backup/replace đúng app state, invalidate sessions, reset stock/catalog/orders/reviews/invoices theo approved baseline; preserve evidence. Re-run health và product invariants; no arbitrary recursive deletion.
8. Teardown owned services của run, không delete unrelated containers/volumes/evidence. Evidence-write unavailable dừng; tool failure không retry vô hạn.

## Safety Requirements

Runtime approval chỉ scope/run/action cụ thể; documentation không cấp quyền. Không external connectivity checks lên public endpoint; dùng approved controlled fixtures cho denial. Credentials/cookies giả runtime không ghi receipts. Không gọi destructive restore khi chưa inventory/approval.

## Testing Requirements

| Case | Scenario | Expected |
|---|---|---|
| R01 | Registry/manifest/compose mismatch | Fail closed trước assessment |
| R02 | User flow qua gateway, two sessions | Login/cookies/CSRF/product/ownership đúng |
| R03 | Unauthenticated/cross-user/admin denial | Deny và no writes/leak |
| R04 | Target/ingress topology + controlled egress checks | Loopback ingress, target internal only, no unauthorized outbound |
| R05 | Restart process và replace owned container giữ storage | Durable state đúng claim, no reseed |
| R06 | Restore với active transaction | Coordination đúng, state baseline, old sessions invalid |
| R07 | Evidence-write failure, image/start/health failure | Stop, receipts honest, no fake readiness |
| R08 | Teardown | Chỉ owned services bị dừng; data/evidence retained theo policy |

Commands cụ thể phải lấy từ approved runbook/current environment lúc chạy; task-spec không chứa live deployment command hoặc PASS giả.

## Acceptance Criteria

Products SL-02–06 đã checks/review; R01–R08 có exact receipts và independent runtime/security review; restore verified không chạm evidence. Docker/provider không sẵn có thì UNVERIFIED/HANDOFF_BLOCKED, không thay mock. Không public deployment claim.

## Evidence Required

Build/start/config/health/business-flow/session/ownership/isolation/restart/restore/teardown receipts; image provenance và run-policy identity; hashes verified. Missing approved recorder/destination là blocker trước run, không ghi log tùy ý rồi gọi append-only.

## Failure Conditions

Public binding, target outbound, unknown registry identity, state/evidence loss, storage permission failures, unsupported image claims hoặc absent approval: stop, preserve receipts; no assessment handoff.

## Related Guides

[Cyber Range](../guides/03-cyber-range-fundamentals.md), [Safety](../guides/17-cyber-range-safety.md).

## Related Runbooks

[Start range](../runbooks/start-cyber-range.md), [Validate isolation](../runbooks/validate-isolation.md), [Restore range](../runbooks/restore-range.md), [Stop range](../runbooks/stop-cyber-range.md). Không tự authorize các procedures.

## Related ADRs

[ADR-013](../adr/ADR-013-runtime-vertical-slice.md), [Evidence immutability](../adr/ADR-010-evidence-immutability.md).
