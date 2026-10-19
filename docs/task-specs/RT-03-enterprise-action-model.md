# RT-03 — Enterprise Action Model

## Status

`IMPLEMENTED` for RT-03A (Generic TTP Action Contract) and RT-03B (Action Constraint Evaluator). Validation pending independent review.

## Purpose

Thiết lập mô hình hành động doanh nghiệp có giới hạn (Enterprise Bounded Actions), hợp đồng năng lực TTP tổng quát (Generic TTP Action Contract), và bộ thẩm định ràng buộc đơn nhất (Single Canonical Action Constraint Evaluator) cho tác tử Red Team dưới điều kiện quan sát một phần (POMDP / Partial Observability), chuyển đổi triệt để từ mô hình hành động gắn cứng với mục tiêu/lỗ hổng cụ thể sang mô hình năng lực TTP trừu tượng, độc lập với mục tiêu (target-independent).

## Background

Sau khi RT-01 thiết lập rào chắn Zero-Knowledge (Fog-of-War) và RT-02 hoàn thành mô hình quan sát doanh nghiệp cùng phép chiếu Belief State tất định, tác tử Red Team có khả năng biểu diễn trạng thái quan sát một phần.

Tuy nhiên, danh mục hành động trước đây (thừa hưởng từ Web Pentest Cyber Range MVP) có các fixture gắn cứng mục tiêu cụ thể (`target_id: lab-sqli-001`). Để phục vụ hoạch định tấn công Red Team trong môi trường mạng doanh nghiệp, Action Model định nghĩa các năng lực TTP trừu tượng (Capabilities) thay vì gán chết đối tượng. Mục tiêu hành động được lựa chọn tại planning/proposal time từ phạm vi hiển thị hợp lệ (`visible_target_ids`), và một Action Constraint Evaluator đơn nhất xác định tính khả thi của action dựa trên Belief State mà không gây đột biến trạng thái hay bypass Safety Gate.

## Scope

- Thiết lập Generic TTP Action Contract chuẩn mực tuân thủ JSON Schema Draft 2020-12 closed object tại `agent/planner/contracts/action.schema.json`.
- Định nghĩa 8 năng lực TTP doanh nghiệp cốt lõi (MVP Generic TTP Capabilities):
  1. `RECON` / `DISCOVERY` (`ACTION-DISCOVERY-001`): Khám phá mạng và dịch vụ mở trên subnet.
  2. `INITIAL_ACCESS` / `FOOTHOLD` (`ACTION-FOOTHOLD-001`): Thiết lập phiên foothold ban đầu qua dịch vụ mở có lỗ hổng.
  3. `HOST_RECON` (`ACTION-HOSTRECON-001`): Thu thập cấu hình hệ điều hành và giao diện nội bộ từ active session.
  4. `CREDENTIAL_ACCESS` / `CREDENTIAL_DISCOVERY` (`ACTION-CREDS-001`): Khám phá và thu thập credential handle hợp lệ.
  5. `LATERAL_MOVEMENT` / `PIVOT` (`ACTION-PIVOT-001`): Mở rộng phiên tấn công sang máy chủ nội bộ qua thông tin xác thực.
  6. `PRIVILEGE_ESCALATION` (`ACTION-PRIVESC-001`): Nâng đặc quyền thực thi cục bộ từ user lên privileged.
  7. `OBJECTIVE_ACCESS` (`ACTION-OBJECTIVE-001`): Truy cập và xác thực mục tiêu crown-jewel (`T1005 Data from Local System`).
  8. `STOP` (`ACTION-STOP-001`): Kết thúc hoạch định khi hoàn thành mục tiêu hoặc cạn ngân sách.
