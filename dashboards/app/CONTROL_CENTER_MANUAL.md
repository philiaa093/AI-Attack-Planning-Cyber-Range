# HỆ THỐNG AUTONOMOUS CYBER RANGE CONTROL CENTER
## TÀI LIỆU THIẾT KẾ KIẾN TRÚC, VẬN HÀNH VÀ BẢO VỆ ĐỒ ÁN

---

## 1. TỔNG QUAN VÀ MỤC TIÊU HỆ THỐNG

Hệ thống **Autonomous Cyber Range Control Center** là trung tâm điều khiển và quan sát thời gian thực cho đồ án nghiên cứu **AI Attack Planning trong Cyber Range cô lập**.

### 1.1 Vòng lặp Điều khiển Tự trị Đóng (Autonomous Closed-Loop)
Hệ thống vận hành theo chu trình khép kín tuyệt đối, không có bất kỳ bước trung gian nào chạy lệnh shell tùy ý:

```text
       ┌────────────────────────────────────────────────────────┐
       │                                                        │
       ▼                                                        │
  1. OBSERVE (ObservationDrivenDiscovery / Tool Adapters)       │
       │                                                        │
       ▼                                                        │
  2. STATE (ObservationNormalizer -> StateManager)              │
       │                                                        │
       ▼                                                        │
  3. PLAN (ObservedStatePlanner: RULE / LLM Provider)           │
       │                                                        │
       ▼                                                        │
  4. SAFETY GATE (CentralizedSafetyGate: 10 policy checks)      │
       │                                                        │
       ├── [DENY] ──► Ghi Audit Deny ──► 0 Dispatch ───────────┤
       │                                                        │
       └── [PERMIT]                                             │
             │                                                  │
             ▼                                                  │
  5. EXECUTE (Controlled Executor: HTTP/Gateway qua 127.0.0.1)  │
       │                                                        │
       ▼                                                        │
  6. COLLECT EVIDENCE (DurableEvidenceRecorder: Hash/Fsync/WORM)│
       │                                                        │
       ▼                                                        │
  7. VERIFY (EvidenceVerifier: Offline Hash / Zero-Network)     │
       │                                                        │
       ▼                                                        │
  8. UPDATE & REPLAN ───────────────────────────────────────────┘
```

### 1.2 Các Nguyên tắc Cốt lõi (Non-Negotiable Invariants)
1. **Không Arbitrary Shell**: AI Agent **chỉ được phép** đề xuất các hành động có kiểu định nghĩa sẵn (`Typed Actions`) từ `ACTION_CATALOG` (13 canonical actions). Không mở subprocess, shell command hay raw exploit execution.
2. **Không Dữ liệu Giả (Zero Fabricated Data)**: Toàn bộ số liệu trên dashboard (số request, danh sách URL/form, container IDs, quyết định gate, hashes, budget còn lại) phải phản ánh 100% trạng thái thực tế từ runtime và evidence storage. Nếu Docker tắt, báo `UNAVAILABLE`, tuyệt đối không giả lập `HEALTHY`.
3. **Fail-Closed Safety**: Mọi trường hợp thiếu token duyệt, vi phạm allowlist target/action, vượt budget hoặc kích hoạt nút dừng khẩn cấp đều dẫn đến từ chối thực thi tức thì (`DENIED` / `BLOCKED`), với **số lượt dispatch HTTP = 0**.
4. **Fail-Safe Telemetry**: Việc phát sóng sự kiện (Event Hook / SSE) cho dashboard chỉ đóng vai trò quan sát (`observability`), tuyệt đối không có thẩm quyền can thiệp hay làm gián đoạn tính an toàn của Safety Gate. Ngoại lệ trong telemetry bus được cô lập hoàn toàn.

---

## 2. KIẾN TRÚC TỔNG THỂ HỆ THỐNG

Hệ thống được tổ chức thành 3 tầng phân tách rõ ràng:

