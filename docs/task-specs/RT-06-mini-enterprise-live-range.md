# RT-06 — Mini Enterprise Live Validation Range

## Status

- **RT-06 — Mini Enterprise Live Validation Range**: `IMPLEMENTED` (Validation pending review).
- **Frozen Protocol**: `BENCHMARK_PROTOCOL_FREEZE_V1 = SEALED` (Verified intact; zero modifications to benchmark methodology, weights, or held-out scenarios).

## Purpose

Chứng minh tính hợp lệ kiến trúc (Architectural Parity & Simulation-to-Live Validation) của toàn bộ pipeline tác tử hoạch định tấn công:
- `PlannerDecisionContext`;
- Mô hình hành động chuẩn mực (`canonical action model`);
- Bộ đánh giá ràng buộc hành động (`ActionConstraintEvaluator`);
- Cổng an toàn tập trung (`CentralizedSafetyGate`);
- Tác tử hoạch định (`RuleBasedPlanner`, LLM, Hybrid);
- Bộ chuẩn hóa quan sát doanh nghiệp (`EnterpriseObservationNormalizer`);
- Phép chiếu trạng thái nhận thức (`BeliefState`).

Khẳng định rằng cùng một lõi tác tử và chu trình POMDP có thể vận hành không chỉ trên môi trường mô phỏng (`SimulationExecutor`) mà còn qua bộ điều hợp thực thi thực địa (`LiveExecutorAdapter`) trong một cyber range Docker/loopback cô lập, tuân thủ Fog-of-War và Zero-Knowledge.

## Background

Sau khi hoàn thành RT-01..RT-05, hệ thống đã chuẩn hóa toàn bộ không gian hành động, mô hình quan sát và đóng băng giao thức đánh giá benchmark (`BENCHMARK_PROTOCOL_FREEZE_V1 = SEALED`). Để đảm bảo công trình nghiên cứu có giá trị thực tiễn và không chỉ là mô phỏng toán học trừu tượng, RT-06 thiết lập một cyber range doanh nghiệp thu nhỏ (Mini Enterprise Cyber Range).

Bất biến kiến trúc cốt lõi:
```
           Planner (Rule / LLM / Hybrid)
                       │
             canonical proposal
                       │
            ActionConstraintEvaluator
                       │
             CentralizedSafetyGate
                       │
         ┌─────────────┴─────────────┐
         ▼                           ▼
SimulationExecutor          LiveExecutorAdapter
         │                           │
  Simulated Transition        Isolated Enterprise Lab
         │                   (DMZ / INT / RESTR / DECOY)
         │                           │
         ▼                           ▼
canonical observation       EnterpriseObservationNormalizer
         │                           │
         └─────────────┬─────────────┘
                       ▼
                 StateManager
                       │
                  BeliefState
                       │
                     Replan
```

Tác tử tuyệt đối không được gọi shell trực tiếp, không mở socket trực tiếp, không nhìn topology Compose hay IP ẩn, và không nhận plaintext credentials.

## Scope

- **Mini Enterprise Range Topology (`runtime/lab/enterprise_range/topology.py`)**:
  - Phân vùng mạng 4 zone cô lập: Zone A (DMZ, `10.0.1.0/24`), Zone B (Internal Corporate, `10.0.2.0/24`), Zone C (Restricted Crown-Jewel Vault, `10.0.3.0/24`), Zone D (Decoy Honeypot, `10.0.4.0/24`), cùng Clean Baseline (`lab-enterprise-clean`).
  - Ma trận chuyển vùng mạng nghiêm ngặt (`validate_network_transition`), đảm bảo nguyên tắc fail-closed: DMZ chỉ cho phép ingress ngoài; Internal yêu cầu pivot từ DMZ; Restricted yêu cầu pivot từ Internal; Decoy kích hoạt cảnh báo phòng thủ.