- Biểu diễn ngữ nghĩa hành động đầy đủ: `action_id`, `action_class`, `name`, `description`, `target_kind`, `preconditions`, `expected_effects`, `step_cost`, `noise_cost`, `required_capability`, `argument_schema`, `mitre_attack`, `classification`.
- Chuẩn hóa thang đo quyền truy cập thống nhất (Canonical Access Hierarchy): `NONE < FOOTHOLD < USER < PRIVILEGED < SYSTEM`. Tự động chuẩn hóa `UNPRIVILEGED` sang `USER`.
- Xây dựng **Action Constraint Evaluator** đơn vị chuẩn duy nhất tại `runtime/evaluators/action_evaluator.py`:
  - Thẩm định 11 chiều điều kiện tiên quyết: `target_visible`, `host_observed`, `service_observed`, `required_service_type`, `finding_confirmed`, `min_access_level`, `require_active_session`, `require_valid_credential`, `require_reachability`, `objective_not_achieved`, `allowed_phases`.
  - Kiểm tra tương thích `target_kind` (`HOST`, `SERVICE`, `ENDPOINT`, `SUBNET`, `OBJECTIVE`, `ENVIRONMENT`, `TARGET`).
  - Quản thúc giả định (Quarantined Hypotheses): `PLANNER_INFERENCE` và facts có `hypothesis=True` tuyệt đối không được thỏa mãn điều kiện tiên quyết mang tính authoritative.
  - Phân biệt quyền hiện thời và quyền lịch sử (Current vs Historical Access): `require_active_session == True` bắt buộc phải có phiên `ACTIVE`. Toàn bộ phiên `CLOSED` không thỏa mãn dù quyền lịch sử là `PRIVILEGED` hoặc `SYSTEM`.
  - Tính thuần khiết và tất định (Pure & Deterministic): zero state mutation, zero network dispatch, zero Ground Truth inspection.
  - Phân tách rạch ròi Eligibility vs Authorization: `eligible=True` chỉ xác nhận tính khả thi logic; `CentralizedSafetyGate` giữ quyền phê duyệt cuối cùng.
- Bảo toàn tương thích ngược 100% với danh mục hành động Web Pentest hiện hữu (`LEGACY_WEB_COMPAT`).
- Xây dựng module canonical Action Registry tại `actions/catalog/action_registry.py` ủy nhiệm hoàn toàn logic thẩm định sang `ActionConstraintEvaluator`.

## Out of Scope

- Thực thi exploit thật hoặc vũ khí hóa exploit.
- Thực thi privilege escalation hoặc credential dumping thật trên hệ thống.
- Xây dựng Simulation Backend (thuộc RT-04).
- Xây dựng Mini Enterprise Live Range Docker (thuộc RT-06).
- Lựa chọn hoặc xếp hạng hành động bằng LLM/RL (thuộc RT-05).

## Inputs

- Canonical Draft 2020-12 schema specification (`agent/planner/contracts/action.schema.json`).
- Action catalog JSON (`actions/catalog/action-catalog.json`).
- Belief State projection interface (`agent/memory/state/belief_state.py`).
- Safety allowlist configuration (`configs/safety/action-allowlist.yaml`).

## Outputs

- Schema cập nhật `agent/planner/contracts/action.schema.json`.
- Danh mục năng lực TTP tổng quát trong `actions/catalog/action-catalog.json`.
- Module quản lý `actions/catalog/action_registry.py`.
- Bộ test suite hợp đồng và ranh giới tại `tests/contracts/test_action_contract.py` và `tests/boundary/test_action_boundary.py`.

## Interfaces

- `ActionRegistry` (`actions/catalog/action_registry.py`):
  - `get_action(action_id: str) -> ActionDefinition | None`
  - `get_all_actions() -> list[ActionDefinition]`
  - `get_enterprise_actions() -> list[ActionDefinition]`
  - `get_legacy_actions() -> list[ActionDefinition]`
  - `validate_action(action: ActionDefinition) -> list[str]`
  - `scan_action_for_target_leakage(action: ActionDefinition) -> list[str]`
  - `evaluate_precondition_contract(action: ActionDefinition, belief_state: Any, target_id: str | None) -> tuple[bool, list[str]]`

## Data Contracts

