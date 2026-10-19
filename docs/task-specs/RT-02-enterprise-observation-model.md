# RT-02 — Enterprise Observation Model

## Status

`IMPLEMENTED` for both RT-02A (Enterprise Observation Model) and RT-02B (Belief State Projection). Validation pending independent review.

## Purpose

Mở rộng canonical Observation Model cho tác tử Red Team trong môi trường mạng doanh nghiệp mô phỏng dưới điều kiện quan sát một phần (POMDP / Partial Observability), thiết lập rào chắn tin cậy (Trust Boundary) giữa Execution/Perception và Planning mà tuyệt đối không cho raw executor/tool output đi trực tiếp vào Planner.

## Background

Trong RT-01 (Zero-Knowledge Boundary), rào chắn giữa Evaluation domain (chứa Ground Truth) và Planner domain đã được xác lập, tầm nhìn mục tiêu của Planner được giới hạn trong `visible_target_ids` theo mô hình sương mù chiến tranh (Fog-of-War).

Tuy nhiên, mô hình quan sát kế thừa từ Web Pentest Cyber Range MVP chỉ hỗ trợ 8 loại fact cơ bản (`TARGET`, `SERVICE`, `ENDPOINT`, `PARAMETER`, `CANDIDATE_FINDING`, `CONFIRMED_FINDING`, `ACTION_OUTCOME`, `CONTROL`). Để phục vụ hoạch định tấn công doanh nghiệp (Enterprise Red Team Planning), hệ thống cần biểu diễn các quan sát thực tế về máy chủ, quyền hạn, thông tin xác thực, phiên kết nối, khả năng tiếp cận mạng và tín hiệu phòng thủ mà vẫn bảo toàn tính cô lập của Ground Truth và an toàn Cyber Range.

## Scope

- Bổ sung 7 Enterprise fact types mới vào canonical Observation contract (`observation.schema.json`): `HOST`, `ACCESS`, `CREDENTIAL`, `SESSION`, `REACHABILITY`, `DETECTION_SIGNAL`, `OBJECTIVE`.
- Bảo toàn tương thích ngược 100% với 8 fact types hiện hữu (`TARGET`, `SERVICE`, `ENDPOINT`, `PARAMETER`, `CANDIDATE_FINDING`, `CONFIRMED_FINDING`, `ACTION_OUTCOME`, `CONTROL`).
- Bổ sung các trường provenance trên observation envelope: `source_kind`, `source_target`, `source_session`, `confidence`, `sequence_num`, `evidence_refs`.
- Xây dựng module chuẩn hóa tin cậy `EnterpriseObservationNormalizer` tại `agent/perception/normalizers/enterprise_normalizer.py`.
- Khử bí mật (Secret Redaction) cho credentials: chỉ lưu handle mờ (`credential_id`, `principal`, `credential_kind`, `observed_scope`, `validity_state`); loại bỏ triệt để plaintext password/secret khỏi Planner context.
- Khử chi tiết thực thi phiên (Session Sanitization): biểu diễn session qua opaque reference (`session_id`, `target_id`, `access_level`, `state`); cấm rò rỉ raw shell, socket, hoặc subprocess.
- Cách ly đồ thị mạng toàn cục (Reachability Isolation): reachability chỉ được sinh từ quan sát probe/action hợp lệ; cấm trích xuất từ Docker Compose, allowlist hay scenario manifest.
- Attacker-Observable Detection Signals: chỉ chấp nhận các tín hiệu mà attacker có thể quan sát (`BLOCKED`, `THROTTLED`, `WAF_REJECTION`, `AUTH_LOCKOUT`, `RATE_LIMITED`); cấm nuốt nhật ký SIEM hay điểm phát hiện ẩn của bên phòng thủ.
- Xác thực Objective: chỉ ghi nhận khi đã đạt được qua action hợp lệ kèm liên kết bằng chứng; không leak metadata flag ẩn trước discovery.
- Phân tách Fact và Hypothesis: giả thuyết suy diễn mang `source_kind="PLANNER_INFERENCE"` và không mở khóa tầm nhìn mục tiêu (`visible_target_ids`).
- Enforce Trust Boundary: mọi object thô/untrusted không thể trực tiếp mở visibility hoặc đi vào Planner nếu chưa qua normalizer chuẩn hóa.

## Out of Scope

- RT-02B Belief State projection (`known_hosts`, `credentials`, `sessions` aggregate state trên `StateManager` / `BeliefState`).
- Thêm các hành động tấn công doanh nghiệp mới (`FOOTHOLD`, `PIVOT`, `PRIVESC`).
- Xây dựng Simulation Backend (thuộc RT-04).
- Xây dựng Mini Enterprise Live Range Docker (thuộc RT-06).
- Implement credential dumping hoặc shell execution engine thật.
- Xóa bỏ alias tương thích ngược `allowed_target_ids`.

## Inputs

- Raw tool / executor results (scanner JSON, probe responses, port scan results, session receipts).
- Action context: `action_id`, `run_id`, `source_target`, `source_session`.
- Evidence references (`evidence_refs`).

## Outputs

- Canonical Observation dictionaries tuân thủ nghiêm ngặt schema `agent/planner/contracts/observation.schema.json`.
- Typed canonical facts với provenance, confidence và định danh duy nhất (`fact_id`).

## Interfaces

- `EnterpriseObservationNormalizer`:
  - `normalize_host_discovery(hosts, ...)` -> Observation
  - `normalize_service_discovery(services, ...)` -> Observation
  - `normalize_credentials(credentials, ...)` -> Observation (redacted)
  - `normalize_session(sessions, ...)` -> Observation (sanitized)
  - `normalize_reachability(edges, ...)` -> Observation (probe-only)
  - `normalize_detection_signal(signals, ...)` -> Observation (attacker-observable)
  - `normalize_objective(objectives, ...)` -> Observation (evidence-backed)
  - `normalize_hypothesis(inferred_facts, ...)` -> Observation (`PLANNER_INFERENCE`)
