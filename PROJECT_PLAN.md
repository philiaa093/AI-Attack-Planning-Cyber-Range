# Project Plan

Roadmap hiện hành: `PLAN-ENTERPRISE-REDTEAM-001`, nền tảng nghiên cứu AI Red Team dưới quan sát một phần. Ưu tiên simulator và benchmark theo [định nghĩa sản phẩm](PROJECT_CONTEXT.md); trạng thái/dependencies chỉ tra tại [TASKS.md](TASKS.md).

## Foundation

Tái dùng contracts, normalizer, belief/state management, bounded actions, Safety Gate, recorder và evaluator hiện có. Không viết lại thành phần chỉ vì roadmap mới; xác định khoảng thiếu bằng source và checks trước khi thêm code.

### Phạm vi đợt chuẩn hóa tài liệu

Người dùng yêu cầu bắt đầu sau đề xuất chuẩn hóa ba file. Allowlist duy nhất: `PROJECT_CONTEXT.md`, `PROJECT_PLAN.md`, `TASKS.md`. Đợt này thu gọn bối cảnh/kế hoạch, đưa RT lên đầu đường đọc, giữ nguyên task IDs/status/dependencies và receipts độc nhất. Không sửa code, contracts, catalog, configs, scenarios, evidence, README hoặc validator; không chạy lab/provider, tự approve, finalize, append history hoặc commit.

Checks: headings/links/dependencies của ba file, bảo toàn bảng/receipt/anchor, scoped whitespace check và repository checker. Kết quả toàn repo phải so với baseline; blocker ngoài allowlist không được tự sửa. Tài liệu cập nhật là `IMPLEMENTED`, chưa `VALIDATED` nếu chưa đủ checks/review.

### Đợt tách code dùng chung khỏi script demo

Theo yêu cầu tiếp tục xử lý thư mục và code của người dùng, phạm vi kỹ thuật là chuyển helpers điều phối lab từ CLI demo về `runtime/lab/control_support.py`; backend và CLI cùng gọi module này. Giữ cấu trúc thư mục hiện có, không mở tính năng simulator hoặc đổi hành vi gate/approval/ownership/evidence. Đây là đợt kỹ thuật riêng, không mở rộng allowlist của đợt tài liệu trước.

Allowlist chính xác:

- `runtime/lab/control_support.py` (mới).
- `scripts/demo/run_professor_demo.py`.
- `dashboards/app/backend/run_manager.py`.
- `dashboards/app/backend/range_controller.py`.
- `scripts/demo/test_professor_demo.py`.
- `tests/backend/test_history_truthfulness.py`.
- `tests/backend/test_profile_planner.py`.
- `tests/backend/test_runtime_events.py`.
- `tests/runtime/test_control_support.py` (mới).
- `PROJECT_CONTEXT.md`, `PROJECT_PLAN.md` (khai báo phạm vi).

Acceptance: backend không import script demo; logic Docker/gate/recorder/verifier dùng chung có một nơi chịu trách nhiệm; import module không sửa PATH hoặc gọi Docker/network. CLI giữ presentation/arguments; discovery Docker chỉ chạy khi thực sự gọi Docker. Giữ nguyên target/origin/action IDs, policy checks, output root `scripts/demo/demo-output`, ownership/container-ID checks và volume preservation. Không sửa contracts/catalog/configs/scenarios hoặc thêm arbitrary command API; không di chuyển/xóa evidence, receipts hay frozen sources.

Checks: focused backend tests, CLI regressions với Docker/provider mocked và HTTP fixture loopback được gate/approval; kiểm import boundary, import side effects, cleanup ownership và evidence failure-stop. Test mới dùng temp directories; không ghi đè/xóa run đã tồn tại. Không chạy Docker services, provider thật hoặc public targets. Chạy scoped diff/AST và repository checker, đối chiếu blocker có trước. Kết quả refactor không nâng trạng thái runtime/task hoặc thay independent approval.

### Đợt gom catalog planner và schema validator