```text
┌─────────────────────────────────────────────────────────────────────────┐
│                   TẦNG 1: FRONTEND OPERATOR DASHBOARD                   │
│          (React 18 + Vite + TypeScript + TailwindCSS + Lucide Icons)    │
│  - 5 Core Observability Cards (Range, Agent, Safety, Executor, Evidence)│
│  - Pipeline Stage Indicator (PREFLIGHT -> OBSERVE -> PLAN -> GATE...)   │
│  - Live Event Stream Log (Server-Sent Events)                           │
│  - Operator Control Panel (Start Run, Stop, Emergency Kill Switch)      │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │ HTTP REST + SSE Stream
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                 TẦNG 2: BACKEND CONTROL PLANE (FastAPI)                 │
│                          (127.0.0.1:8000)                               │
│  ├── Control API (`control_api.py`): REST Handlers + SSE Endpoints      │
│  ├── Run Manager (`run_manager.py`): Quản lý luồng worker, mutex state  │
│  ├── Event Sink (`event_sink.py`): Bounded Ring Buffer + Multi-SSE Bus  │
│  ├── Range Controller (`range_controller.py`): Quản lý vòng đời Docker  │
│  └── Pydantic Schemas (`models.py`): Typed Contract Models              │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │ Thread Callback / In-Memory Bridge
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                TẦNG 3: AUTONOMOUS RUNTIME & CYBER RANGE                 │
│  ├── Autonomous Runner (`runtime/autonomous_runner.py`): Vòng lặp agent │
│  ├── Centralized Safety Gate (`runtime/discovery_gate.py`): Thẩm quyền  │
│  ├── Durable Evidence Recorder (`runtime/discovery_recorder.py`)        │
│  ├── Observed State Planner (`runtime/observed_planner.py`): RULE/LLM   │
│  ├── State Manager (`agent/memory/state/state_manager.py`)              │
│  └── ShopLab Cyber Range (Docker Compose: lab-ecommerce, gateway)       │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 3. DANH MỤC SỰ KIỆN THỜI GIAN THỰC (STRUCTURED RUNTIME EVENT CATALOG)

Tầng runtime `AutonomousRunner` phát sinh các sự kiện có cấu trúc chuẩn hóa qua `event_hook`. Mỗi sự kiện tuân thủ schema `AgentEvent`:

```json
{
  "id": 104,
  "event_type": "SAFETY_PERMITTED",
  "timestamp": "2026-10-11T14:30:15.120Z",
  "run_id": "RUN-DEMO-20261011-001",
  "iteration": 1,
  "data": {
    "action_id": "ACTION-RECON-001",
    "target": "http://127.0.0.1:18088/shop",
    "decision": "PERMIT"
  }
}
```

### Bảng Sự Kiện Đầy Đủ (Lifecycle Event Catalog)

| Tên Sự Kiện | Giai Đoạn Kích Hoạt | Dữ Liệu Chứa Trong Payload | Trạng Thái Pipeline |
|---|---|---|---|
| `RUN_STARTED` | Khởi đầu phiên thực thi mới | `run_id`, `max_iterations`, `target_allowlist` | `PREFLIGHT` |
| `AGENT_ITERATION_STARTED` | Bắt đầu một vòng lặp | `iteration`, `max_iterations`, `budget_remaining` | `OBSERVE` |
| `PLANNER_STARTED` | Bắt đầu gọi Planner | `iteration`, `requested_mode` | `PLAN` |
| `PLANNER_PROPOSED` | Planner trả về hành động đề xuất | `action_id`, `action_type`, `target`, `parameters` | `PLAN` |
| `PLANNER_FALLBACK` | LLM mất kết nối, fallback về RULE | `primary_mode`, `fallback_mode`, `reason` | `PLAN` |
| `SAFETY_EVALUATION_STARTED`| Gate tiếp nhận đề xuất để kiểm định | `action_id`, `target_id`, `policy_id` | `SAFETY` |
| `SAFETY_PERMITTED` | Gate chấp thuận cho phép dispatch | `action_id`, `target`, `decision: PERMIT` | `SAFETY` |
| `SAFETY_DENIED` | Gate từ chối do vi phạm chính sách | `action_id`, `target`, `decision: DENY`, `reason` | `SAFETY` |
| `ACTION_DISPATCH_STARTED` | Bắt đầu gửi HTTP request qua Gateway | `action_id`, `target`, `method: GET` | `EXECUTE` |
| `ACTION_DISPATCHED` | Nhận phản hồi HTTP từ Cyber Range | `action_id`, `status_code`, `latency_ms`, `bytes` | `EXECUTE` |
| `ACTION_COMPLETED` | Xử lý xong phản hồi hành động | `action_id`, `success: true`, `observation_count` | `EXECUTE` |
| `ACTION_FAILED` | Thất bại khi thực thi hành động | `action_id`, `error_type`, `message` | `EXECUTE` |
| `OBSERVATION_RECEIVED` | Tiếp nhận và bóc tách dữ liệu mới | `source_url`, `links_found`, `forms_found` | `OBSERVE` |
| `STATE_UPDATED` | StateManager cập nhật facts mới | `state_version`, `endpoints_count`, `facts_count` | `STATE` |
| `BUDGET_UPDATED` | Trừ ngân sách request/thời gian | `budget_remaining`, `budget_consumed`, `max_budget` | - |
| `EVIDENCE_RECORDED` | Ghi bằng chứng xuống ổ cứng và fsync | `evidence_id`, `artifact_path`, `sha256` | `EVIDENCE` |
| `EVIDENCE_VERIFIED` | Xác minh chữ ký SHA256 offline | `evidence_id`, `verified: true`, `rule_id` | `VERIFY` |
| `FINDING_CREATED` | Tạo finding lỗ hổng sau xác minh | `finding_id`, `type`, `severity`, `target` | `VERIFY` |
| `STOP_CONDITION_REACHED` | Đạt điều kiện dừng (hết trang/budget) | `condition`, `iteration`, `total_actions` | `COMPLETE` |
| `EMERGENCY_STOP_ACTIVATED`| Bấm nút khẩn cấp (Kill Switch ON) | `reason`, `kill_switch_active: true` | `BLOCKED` |
| `RUN_STOPPED` | Dừng an toàn theo yêu cầu người dùng | `run_id`, `reason`, `total_iterations` | `COMPLETE` |
| `RUN_COMPLETED` | Hoàn thành toàn bộ quy trình demo | `run_id`, `total_iterations`, `evidence_count` | `COMPLETE` |

---

## 4. CHI TIẾT CÁC ENDPOINT REST VÀ SSE (API REFERENCE)

FastAPI Control Plane chạy mặc định tại `http://127.0.0.1:8000`.

