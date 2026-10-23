# RT-04 — Enterprise Attack Simulator

## Status

`IMPLEMENTED` for RT-04A (Hidden Scenario & True-State Model), RT-04B (Transition & Observation Simulator), and RT-04C (Unified Episode Environment & Gymnasium Adapter). Validation pending independent review.

## Purpose

Thiết lập mô hình kịch bản ẩn (Hidden Scenario Contract), mô hình trạng thái thực (True State Contract), và Transition Engine cùng Observation Generator chuẩn mực làm nền tảng cho Enterprise Attack Simulator. Đảm bảo phân tách vật lý tuyệt đối giữa môi trường giả lập (Evaluation / Simulation Environment) và miền tác tử hoạch định (Planner Domain) theo nguyên tắc Zero-Knowledge và Fog-of-War (POMDP).

## Background

Sau khi RT-01 thiết lập rào chắn Zero-Knowledge (Fog-of-War), RT-02 chuẩn hóa mô hình quan sát doanh nghiệp (Enterprise Observation) và phép chiếu Belief State tất định, và RT-03 xây dựng Generic TTP Action Contract cùng Action Constraint Evaluator, hệ thống cần một môi trường giả lập tấn công mạng doanh nghiệp (Enterprise Attack Simulator) để đánh giá năng lực hoạch định của các planner trước khi triển khai trên Cyber Range thực tế (tuân thủ ADR-007).

Trong kiến trúc này, True State và Hidden Scenario đại diện cho chân lý ẩn của môi trường (Ground Truth Environment). Tác tử Red Team (Planner) tuyệt đối không được đọc trực tiếp cấu trúc mạng, lỗ hổng ẩn, thông tin xác thực, vị trí crown jewel hay ngưỡng phát hiện phòng thủ. Tác tử chỉ tiếp nhận thông tin gián tiếp thông qua các quan sát chuẩn (Canonical Observations) để cập nhật Belief State.

## Scope

- Thiết lập Hidden Scenario Schema chuẩn mực tuân thủ JSON Schema Draft 2020-12 closed object (`additionalProperties: false`) tại `runtime/simulation/contracts/scenario.schema.json`.
- Thiết lập True State Schema chuẩn mực tuân thủ Draft 2020-12 closed object tại `runtime/simulation/contracts/true-state.schema.json`.
- Xây dựng các dataclass mô hình Python độc lập trong `runtime/simulation/models/`:
  - `scenario.py`: `HiddenScenario`, `HiddenNode`, `HiddenTopology`, `HiddenCredential`, `ObjectiveDefinition`, `DetectionModel`, `ScenarioTransition`.
  - `true_state.py`: `TrueState`, `NodeTrueState`, `SimulatedSession`, `CredentialTruth`, `ReachabilityEdge`, `ObjectiveTruth`, `DefenderState`, `SimulatorActionRecord`.
  - `evaluator_view.py`: `ScenarioEvaluationView` (giao diện chỉ đọc phục vụ bộ chấm điểm và benchmark đánh giá).
- Xây dựng module canonical loader và bộ thẩm định toàn vẹn ngữ nghĩa tại `runtime/simulation/loader.py`:
  - Thẩm định closed schema bằng `validate_shape`.
  - Thẩm định liên kết ngữ nghĩa (semantic integrity): entry seed tồn tại trong danh mục node, mục tiêu objective thuộc node hợp lệ, cạnh topology kết nối đúng node, credential gán đúng node.
- Xây dựng 4 kịch bản mẫu khai báo chuẩn mực (Declarative Scenario Fixtures) tại `runtime/simulation/fixtures/scenarios/`:
  - `scenario_s1_straight.json`: Tiến trình 3 tầng thẳng (Entry foothold -> Internal pivot -> Crown jewel DB).
  - `scenario_s2_decoy.json`: Tiến trình doanh nghiệp có nhánh bẫy honeypot và honey-token gây báo động phòng thủ.
  - `scenario_s3_blocked.json`: Đường tấn công chính bị firewall chặn (`is_blocked: true`), đòi hỏi planner phải replan qua jump-box.
  - `scenario_s4_clean.json`: Hệ thống đã được vá an toàn, không có lỗ hổng khai thác và không thể đạt được mục tiêu (clean control baseline).
- Xây dựng Transition Engine (`runtime/simulation/engine/transition_engine.py`):
  - Biến action được authorized thành copy-on-write `new_true_state` và danh sách raw simulated observations.
  - Đánh giá điều kiện thực tế (preconditions thực trên HiddenScenario + TrueState).
  - Tích lũy `noise_delta` và cập nhật máy trạng thái phòng thủ (`QUIET < MONITORING < ALERTED < CONTAINED`).
- Xây dựng Observation Generator (`runtime/simulation/engine/observation_generator.py`):
  - Sinh envelope `Observation` canonical tuân thủ schema Draft 2020-12.
  - Tẩy xóa triệt để (fail-closed sanitization) các secret và token rò rỉ Ground Truth.
  - Tự động phát sinh fact fallback `ACTION_OUTCOME` failure khi không khớp template.
