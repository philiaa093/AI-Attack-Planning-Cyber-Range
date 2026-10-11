# TASK-012 — Web target A

## Status

`IMPLEMENTED`.

## Purpose

Duy trì đặc tả target A lịch sử và xác định điều kiện kiểm chứng lại khi web target A thay đổi UI, build hoặc upstream.

## Background

TASKS.md ghi `VALIDATED` cho slice Docker lịch sử; marker của spec là `IMPLEMENTED` và target A có identity riêng. TARGETS-012 ghi phạm vi unit-test lịch sử gồm health/reset/family/schema, không phải image digest hay upstream pin. Linkage RUNTIME-004 cần đối chiếu riêng về phạm vi/hash trước tái sử dụng. Validation cũ không áp dụng tự động cho snapshot mới.

## Scope

Phân biệt giữ target A hiện hữu với thay bằng upstream hoặc target khác. Chỉ ghi target/version/source/manifest/image provenance khi record thực có; product/runtime/safety/provenance/replay dùng acceptance tại [SL-07](SL-07-lab-runtime.md), [SL-08](SL-08-discovery-safety.md) và [SL-09](SL-09-observation-planner.md).

## Out of Scope

Không mặc nhiên thay target A bằng Oscar, không đổi target ID chỉ vì UI, không thêm lỗi, payload, workflow khai thác hoặc lệnh live. Không sửa registry, compose, manifest, contracts, evidence hoặc safety defaults.

## Inputs

Identity target A hiện có, approved target snapshot, source/version/provenance có chứng cứ, mapping được duyệt nếu replacement và impact assessment.

## Outputs

Danh sách phần giữ nguyên, phần chịu ảnh hưởng và receipts mới cần thiết cho target A; không phải target build, runtime deployment hay approval.

## Interfaces

Target A chỉ giao tiếp qua identity đã đăng ký, gateway và policy có thẩm quyền. Links/forms/redirects/auth responses tương lai phải theo SL-08; planner chỉ dùng observed state theo SL-09.

## Data Contracts

Record target ID, snapshot identity, source/version/manifest/image reference chỉ khi observed. Image tag `latest` lịch sử không phải immutable pin; không suy digest, product acceptance hoặc isolation từ tag.

## Dependencies

TASK-011

## Implementation Requirements

1. Giữ target A lịch sử khi chỉ UI/build thay đổi; đánh giá tác động tới product flow, authentication, redirects, storage và gateway.
2. Nếu upstream thay thế, cần approved mapping giữa target A và identity mới; không coi Oscar candidate bị chặn execution là replacement.
3. Rà soát provenance, product acceptance và baseline mới theo SL-07 trước runtime; không đổi routes/schema để ép tương thích target cũ.
4. Nêu rõ evidence/status lịch sử được bảo toàn, không chuyển thành receipt cho snapshot mới.

## Safety Requirements

Mọi execution vẫn cần lab mode, target/action allowlist, approval, rate/order/budget, refusal, audit và restore. Target/identity malformed, unknown hoặc missing approval phải zero dispatch.

## Testing Requirements

Tạo impact assessment và receipts mới cho thành phần A bị ảnh hưởng; product, isolation, restore và gateway kiểm chứng theo SL-07. Kiểm tra discovery/safety và observed-state provenance theo SL-08/SL-09 khi thuộc scope được duyệt.

## Acceptance Criteria

Phân loại rõ giữ nguyên/thay đổi/thay thế của target A, có baseline và receipts cần chạy lại; provenance không bịa; evidence cũ không bị thay đổi. Không coi HTTP status hoặc UI rendering là product acceptance hay confirmed finding.

## Evidence Required

Dẫn evidence lịch sử theo identity/phạm vi của target A. Snapshot mới cần run ID, UTC, source, hash, redaction, expected/observed và approval trước khi claim observed.

## Failure Conditions

Không xác định được identity/mapping, source conflict, missing provenance, product/isolation/restore gap, evidence-loss risk hoặc safety mismatch: không handoff runtime, giữ status/evidence lịch sử.

## Related Guides

Xem web-security và cyber-range safety guides; SL-07–SL-09 là acceptance chuẩn cho runtime và assessment.

## Related Runbooks

Không có lệnh live trong spec; runbook chỉ có hiệu lực sau scope và per-run approval riêng.

## Related ADRs

ADR-003 giữ family boundary; ADR-012/ADR-013 giữ policy gate và runtime scope.