- **Micro-Services Doanh Nghiệp Thu Nhỏ (`runtime/lab/enterprise_range/services.py`)**:
  - `DMZServiceHandler`: Cổng biên cung cấp endpoint khám phá (`/api/v1/discovery`), thử thách foothold có kiểm soát (`/api/v1/auth/foothold`), trinh sát máy (`/api/v1/system/recon`), và chứng chỉ tổng hợp cho Zone B.
  - `InternalServiceHandler`: Dịch vụ định danh và ứng dụng nội bộ hỗ trợ pivot có kiểm soát (`/api/v1/pivot`), leo thang đặc quyền hữu hạn (`/api/v1/auth/privesc`), và thu hoạch API token của Restricted Vault.
  - `RestrictedServiceHandler`: Dịch vụ lưu trữ mục tiêu tối thượng (`/api/v1/vault/objective`) chỉ cho phép truy cập khi có session người dùng hợp lệ và chứng chỉ xác thực.
  - `DecoyServiceHandler`: Dịch vụ honeypot kích hoạt tín hiệu phòng vệ (`WAF_REJECTION`, `AUTH_LOCKOUT`).
  - `CleanControlServiceHandler`: Dịch vụ sạch không có lỗ hổng để kiểm thử kiềm chế (restraint).
- **Harness Quản Lý Cyber Range (`runtime/lab/enterprise_range/harness.py`)**:
  - Quản lý vòng đời dịch vụ HTTP loopback trên các cổng ngẫu nhiên độc lập.
  - Kiểm tra rào chắn mạng (firewall isolation boundary) trước mỗi dispatch mạng.
  - Hỗ trợ cô lập/chặn route (`block_route`, `unblock_route`) để kiểm chứng hành vi L2 replan.
- **Docker Compose Topology (`cyber-range/enterprise_range/compose.enterprise.yaml`, `Dockerfile`)**:
  - Cấu hình 4 mạng bridge cô lập không có gateway internet ra ngoài (`internal: true`).
- **Live Executor Adapter (`runtime/lab/live_executor_adapter.py`)**:
  - Tương đương hoàn toàn về pipeline với `SimulationExecutor`.
  - Kiểm tra an toàn tham số (từ chối shell, command, exec, socket, subprocess).
  - Tích hợp `ActionConstraintEvaluator` và `CentralizedSafetyGate`.
  - Chuẩn hóa kết quả thô qua `EnterpriseObservationNormalizer` để tạo observation chuẩn với opaque handles.
  - Xử lý hành động `ACTION-STOP-001` sạch sẽ mà không phát sinh bất kỳ network I/O nào.
- **Live Episode Environment (`runtime/lab/live_environment.py`)**:
  - Cung cấp giao diện tương thích hoàn toàn với `EpisodeEnvironment` cho `PlannerEpisodeRunner`.
  - Quản lý trạng thái tập, khởi tạo Fog-of-War ban đầu (chỉ entry node được nhìn thấy), tính toán ngân sách và điều kiện kết thúc.
- **Bộ Kiểm Thử và 4 Ca Kiểm Chứng Thực Địa (`tests/runtime/test_live_validation_range.py`)**:
  - L1 Straight: DMZ -> Foothold -> Recon -> Pivot Internal -> Privesc -> Pivot Restricted -> Objective Access.
  - L2 Blocked/Replan: Route chính bị chặn, sinh tín hiệu phòng vệ, replan qua route phụ thành công.
  - L3 Clean Control: Tác tử dừng lại sạch sẽ qua STOP khi gặp mục tiêu sạch không có lỗ hổng.
  - L4 Decoy: Tác tử tương tác với honeypot và nhận tín hiệu cảnh báo phòng thủ chuẩn mực.

## Out of Scope

- Bắt đầu thực thi benchmark so sánh chính RT-07 (được giữ lại cho tranche tiếp theo).
- Thay đổi prompt LLM, schema, trọng số chấm điểm hybrid, hay tập kịch bản held-out đã đóng băng.
- Triển khai Active Directory thật, kernel exploits, credential dumping bộ nhớ OS thật, hay các payload phá hoại.
- Phá vỡ tính tương thích ngược với ShopLab / e-commerce lab hiện hữu.

## Inputs