- Xây dựng Simulation Executor (`runtime/simulation/engine/simulation_executor.py`):
  - Tích hợp chuỗi khép kín: Planner Proposal -> ActionConstraintEvaluator -> CentralizedSafetyGate -> TransitionEngine -> ObservationGenerator -> StateManager -> BeliefState.
- Xây dựng Bootstrap Observation Generator (`runtime/simulation/bootstrap.py`):
  - Phát sinh canonical observation tại $t=0$ chỉ chứa duy nhất `entry_seed`, bảo toàn Fog-of-War.
- Xây dựng Canonical Episode Environment (`runtime/simulation/environment.py`):
  - Quản trị vòng đời tập mô phỏng (episode loop): reset, step, budget, kill switch, terminal conditions (OBJECTIVE_ACHIEVED, PLANNER_STOP, CONTAINED, MAX_STEPS, BUDGET_EXHAUSTED).
- Xây dựng Farama Gymnasium Adapter (`runtime/simulation/gym_adapter.py`):
  - `SimulationGymEnv(gym.Env)` tuân thủ API Farama Gym v1.4+, action masking động, vector quan sát 16 chiều trích xuất 100% từ BeliefState.
- Xây dựng test suite toàn diện:
  - `tests/simulation/test_scenario_contract.py`: Kiểm thử hợp đồng kịch bản Draft 2020-12 và S1–S4.
  - `tests/simulation/test_true_state_contract.py`: Kiểm thử hợp đồng True State và tính độc lập với Belief State.
  - `tests/simulation/test_scenario_loader.py`: Kiểm thử nạp kịch bản và tính toàn vẹn ngữ nghĩa fail-closed.
  - `tests/simulation/test_evaluator_view.py`: Kiểm thử giao diện chỉ đọc cho evaluation.
  - `tests/simulation/test_transition_engine.py`: Kiểm thử Transition Engine trên S1–S4, copy-on-write, auth, determinism.
  - `tests/simulation/test_observation_generator.py`: Kiểm thử sinh quan sát canonical và chống rò rỉ Ground Truth.
  - `tests/simulation/test_simulation_executor.py`: Kiểm thử pipeline thực thi end-to-end với safety gate và replan.
  - `tests/simulation/test_bootstrap.py`: Kiểm thử sinh quan sát bootstrap tại $t=0$.
  - `tests/simulation/test_episode_environment.py`: Kiểm thử canonical EpisodeEnvironment lifecycle và điều kiện dừng.
  - `tests/simulation/test_gym_adapter.py`: Kiểm thử adapter Gymnasium và action masking.
  - `tests/simulation/test_episode_replay.py`: Kiểm thử tính tất định replay bit-for-bit.
  - `tests/simulation/test_legacy_rl_compat.py`: Kiểm thử tính tương thích ngược và deprecation của legacy RL env.
  - `tests/boundary/test_simulation_boundary.py`: Kiểm thử ranh giới ngăn chặn rò rỉ chân lý ẩn sang Planner.

## Out of Scope

- Thay đổi các bộ lập lịch Rule/LLM/Hybrid — thuộc RT-05.
- Cấu hình hạ tầng mạng Docker Cyber Range — thuộc RT-06.
- Đào tạo RL policy hay thuật toán huấn luyện — thuộc RT-07.

## Inputs

- Draft 2020-12 JSON Schema specification.
- Bộ từ vựng quan sát chuẩn từ RT-02 (`agent/planner/contracts/observation.schema.json`).
- Thang đo quyền truy cập chuẩn từ RT-03 (`NONE < FOOTHOLD < USER < PRIVILEGED < SYSTEM`).
- Quy ước nhận diện mục tiêu lab (`lab-[a-z0-9-]+`).

## Outputs

- `runtime/simulation/contracts/scenario.schema.json`.
- `runtime/simulation/contracts/true-state.schema.json`.
- `runtime/simulation/models/scenario.py`.
- `runtime/simulation/models/true_state.py`.
- `runtime/simulation/models/evaluator_view.py`.
- `runtime/simulation/loader.py`.
- `runtime/simulation/fixtures/scenarios/scenario_s1_straight.json`.
- `runtime/simulation/fixtures/scenarios/scenario_s2_decoy.json`.
- `runtime/simulation/fixtures/scenarios/scenario_s3_blocked.json`.
- `runtime/simulation/fixtures/scenarios/scenario_s4_clean.json`.
- `tests/simulation/test_scenario_contract.py`.
- `tests/simulation/test_true_state_contract.py`.
- `tests/simulation/test_scenario_loader.py`.
- `tests/simulation/test_evaluator_view.py`.
- `tests/boundary/test_simulation_boundary.py`.

## Interfaces

- `ScenarioLoader`:
  - `load_from_file(path: Path | str) -> HiddenScenario`
  - `load_from_dict(data: Mapping[str, Any]) -> HiddenScenario`
  - `validate_scenario_data(data: Mapping[str, Any]) -> list[str]`