- `ActionDefinition`: Biểu diễn năng lực TTP đóng kín, định kiểu chặt chẽ.
- `PreconditionContract`: Các ràng buộc điều kiện tiên quyết có cấu trúc (`target_visible`, `host_observed`, `require_active_session`, `min_access_level`, `require_reachability`, `require_valid_credential`, `objective_not_achieved`).
- `EffectContract`: Kỳ vọng chuyển đổi trạng thái dùng riêng cho tài liệu và thuật toán heuristic, không có phương thức biến đổi Belief State.
- `MitreAttackMetadata`: Dữ liệu ánh xạ tham chiếu MITRE ATT&CK (`tactic`, `technique_id`, `technique_name`).

## Dependencies

- RT-01: Zero-Knowledge Boundary & Fog-of-War target scoping.
- RT-02: Enterprise Observation Model & Belief State Projection.

## Implementation Requirements

- Giữ vững nguyên tắc Draft 2020-12 closed object (`additionalProperties: false`).
- Không tạo nguồn chân lý thứ hai (single source of truth tại `actions/catalog/action-catalog.json`).
- Mọi định nghĩa hành động doanh nghiệp phải hoàn toàn độc lập với mục tiêu (target-independent): không chứa target ID, IP, hostname, vulnerability fixture name.
- Giữ nguyên các fixture hành động cũ (`LEGACY_WEB_COMPAT`) để bảo đảm tính tương thích hồi quy.

## Safety Requirements

- Action Catalog định nghĩa năng lực (Capabilities), không thay thế Safety Gate. Mọi đề xuất hành động từ Planner bắt buộc phải qua CentralizedSafetyGate thẩm định allowlist, target scope, ngân sách và kill switch trước khi cấp quyền.
- Không cho phép arbitrary shell, dynamic commands, hoặc payload injection trong action contract.

## Testing Requirements

- Kiểm thử hợp đồng (`tests/contracts/test_action_contract.py`):
  - Schema là Draft 2020-12 closed object.
  - Toàn bộ generic enterprise actions thỏa mãn schema.
  - Toàn bộ legacy actions giữ vững tương thích và được phân loại đúng.
  - Preconditions là dữ liệu có cấu trúc, từ chối mã tùy ý.
  - Chi phí bước và chi phí tín hiệu hoạt động (noise_cost) không âm.
- Kiểm thử ranh giới (`tests/boundary/test_action_boundary.py`):
  - Enterprise actions không chứa mục tiêu/IP cố định.
  - Expected effects không biến đổi Belief State.
  - Closed session không thỏa mãn yêu cầu active session dù có proven access level cao trong quá khứ.
  - Định nghĩa hành động không tham chiếu Ground Truth hoặc làm rò rỉ topology ẩn.
  - Metadata dành cho Planner tuyệt đối trung lập với mục tiêu.

## Acceptance Criteria

- Canonical Generic TTP Action Contract đạt chuẩn `action.schema.json`.
- Danh mục hành động doanh nghiệp không chứa rò rỉ mục tiêu.
- Các điều kiện tiên quyết được chuẩn hóa dạng dữ liệu có cấu trúc.
- Bất biến cứng ngăn chặn hiệu ứng trực tiếp đột biến Belief State được kiểm chứng qua boundary test.
- Mô hình chi phí hoạt động có cận và không âm.
- Không có hồi quy trên bộ kiểm thử RT-01 và RT-02.

## Evidence Required

- Báo cáo kết quả kiểm thử đơn vị, hợp đồng và ranh giới (`tests/contracts`, `tests/boundary`).
- Biên bản chạy kiểm tra tĩnh và scaffold validator.

## Failure Conditions

- Xuất hiện mã eval hoặc shell script trong preconditions.
- Tồn tại IP, hostname, hoặc target ID cố định trong định nghĩa hành động doanh nghiệp.
- `expected_effects` có khả năng đột biến trực tiếp Belief State.
- Hồi quy trên các boundary test suites của RT-01 và RT-02.

## Related Guides

- `docs/guides/07-planning-and-replanning.md`
- `docs/guides/17-cyber-range-safety.md`

## Related Runbooks

- `docs/runbooks/run-rule-planner.md`
- `docs/runbooks/run-llm-planner.md`

## Related ADRs

- `docs/adr/ADR-004-bounded-action-catalog.md`
- `docs/adr/ADR-014-enterprise-red-team-belief-state.md`
