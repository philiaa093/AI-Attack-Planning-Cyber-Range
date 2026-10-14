# Task 20 — Planner interface ngoại tuyến

> Đường dẫn source đã chuyển ngày 2026-10-14; xem [bản đồ thư mục](../repository-layout.md). Receipts, command invocations và hash/path lịch sử bên dưới thuộc source trước khi chuyển. Các liên kết tới source và ví dụ import Python đã theo vị trí mới.

Implementation artifact và canonical TASK-020: `IMPLEMENTED` trong phạm vi ABC/DTO/state-read adapter ngoại tuyến, cập nhật ngày 2026-10-12 theo yêu cầu người dùng. Trạng thái tại [TASKS.md](../../TASKS.md#task-020--planner-interface-ngoại-tuyến); chưa `VALIDATED`.
Independent review và runtime integration: `UNRESOLVED`.

## Phạm vi và nguồn

[Planner ABC](../../runtime/planners/planner_interface.py) và [focused tests](../../tests/runtime/test_planner_interface.py)
cung cấp giao diện chung cho RULE, LLM, RL và HYBRID. Không có strategy thực tế,
provider call, training, dispatcher, runner integration hoặc runtime claim trong
phần triển khai này. Các mode labels trong tests thuộc synthetic fixtures.

Nguồn: [Task 20](../task-specs/TASK-020-planner-interface.md),
[Task 19](../task-specs/TASK-019-knowledge-state-store.md),
[state schema](../../agent/planner/contracts/state.schema.json),
[plan schema](../../agent/planner/contracts/plan.schema.json),
[ADR-005](../adr/ADR-005-planner-executor-perception-separation.md),
[ADR-006](../adr/ADR-006-shared-planner-interface.md),
[ADR-009](../adr/ADR-009-ground-truth-isolation.md),
[ADR-011](../adr/ADR-011-same-budgets-across-planners.md) và
[ADR-012](../adr/ADR-012-safety-engine-control.md).
Canonical schemas giữ nguyên; mỗi decision chứa một proposal hoặc một lý do dừng.
Không thêm các fields mà planning prose mô tả nhưng plan schema chưa hỗ trợ.

## API và luồng dữ liệu

1. Coordinator đọc `StateSnapshot.from_store(store, context)` qua `get_state` của
   Task 19; không truyền writable store vào strategy.
2. `PlanningInput` chứa snapshot, candidate action/target sets và fallback policy.
3. `Planner.plan(request)` kiểm tra input/budget rồi gọi abstract hook `_plan`.
4. `Planner.replan(request, previous=..., feedback=...)` nhận snapshot mới và
   feedback gắn với context/revision/action của decision trước; mặc định gọi
   `_plan`, strategy cần lịch sử override `_replan`.
5. Cả hai entry points kiểm tra output type, context, revision, objective, scope
   và mode/fallback trước khi trả `PlanningDecision`.

Subclass implement property `mode` và `_plan`. Entry points `plan`/`replan` không
được override; TypeError khi định nghĩa subclass vi phạm. Đây là Template Method
kết hợp Strategy pattern, để shared checks không phải lặp trong từng backend.
Trusted Python strategy có thể chứa code tùy ý; ABC không phải sandbox.

State/proposal DTO giữ canonical JSON immutable, với `to_dict()` trả detached
copy. `StateSnapshot.revision` là SHA-256 của context key và canonical state;
session/episode khác nhau tạo revision khác ngay cả khi state giống nhau.
Hash dùng để liên kết dữ liệu, không phải chữ ký hoặc chứng nhận tính xác thực.

`PlanProposal.from_dict()` validate canonical schema; `to_dict()` giữ đúng shape,
bao gồm các optional fields hiện hành. Provenance/context nằm ở decision envelope,
không thêm vào plan JSON có `additionalProperties: false`.

## Ranh giới kiểm tra

Reject unknown schema fields, malformed IDs/types, duplicate JSON keys/fact IDs,
non-finite numbers, detected unredacted secrets, documents quá 1 MiB và malformed
feedback. Input phải được normalizer/store chuẩn hóa và redact trước; existing
redactor chỉ phát hiện những patterns đã hỗ trợ, không chứng minh loại bỏ mọi
secret hoặc ground truth nằm trong arbitrary fact values. Fact strings là data
không tin cậy, không được coi là instructions cho backend.

Budget nào bằng 0 thì dừng trước strategy; scope rỗng hoặc phase TERMINAL trả
NO_VALID_CANDIDATE. TERMINAL không tự chứng minh objective thành công. Planner
không trừ budget; StateManager tiếp tục là owner duy nhất. Revision có thể không
đổi sau feedback không làm thay đổi state; không yêu cầu hash mới một cách giả tạo.

Requested/actual mode khác nhau cần fallback_reason và `fallback_allowed=True`.
Chuyển backend do coordinator chọn giữa hai decisions khác với fallback trong
một decision; previous decision có thể thuộc mode khác với planner hiện tại.

Candidate sets là bộ lọc caller cung cấp, không phải canonical authorization.
Coordinator cần thu hẹp theo policy; dispatcher vẫn phải kiểm canonical catalog,
lab mode, target/action allowlists, approval, rate/order/budget, kill switch, audit
và restore. Proposal không cấp quyền dispatch. Ghi evidence-before-state, kiểm
evidence/source-observation/resource references và stale-state check trước dispatch
thuộc integration tiếp theo; ABC không thể xác minh các references từ state alone.

## Ví dụ không dispatch

Ví dụ chỉ tạo DTO từ StateManager và định nghĩa subclass dừng an toàn.

```python
from agent.memory.state.state_manager import StateManager
from runtime.state.knowledge_state_store import StoreContext
from runtime.planners.planner_interface import (
    Planner, PlanningDecision, PlanningInput, StateSnapshot,
)


class ExamplePlanner(Planner):
    @property
    def mode(self):
        return "RULE"

    def _plan(self, request):
        return PlanningDecision(
            context=request.state.context,
            input_revision=request.state.revision,
            requested_mode=self.mode,
            actual_mode=self.mode,
            stop_reason="NO_VALID_CANDIDATE",
        )


context = StoreContext("RUN-020-EXAMPLE", "SESSION-1", "EPISODE-1")
state = StateManager(context.run_id, "SCN-001", "OBJ-020").get_state()
snapshot = StateSnapshot.from_state(state, context=context)
request = PlanningInput(snapshot, {"ACTION-PLAN-003"}, {"lab-fixture"})
decision = ExamplePlanner().plan(request)
assert decision.proposal is None
assert decision.stop_reason == "NO_VALID_CANDIDATE"
assert snapshot.to_dict() == state
```

## Kiểm tra và bàn giao

Build label: `BUILD-TASK020-INTERFACE-OFFLINE-20261012` (nhãn phiên, chưa được duyệt).
Source HEAD quan sát: `d9ae6ca0d5bb03ce381d7249665237f272eeddc9`.
Receipt UTC: `2026-10-11T20:19:17.7509756Z`; ngày địa phương Asia/Saigon là
2026-10-12. Working tree đã dirty trước triển khai. Source kiểm thử là synthetic
RUN-020/session/episode fixtures; không phải live run hoặc dữ liệu production.

| Exact command | Exit | Observed |
|---|---|---|
| `python -B -m unittest discover -s tests/runtime -p test_planner_interface.py -v` | 0 | 28 tests PASS ở lượt cuối; lượt đầu 25 tests PASS trước bổ sung 3 cases |
| `python -B -m unittest discover -s tests/runtime -p test_knowledge_state_store.py -v` | 0 | 21 tests PASS |
| `python -B -m unittest discover -s tests/planner -p test_planner_contracts.py -v` | 0 | 16 tests PASS |
| `git diff --check -- runtime/planner_interface.py runtime/planner_interface.md tests/runtime/test_planner_interface.py` | 0 | Không tracked whitespace errors; new files được kiểm riêng bên dưới |
| Combined AST/example/whitespace command bên dưới | 0 | AST PASS 2 files; DOCUMENT EXAMPLE PASS; WHITESPACE PASS 3 new files |
| Filtered repository checker command bên dưới | 1 | repository_errors=656; task020_errors=0; HANDOFF_BLOCKED |

Exact combined AST/example/whitespace check:

```text
python -B -c "import ast,pathlib; paths=['runtime/planner_interface.py','tests/runtime/test_planner_interface.py']; [ast.parse(pathlib.Path(p).read_text(encoding='utf-8'),filename=p) for p in paths]; print('AST PASS: 2 files'); text=pathlib.Path('runtime/planner_interface.md').read_text(encoding='utf-8'); fence=chr(96)*3; example=text.split(fence+'python\n',1)[1].split('\n'+fence,1)[0]; exec(compile(example,'planner_interface.md example','exec')); print('DOCUMENT EXAMPLE PASS'); paths.append('runtime/planner_interface.md'); assert all(not line.endswith((' ',chr(9))) for p in paths for line in pathlib.Path(p).read_text(encoding='utf-8').splitlines()); print('WHITESPACE PASS: 3 new files')"
```

Exact repository checker, đầy đủ `validate()` rồi lọc scope để phân loại lỗi,
vẫn exit 1 nếu có bất kỳ repository error:

```text
python -B -c "from scripts.validation.validate_scaffold import validate; scope=('runtime/planner_interface.py','runtime/planner_interface.md','tests/runtime/test_planner_interface.py'); errors=validate(); affected=[e for e in errors if any(p in e for p in scope)]; print('repository_errors='+str(len(errors))); print('task020_errors='+str(len(affected))); print('\n'.join(affected)); print('outside_scope_examples:'); print('\n'.join(e for e in errors[:6] if e not in affected)); raise SystemExit(1 if errors else 0)"
```

Examples outside scope: dashboards/app/README.md, dashboards/app/frontend/README.md
và dashboards/app/frontend/node_modules/** (external URL hoặc forbidden field).
Không sửa/xóa các paths này hoặc bypass checker. 65 tests liên quan PASS; không
chuyển repository FAIL thành PASS hoặc tự review/approve.

Source SHA-256, command `Get-FileHash -Algorithm SHA256 runtime/planner_interface.py, tests/runtime/test_planner_interface.py`:

- runtime/planner_interface.py: FF21A370903B930F0A6BB32361FC20129E20E46102CDB4D732EC6EBE37AD483F
- tests/runtime/test_planner_interface.py: 50A8EC2EE00278B9081A51FD31531434BFAAABBDBB9AE4E59FBD53313E229E7C

Expected/observed: malformed input hoặc mismatch bị reject; exhausted budget không
gọi strategy; budget không bị trừ lần hai; context không bị lẫn; snapshot/input
không đổi sau plan/replan; fallback không được phép bị reject. Assertions PASS.
Tests sử dụng fixtures, StateManager và SQLite in-memory; không chứng minh backend
RULE/LLM/RL thực tế, Docker/provider runtime hoặc independent approval. Redaction
completeness, reference integrity và durable evidence/consumer integration vẫn
UNRESOLVED. Tài liệu receipts không thay immutable evidence recorder.

Exact added files trong phiên triển khai: runtime/planner_interface.py, runtime/planner_interface.md,
tests/runtime/test_planner_interface.py. Deleted files: none. Phiên triển khai không sửa
các files đã dirty trước phiên, contracts, configuration, catalog hoặc evidence.

## Đồng bộ tài liệu và trạng thái ngày 2026-10-12

Người dùng yêu cầu cập nhật tài liệu/trạng thái. TASK-020 đổi SPEC_ONLY → IMPLEMENTED
chỉ cho offline ABC/DTO/state-read adapter; chưa VALIDATED. Source SHA-256 của hai
file Python khớp receipts triển khai phía trên; không chạy lại 65 tests trong lần
cập nhật tài liệu. Receipt UTC: 2026-10-11T20:27:35.3940450Z (ngày địa phương
Asia/Saigon 2026-10-12).

| Check của lần cập nhật tài liệu | Exit | Observed |
|---|---|---|
| Scoped document/link/whitespace command bên dưới | 0 | scoped_document_errors=0; local_links_checked=75; WHITESPACE PASS 5 documents |
| Status/dependencies/source hashes command bên dưới | 0 | STATUS/DEPENDENCIES/SOURCE HASHES PASS |
| Repository checker cho scope tài liệu bên dưới | 1 | repository_errors=656; task020_document_errors=0; HANDOFF_BLOCKED |
| Scoped git diff --check bên dưới | 0 | Không whitespace errors; LF/CRLF conversion warnings ở hai root docs |

Exact commands:

```text
python -B -c "from pathlib import Path; import re; import scripts.validation.validate_scaffold as v; paths=['PROJECT_CONTEXT.md','PROJECT_PLAN.md','TASKS.md','docs/task-specs/TASK-020-planner-interface.md','runtime/planner_interface.md']; errors=[]; [v._check_markdown(v.ROOT/p,errors,v.TASK_HEADINGS if p.startswith('docs/task-specs/') else v.ROOT_HEADINGS.get(p)) for p in paths]; links=[(p,target) for p in paths for target in re.findall(r'\[[^\]]+\]\(([^)]+)\)',(v.ROOT/p).read_text(encoding='utf-8')) if not target.startswith('#') and not re.match(r'[a-z]+://',target)]; assert all(((v.ROOT/p).parent/target.split('#',1)[0]).resolve().is_relative_to(v.ROOT) and ((v.ROOT/p).parent/target.split('#',1)[0]).resolve().exists() for p,target in links); assert all(not line.endswith((' ',chr(9))) for p in paths for line in (v.ROOT/p).read_text(encoding='utf-8').splitlines()); print('scoped_document_errors='+str(len(errors))); print('local_links_checked='+str(len(links))); print('WHITESPACE PASS: 5 documents'); print('\n'.join(errors).encode('ascii','backslashreplace').decode()); raise SystemExit(1 if errors else 0)"
python -B -c "import hashlib,re; from pathlib import Path; text=Path('TASKS.md').read_text(encoding='utf-8'); rows={m[0]:(m[1],m[2]) for m in re.findall(r'^\| (TASK-\d{3}) \| [^|]+ \| .(\w+). \| ([^|]+) \|',text,re.M)}; assert len(rows)==35; assert rows['TASK-020']==('IMPLEMENTED','TASK-004, TASK-005, TASK-019'); assert rows['TASK-026'][0]==rows['TASK-032'][0]=='DEFERRED'; assert all(rows['TASK-'+str(n).zfill(3)][0]=='SPEC_ONLY' for n in (21,22,23,24,25,27,28,29,30,31,33,34,35)); spec=Path('docs/task-specs/TASK-020-planner-interface.md').read_text(encoding='utf-8'); assert 'IMPLEMENTED' in spec.split('## Status',1)[1].split('## Purpose',1)[0]; assert 'Tasks 020-025' not in text; expected={'runtime/planner_interface.py':'ff21a370903b930f0a6bb32361fc20129e20e46102cdb4d732ec6ebe37ad483f','tests/runtime/test_planner_interface.py':'50a8ec2ee00278b9081a51fd31531434bfaaabbdbb9ae4e59fbd53313e229e7c'}; assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in expected.items()); print('STATUS/DEPENDENCIES/SOURCE HASHES PASS')"
python -B -c "from scripts.validation.validate_scaffold import validate; scope=('PROJECT_CONTEXT.md','PROJECT_PLAN.md','TASKS.md','docs/task-specs/TASK-020-planner-interface.md','runtime/planner_interface.md'); errors=validate(); affected=[e for e in errors if any(e.startswith(p+':') or p in e for p in scope)]; print('repository_errors='+str(len(errors))); print('task020_document_errors='+str(len(affected))); print('\n'.join(affected).encode('ascii','backslashreplace').decode()); raise SystemExit(1 if errors else 0)"
git diff --check -- PROJECT_CONTEXT.md PROJECT_PLAN.md TASKS.md docs/task-specs/TASK-020-planner-interface.md
```

Exact changed files của lần cập nhật tài liệu: PROJECT_CONTEXT.md, PROJECT_PLAN.md,
TASKS.md, docs/task-specs/TASK-020-planner-interface.md và runtime/planner_interface.md.
Deleted files: none. Chỉ sửa tài liệu; không đổi code/tests/contracts/configuration
hoặc evidence. Task IDs/dependencies giữ nguyên; các task phụ thuộc không được tự
nâng trạng thái, TASK-026/032 vẫn DEFERRED.

Unverified và next handoff giữ như dưới đây; repository FAIL không được chuyển
thành PASS từ các scoped checks.

Pending handoff payload: scope=TASK-020 offline ABC/DTO/state-read adapter;
status=HANDOFF_BLOCKED; blocker=REPOSITORY_CHECKER_FAILED;
required_next=giải quyết repository blockers theo scope riêng, rồi review độc lập
shared interface/identity/provenance, sau đó integration riêng với
coordinator/gate/recorder; unverified=real backends, reference/evidence integrity,
live integration và independent approval.
Không self-approve/finalize, append history hoặc nâng thành VALIDATED. Cập nhật trạng thái tài liệu không cấp runtime approval.