- `actions/catalog/action-catalog.json`: Danh mục 9 canonical actions.
- `agent/perception/normalizers/enterprise_normalizer.py`: Bộ chuẩn hóa quan sát doanh nghiệp.
- `runtime/evaluators/action_evaluator.py`: Bộ đánh giá điều kiện tiên quyết hành động.
- `runtime/safety/discovery_gate.py`: CentralizedSafetyGate và KillSwitch.
- `runtime/planners/rule_based_planner.py`: Rule-Based Planner baseline.
- `runtime/orchestration/planner_runner.py`: Vòng lặp điều phối tập hoạch định.

## Outputs

- `runtime/lab/enterprise_range/topology.py`: Định nghĩa topology mạng 4 zone và bộ kiểm tra rào chắn.
- `runtime/lab/enterprise_range/services.py`: Handlers micro-service HTTP bounded của các zone.
- `runtime/lab/enterprise_range/harness.py`: Harness quản lý live range và tường lửa biên.
- `runtime/lab/enterprise_range/server.py`: Điểm nhập container độc lập.
- `cyber-range/enterprise_range/Dockerfile`: Định nghĩa build container range.
- `cyber-range/enterprise_range/compose.enterprise.yaml`: Cấu hình Docker Compose cô lập.
- `runtime/lab/live_executor_adapter.py`: Bộ điều hợp thực thi live đạt tính tương đương với SimulationExecutor.
- `runtime/lab/live_environment.py`: Môi trường live episode cho PlannerEpisodeRunner.
- `tests/runtime/test_live_validation_range.py`: Bộ kiểm thử 21 test bao phủ toàn bộ bất biến A-W.

## Interfaces

- `LiveExecutorAdapter.execute_proposal(proposal, belief_state=None, approval_token=None) -> LiveExecutionResult`
- `LiveEpisodeEnvironment.reset() -> BeliefState`
- `LiveEpisodeEnvironment.step(proposal) -> EpisodeStepResult`
- `EnterpriseLiveRangeHarness.start() -> dict[str, str]`
- `EnterpriseLiveRangeHarness.stop() -> None`
- `EnterpriseLiveRangeHarness.reset_all() -> None`
- `EnterpriseLiveRangeHarness.dispatch_bounded_request(target_id, method, path, body, from_target_id, timeout) -> dict`

## Data Contracts

- Bounded Proposal Mapping: Tuân thủ `action.schema.json` với các tham số bị giới hạn; cấm tuyệt đối shell command/script.
- Canonical Observation: Tuân thủ `observation.schema.json` với opaque handles (`SESS-OPAQ-*`, `CRED-OPAQ-*`, `FACT-*`).
- Secret Redaction: Không chứa token plaintext (`raw_secret`, `secret_token`) trong payload gửi tới planner hay evidence bundle.

## Dependencies

- Python 3.10+ tiêu chuẩn (sử dụng thư viện chuẩn `http.server`, `http.client`, `urllib.parse`, `threading`, `json`).
- `actions.catalog.action_registry`: Quản lý danh mục hành động chuẩn mực.
- `agent.memory.state`: StateManager và BeliefState projection.
- `agent.perception.normalizers`: EnterpriseObservationNormalizer.
- `runtime.evaluators.action_evaluator`: ActionConstraintEvaluator.
- `runtime.safety.discovery_gate`: CentralizedSafetyGate.

## Implementation Requirements

1. **Strict Pipeline Parity**: Chuỗi xử lý của `LiveExecutorAdapter` phải bit-for-bit tương đương về mặt ngữ nghĩa với `SimulationExecutor`.
2. **Fog-of-War Enforcement**: Tại $t=0$, Planner chỉ được nhìn thấy entry target (`lab-enterprise-dmz`). Các node nội bộ chỉ được phát hiện sau khi quan sát thấy qua `HOST_RECON`.
3. **Cross-Zone Access Control**: Yêu cầu session hợp lệ trên node nguồn trước khi cho phép pivot sang node đích trong zone kế tiếp.
4. **Secret Isolation**: Secret tổng hợp chỉ lưu trữ ở phía service/executor; Planner chỉ nhận được opaque handle định danh.
5. **Clean STOP Semantics**: Hành động `ACTION-STOP-001` phải kết thúc tập ngay lập tức mà không phát sinh bất kỳ request mạng nào.

