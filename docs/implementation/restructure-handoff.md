# Bàn giao tái cấu trúc thư mục

Phạm vi người dùng chọn: tái cấu trúc sâu, gom code, sửa import và kiểm thử. Status: `IMPLEMENTED`; independent review `NOT_RUN`. Không đổi contracts, safety policy, action semantics hoặc trạng thái task. Không commit, append history hoặc self-approve.

## Exact files và bảo toàn dữ liệu

- Tổng 124 file chuyển vị trí; bảng đường dẫn và hash trước/sau: [moves.tsv](restructure-20261014/moves.tsv). Python modules vào chín package runtime; tài liệu triển khai về `docs/implementation/`; nguồn báo cáo về `docs/thesis/`; Word drafts và PDF về `docs/thesis/drafts/` và `docs/literature/`. Word/PDF chỉ đổi vị trí, giữ nguyên nội dung.
- Exact changed files, bao gồm file mới/chuyển và sửa import/đường dẫn: [changed-files.txt](restructure-20261014/changed-files.txt). Các file receipt bổ sung được liệt kê trong [receipt-files.txt](restructure-20261014/receipt-files.txt).
- Exact deleted content: [deleted-files.txt](restructure-20261014/deleted-files.txt): không xóa nội dung. Đường dẫn cũ biến mất do chuyển nằm trong moves.tsv.
- 4.827 evidence/receipt/archive files giữ đường dẫn và hash: [preserved-files.tsv](restructure-20261014/preserved-files.tsv). Source snapshots, reports và evidence lịch sử không bị sửa.
- Sửa imports/mock targets, tính repository root, source hashing, inventory dashboard, Compose/Docker entry points, validator report paths và Markdown links. Một link source cũ trong receipt được validator đối chiếu qua mapping exact, có regression kiểm tra destination phải tồn tại và không áp dụng cho tài liệu khác.
- Giữ working tree chưa commit của người dùng; danh sách Git trước chuyển: [git-before.txt](restructure-20261014/git-before.txt).

## Command receipts

[Exact invocations, exit codes và output](restructure-20261014/command-receipts.md). 955 Python tests PASS trong các suite có source hiện hành; 37 frontend tests PASS, TypeScript/build PASS. Scaffold gate PASS và whitespace PASS. [Final delivery gate](restructure-20261014/gate-delivery.txt); [final preservation check](restructure-20261014/preservation-delivery.txt). Intermediate failures được giữ riêng; không ghi đè hoặc chuyển failures thành PASS.

Full integration discovery exit 1: 142 tests pass, một legacy module không import được. Driver riêng chạy 142 tests với exclusion công khai; không mô tả full discovery là PASS. Lỗi đã tái hiện bằng source bytes trước chuyển trong bản sao cô lập. Checks là offline/mock/temp và loopback fixtures, không chứng minh Docker runtime.

## Unverified, blockers và pending handoff payload

- `INTEGRATION_LEGACY_SOURCE_MISSING`: `test_runtime_lifecycle.py` tham chiếu `EvidenceLog`, `RuntimeConfig`, `RuntimeRunner`, `RuntimeHTTPServer` không có trong source trước chuyển. Giữ exact baseline bytes của test; không thêm implementation giả hoặc skip. Full integration suite vẫn bị chặn bởi lỗi cũ này.
- New import paths thay đổi source API; external callers cần theo [folder map](../repository-layout.md). Không có aliases cho đường dẫn cũ.
- Docker image/Compose execution, actual provider, live lab, reload process dashboard và xuất Word chưa chạy. Compose/Dockerfile chỉ sửa tên module entry point; process đang chạy cần restart để dùng source mới.
- Historical hashes/receipts thuộc source trước chuyển; checks hiện tại không xác nhận lại approvals hoặc kết quả nghiên cứu cũ.
- Pending payload: folder map, moves/hashes, exact changed/deleted files, receipts và preservation manifest cho independent review. Cần scope riêng để xử lý missing legacy lifecycle source và authorized Docker check nếu muốn kiểm chứng entry points trên container. Chưa có independent approval hoặc finalization.