- `validate_canonical_observation(obs)` -> `list[str]` (fail-closed validator).
- `ObservationNormalizer`: cập nhật `_make_fact_id` và `_deduplicate` hỗ trợ structured facts.
- `PlannerStateAdapter.ingest_observation(obs)`: chốt chặn trust boundary kiểm định schema trước state ingestion.
- `AutonomousRunner._ingest_and_update_visibility(obs)`: chốt chặn fog-of-war chặn hypothesis và unnormalized objects.

## Data Contracts

- `agent/planner/contracts/observation.schema.json`:
  - Canonical fact types enum (15 types).
  - Fact value cho phép primitive types và structured object.
  - Root properties bao gồm provenance metadata (`source_kind`, `source_target`, `source_session`, `confidence`, `sequence_num`, `evidence_refs`).
  - Closed Draft 2020-12 object (`additionalProperties: false` ở root và fact definition).

## Dependencies

- RT-00: Enterprise Red Team Planning Rebaseline.
- RT-01: Zero-Knowledge Boundary (Ground Truth isolation & Planner visibility boundary).
- `TASK-006`: Observation Contract baseline.
- `TASK-018`: Observation Normalizer baseline.

## Implementation Requirements

- Luồng dữ liệu bắt buộc: `Raw Result -> Adapter -> Trusted Normalizer -> Canonical Observation -> State Store -> Planner`.
- Tuyệt đối không cho phép raw tool stdout hay arbitrary JSON bypass normalizer vào Planner.
- Toàn bộ timestamp phải là ISO 8601 UTC kết thúc bằng `Z`.
- Plaintext secrets phải được chuyển đổi thành opaque hash handle trước khi vào canonical observation.
- Mọi detection signal phải thuộc tập quan sát được của attacker; cấm ingest defender-private fields (`ground_truth`, `siem_alert_id`, `siem_score`).

## Safety Requirements

- Closed schema: mọi thuộc tính không khai báo đều bị từ chối fail-closed.
- Không public targets, không credentials thực tế, không dynamic actions, không shell injection.
- Lab policy: target allowlist, budget ceiling, rate limit, audit logging và immutable evidence references tiếp tục được bảo toàn.

## Testing Requirements

- Unit test suite: `tests/perception/test_enterprise_observation.py` (10 tests PASS).
- Contract test suite: `tests/contracts/test_contracts.py` (13 tests PASS).
- Boundary test suite: `tests/boundary/test_observation_boundary.py` (5 tests PASS).
- Toàn bộ suite boundary kế thừa RT-01: `tests/boundary/` (21 tests PASS).
- Kiểm thử không suy thoái toàn bộ planner suites và autonomous runner.

## Acceptance Criteria

1. Canonical Observation vocabulary hỗ trợ đầy đủ 15 fact types doanh nghiệp.
2. Raw tool output không bypass normalizer vào Planner.
3. Provenance đầy đủ để truy vết quan sát về action và evidence.
4. Credentials và sessions sử dụng opaque reference semantics, không lộ plaintext secrets hoặc raw subprocess.
5. Reachability không rò rỉ topology ẩn toàn cục.
6. Detection signal không nhận dữ liệu riêng của phía phòng thủ (defender-private SIEM).
7. Objective không bị tổng hợp từ manifest ẩn khi chưa phát hiện thực tế.
8. Visibility của Planner chỉ được mở rộng qua validated canonical observations, không bị mở bởi raw/malformed object hay hypothesis.
9. Ranh giới RT-01A và RT-01B được giữ vững 100%.
10. Không tạo hồi quy (regression) ngoài phạm vi RT-02A.

## Evidence Required

- Lệnh chạy test và kết quả exit code 0 cho `tests/perception/`, `tests/contracts/`, `tests/boundary/`, và `tests/runtime/`.
- Schema diff và JSON Schema validation receipts.
- Báo cáo trạng thái và allowlist đề xuất cho RT-02B trong `TASKS.md`.

## Failure Conditions

- Xuất hiện plaintext password trong canonical observation fact.
- Rò rỉ raw subprocess hoặc shell handle trong SESSION fact.
- Tạo reachability edge từ file Docker Compose hoặc allowlist thay vì quan sát thực.
- Xuất hiện trường Ground Truth (`truth`, `siem_alert_id`, v.v.) trong Planner context.
- Hypothesis tự động mở rộng `visible_target_ids`.
- Bất kỳ test nào trong bộ kiểm thử boundary hoặc contracts bị FAIL.

## Related Guides

- [06 AI Agent Fundamentals](../guides/06-ai-agent-fundamentals.md)
- [07 Planning and Replanning](../guides/07-planning-and-replanning.md)
- [10 MDP and POMDP](../guides/10-mdp-and-pomdp.md)
- [15 Ground Truth](../guides/15-ground-truth.md)
- [17 Cyber Range Safety](../guides/17-cyber-range-safety.md)

## Related Runbooks

- [run-rule-planner.md](../runbooks/run-rule-planner.md)
- [validate-isolation.md](../runbooks/validate-isolation.md)
- [collect-evidence.md](../runbooks/collect-evidence.md)

## Related ADRs

- [ADR-005: Planner, executor, and perception separation](../adr/ADR-005-planner-executor-perception-separation.md)
- [ADR-009: Ground-truth isolation](../adr/ADR-009-ground-truth-isolation.md)
- [ADR-014: Enterprise Red Team Belief State](../adr/ADR-014-enterprise-red-team-belief-state.md)