Theo yêu cầu bắt đầu dọn code ngày 2026-10-18, chuyển hai bản Python `ACTION_CATALOG` giống nhau về `agent/planner/action_catalog.py` và bốn hàm schema thuần về `shared/schema_validation.py`. Giữ nguyên 13 entries, thứ tự, metadata, signature, error lists và exception behavior; không thay bằng JSON catalog 16 actions. Script checker reexport API cũ và vẫn chạy trực tiếp từ mọi working directory. `ROOT`, `load_json` và session/comment rules giữ tại script; đợt này chưa loại toàn bộ dependency runtime vào scripts.

Allowlist chính xác:

- `PROJECT_PLAN.md` (khai báo phạm vi này).
- `agent/planner/action_catalog.py`, `shared/__init__.py`, `shared/schema_validation.py` (mới).
- `agent/planner/llm/planner.py`, `runtime/planners/observed_planner.py` (gom catalog; observed planner chỉ đổi thêm import schema).
- `scripts/validation/validate_scaffold.py` (chuyển bốn hàm, compatibility imports và direct-CLI bootstrap).
- `runtime/discovery/discovery_report_importer.py`, `runtime/evidence/discovery_recorder.py`, `runtime/evidence/evidence_package.py`, `runtime/evidence/evidence_readonly.py` (chỉ đổi import schema).
- `runtime/orchestration/autonomous_runner.py`, `runtime/planners/planner_adapter.py`, `runtime/planners/planner_interface.py`, `runtime/simulation/loader.py`, `runtime/state/knowledge_state_store.py` (chỉ đổi import schema).
- `agent/perception/normalizers/enterprise_normalizer.py`, `actions/catalog/action_registry.py` (chỉ đổi import schema).
- `tests/contracts/test_contracts.py`, `tests/runtime/test_discovery_report_importer.py` (compatibility, boundary và focused schema regressions).

Acceptance/checks: đối chiếu AST bốn hàm và hai catalog trước/sau; giữ legacy import identity; kiểm malformed inputs, bool/integer, nonfinite, UTC, local refs, branches, closed objects và bounds bằng focused offline tests. Kiểm direct CLI từ repo và cwd ngoài repo, import shared không I/O/process/network/environment mutation, scoped AST/diff và repository checker so với baseline. Các tests ghi temp directories hoặc memory; không chạy Docker/provider/live targets. Giữ nguyên các thay đổi RT đang có, task status, contracts/configs/catalog JSON/scenarios, evidence/receipts/frozen sources; không append history, approve, finalize hoặc commit.

### Ba mốc sản phẩm

| Mốc | Phạm vi | Điều kiện kết thúc |
|---|---|---|
| 1. Episode mô phỏng | RT-04 và phần tích hợp RT-05 | Seed hợp lệ, partial observations, belief update, proposal, gate, simulated transition, evidence và stop/result chạy trọn vòng; RULE và random đối chứng có provenance rõ. |
| 2. Benchmark tái lập | Experiment offline hỗ trợ RT-04/RT-05, chuẩn bị RT-07 | Một entry point tạo bảng so sánh trên scenario splits, seeds, actions, policies và budgets cố định; cùng input tái lập transition/metrics; failures vẫn nằm trong mẫu đánh giá. |
| 3. So sánh thuật toán mở rộng | RT-05 và đánh giá offline trước live range | Tích hợp từng LLM/RL/HYBRID trên cùng observation/action contract, ghi mode/fallback, so với baseline và test held-out. |

Đây là mốc nhỏ để phát triển/kiểm tra simulator, không đổi dependencies hay giảm acceptance của task. Offline benchmark không đóng RT-07 toàn phần: backlog RT-07 vẫn cần RT-05 và RT-06 cùng đánh giá simulator/live range. Không dùng live range làm điều kiện để bắt đầu nghiên cứu offline.

### Enterprise Red Team Planning Roadmap (RT-00 .. RT-07)

