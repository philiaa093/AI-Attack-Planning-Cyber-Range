# Những file đưa lên Git

Phạm vi ngày 2026-10-14: đưa source hiện hành và lần sắp xếp thư mục lên `origin/main` theo yêu cầu người dùng. Commit/push không thay đổi status task, không phải independent approval hoặc xác nhận runtime.

| Nên đưa lên Git | Lý do |
|---|---|
| Code ở runtime, agent, actions, tools, dashboards và cyber-range | Cần để đọc, chạy và phát triển dự án |
| Tests, scripts, Dockerfile, Compose, configs/scenarios/contracts | Tái lập hành vi và giữ các ranh giới safety |
| package.json, package-lock.json, requirements.txt | Khai báo và pin dependency; lockfile không phải dependency đã cài |
| .env.example, tài liệu gốc, docs, thesis Markdown và script/SVG | Cấu hình mẫu không có secret; nguồn tài liệu cần version control |
| Ảnh demo đã chọn và receipts/handoff nhỏ gắn với thay đổi source | Minh họa có provenance và phục vụ kiểm tra thay đổi |
| Evidence hiện hành đã redact, có run ID/hash, và evidence lịch sử đang tracked | Không làm mất liên kết bằng chứng của tài liệu; Git không thay thế independent verification |
| reports/TASK-015-offline-contracts.json và TASK-015-offline-handoff.md | Hồ sơ bàn giao được tài liệu tham chiếu; không phải output chạy thường xuyên |

| Giữ cục bộ, không đưa lên Git | Quy tắc |
|---|---|
| API keys, .env thật, private keys, credential/secret files | Ignore; dùng environment hoặc secret store riêng |
| node_modules, frontend dist, virtualenv, bytecode và test/build caches | Sinh lại từ source/dependencies |
| Session/PID/log và SQLite/database files | Dữ liệu máy/phiên chạy, có thể chứa thông tin nhạy cảm |
| scripts/demo/demo-output và runtime evaluation/audit output | Volume lớn và thay đổi theo từng lần chạy; chỉ promote gói đã kiểm tra khi cần |
| gate-hygiene, gate-remediation, cache-quarantine, sequence-artifacts và dashboard handoffs | Bản chụp/source/build trùng lặp, đường dẫn và state của máy; giữ bản local nguyên trạng |
| reports/evaluation-runs và defense_receipts.json | Kết quả phiên/local readiness, không coi là trạng thái triển khai hiện tại |
| docs/literature, Word drafts, text checks và Word/PDF sinh ra | Tài liệu tham khảo có thể hạn chế phân phối; bản thảo cá nhân và bản xuất không cần đi cùng source |
| IDE settings và file tạm hệ điều hành | Không liên quan hành vi dự án |

`.gitignore` không xóa file trên máy và không tự loại file đã tracked. Evidence lịch sử đã tracked tiếp tục được bảo toàn; lần này không bỏ theo dõi evidence hoặc sửa nội dung evidence. Không chặn toàn bộ `evidence/`, `reports/`, JSON hoặc ảnh vì sẽ làm mất tài liệu/contract/bằng chứng cần thiết. Word/PDF được ignore theo destination cụ thể; tài liệu do dự án tự viết ở nơi khác có thể version control nếu cần.

`.gitattributes` giữ nguyên bytes của các pentest evidence mới và receipts bàn giao khi checkout trên Windows/Linux, tránh Git đổi LF/CRLF làm lệch hash. Evidence đã tracked giữ nguyên Git blobs lịch sử; không migrate encoding của chúng. Markdown được phép có trailing spaces để xuống dòng có chủ đích. Không sửa output lịch sử chỉ để làm sạch whitespace.

Trước push: kiểm tra candidate/index về secret và kích thước, `git diff --cached --check`, scaffold gate, kiểm tra cây staged trong workspace sạch. Không force-push, không sửa lịch sử remote và không sửa `.git` bằng tay. `.gitignore` là nơi thay quy tắc file được đưa lên repo.

Để promote một artifact đang ignore: kiểm tra redaction, provenance/hash, quyền phân phối và kích thước trước; stage đúng file/gói bằng `git add -f -- <path>`. Gói nhiều dữ liệu/binary nên dùng kho artifact hoặc Git LFS trong scope riêng. Không thêm LFS/dependency mới trong lần này vì candidate hiện tại nhỏ.

Kết quả kiểm tra source trước push có giới hạn: [handoff tái cấu trúc](implementation/restructure-handoff.md) ghi rõ lỗi legacy lifecycle tồn tại trước khi chuyển. Các suite hiện hành PASS không biến full integration discovery thành PASS, không xác nhận Docker/provider hoặc nâng các task `DEFERRED`.
