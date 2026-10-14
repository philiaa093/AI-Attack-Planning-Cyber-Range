# Bàn giao TASK-015 — discovery report ngoại tuyến

## Phạm vi và trạng thái

Hồ sơ được đưa vào repository chính theo yêu cầu người dùng: “bàn giao lại các tài liệu trong thư mục chính đi”. Đây là bàn giao tài liệu, không phải phê duyệt build hoặc cập nhật trạng thái task.

- Task: `TASK-015`.
- Plan: `PLAN-TASK015-OFFLINE-SIM-005`.
- Build bàn giao: `BUILD-TASK015-OFFLINE-SIM-005-H1`.
- Base HEAD của build: `d9ae6ca0d5bb03ce381d7249665237f272eeddc9`.
- Phạm vi: `OFFLINE_DEFENSIVE_REVIEW_SIMULATION`.
- Gate: **HANDOFF_BLOCKED**; review: **NOT_RUN**.
- Toàn TASK-015: **chưa được chứng nhận hoàn tất**; không đổi `TASKS.md`.

Contract PLAN/BUILD, receipts, hashes và pending payload nằm trong [TASK-015-offline-contracts.json](TASK-015-offline-contracts.json). Các contract này được chép từ hồ sơ phiên làm việc, không cấp lại approval và không thay baseline lịch sử.

## Code đã nằm trong repository chính

| File | Nội dung |
|---|---|
| [runtime/discovery_report_importer.py](../runtime/discovery_report_importer.py) | Nhập báo cáo httpx JSONL/WhatWeb JSON; metadata và canonical observations ngoại tuyến; mô phỏng review bằng fixture opt-in |
| [tests/runtime/test_discovery_report_importer.py](../tests/runtime/test_discovery_report_importer.py) | 45 tests importer/observations/simulation bằng stdlib unittest |

Hai file đã có trực tiếp trong `E:/PBL6_FINAL`; tại lượt xác nhận vị trí chúng là untracked, chưa commit. Không có file code bị xóa trong scope này. Việc đưa hồ sơ vào `reports/` không sửa code, runner, planner, schema, catalog, cấu hình hoặc evidence.

## Hành vi đã triển khai

- Nhập báo cáo có giới hạn, kiểm tra path/UTF-8/JSON/URL/approval/allowlists/lab mode/kill switch; không chạy công cụ ngoài.
- Metadata target chưa được xác minh. Canonical observations có outcome `PARTIAL`; declarations của target có confidence 0.
- Fixture chỉ có `rule`, `audit`, `control`, mỗi mục có `expected` và `observed` thuộc `CLEAR/BLOCKED/MISSING`; tối đa 16 KiB.
- Review mô phỏng tối đa 3 bước, ceiling monotonic 5 giây trong nhánh simulation. Rule bị chặn thì review audit, không tìm đường vượt firewall. Có dừng khi thiếu dữ liệu, không tiến triển hoặc hết budget.
- Evidence có hash và causal linkage; expected/observed tách biệt; giữ artifacts đã ghi khi bước sau lỗi.
- Không network dispatch, subprocess, provider hoặc tích hợp autonomous attack workflow trong phần importer/simulation này. `external_execution` vẫn `UNRESOLVED`.

## Receipts mới nhất của build

Các lệnh dưới đây đã chạy ở lượt 2026-10-11T14:21Z; đây không phải lượt chạy mới khi sao chép tài liệu.

| Command | Exit | Kết quả |
|---|---:|---|
| `python -B -m unittest discover -s tests/runtime -p test_discovery_report_importer.py -v` | 0 | 45 tests OK |
| `python -B -m unittest discover -s tests/unit -p test_tool_adapters.py -v` | 0 | 27 tests OK |
| `python -B -m unittest discover -s tests/unit -p test_observation_normalizer.py -v` | 0 | 33 tests OK |
| `python -B scripts/validation/validate_scaffold.py` | 1 | SCAFFOLD INVALID tại `dashboards/app/frontend/tsconfig.json`, dòng 9 cột 5 |
| `git diff --check` | 0 | Không lỗi whitespace; LF/CRLF warnings; không kiểm untracked content |
| AST parse hai file code/test | 0 | AST PASS: 2 files; command đầy đủ trong JSON |

Tổng 105 tests PASS. Own whitespace scan PASS. Hash trước/sau của 15 đường dẫn source/dependency/shared tests không đổi trong lượt này; không chứng minh mọi dependency bắc cầu hoặc không có thay đổi tạm thời giữa hai lần hash.

Gate đã xác minh contract fields, IDs, HEAD, declared scope và own source hashes; dừng với exit 2 vì blockers. Repair budget chưa dùng: 0/1. Không có REVIEW_CONTRACT cho SIM-005-H1.

## Blockers và việc chưa kiểm chứng

1. **Baseline lịch sử chưa đối chiếu được:** baseline ngoài scope chỉ lưu aggregate hash, không có per-file manifest để xác định đầy đủ delta. Không thay baseline cũ bằng snapshot mới hoặc quy mọi thay đổi cho phiên khác.
2. **Worktree tiếp tục thay đổi ngoài scope:** lượt 14:20Z thấy 24 file mới dưới `scripts/demo/demo-output/`; nguồn gốc `UNRESOLVED`, không xóa/revert.
3. **Required checker FAIL:** lỗi JSON nêu trên ở dashboard ngoài scope TASK-015. Receipt FAIL được giữ nguyên, không thay bằng PASS cũ.

Chưa kiểm chứng scanner/version/provenance thật, firewall thật, provider, planner/runtime consumption và adversarial ancestor filesystem race trên Windows. Adapter mock legacy chưa được thay thế. Approval lịch sử OBS-004 chỉ thuộc artifact ngoại tuyến trước SIM-005, không phê duyệt build mới.

## Pending handoff

Owner phạm vi dashboard xử lý lỗi checker theo scope riêng; đối chiếu baseline lịch sử và ổn định worktree trước gate mới. Chỉ sau gate hợp lệ mới tiếp tục review. Không tự xóa blocker, ghi APPROVE, sửa task status, chạy live workflow hoặc commit.

Tài liệu này và JSON là hồ sơ bàn giao bị chặn, không phải runtime evidence hoặc chứng nhận toàn TASK-015 hoàn tất. Không sửa/xóa hồ sơ gốc ngoài repository hay evidence lịch sử.