- `HiddenScenario`:
  - `create_initial_true_state(run_id: str, seed: int | None = None) -> TrueState`
  - `get_node(node_id: str) -> HiddenNode | None`
  - `get_entry_node() -> HiddenNode`
  - `get_reachable_neighbors(node_id: str) -> list[str]`
  - `to_dict() -> dict[str, Any]`
  - `deterministic_hash() -> str`
- `TrueState`:
  - `to_dict() -> dict[str, Any]`
  - `from_dict(data: Mapping[str, Any]) -> TrueState`
  - `get_node_access_level(node_id: str) -> str`
  - `has_active_session(node_id: str) -> bool`
  - `is_objective_achieved() -> bool`
  - `deterministic_hash() -> str`
- `ScenarioEvaluationView`:
  - `is_objective_achieved() -> bool`
  - `get_detection_state() -> str`
  - `get_accumulated_noise() -> float`
  - `get_compromised_node_ids() -> frozenset[str]`
  - `get_discovered_node_ids_in_belief() -> frozenset[str]`
  - `get_alignment_summary() -> dict[str, Any]`

## Data Contracts

- `HiddenScenario`: Định nghĩa kịch bản ẩn (node inventory, topology edges, vulnerabilities, credentials, detection model, transitions).
- `TrueState`: Biểu diễn chân lý thời gian chạy của môi trường (node states, active sessions, credential truth, reachability truth, objective truth, defender detection state).
- `ScenarioEvaluationView`: Cấu trúc chỉ đọc dành riêng cho Evaluation tooling chấm điểm.

## Dependencies

- RT-01: Zero-Knowledge Boundary & Fog-of-War scoping.
- RT-02: Enterprise Observation Model & Belief State Projection.
- RT-03: Generic TTP Action Contract & Action Constraint Evaluator.
- ADR-007: Simulator before Cyber Range RL.

## Implementation Requirements

- Draft 2020-12 closed object (`additionalProperties: false`) cho mọi schema.
- True State và Belief State là hai mô hình hoàn toàn độc lập; True State tuyệt đối không kế thừa hay subclass `BeliefState`.
- Không chứa mã thực thi tùy ý, eval string, shell command hoặc payload trong định nghĩa kịch bản.
- Tính tất định: cùng kịch bản, cùng random seed sinh ra biểu diễn và chuỗi băm đồng nhất 100%.

## Safety Requirements

- Miền Planner tuyệt đối không được truy cập hay import các module thuộc `runtime.simulation`.
- Initial Fog-of-War invariant: tại $t=0$, planner chỉ thấy duy nhất node `entry_seed`; toàn bộ topology, lỗ hổng và credential ẩn không bị rò rỉ.
- Action Catalog giữ nguyên tính trung lập với mục tiêu; kịch bản không rewrite action definitions.

## Testing Requirements

- Hợp đồng kịch bản (`tests/simulation/test_scenario_contract.py`): thẩm định Draft 2020-12, hợp thức hóa S1–S4, từ chối thuộc tính lạ.
- Hợp đồng True State (`tests/simulation/test_true_state_contract.py`): thẩm định Draft 2020-12, xác nhận phân tách vật lý với Belief State, tuần tự hóa tất định.
- Nạp kịch bản (`tests/simulation/test_scenario_loader.py`): kiểm thử toàn vẹn tham chiếu ngữ nghĩa fail-closed.
- Ranh giới giả lập (`tests/boundary/test_simulation_boundary.py`): quét AST đảm bảo Planner không import simulation, kiểm tra không rò rỉ mục tiêu/topology/credential tại $t=0$.

## Acceptance Criteria

1. Hidden Scenario contract tồn tại và tuân thủ Draft 2020-12 closed object.
2. True State contract tồn tại và tuân thủ Draft 2020-12 closed object.
3. 4 kịch bản S1–S4 được định nghĩa đầy đủ và thẩm định thành công.
4. Ranh giới vật lý được bảo vệ: Planner không thể đọc chân lý môi trường ẩn.
5. True State và Belief State là hai mô hình tách biệt.
6. Hỗ trợ mô phỏng tất định và tái lập replay qua random seed.
7. Toàn bộ test suite RT-01, RT-02, RT-03 tiếp tục PASS 100%.

## Evidence Required

- Báo cáo chạy test suite: `tests/simulation`, `tests/boundary`, `tests/contracts`.
- Biên bản thẩm định cấu trúc scaffold validator.

## Failure Conditions

- Module trong `runtime/planners` hay `agent/planner` import trực tiếp `runtime.simulation`.
- Kịch bản chứa shell command hoặc exploit payload.
- True State kế thừa từ Belief State.
- Hồi quy trên các test suite RT-01, RT-02, RT-03.

## Related Guides

- `docs/guides/03-cyber-range-fundamentals.md`
- `docs/guides/10-mdp-and-pomdp.md`
- `docs/guides/17-cyber-range-safety.md`

## Related Runbooks

- `docs/runbooks/run-rule-planner.md`
- `docs/runbooks/run-experiment.md`

## Related ADRs

- `docs/adr/ADR-007-simulator-before-cyber-range-rl.md`
- `docs/adr/ADR-009-ground-truth-isolation.md`
- `docs/adr/ADR-014-enterprise-red-team-belief-state.md`
