# RT-05 — Planner Integration & Benchmark Baselines

## Status

- **RT-05A — Common Planner Episode Interface & Rule Baseline**: `IMPLEMENTED` (Validation pending review).
- **RT-05A1 — Benchmark Action-Space Normalization**: `IMPLEMENTED` (Validation pending review).
- **RT-05B — LLM Planner Episode Integration & Structured TTP Prompting**: `IMPLEMENTED` (Validation pending review).
- **RT-05C — Hybrid Belief-State Planner (Proposed Method)**: `IMPLEMENTED` (Validation pending review).
- **RT-05D — Benchmark Protocol & Methodology Freeze**: `IMPLEMENTED` (Frozen for evaluation).

## Purpose

Thiết lập một lớp tích hợp tập hoạch định chuẩn mực, trung lập với planner (Planner-Neutral Episode Integration Layer) cho phép các chiến lược hoạch định khác nhau (Rule-Based baseline, LLM planner, Hybrid router) cùng tương tác với `EpisodeEnvironment` thông qua một bề mặt thông tin an toàn duy nhất (`PlannerDecisionContext`). Đảm bảo nguyên tắc Zero-Knowledge và Fog-of-War tuyệt đối, không rò rỉ Ground Truth hay reward cơ học, và xây dựng Rule-Based Planner như baseline đầu tiên thực thi tất định trên 4 kịch bản chuẩn mực S1–S4.

## Background

Sau khi RT-01..RT-04 hoàn tất, hệ thống đã thiết lập:
1. Rào chắn Zero-Knowledge / Fog-of-War (RT-01).
2. Mô hình quan sát doanh nghiệp (Enterprise Observation) và phép chiếu Belief State tất định (RT-02).
3. Generic TTP Action Catalog và Action Constraint Evaluator (RT-03).
4. Enterprise Attack Simulator với TrueState, HiddenScenario, Transition/Observation engine, EpisodeEnvironment và Farama Gymnasium adapter (RT-04).

Để so sánh công bằng giữa các thuật toán hoạch định (Rule vs LLM vs Hybrid), kiến trúc benchmark bắt buộc mọi planner phải nhận cùng một bề mặt thông tin an toàn (Planner-Safe Information Surface). Không cho phép từng planner có một đường tích hợp riêng hoặc đọc trực tiếp trạng thái simulator. Chu trình chuẩn:
```
EpisodeEnvironment
  -> PlannerDecisionContext (chỉ chứa thông tin an toàn cho planner)
  -> CandidateGenerator (sinh đề xuất từ visible targets & ActionRegistry)
  -> Planner (Rule / LLM / Hybrid quyết định)
  -> Proposal
  -> EpisodeEnvironment.step()
```

## Scope

### RT-05A — Common Planner Episode Interface & Rule Baseline (Implemented)
- **PlannerDecisionContext (`runtime/planners/planner_context.py`)**:
  - Dataclass bất biến (`frozen=True`) chứa thông tin an toàn cho planner: `run_id`, `step_index`, `max_steps`, `current_phase`, `remaining_budget`, `max_budget`, `visible_target_ids`, `belief_state`, `candidate_proposals`, `eligible_proposals`, `rejected_proposals`, `previous_outcome`, `objective_statement`, `action_history`.
  - Cơ chế quét đệ quy thời gian chạy (`_scan_for_forbidden_data`) từ chối các trường chân lý ẩn (`true_state`, `hidden_scenario`, `hidden_nodes`, `hidden_topology`, `hidden_credentials`, `detection_model`, `defender_state`, `evaluator_view`) và reward cơ học (`reward`, `gym_reward`).
  - Hợp đồng vết quyết định (`PlannerDecisionTrace`): ghi lại `step_index`, `visible_targets`, `candidate_action_ids`, `eligible_candidates`, `chosen_proposal`, `rationale`, `reason_code`, `observable_prior_outcome`, `planning_latency_ms`.
