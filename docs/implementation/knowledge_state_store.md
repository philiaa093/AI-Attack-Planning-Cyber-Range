# Task 19: Kho trạng thái và tri thức ngoại tuyến

> Đường dẫn source đã chuyển ngày 2026-10-14; xem [bản đồ thư mục](../repository-layout.md). Receipts, command invocations và hash/path lịch sử bên dưới thuộc source trước khi chuyển. Các liên kết tới source và ví dụ import Python đã theo vị trí mới.

Bổ sung SQLite để lưu observations và truy vấn facts; tái dùng StateManager hiện có.
Phần bổ sung là IMPLEMENTED ngoại tuyến, chưa được review độc lập hoặc VALIDATED.
Receipts bên dưới thuộc phiên triển khai ngày 2026-10-11. Ngày 2026-10-12, theo yêu
cầu người dùng, [TASKS.md](../../TASKS.md#task-019--knowledge-state-store-sqlite-ngoại-tuyến)
và [đặc tả Task 19](../task-specs/TASK-019-knowledge-state-store.md) ghi trạng thái
hiện hành IMPLEMENTED; validation lịch sử giữ nguyên phạm vi. Hai source hashes
được đối chiếu khớp receipts; không chạy lại suites trong lần sửa tài liệu này.

## Quyết định kiến trúc

| Lựa chọn | Phù hợp | Giới hạn |
|---|---|---|
| dict và KnowledgeRepository | Unit test, một tiến trình, dữ liệu nhỏ | Mất dữ liệu khi tiến trình dừng |
| SQLite với `:memory:` | Test cùng API/schema với bản lưu trên đĩa | Chỉ tồn tại trong connection |
| SQLite file | Lab đơn máy, cần lưu bền vững và replay | Một writer tại một thời điểm; không phải DB phân tán |

MVP dùng SQLite và StateManager in-memory trong lúc replay. Chưa thêm cache riêng:
cache cần cơ chế vô hiệu hóa giữa nhiều connection. Không cần database server.

Luồng dữ liệu:

```text
Normalizer -> observation đã redact -> validation/scope/idempotency
                                      -> SQLite transaction
                                         observations append-only
                                         StateManager -> state snapshot + facts index
Planner/consumer <- get_state / query_facts / list_assets
```

Store chỉ lưu dữ liệu. Quyền dispatch vẫn thuộc policy/gate và approval hiện có.
Không nối phần bổ sung này vào runner, executor hoặc vòng lặp tự hành.

## Schema và identities

| Đối tượng | Khóa/Index | Nội dung |
|---|---|---|
| contexts | context_id PRIMARY KEY | Định nghĩa bất biến, initial budget, allowlists và state JSON hiện tại |
| observations | seq PRIMARY KEY; UNIQUE(context_id, observation_id) | JSON chuẩn hóa + source/hash/redaction/costs/phase, SHA-256, ingestion UTC |
| facts | PRIMARY KEY(context_id, fact_id) | subject, fact_type, confidence, fact JSON và source_observation_id |
| facts_subject | context_id, subject, fact_type, confidence | Lọc tri thức của từng tài sản |
| facts_type | context_id, fact_type, confidence | Lọc loại fact và confidence |
| assets (view) | Nhóm context_id, subject | Tài sản có TARGET/SERVICE/ENDPOINT facts và số facts tương ứng |

context_id là JSON tuple `(run_id, session_id, episode_id)` để tránh nối chuỗi nhập
nhằng. session_id là nhãn mô phỏng, tuyệt đối không phải cookie/token. Không merge
facts giữa context chỉ vì cùng route, target ID hay observation ID.

Tài sản dùng canonical target ID trong subject, không suy identity từ IP/URL tùy ý.
Assets view chỉ tính ba loại facts nói trên; không tự tạo tài sản từ mọi subject.
Lịch sử đầy đủ của confidence/provenance nằm trong observations. Facts hiện tại
giữ confidence cao nhất theo StateManager; không diễn giải confidence là xác suất
đã hiệu chuẩn hoặc suy confirmed finding từ việc tồn tại endpoint.

## API và ví dụ chạy trong bộ nhớ

Chạy từ repository root với Python. Chỉ dùng thư viện chuẩn và module đã có trong
repo; không cài thêm dependency. DDL đầy đủ nằm trong `_DDL` của file Python.

```python
import hashlib
from runtime.state.knowledge_state_store import KnowledgeStateStore, StoreContext

ctx = StoreContext("RUN-019", "SESSION-DEMO", "EPISODE-1")
obs = {
    "observation_id": "OBS-1",
    "run_id": "RUN-019",
    "action_id": "ACTION-RECON-001",
    "timestamp_utc": "2026-10-11T00:00:00Z",
    "outcome": "SUCCESS",
    "new_facts": [{
        "fact_id": "F-1", "fact_type": "ENDPOINT",
        "subject": "lab-fixture", "value": "/inventory",
        "confidence": 0.8,
    }],
    "evidence_refs": [],
}

with KnowledgeStateStore(":memory:") as store:
    store.create_context(
        ctx, scenario_id="SCN-001", objective_id="OBJ-019",
        budget={"actions": 10, "requests": 20, "seconds": 60.0},
        allowed_subjects={"lab-fixture"},
        allowed_actions={"ACTION-RECON-001"},
    )
    # Demo hash của nguồn giả; khi nhập report thật, truyền hash nguồn thực tế.
    source_hash = hashlib.sha256(b"synthetic-fixture").hexdigest()
    store.ingest(ctx, obs, source="SYNTHETIC-FIXTURE",
                 source_sha256=source_hash, phase="DISCOVERY")
    endpoints = store.query_facts(ctx, subject="lab-fixture",
                                  fact_type="ENDPOINT", limit=100)
    assets = store.list_assets(ctx)
    state = store.get_state(ctx)
    assert store.reconstruct(ctx) == state
```

Để lưu qua lần đóng/mở connection, thay `:memory:` bằng đường dẫn file SQLite mới
trong thư mục dữ liệu riêng được giao. Không dùng DB của target hoặc evidence có
sẵn. DB có schema/application ID không phù hợp bị từ chối trước writes, không tự
migrate. Chỉ định một connection/instance cho mỗi thread; nhiều instance trên cùng
file sử dụng BEGIN IMMEDIATE và timeout 5 giây để tuần tự hóa writes.

State JSON giữ nguyên state.schema.json: schema_version, run_id, scenario_id,
objective_id, phase, remaining_budget, observed_facts và previous_actions.
Metadata session/episode/source thuộc store envelope, không thêm field vào contract.

## Tính nhất quán và trust boundary

- Validate observation/state bằng validator contract hiện có; giới hạn observation
  1 MiB, finite JSON numbers, UTC timestamp và IDs. Chuẩn hóa UTC/hash/source
  metadata trước so sánh. Input/output được serialize để tách mutable objects.
- Input phải đã được Normalizer redact. Store từ chối các secret patterns được
  redactor hiện có nhận diện. Đây không phải chứng minh mọi secret đã được loại;
  raw HTML, source code, ground truth và dữ liệu nhạy cảm phải bị loại ở upstream.
- Allowlist trong context là phạm vi dữ liệu caller cung cấp sau policy approval;
  store không đọc hay cấp approval, không thay canonical policy. Hash nguồn là
  thông tin caller cung cấp; store không đọc source file hoặc dereference evidence.
- Cùng observation ID + cùng toàn bộ envelope: trả False, không trừ budget.
  Cùng ID khác dữ liệu/provenance/cost/phase: raise ValueError, không overwrite.
- Cùng fact ID khác subject/type/value: từ chối; dùng ID mới cho fact thay đổi.
  Cùng semantics được cập nhật confidence theo StateManager hiện có.
- Journal, facts và snapshot được commit cùng transaction, synchronous FULL.
  Lỗi write rollback tất cả; caller phải xử lý failure theo quy trình của mình.
- Chỉ StateManager tính budget. requests/seconds là costs caller đã đo và truyền;
  import ngoại tuyến có thể truyền 0. apply_observation vẫn giảm actions một lần
  theo semantics có sẵn, kể cả DENIED/ERROR. Không giảm budget lần nữa ở wrapper.
- reconstruct kiểm hash từng envelope và so snapshot với replay theo seq, không
  truy cập mạng/provider. get_state và query_facts đọc projections nhanh; không
  kiểm toàn bộ journal mỗi lần đọc.

SQLite journal này là dữ liệu vận hành, không thay thế immutable evidence recorder.
Hash không cung cấp chữ ký chống giả mạo; owner có quyền DB có thể sửa cả hash,
projection hoặc bỏ trigger. Evidence expected/observed vẫn tách riêng theo recorder.
SQL triggers chỉ chặn UPDATE/DELETE journal trong schema hiện hành.

## Hiệu năng và giới hạn chưa kiểm chứng

Planner đọc snapshot hoặc query facts có index và phân trang tối đa 1000 mỗi lần;
không phải replay toàn bộ history để truy vấn. list_assets trả inventory của context.
Mỗi ingest hiện replay toàn bộ history và refresh facts để bảo toàn API StateManager
mà không sửa internals. Chi phí ghi tăng theo history; chưa benchmark dữ liệu lớn.
Nếu cần ingest dài hạn, cần scope riêng cho checkpoint API/state restoration đã
được review. Không âm thầm thay semantics budgets hoặc fact aggregation.

Chưa kiểm actual process kill/power loss, container replacement/restore, DB trên
network filesystem, report thật hoặc consumer integration. Checks chỉ chứng minh
fixtures, temp SQLite files, connection reopen và hai writers trong cùng process.

## Command receipts và bàn giao

Build label: BUILD-TASK019-SQLITE-OFFLINE-20261011. Đây là nhãn bàn giao phiên,
không phải build contract đã được phê duyệt. Source HEAD được quan sát cuối checks:
`d9ae6ca0d5bb03ce381d7249665237f272eeddc9`. Working tree đã dirty trước triển khai.
Receipt UTC được ghi nhận: `2026-10-11T15:36:32.9063448Z`.
Nguồn kiểm thử: synthetic fixtures với run ID RUN-019/RUN-020, không phải live run.

| Exact command/check | Exit | Observed |
|---|---|---|
| `python -B -m unittest discover -s tests/runtime -p test_knowledge_state_store.py -v` | 0 | 21 tests PASS |
| `python -B -m unittest discover -s tests/unit -p test_knowledge_state_store.py -v` | 0 | 39 historical API regression tests PASS |
| `python -B scripts/validation/validate_scaffold.py` | 1 | SCAFFOLD INVALID, errors outside task scope; handoff blocked |
| `git diff --check` | 0 | PASS; existing tracked files emitted CRLF conversion warnings |
| `python -B -c "import ast,pathlib; paths=['runtime/knowledge_state_store.py','tests/runtime/test_knowledge_state_store.py']; [ast.parse(pathlib.Path(p).read_text(encoding='utf-8'),filename=p) for p in paths]; print('AST PASS: 2 files')"` | 0 | AST PASS: 2 files |
| `python -B -c "from pathlib import Path; fence=chr(96)*3; text=Path('runtime/knowledge_state_store.md').read_text(encoding='utf-8'); example=text.split(fence+'python\n',1)[1].split('\n'+fence,1)[0]; exec(compile(example,'knowledge_state_store.md example','exec')); print('DOCUMENT EXAMPLE PASS')"` | 0 | DOCUMENT EXAMPLE PASS |

Sau khi tạo tài liệu, gọi lại `validate()` bằng Python và lọc ba paths Task 19:
exit 1, repository_errors=656, task019_errors=0. Errors thuộc dashboard/node_modules,
artifacts có sẵn, demo/reports và các paths ngoài scope; không sửa hoặc xóa chúng.
Exact filtered check:

```text
python -B -c "from pathlib import Path; from scripts.validation.validate_scaffold import validate; scope=('runtime/knowledge_state_store.py','runtime/knowledge_state_store.md','tests/runtime/test_knowledge_state_store.py'); errors=validate(); affected=[e for e in errors if any(p in e for p in scope)]; print('repository_errors='+str(len(errors))); print('task019_errors='+str(len(affected))); print('\n'.join(affected)); raise SystemExit(1 if errors else 0)"
```

Kiểm tra cập nhật tài liệu ngày 2026-10-12 (không chạy lại suites triển khai):
repository check sau đồng bộ exit 1, repository_errors=656,
task019_document_errors=0; scoped document/link check exit 0,
scoped_document_errors=0, local_links_checked=59. Status/source hashes/whitespace
check PASS; các bảng trạng thái của 34 TASK khác và cấu trúc headings được bảo toàn.
`git diff --check` dưới đây exit 0. Exact commands cho gate và document/link check:

```text
python -B -c "from scripts.validation.validate_scaffold import validate; scope=('PROJECT_CONTEXT.md','PROJECT_PLAN.md','TASKS.md','docs/task-specs/TASK-019-knowledge-state-store.md','runtime/knowledge_state_store.md'); errors=validate(); affected=[e for e in errors if any(e.startswith(p+':') or p in e for p in scope)]; print('repository_errors='+str(len(errors))); print('task019_document_errors='+str(len(affected))); print('\n'.join(affected).encode('ascii','backslashreplace').decode()); raise SystemExit(1 if errors else 0)"
python -B -c "from pathlib import Path; import re; import scripts.validation.validate_scaffold as v; paths=['PROJECT_CONTEXT.md','PROJECT_PLAN.md','TASKS.md','docs/task-specs/TASK-019-knowledge-state-store.md','runtime/knowledge_state_store.md']; errors=[]; [v._check_markdown(v.ROOT/p,errors,v.TASK_HEADINGS if p.startswith('docs/task-specs/') else v.ROOT_HEADINGS.get(p)) for p in paths]; links=[(p,target) for p in paths for target in re.findall(r'\[[^\]]+\]\(([^)]+)\)',(v.ROOT/p).read_text(encoding='utf-8')) if not target.startswith('#') and not re.match(r'[a-z]+://',target)]; assert all(((v.ROOT/p).parent/target.split('#',1)[0]).resolve().is_relative_to(v.ROOT) and ((v.ROOT/p).parent/target.split('#',1)[0]).resolve().exists() for p,target in links); print('scoped_document_errors='+str(len(errors))); print('local_links_checked='+str(len(links))); print('\n'.join(errors).encode('ascii','backslashreplace').decode()); raise SystemExit(1 if errors else 0)"
git -c core.safecrlf=false diff --check -- PROJECT_CONTEXT.md PROJECT_PLAN.md TASKS.md docs/task-specs/TASK-019-knowledge-state-store.md
```

Lần cập nhật tài liệu sửa đúng năm paths: PROJECT_CONTEXT.md, PROJECT_PLAN.md,
TASKS.md, docs/task-specs/TASK-019-knowledge-state-store.md và tài liệu này.
Không xóa file; code/contracts/configuration và evidence lịch sử không bị sửa.

Lượt đầu suite mới có 19 tests, exit 1 với hai lỗi cleanup Windows: test dùng
sqlite3 connection context manager mà chưa đóng connection. Sửa tests bằng
contextlib.closing; lượt chạy cuối ở bảng có 21 tests PASS. Không chuyển lượt lỗi
thành PASS hoặc claim persistence qua process restart từ connection reopen.

Expected/observed cho synthetic checks: retry phải giữ budget/journal; conflict và
scope violations phải không thay state; lỗi projection write phải rollback journal;
session/episode phải độc lập; replay phải khớp snapshot. Assertions đã PASS.

Exact added files trong phiên triển khai ngày 2026-10-11:

- runtime/knowledge_state_store.py
- runtime/knowledge_state_store.md
- tests/runtime/test_knowledge_state_store.py

Deleted files trong phiên triển khai: none. Phiên triển khai không sửa StateManager,
contracts, cấu hình, TASKS.md hoặc historical evidence. Source SHA-256 tại receipt UTC:

- runtime/knowledge_state_store.py: D3B5DE91295AE536981789D8E863ED0EBBC17B051A6E3F40BD8E9A5727F4A79E
- tests/runtime/test_knowledge_state_store.py: 3676D81C95378EA51630E12FF82FE31912FFBF83607DA79BF1C2397B377ED853

Pending handoff payload: scope=offline SQLite state store; status=HANDOFF_BLOCKED;
blocker=REPOSITORY_CHECKER_FAILED; required_next=repository blockers xử lý theo scope
riêng, review độc lập schema/identity/budget/provenance và consumer compatibility;
unverified=live integration, durable evidence binding, process/container restore,
performance. Không tự approve/finalize hoặc nâng validation.