### 4.1 Bảng Tra Cứu Endpoints

| Đường dẫn (Route) | Phương thức | Mô tả Chức năng | Định dạng Phản hồi |
|---|---|---|---|
| `/api/status` | `GET` | Snapshot toàn diện gom trạng thái Range, Run, Agent, Safety, Evidence, Pipeline | JSON (`SystemStatus`) |
| `/api/range/status` | `GET` | Chi tiết container Docker và HTTP Health Probe của Gateway | JSON (`RangeStatus`) |
| `/api/range/start` | `POST` | Khởi động containers ShopLab có theo dõi quyền sở hữu (`_owned`) | JSON (`RangeStatus`) |
| `/api/range/stop` | `POST` | Dừng các container thuộc quyền sở hữu của phiên, bảo toàn database volume | JSON (`RangeStatus`) |
| `/api/demo/preflight` | `POST` | Chạy kiểm tra preflight thật (Docker, image, storage write, policy imports) | JSON (`PreflightResponse`) |
| `/api/runs/current` | `GET` | Thông tin chi tiết run đang chạy hoặc run gần nhất | JSON (`RunStatus`) |
| `/api/runs` | `POST` | Khởi động run mới (`presentation`, `deny-demo`, `autonomous`) | JSON (`ControlResponse`) |
| `/api/runs/{id}/stop` | `POST` | Yêu cầu dừng an toàn phiên đang chạy | JSON (`ControlResponse`) |
| `/api/emergency-stop` | `POST` | **Kích hoạt khẩn cấp Kill Switch**, đóng băng toàn bộ dispatches | JSON (`ControlResponse`) |
| `/api/events` | `GET` | Luồng sự kiện Server-Sent Events (SSE) toàn hệ thống | `text/event-stream` |
| `/api/runs/{id}/events` | `GET` | Luồng sự kiện Server-Sent Events (SSE) lọc theo `run_id` | `text/event-stream` |