## Safety Requirements

- Cổng an toàn trung tâm (`CentralizedSafetyGate`) và `KillSwitch` có quyền phủ quyết tuyệt đối; khi kích hoạt hoặc bị từ chối, zero network dispatch được gửi đi.
- Lab mode là bắt buộc (`lab_mode=True`); từ chối mọi mục tiêu nằm ngoài `target_allowlist`.
- Từ chối ngay lập tức mọi tham số proposal chứa các khóa nguy hiểm (`command`, `shell`, `exec`, `eval`, `powershell`, `subprocess`, v.v.).

## Testing Requirements

- Bộ kiểm thử `tests/runtime/test_live_validation_range.py` phải đạt 100% pass với 21 bài test bao phủ các bất biến từ A đến W.
- Kiểm chứng 4 ca thực địa: L1 (Straight), L2 (Blocked/Replan), L3 (Clean Control), L4 (Decoy).
- Toàn bộ suite kiểm thử `tests/runtime/test_benchmark_protocol.py` (20 tests) phải giữ nguyên kết quả pass.
- Không gây hồi quy lên các test suite hiện hữu của perception, contracts, runtime, và ShopLab.

## Acceptance Criteria

1. Tất cả 21 bài kiểm thử trong `tests/runtime/test_live_validation_range.py` pass.
2. `BENCHMARK_PROTOCOL_FREEZE_V1 = SEALED` được giữ nguyên vẹn; các giá trị băm của prompt và trọng số chấm điểm không bị thay đổi.
3. Không có bất kỳ shell command tùy ý nào được chuyển đến hệ thống host hay container.
4. Tác tử `RuleBasedPlanner` hoàn thành chuỗi thâm nhập L1 (21 bước) đạt mục tiêu tối thượng mà không cần biết trước topology Compose.

## Evidence Required

- Biên bản kiểm thử `test_live_validation_range.py` (21 passed).
- Biên bản kiểm thử `test_benchmark_protocol.py` (20 passed).
- Biên bản toàn bộ suite `tests/runtime/` (618 passed, 2 skipped, 387 subtests passed).
- Biên bản kiểm tra scaffold `validate_scaffold.py` xác nhận 0 hồi quy vi phạm.

## Failure Conditions

- Bất kỳ hành vi bypass nào vượt qua `CentralizedSafetyGate` hoặc `ActionConstraintEvaluator`.
- Plaintext secrets lọt vào `BeliefState`, quan sát hoặc evidence bundle.
- Chỉnh sửa các file đã đóng băng của benchmark protocol (`evaluation/experiments/protocol_freeze.json`, v.v.).
- Bắt đầu chạy benchmark held-out RT-07 trước khi có phê duyệt.

## Related Guides

- `docs/guides/03-cyber-range-fundamentals.md`: Nền tảng thiết kế môi trường cyber range.
- `docs/guides/17-cyber-range-safety.md`: Nguyên tắc an toàn và kiểm soát rủi ro trong cyber range.
- `docs/guides/07-planning-and-replanning.md`: Cơ chế hoạch định và tái hoạch định khi gặp chướng ngại.

## Related Runbooks

- `docs/runbooks/start-cyber-range.md`: Quy trình khởi động cyber range.
- `docs/runbooks/stop-cyber-range.md`: Quy trình dừng và dọn dẹp cyber range.
- `docs/runbooks/validate-isolation.md`: Kiểm tra tính cô lập của phân vùng mạng.

## Related ADRs

- `docs/adr/ADR-004-cyber-range-network-architecture.md`: Kiến trúc phân vùng mạng cyber range.
- `docs/adr/ADR-005-safety-gate-and-authorization.md`: Cổng an toàn tập trung và cơ chế ủy quyền.
- `docs/adr/ADR-007-observation-normalization-and-provenance.md`: Chuẩn hóa quan sát và lưu vết xuất xứ.
