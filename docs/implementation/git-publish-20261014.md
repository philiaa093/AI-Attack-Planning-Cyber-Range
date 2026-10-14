# Bàn giao Git ngày 2026-10-14

Người dùng yêu cầu phân tích file nên push, sửa quy tắc Git và push source hiện hành. Remote: `origin`, branch: `main`; baseline local/remote cùng `d9ae6ca0d5bb03ce381d7249665237f272eeddc9`. Authorization commit/push thuộc yêu cầu này, không suy ra approval cho runtime hoặc thay đổi task status.

## Phạm vi đưa lên Git

Code, tests, docs, contracts/configs/scenarios hiện hành, dependency manifests/lockfile, selected screenshots, 434 file pentest evidence mới đã kiểm tra trường nhạy cảm, hai hồ sơ bàn giao TASK-015 và lần chuyển thư mục trước. Bao gồm các thay đổi sẵn có của người dùng; không quy toàn bộ implementation cho lượt Git này.

Thay đổi của lượt Git: `.gitignore`, `.gitattributes`, [quy tắc Git](../git-policy.md), link từ README, một link local artifact trong sequential work note, bỏ blank line cuối file/whitespace trong 10 source/docs files. Không sửa nội dung evidence, configs, contracts, catalog hoặc scenario trong lượt Git; các delta source khác có sẵn từ trước.

[Exact staged changed/added/deleted/renamed paths](git-publish-files-20261014.tsv). Delete entry `runtime/autonomous_runner.py` tương ứng source chuyển về `runtime/orchestration/autonomous_runner.py`; Git chưa nhận diện thành rename do delta source. Không xóa nội dung local nào để publish.

Local output, dependency/build/cache, sessions, credentials, database, duplicate archives và Word/PDF được giữ trên máy và ignore. Phân loại cụ thể tại [git-policy.md](../git-policy.md). `.git` không bị sửa bằng tay; không force-push hoặc viết lại lịch sử.

## Command receipts trước commit

| Invocation/check thực tế | Exit/result |
|---|---|
| `git fetch origin main`; `git rev-list --left-right --count HEAD...origin/main` | 0; `0 0` |
| stdlib inline driver gọi `git check-ignore --quiet --no-index` | 26 ignored paths + 17 retained paths PASS |
| `git add -A -- .`; `git add --renormalize -- evidence` | 0; existing evidence modifications in index: 0 |
| `git diff --cached --check` | 0 |
| `git ls-files -ci --exclude-standard` | Empty: không có ignored artifact đã tracked |
| stdlib scanner đọc staged objects, kiểm tra private/provider/GitHub/AWS key patterns và nonredacted credential/cookie JSON fields | 0 flagged; bounded scan, không phải chứng minh tuyệt đối không có secret |
| `git cat-file --batch` export đúng index objects ra thư mục sạch ngoài repo | 0; không gồm ignored output/dependencies |
| `python -B scripts/validation/validate_scaffold.py` trong clean index copy | 0; 1.375 files checked trước khi thêm hai file bàn giao này |
| `python -B -m unittest discover -s tests/runtime -p test_*.py` trong clean index copy | 0; 437 tests PASS |
| `python -B -m unittest discover -s tests/backend -p test_*.py` trong clean index copy | 0; 74 tests PASS |
| `python -B -m unittest discover -s tests/scaffold -p test_*.py` trong clean index copy | 0; 49 tests PASS |
| So sánh SHA-256 working files với preservation manifest của lượt tái cấu trúc | 4.827 historical files unchanged |
| So sánh Git index với working bytes cho evidence mới/receipts | Exact bytes match; existing evidence Git blobs không thay đổi |

Raw command outputs, pre-stage snapshot, staged hashes và export nằm cục bộ tại `C:/Users/DELL/AppData/Local/Temp/pbl6-publish-j_svvb1g/`. Thư mục tạm này không được publish. 955 tests Python/37 frontend tests và frontend build của source trước lượt Git được ghi trong [handoff tái cấu trúc](restructure-handoff.md); không gọi đó là lượt chạy lại toàn bộ suite trong lần Git này.

## Giới hạn và pending handoff

`INTEGRATION_LEGACY_SOURCE_MISSING` tồn tại trước lượt tái cấu trúc: full integration discovery lỗi import `test_runtime_lifecycle.py`; không sửa giả, skip hoặc gọi full suite PASS. Independent review, Docker/real-provider run, Word export và process reload chưa thực hiện. `TASK-026`/`TASK-032` giữ `DEFERRED`.

Pending payload cho review: Git commit/diff, manifest file changes, git-policy, clean index checks và preservation records. Publication không self-approve hoặc finalize implementation; kết quả push và commit ID được trả riêng trong chat sau thao tác thực tế.