### 4.2 Giao thức SSE (Server-Sent Events Protocol)
- Kết nối thông qua chuẩn HTML5 `EventSource`.
- Mỗi thông điệp gồm `id: <int>`, `event: <event_type>`, `data: <json>`.
- Định kỳ 15 giây gửi gói `: ping\n\n` nhằm ngăn ngừa router/proxy ngắt kết nối idle.

---

## 5. HƯỚNG DẪN KỊCH BẢN BẢO VỆ DEMO CHO GIẢNG VIÊN (DEMO RUNBOOK)

Khi trình bày trước hội đồng hoặc giảng viên, sử dụng kịch bản sau để thể hiện trọn vẹn giá trị kỹ thuật và tính trung thực của hệ thống:

### Kịch bản 1: Presentation Demo (Khám phá & Lập kế hoạch Bounded)
1. **Mục đích**: Chứng minh vòng lặp AI Agent tự khám phá ứng dụng web thật trong ShopLab, trích xuất form/link, đưa vào StateManager và lập kế hoạch mà không cần danh sách route cho trước.
2. **Thao tác**:
   - Trên Control Center, bấm **Start Range** (hoặc kiểm tra status Gateway `HEALTHY`).
   - Bấm **Start Run** với chế độ `presentation`.
3. **Điểm cần trình bày**:
   - *“Hệ thống không nạp sẵn từ điển URL (wordlist). Toàn bộ danh sách trang, liên kết và tham số form đều được AI Agent quan sát trực tiếp từ HTML nhận về từ Gateway 127.0.0.1:18088.”*
   - *“Dữ liệu quan sát được chuẩn hóa qua `ObservationNormalizer`, cập nhật vào `StateManager` đúng 1 lần duy nhất để chống ghi đè dữ liệu.”*
   - *“AI Planner đưa ra đề xuất hành động theo chế độ RULE baseline có ghi rõ xuất xứ (`provenance`).”*

### Kịch bản 2: Safety Deny Demo (Minh chứng An toàn Tuyệt đối)
1. **Mục đích**: Chứng minh Safety Gate là chốt chặn quyền lực tối cao — khi AI đề xuất mục tiêu ngoài phạm vi cho phép, hành động bị từ chối và **hoàn toàn không có gói tin mạng nào được gửi ra ngoài**.
2. **Thao tác**:
   - Chọn chế độ `deny-demo` và bấm **Start Run**.
3. **Điểm cần trình bày**:
   - *“Ở đây, chúng tôi cố tình tạo một đề xuất nhắm vào target `lab-not-approved` nằm ngoài allowlist.”*
   - *“Trên màn hình, thẻ Safety Gate lập tức chuyển sang trạng thái `DENIED` với lý do `TARGET_NOT_ALLOWLISTED`.”*
   - *“Quan sát thẻ Controlled Executor: Trạng thái hiển thị rõ `NOT CALLED` và bộ đếm `network_dispatches = 0`. Điều này chứng minh AI không thể tự ý bắn request ra ngoài tầm kiểm soát.”*

### Kịch bản 3: Fallback Offline Demo (Khả năng chịu lỗi khi mất LLM)
1. **Mục đích**: Thể hiện tính bền vững của kiến trúc khi LLM API gặp sự cố hoặc mất mạng.
2. **Thao tác**:
   - Chọn chế độ mô phỏng mất kết nối nhà cung cấp LLM.
3. **Điểm cần trình bày**:
   - *“Khi nhà cung cấp LLM bị ngắt kết nối (hoặc không có API key), hệ thống tự động fallback an toàn về bộ quy tắc định sẵn (`RULE planner`).”*
   - *“Hệ thống ghi nhận minh bạch: `Requested Mode: LLM`, `Actual Mode: RULE`, `Fallback Reason: PROVIDER_UNAVAILABLE` — không hề giả mạo kết quả của LLM.”*

