# Project Context

## Purpose

Sản phẩm chính là **nền tảng nghiên cứu AI Red Team dưới quan sát một phần**, ưu tiên mô phỏng và so sánh thuật toán theo lựa chọn của người dùng ngày 2026-10-17. Người nghiên cứu chọn scenario, planner, seed và ngân sách; hệ thống tạo episode, bằng chứng và kết quả có thể tái lập.

Câu hỏi nghiên cứu: planner nào đạt mục tiêu tốt hơn khi cùng quan sát được phép, danh mục hành động, chính sách và ngân sách? Kết quả cần đo được hiệu quả, chi phí và độ chính xác của belief state, không suy ra từ số file, giao diện hoặc số test.

Web Pentest MVP, ShopLab, Django Oscar và các demo là baseline/tài liệu lịch sử để tái dùng có chọn lọc. Mở rộng nghiệp vụ ecommerce, dashboard hoặc live range không nằm trên đường ưu tiên trước simulator và benchmark.

## Architecture

Luồng nghiên cứu: seed được duyệt; observation đã chuẩn hóa; belief state; planner proposal; Safety Gate; bounded simulator/executor; observation mới; evidence; cập nhật belief và đánh giá.

- **Planner** chỉ đọc observations đã redact và belief state từ observations. Hypothesis không trở thành fact hoặc tự mở thêm mục tiêu.
- **Simulator** sở hữu true state; **Evaluator** được dùng ground truth để chấm kết quả. Ground truth thuộc `evaluation/**`, không thuộc planner input.
- **Safety Gate** giữ canonical allowlist và thẩm quyền authorization. Planner chỉ thấy các thực thể và quan hệ đã quan sát, không nhận full target allowlist, global/hidden topology, target source, hidden credentials hoặc defender-private state.
- **Executor** chỉ thực hiện bounded action đã được duyệt. Kiểm tra eligibility không thay authorization. Mọi request/redirect/auxiliary request hoặc bước mô phỏng phải qua gate trước side effect.
- **Evidence** ghi intent/result có provenance trước khi tiếp tục; lỗi ghi phải dừng. Expected và observed tách biệt. HTTP 200, reflection hoặc banner không tự xác nhận vulnerability/access.

Simulator và live range hướng tới cùng executor/result/observation contract. Simulator được kiểm chứng trước live range; các điểm này là yêu cầu thiết kế, không phải claim mọi tuyến code hiện đã tuân thủ. Quyết định nền tại [ADR-014](docs/adr/ADR-014-enterprise-red-team-belief-state.md).

## Planner model

| Mode | Vai trò |
|---|---|
| `RULE` | Baseline xác định, dùng cùng observations/actions/budgets với các đối chứng. |
| `LLM` | Đề xuất schema-bound; ghi rõ provider, requested/executed mode và fallback. |
| `RL` | Policy trên môi trường mô phỏng đã kiểm chứng; replay metadata cũ chưa chứng minh enterprise planning. |
| `HYBRID` | Phối hợp planner sau khi các baseline có thể so sánh; không bypass gate. |

Random baseline là đối chứng nghiên cứu cần định danh rõ trong experiment, không âm thầm thêm/đổi canonical planner mode. Planner output luôn là proposal data. Lỗi provider, malformed output và fallback phải hiện trong kết quả; rule fallback không được gọi là LLM success.

## Current state

[TASKS.md](TASKS.md) là nguồn duy nhất cho bảng trạng thái/dependencies và receipts. Không chép lại số test, source hashes hoặc gate results vào context/plan.

- Các phần RT đang triển khai trong working tree chưa đồng nghĩa đã commit, review hoặc `VALIDATED`; simulator hoàn chỉnh và benchmark enterprise vẫn cần observed evidence.
- [Pipeline đánh giá hiện có](runtime/evaluation/evaluate_all.py) chạy hai metadata selectors `synthetic-review`/`synthetic-random`. Kết quả đó không phải so sánh enterprise `RULE`/`LLM`/`RL`/`HYBRID`.
- Validation foundation/Web/ShopLab chỉ có giá trị cho source và phạm vi receipt gốc. Không chuyển sang kiến trúc RT hoặc extension mới.
- Claim gate SL-12 và claim validation toàn hệ thống còn mâu thuẫn giữa các tài liệu; xem [blockers](TASKS.md#blockers). Chưa có kết luận review mới trong đợt chuẩn hóa này.
- `TASK-026` và `TASK-032` giữ `DEFERRED`.

Mốc tiếp theo và acceptance tại [PROJECT_PLAN.md](PROJECT_PLAN.md). Các receipts đã ghi được bảo toàn trong [ledger](TASKS.md#checks-and-observed-implementation-state), kể cả khi chứa đường dẫn/trạng thái của source cũ.

## Boundaries

Chỉ simulation hoặc local isolated lab với dữ liệu giả. Lab mode, target/action allowlists, approval, order/rate/budget checks, refusal, kill switch, audit và restore vẫn bắt buộc. Safety scope là giao của canonical allowlist và run-approved scope; planner-visible scope chỉ từ observations.

Không public targets, Internet scanning, production data, credentials cố định, arbitrary shell, dynamic actions, free-form payload mới, persistence/credential theft/host file read hoặc lateral movement thật ngoài bounded scope đã duyệt. Không tự đổi action IDs/contract semantics để qua validator.

Evidence cần UTC, run ID, source, hash, redaction, expected state và observed state; không overwrite, xóa hoặc tái sử dụng run để sửa kết quả. Khi có evidence-loss risk hoặc nguồn xung đột, dừng thao tác liên quan và ghi blocker.

## Source hierarchy

User source và approved contracts outrank derivative documents; evidence outranks prose cho observed claims. [AGENTS.md](AGENTS.md) quy định governance; context định nghĩa sản phẩm/ranh giới; plan quy định mốc/acceptance; TASKS quản lý trạng thái/receipts; ADR ghi quyết định kiến trúc. Tài liệu cũ giữ giá trị trong phạm vi lịch sử, không tự trở thành roadmap hiện hành.

Đợt chuẩn hóa tài liệu chỉ có allowlist `PROJECT_CONTEXT.md`, `PROJECT_PLAN.md`, `TASKS.md`. Các đợt sửa cấu trúc/code theo yêu cầu tiếp theo dùng allowlist riêng tại [plan](PROJECT_PLAN.md); không suy ra quyền sửa contracts, configs, catalog, scenarios, dependencies hay evidence. Sửa tài liệu không cấp per-run/per-action approval. Không self-approve, finalize, append history hoặc commit.