- **Canonical Candidate Proposal Generator (`runtime/planners/candidate_generator.py`)**:
  - Tái sử dụng thống nhất bởi mọi Planner và `SimulationGymEnv`.
  - Sinh candidate proposals thuần túy từ `belief_state.visible_target_ids` và `ActionRegistry`. Tuyệt đối không đọc danh mục node của `HiddenScenario`.
  - Không đọc danh sách target allowlist của `CentralizedSafetyGate`.
  - Sử dụng `ActionConstraintEvaluator` để phân tách rạch ròi giữa hành động hợp lệ (`eligible_proposals`) và bị từ chối có lý do (`rejected_proposals`), gán chi phí `step_cost` và `noise_cost`.
- **Gym Action-Mask Non-Leakage (`runtime/simulation/gym_adapter.py`)**:
  - `SimulationGymEnv._generate_admissible_proposals` ủy quyền trực tiếp cho `CandidateGenerator`.
  - Đảm bảo tại $t=0$, không gian hành động và action mask không tiết lộ số lượng hoặc định danh của các node ẩn.
- **Rule-Based Planner Baseline (`runtime/planners/rule_based_planner.py`)**:
  - Tích hợp giao diện `_plan_context(context: PlannerDecisionContext) -> PlannerDecision`.
  - Duy trì tính tương thích ngược hoàn toàn với các kiểm thử evidence-review cũ (`PlanningInput`).
  - Phân cấp ưu tiên ngữ nghĩa chuẩn mực (Semantic Priority Hierarchy):
    1. `OBJECTIVE_COMPLETE`: Dừng nếu mục tiêu đã được xác nhận đạt được trong `BeliefState`.
    2. `BUDGET_EXHAUSTED`: Dừng an toàn khi ngân sách hành động hoặc bước chạy chạm giới hạn.
    3. `NETWORK_RECON` (`ACTION-RECON-001`, `ACTION-DISCOVERY-001`): Khám phá dịch vụ trên node hiển thị mới.
    4. `SERVICE_SCAN` (`ACTION-SCAN-001`): Quét dịch vụ khi đã thấy cổng nhưng chưa có finding.
    5. `INITIAL_ACCESS_FOOTHOLD` (`ACTION-WEB-001`): Khai thác lỗ hổng dịch vụ để tạo session ban đầu.
    6. `HOST_RECON` (`ACTION-HOSTRECON-001`): Thu thập cấu hình nội bộ trên host có session.
    7. `CREDENTIAL_DISCOVERY` (`ACTION-AUTH-001`, `ACTION-CREDS-001`): Thu hoạch chứng chỉ trên host đã kiểm soát.
    8. `LATERAL_PIVOT` (`ACTION-FLOW-001`, `ACTION-PIVOT-001`): Di chuyển ngang sang host mới có reachability và credentials.
    9. `PRIVILEGE_ESCALATION` (`ACTION-PRIVESC-001`): Leo thang đặc quyền trên session hiện hữu.
    10. `PURSUING_MISSION_OBJECTIVE` (`ACTION-FLOW-002`, `ACTION-OBJECTIVE-001`): Truy cập mục tiêu crown jewel khi đủ điều kiện.
    11. `NO_VALID_CANDIDATE`: Dừng sạch sẽ khi không còn hành động tiến trình nào khả thi.
  - Tính tất định: Sắp xếp tie-breaking ổn định theo `(target_id, from_node_id, has_credential, credential_id, action_id)`.
  - Theo dõi lịch sử thất bại và tránh lặp lại hành động/đường pivot đã thất bại mà không cần trạng thái nội bộ ẩn.
- **Common Episode Runner (`runtime/orchestration/planner_runner.py`)**:
  - `PlannerEpisodeRunner(env, planner, candidate_generator)`: Điều phối vòng lặp tập hoạch định qua `PlannerDecisionContext`.
  - Độc lập hoàn toàn giữa môi trường giả lập và logic planner.

### RT-05A1 — Benchmark Action-Space Normalization (Implemented)
- Chuẩn hóa không gian hành động thử nghiệm thành 9 canonical generic benchmark actions.
- Loại bỏ hoàn toàn sự trùng lặp bí danh (legacy aliases) trong không gian ứng viên của tác tử.
- Ánh xạ tự động giữa canonical actions và legacy scenario execution identifiers.

