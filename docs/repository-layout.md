# Cấu trúc thư mục

Thiết kế và chuyển đường dẫn theo yêu cầu ngày 2026-10-14. Chưa có independent review; việc sắp xếp không nâng trạng thái runtime hoặc task.

```text
PBL6_FINAL/
├── README.md, AGENTS.md                 # Điểm vào và quy tắc làm việc
├── PROJECT_CONTEXT.md, PROJECT_PLAN.md  # Nguồn bối cảnh và kế hoạch
├── TASKS.md, CHANGELOG.md               # Trạng thái và lịch sử hiện có
├── runtime/                            # Code thực thi
│   ├── orchestration/                  # Runner và PTES coordinator
│   ├── discovery/                      # Discovery engine, report importer
│   ├── safety/                         # CentralizedSafetyGate
│   ├── planners/                       # Interface, adapter, RULE/LLM/HYBRID
│   ├── state/                          # KnowledgeStateStore
│   ├── evidence/                       # Recorder, verifier, report/replay
│   ├── evaluation/                     # Offline RL, reward, evaluation, costs
│   ├── audit/                          # Audit packaging, custody, reconciliation
│   └── lab/                            # Bounded executor, fixtures, capabilities
├── agent/                              # Planner contracts, memory, perception
├── actions/                            # Action catalog, safety, action contracts
├── tools/                              # Adapters, parsers, tool contracts
├── dashboards/                         # App, thiết kế, ảnh và export
│   └── app/{backend,frontend}/
├── cyber-range/                        # Compose, gateway, targets, snapshots/reset
├── configs/                            # Cấu hình có thẩm quyền
├── scenarios/                          # Scenario contracts và fixtures
├── evaluation/                         # Metrics, ground truth, research contracts
├── tests/                              # Kiểm thử theo thành phần
├── scripts/                            # Demo, lab, validation, evaluation utilities
├── docs/
│   ├── adr/, guides/, runbooks/, task-specs/
│   ├── implementation/                 # Tài liệu API/triển khai trước ở runtime/
│   ├── thesis/                         # Nguồn báo cáo học thuật trước ở report/
│   │   ├── chapters/, appendices/, figures/, tables/
│   │   ├── word/                       # Bản xuất Word/PDF và script tạo báo cáo
│   │   ├── drafts/                     # Bản Word cá nhân trước ở MicroWord/
│   │   └── checks/                     # Các file kiểm tra văn bản rời
│   └── literature/                     # PDF tham khảo trước ở pdf/
├── evidence/                           # Bằng chứng bất biến
└── reports/                            # Kết quả sinh ra, audit/defense receipts
```

Đặt code mới cạnh thành phần chịu trách nhiệm. Giữ tên package Python hiện có; import dùng đường dẫn mới, ví dụ `from runtime.safety.discovery_gate import CentralizedSafetyGate`. Không có lớp alias cho import cũ. `agent/` và `runtime/planners/` phân biệt contracts/thành phần nền với executable planners; `evaluation/` và `runtime/evaluation/` phân biệt ground truth/metrics với máy chạy offline. Ground truth không được chuyển vào planner input.

Tài liệu kiến trúc chung ở `docs/`; tài liệu API và giới hạn triển khai ở `docs/implementation/`. Bản thảo luận văn ở `docs/thesis/`; báo cáo sinh từ run ở `reports/` hoặc destination evidence đã được duyệt. Cấu hình, contracts và registry giữ đường dẫn hiện hành. Chuyển thư mục không cấp quyền chạy lab hoặc đổi policy.

Các thư mục lịch sử `runtime/audit-artifacts/`, `runtime/cache-quarantine/`, `runtime/evaluation-runs/`, `runtime/gate-hygiene/`, `runtime/gate-remediation/`, `runtime/sequence-artifacts/`, `dashboards/app/handoffs/`, `scripts/demo/demo-output/`, cùng `evidence/` và `reports/` được giữ nguyên. Chúng chứa receipts, frozen sources hoặc hash/path binding; chuyển chúng cần migration custody riêng. `runtime/evaluation/evaluate_all.py` tiếp tục ghi dưới `runtime/evaluation-runs/` để giữ ranh giới destination hiện hành. Hash trong receipt cũ thuộc source cũ, không xác nhận source sau tái cấu trúc.

Các lệnh entry point đổi đường dẫn:

| Trước | Hiện tại |
|---|---|
| `python -B -m runtime.evaluate_all` | `python -B -m runtime.evaluation.evaluate_all` |
| `python -B -m runtime.generate_audit_package` | `python -B -m runtime.audit.generate_audit_package` |
| `python -B -m runtime.invoice_reconciliation` | `python -B -m runtime.audit.invoice_reconciliation` |
| `python -B -m runtime.repository_cleanup` | `python -B -m runtime.audit.repository_cleanup` |
| `python -B -m runtime.restore_historical_runs` | `python -B -m runtime.audit.restore_historical_runs` |
| `python -B -m runtime.cli` | `python -B -m runtime.lab.cli` |
| `python -m runtime.server` | `python -m runtime.lab.server` |
| `runtime/rl_requirements.txt` | `runtime/evaluation/requirements.txt` |

Launcher dashboard giữ đường dẫn `scripts/demo/start_control_center.ps1`. Compose/Dockerfile đã đổi module entry point; chưa chạy Docker trong lần sắp xếp này. Các command receipts lịch sử trong tài liệu được giữ như lịch sử; dùng bảng trên cho source hiện tại.

Kiểm tra offline: `python -B scripts/validation/validate_scaffold.py` và các suite trong `tests/`. Dùng `-B` để tránh sinh bytecode vào cây source. Danh sách chuyển file, thay đổi và receipts lần này nằm trong [handoff](implementation/restructure-handoff.md).