- RT-00: định nghĩa sản phẩm, governance và quyết định kiến trúc.
- RT-01: zero-knowledge/visibility boundary; tách Safety Scope khỏi Planner-Visible Scope.
- RT-02: observations và belief state, facts/hypotheses, credential/session opaque references.
- RT-03: generic bounded actions và eligibility evaluator; authorization vẫn thuộc gate.
- RT-04: simulator sở hữu true state, transition từ approved actions và partial observations; kiểm chứng trước live range.
- RT-05: nối các planner với simulator qua contract chung, provenance và fallback tường minh.
- RT-06: mini enterprise live range cô lập, chỉ sau RT-04/RT-05 và approved executable scope riêng.
- RT-07: đánh giá thực nghiệm theo acceptance đầy đủ của backlog; không chuyển synthetic replay thành kết quả enterprise.

Chi tiết trạng thái/acceptance ở [bảng RT](TASKS.md#enterprise-red-team-planning-backlog); quyết định kiến trúc ở [ADR-014](docs/adr/ADR-014-enterprise-red-team-belief-state.md).

## Literature/Threat

Chốt giả thuyết nghiên cứu, assets, attacker observations, goal và metrics trước experiment. Không cung cấp global/hidden topology, full target allowlist, target source, ground truth hoặc defender-private state cho planner; quan hệ khám phá hợp lệ từ observations được phép vào belief state. Các giới hạn family Web cũ giữ trong baseline theo [ADR-003](docs/adr/ADR-003-three-vulnerability-families.md); mở rộng enterprise không tự cấp quyền active exploitation.

## Cyber Range

ShopLab/Web targets và các receipts SL là baseline lịch sử. Dừng mở rộng ecommerce, đổi ứng dụng upstream và demo lab trên đường ưu tiên hiện tại; giữ code, data và evidence để tái dùng có chọn lọc.

Kế hoạch `PLAN-SHOPLAB-PTES-001` và `PLAN-OSCAR-ADOPTION-001` không còn là lộ trình chính. Acceptance nghiệp vụ/gateway/storage/restore và source-review gaps vẫn nằm ở [backlog SL](TASKS.md#shoplabptes-implementation-backlog), [task specs](docs/task-specs/index.md#shoplab-task-contracts) và [receipt Oscar](TASKS.md#oscar--thẩm-định-nguồn-offline); không xóa pending work hay chuyển PASS sang target mới.

RT-06 chỉ mở sau simulator được kiểm chứng và có tranche riêng: approved manifests/images, internal networks, loopback ingress, egress denial, storage/restore và per-request gate. Giữ cùng executor/result/observation contract; không suy Docker validation từ config hoặc offline tests.

## Perception/Tooling

Mọi observation qua validation/canonicalization/redaction trước state/planner. Không đọc compose/allowlist/ground truth để mở visibility. Facts authoritative cần provenance/evidence; hypothesis không tự tạo capability, session hay quyền truy cập.

Tái dùng StateManager và normalizers; giữ budget ownership, identity, idempotent replay và conflict detection. Recorder ghi intent trước action và result trước bước kế tiếp; evidence failure dừng cả episode. Tool adapters offline không chứng minh external-tool execution.

Kế hoạch đã duyệt `PLAN-TASK016-ZAP-EVIDENCE-002` được giữ làm pending work, không triển khai trong đợt này: xử lý checker theo scope riêng; bounded offline import qua `DurableEvidenceRecorder.persist_phase_artifact` với run/source/root tường minh, intent rồi minimized result/rejection, hash cùng bounded snapshot, persist trước return và sticky halt; kiểm no-overwrite/containment bằng temp-directory tests và bàn giao review. Không lưu raw reports hoặc dùng dispatch-success cho import; Windows power-loss durability còn `UNRESOLVED`. Các pending integration khác tra [ledger](TASKS.md#checks-and-observed-implementation-state).

## Rule

RULE là baseline xác định trên belief state từ observations, không preset đường đi hoặc vị trí lỗi. Cần cùng input/action/budget với đối chứng; không ghi rule fallback thành LLM. Random đối chứng chỉ chọn hành động hợp lệ và phải được mô tả trung thực trong experiment.

## LLM

Tích hợp sau khi episode và baseline có thể tái lập. Prompt chỉ chứa observed belief state và candidates được phép. Proposals tuân thủ schema, malformed output fail closed; mode/provider/model/fallback được ghi rõ. Không coi mock, fixture hoặc metadata-review tests là provider-backed enterprise result.

## RL Environment

Tái dùng replay hiện có làm regression cho state/reward/protocol; `READ_INVENTORY`/`REVIEW_REPORT` không phải simulator enterprise. Môi trường mới cần approved action semantics, partial observations, transition/termination/cost rõ ràng và seeded randomness nằm trong simulator.

Train/validation/test tách biệt; giữ failures trong denominator; mask/eligibility không thay gate approval. True state và evaluator-only rewards không được rò vào planner context. Mọi thay đổi contract/config/scenario cần allowlist riêng.

## RL Planner

Tái dùng Q-learning khi state/action/reward phù hợp môi trường mới; kiểm chứng mapping và termination trước training. Có code/tabular replay chưa chứng minh hội tụ, tối ưu hay hiệu quả enterprise. `TASK-026` giữ `DEFERRED`; không thêm DQN/PPO hoặc dependency mới trước khi benchmark tối thiểu ổn định.

## Hybrid

Tái dùng router sau khi các planner độc lập có thể đánh giá công bằng. Handoff phải giữ state revision, decision history, budget ownership, requested/executed mode và fallback. Thiếu adapter hoặc backend thì ghi `UNRESOLVED`, không tự đổi mode hay bypass gate.

## Evaluation

[Pipeline hiện có](runtime/evaluation/evaluate_all.py) chỉ chạy `synthetic-review` và `synthetic-random`; giữ nó làm regression cho log/hash/metrics/report. Nối episode simulator mới vào phần tái dùng được, tránh tạo evaluator song song. Kết quả synthetic, simulator và live range phải phân biệt trong report.

Benchmark tối thiểu cần scenario versions/splits, seed set, action catalog/policy/source hashes, planner identity, budgets và success/stop conditions cố định. Đánh giá success rate, steps to goal, budget efficiency, belief accuracy; các tín hiệu ground truth chỉ evaluator chấm sau run. Việc chọn đối chứng/tham số phải hoàn tất trước final held-out test.

Không dùng HTTP 200/reflection làm confirmation; không bỏ failed runs khỏi mẫu; không dùng số test hoặc UI screenshot thay experimental metrics. RT-07 toàn phần giữ dependencies/acceptance đã ghi ở TASKS.

## Dashboard

`TASK-032` giữ `DEFERRED`. Dashboard hiện có phục vụ xem kết quả/demo, không dẫn dắt kiến trúc hoặc là điều kiện của benchmark. Tạm ngừng thêm UI tính năng; output ban đầu dùng artifacts/bảng so sánh hiện có.

## Final Reproducibility

Người khác phải tái lập được experiment offline từ manifest và input cố định, với documented dependencies, seeds, policy/action/source hashes, run ID và immutable outputs. Run mới có identity/destination mới; không sửa byte evidence hoặc di chuyển đường dẫn đang được hash-bind.

Required focused checks cho tranche runtime sau này: malformed input/approval thiếu, zero side effects khi deny, rate/order/budget/kill switch, true-state isolation, deterministic transition/metrics, evidence failure-stop, replay integrity và mode/fallback truthfulness. Live range cần thêm isolation/storage/restore receipts riêng.

Bàn giao ghi exact changed/deleted files, commands/exit codes, unverified items, blockers và pending payload. Repository checker: `scripts/validation/validate_scaffold.py`. Claim review hoặc `VALIDATED` cần bằng chứng cho matching source; self-review không thay independent approval.

## Completion rule

Mỗi mốc cần code trong approved allowlist, focused checks và observed evidence cho đúng acceptance. Có file, schema, test PASS hoặc tài liệu mới chưa đóng task rộng hơn. Giữ nguyên `TASK-001..035`, `SL-01..12`, `RT-00..07` và dependencies; trạng thái chỉ tại TASKS.

Simulator phải hoàn thành/kiểm chứng trước RT-06. Offline milestones không tự đóng RT-07, và baseline validation không chuyển sang RT. SL-12 gate claims còn xung đột được giữ `UNRESOLVED` để đối chiếu receipts/build; không tự chọn PASS, review/approve hoặc nâng runtime validation.