### RT-05B — LLM Belief-State Planner Baseline (Implemented)
- Tích hợp Pure LLM Baseline sử dụng cùng `PlannerDecisionContext`, `CandidateGenerator`, và 9 canonical actions.
- Bộ tuần tự hóa ngữ cảnh an toàn `serialize_llm_context` có cơ chế quét và chặn rò rỉ Ground Truth và reward.
- Server-side candidate membership validation: mô hình chọn qua khóa ứng viên (`CAND-001`), hệ thống phục hồi proposal thật từ bộ nhớ; không tin cậy các trường do mô hình tự gửi.
- Xử lý quyết định không hợp lệ theo nguyên tắc fail-closed (`fallback_to_rule=False` mặc định).
- Dữ liệu quan sát được đóng gói an toàn (Prompt Injection Resilience).

### RT-05C — Hybrid Belief-State Planner (Proposed Method) (Implemented)
- Phương pháp nghiên cứu đề xuất: Kết hợp LLM semantic ranking và deterministic symbolic scoring thành mô hình hợp nhất (fusion ranking).
- Bất biến nghiên cứu: Rule, LLM, và Hybrid nhận cùng một bề mặt thông tin an toàn. Hybrid chỉ thực hiện thêm tính toán (computation) trên cùng dữ liệu quan sát, không nhận thêm quan sát ẩn.
- Cấu hình chấm điểm phiên bản hóa `HYBRID_SCORING_V1` với trọng số minh bạch:
  $$HybridScore(c) = w_{sem} \cdot S_{sem}(c) + w_{prog} \cdot S_{prog}(c) - w_{noise} \cdot C_{noise}(c) - w_{step} \cdot C_{step}(c) - w_{rep} \cdot P_{rep}(c) - w_{fail} \cdot P_{fail}(c)$$
- Tự động hạ cấp sang `SYMBOLIC_ONLY` khi LLM semantic component bị lỗi hoặc từ chối; tuyệt đối không gọi `RuleBasedPlanner`.
- Hỗ trợ các chế độ ablation độc lập: Full, without-noise, without-penalties, semantic-only, symbolic-only.

### RT-05D — Benchmark Protocol & Methodology Freeze (Implemented)
- Đóng băng giao thức thực nghiệm trước khi chạy comparative benchmark chính nhằm ngăn chặn over-fitting / prompt tuning trên tập evaluation.
- Phân định rạch ròi: S1–S4 là `development / engineering validation scenarios`; 12 kịch bản held-out (H1–H12) trong `evaluation/datasets/held_out/` dành riêng cho comparative evaluation.
- Đóng băng phiên bản và hàm băm: `RULE_POLICY_V1`, `LLM_ATTACK_PLANNER_PROMPT_V1` (hash `1d35855b...`), `HYBRID_SCORING_V1_FROZEN` (hash `0e595f72...`), `HYBRID_PLANNER_PROMPT_V1` (hash `d1280d0b...`).
- Minh bạch việc chọn trọng số: Các trọng số V1 được chọn theo kinh nghiệm trong giai đoạn phát triển và được đóng băng trước khi đánh giá held-out; không tuning trên tập held-out.
- Hình thức hóa định lượng 3 chỉ số chính: Goal Completion Rate (loại bỏ clean control khỏi mẫu số), Dead-End Recovery Rate (mẫu số chỉ tính các tập có cơ hội phục hồi sau dead-end), Clean-Control Restraint (đánh giá hành vi STOP sạch sẽ, chống loop vô hạn và false claims).
- Tiền đăng ký ma trận so sánh (RULE, LLM, HYBRID_FULL) và 4 cấu hình ablation với câu hỏi nghiên cứu cụ thể.
- Đóng băng seed manifest: 5 simulator seeds cố định (1001-1005) dùng chung cho mọi planner để đảm bảo tính công bằng.

## Out of Scope

- **RT-06**: Docker Live Cyber Range deployment.
- **RT-07**: RL policy training (PPO/DQN) và full comparative evaluation benchmark.

## Inputs

- `EpisodeEnvironment` từ RT-04 (`runtime/simulation/environment.py`).
- `BeliefState` và `StateManager` từ RT-02 (`agent/memory/state/belief_state.py`).
- `ActionRegistry` và `ActionConstraintEvaluator` từ RT-03 (`actions/catalog/action_registry.py`, `runtime/evaluators/action_evaluator.py`).
- Hợp đồng `CentralizedSafetyGate` (`runtime/safety/discovery_gate.py`).
- 4 kịch bản chuẩn mực S1–S4 (`runtime/simulation/fixtures/scenarios/`).