### Kịch bản 4: Emergency Stop (Nút Dừng Khẩn Cấp)
1. **Mục đích**: Thể hiện khả năng ngắt can thiệp tức thì của người vận hành (`Operator Control`).
2. **Thao tác**:
   - Trong lúc Agent đang chạy, bấm nút đỏ **EMERGENCY STOP**.
3. **Điểm cần trình bày**:
   - *“Nút dừng khẩn cấp kích hoạt biến `KillSwitch.activate()`. Luồng thực thi bị khóa ngay lập tức, chuyển pipeline sang `BLOCKED`.”*
   - *“Tất cả bằng chứng thu thập trước thời điểm dừng khẩn cấp được bảo toàn nguyên vẹn (`preserve_evidence = True`), không bị mất mát hay hỏng hóc.”*

---

## 6. HƯỚNG DẪN KIỂM THỬ VÀ XÁC MINH TOÀN DIỆN

Trước khi đem hệ thống đi demo, chạy lần lượt các lệnh kiểm thử sau từ PowerShell tại thư mục gốc `E:\PBL6_FINAL`:

```powershell
# 1. Kiểm tra Backend REST API (8 tests PASS)
python -B -m unittest tests/backend/test_control_api.py -v

# 2. Kiểm tra Runtime Event Hook & SSE Stream (7 tests PASS)
python -B -m unittest tests/backend/test_runtime_events.py -v

# 3. Kiểm tra kịch bản Demo Giảng viên (21 tests PASS)
python -B -m unittest scripts/demo/test_professor_demo.py -v

# 4. Kiểm tra Hợp đồng An toàn Safety Contracts (17 tests PASS)
python -B -m unittest tests/safety/test_safety.py -v

# 5. Khởi động Backend Control Plane phục vụ Dashboard
python -B -m uvicorn dashboards.app.backend.control_api:app --host 127.0.0.1 --port 8000
```

---

## 7. BẢNG TỔNG KẾT MÃ NGUỒN CÁC PHẦN ĐÃ THỰC HIỆN

| Tệp Tin (File) | Tầng Kiến Trúc | Trách Nhiệm Kỹ Thuật |
|---|---|---|
| `runtime/autonomous_runner.py` | Runtime Core | Thêm `event_hook`, helper `_emit_event()` cách ly lỗi telemetry, phát sinh 20+ sự kiện chuẩn. |
| `dashboards/app/backend/models.py` | Backend Model | Typed Pydantic models: `RangeStatus`, `AgentStatus`, `RunStatus`, `PipelineStatus`, `AgentEvent`. |
| `dashboards/app/backend/event_sink.py` | Backend Bus | Event Bus thread-safe, hàng đợi bất đồng bộ multi-subscriber SSE, ring buffer lịch sử. |
| `dashboards/app/backend/range_controller.py`| Backend Controller| Quản lý Docker Compose cô lập, theo dõi container sở hữu, bảo toàn named volume. |
| `dashboards/app/backend/run_manager.py` | Backend Orchestrator| Quản lý luồng worker, snapshot trạng thái, nút dừng khẩn cấp Kill Switch, cầu nối event_hook. |
| `dashboards/app/backend/control_api.py` | Backend API | Router FastAPI REST & SSE (`/api/status`, `/api/runs`, `/api/events`, v.v.), CORS. |
| `tests/backend/test_control_api.py` | Test Suite | 8 Unit tests cho REST endpoints, preflight, status aggregation. |
| `tests/backend/test_runtime_events.py` | Test Suite | 7 Unit tests cho event hook, SSE streaming, deny-demo 0-dispatch invariant, emergency stop. |
| `dashboards/app/backend/README.md` | Tài liệu | Đặc tả kỹ thuật backend chi tiết, schema sự kiện, hướng dẫn API. |
| `dashboards/app/README.md` | Tài liệu | Tổng quan trung tâm điều khiển, sơ đồ dữ liệu, hướng dẫn khởi chạy. |
| `dashboards/app/CONTROL_CENTER_MANUAL.md` | Tài liệu Báo Cáo | Cẩm nang kiến trúc, vận hành và bảo vệ đồ án trước giảng viên. |