## Outputs

- `runtime/planners/planner_context.py`: `PlannerDecisionContext`, `PlannerDecision`, `PlannerDecisionTrace`.
- `runtime/planners/candidate_generator.py`: `CandidateGenerator`, `CandidateProposal`, `ProposalReason`.
- `runtime/planners/planner_interface.py`: Hỗ trợ `PlannerDecisionContext` và `_validate_context_decision`.
- `runtime/planners/rule_based_planner.py`: Triển khai `_plan_context` theo phân cấp ngữ nghĩa chuẩn mực.
- `runtime/orchestration/planner_runner.py`: `PlannerEpisodeRunner`, `EpisodeRunResult`.
- `runtime/simulation/gym_adapter.py`: Tích hợp `CandidateGenerator` bảo vệ action mask non-leakage.
- `tests/runtime/test_planner_context.py`: Kiểm thử hợp đồng ngữ cảnh planner an toàn.
- `tests/runtime/test_candidate_generator.py`: Kiểm thử bộ sinh đề xuất chuẩn tắc.
- `tests/runtime/test_rule_planner_baseline.py`: Kiểm thử baseline Rule trên S1–S4.
- `tests/boundary/test_planner_boundary.py`: Kiểm thử ranh giới import AST cô lập simulation.

## Interfaces

- `PlannerDecisionContext`:
  - `create(...) -> PlannerDecisionContext`
  - `to_dict() -> dict[str, Any]`
  - `deterministic_hash() -> str`
- `CandidateGenerator`:
  - `generate_proposals(belief_state, registry, evaluator=None, target_allowlist=None) -> list[CandidateProposal]`
  - `get_eligible_proposals(...) -> list[CandidateProposal]`
  - `get_rejected_proposals(...) -> list[CandidateProposal]`
- `Planner`:
  - `plan(request: PlanningInput | PlannerDecisionContext) -> PlanResponse | PlannerDecision`
  - `_plan_context(context: PlannerDecisionContext) -> PlannerDecision`
- `PlannerEpisodeRunner`:
  - `run_episode(max_steps=None, budget=None) -> EpisodeRunResult`

## Data Contracts

- `PlannerDecisionContext`: Cấu trúc dữ liệu an toàn bất biến chứa thông tin nhìn thấy được của tác tử tại mỗi bước hoạch định.
- `PlannerDecision`: Quyết định của tác tử gồm `proposal: dict`, `rationale: str`, `reason_code: str`, `confidence: float`.
- `PlannerDecisionTrace`: Cấu trúc ghi vết an toàn từng bước cho benchmark và thẩm định chỉ số.
- `CandidateProposal`: Biểu diễn đề xuất hành động kèm tham số, trạng thái hợp lệ `is_eligible`, và chi phí (`step_cost`, `noise_cost`).

## Dependencies

- RT-01: Zero-Knowledge Boundary & Fog-of-War scoping.
- RT-02: Enterprise Observation Model & Belief State Projection.
- RT-03: Generic TTP Action Catalog & Action Constraint Evaluator.
- RT-04: Enterprise Attack Simulator & Episode Environment.
- ADR-007: Simulator before Cyber Range RL.
- ADR-009: Ground Truth Isolation.
- ADR-014: Enterprise Red Team Belief State.

## Implementation Requirements

- Tuyệt đối không để lộ Ground Truth (`TrueState`, `HiddenScenario`, `ScenarioEvaluationView`, hidden topology, credentials, objective locations) hoặc Gym numeric reward trong `PlannerDecisionContext`.
- Candidate generation chỉ dựa trên `visible_target_ids` và `ActionRegistry`; không duyệt kho node kịch bản.
- Quyết định của Rule planner phải tất định 100% đối với cùng một ngữ cảnh `PlannerDecisionContext`.
- Không phụ thuộc vào tên kịch bản, S1–S4 ID, hoặc hard-coded path.
- Duy trì tính tương thích ngược hoàn toàn với `PlanningInput` cho các kiểm thử Task-021.

## Safety Requirements

- Miền `runtime/planners/**` tuyệt đối không import các module chân lý ẩn từ `runtime/simulation/**`.
- Phân tách vai trò rõ ràng: `ActionConstraintEvaluator` xác định tính hợp lệ logic ("logically eligible under current belief"); Planner xác định lựa chọn ("which eligible action to choose"); `CentralizedSafetyGate` là thẩm quyền an toàn cuối cùng ("authorized for live execution").
- Rule planner không được phép vượt qua (bypass) Safety Gate hoặc ActionConstraintEvaluator.
- Khi Safety Gate từ chối (DENY), hệ thống ghi nhận kết quả thất bại chuẩn tắc và cập nhật Belief State mà không gây crash hay bypass.

## Testing Requirements

- `tests/runtime/test_planner_context.py`: Kiểm thử bất biến, không chứa TrueState/HiddenScenario/EvaluatorView/Reward, hash tất định.
- `tests/runtime/test_candidate_generator.py`: Kiểm thử chỉ dùng visible targets, không đọc Safety full allowlist, đánh giá eligibility chuẩn mực.
- `tests/simulation/test_gym_adapter.py`: Kiểm thử Gym action mask không rò rỉ số lượng/ID node ẩn tại $t=0$.
- `tests/boundary/test_planner_boundary.py`: Kiểm thử AST import scan đảm bảo `runtime/planners/**` không import `runtime/simulation/**`.
- `tests/runtime/test_rule_planner_baseline.py`: Kiểm thử tính tất định, chỉ chọn eligible candidates, không chọn node ẩn, hành vi thực thi trên S1 (đạt mục tiêu), S2 (vào decoy), S3 (replan khi bị block), S4 (dừng sạch sẽ khi không có lỗ hổng), và phản ứng khi Safety Gate từ chối.

## Acceptance Criteria

1. `PlannerDecisionContext` cung cấp bề mặt thông tin an toàn duy nhất, không rò rỉ chân lý ẩn hay Gym reward.
2. `CandidateGenerator` chuẩn hóa sinh đề xuất từ visible targets, được dùng chung bởi Planner và `SimulationGymEnv`.
3. Gym action mask không làm lộ thông tin node ẩn tại $t=0$.
4. Rule Planner thực thi dựa trên phân cấp ngữ nghĩa chuẩn mực, không hard-code kịch bản, và có tính tất định bit-for-bit.
5. Hành vi Rule baseline trên S1–S4 thể hiện đúng nguyên lý nghiên cứu (S1 thành công, S2 sập bẫy decoy, S3 replan vượt firewall, S4 dừng sạch sẽ).
6. Toàn bộ test suite runtime (525+ tests), simulation (73 tests), boundary (42 tests) PASS 100%.

## Evidence Required

- Biên bản kiểm thử các suite: `tests/runtime/test_planner_context.py`, `tests/runtime/test_candidate_generator.py`, `tests/simulation/test_gym_adapter.py`, `tests/boundary/test_planner_boundary.py`, `tests/runtime/test_rule_planner_baseline.py`.
- Biên bản chạy toàn bộ test suite runtime, simulation, boundary.
- Biên bản thực thi của scaffold validator (`scripts/validation/validate_scaffold.py`).

## Failure Conditions

- `PlannerDecisionContext` chứa trường chân lý ẩn hoặc Gym reward.
- Action mask hoặc Candidate Generator sinh hành động trên node chưa nhìn thấy (hidden target).
- `runtime/planners/**` import trực tiếp `runtime/simulation/**`.
- Rule planner không tất định khi cùng nhận một ngữ cảnh.
- Gây hồi quy trên các test suite RT-01..RT-04.

## Related Guides

- `docs/guides/06-ai-agent-fundamentals.md`
- `docs/guides/07-planning-and-replanning.md`
- `docs/guides/10-mdp-and-pomdp.md`
- `docs/guides/14-hybrid-planning.md`
- `docs/guides/17-cyber-range-safety.md`

## Related Runbooks

- `docs/runbooks/run-rule-planner.md`
- `docs/runbooks/run-experiment.md`
- `docs/runbooks/validate-isolation.md`

## Related ADRs

- `docs/adr/ADR-007-simulator-before-cyber-range-rl.md`
- `docs/adr/ADR-009-ground-truth-isolation.md`
- `docs/adr/ADR-014-enterprise-red-team-belief-state.md`
