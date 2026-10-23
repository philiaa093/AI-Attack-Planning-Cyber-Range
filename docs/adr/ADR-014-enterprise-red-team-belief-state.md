# Enterprise Red Team Belief State

## Status

`IMPLEMENTED` documentation decision, được khởi tạo trong tranche tái chuẩn hóa `RT-00 — Enterprise Red Team Planning Rebaseline`. Chưa có independent review; validation pending.

## Context

Dự án chuyển đổi trọng tâm nghiên cứu từ bounded Web Pentest MVP (ShopLab) sang bài toán cốt lõi: **AI Attack Planning for Red Team under Partial Observability (Belief-State Planning)**. Toàn bộ nền tảng, cơ chế an toàn, mô hình kiểm thử và bằng chứng lịch sử (TASK-001..035, SL-01..11) được bảo toàn nguyên trạng làm baseline kiểm chứng.

Trong môi trường mạng doanh nghiệp thực tế, tác tử Red Team không sở hữu tầm nhìn toàn tri (omniscient / oracle view):
- Sơ đồ mạng tổng thể (global network topology), danh sách máy chủ, dịch vụ nội bộ, cấu hình phòng thủ và tài khoản tiềm năng không được biết trước.
- Việc cung cấp cho planner toàn bộ bản đồ mục tiêu, full target allowlist hoặc ground truth sẽ làm suy giảm giá trị học thuật, biến bài toán hoạch định dưới quan sát một phần (POMDP / belief-state planning) thành bài toán tìm đường đơn thuần trên đồ thị đã biết (fully observable pathfinding).
- Đồng thời, yêu cầu an toàn, quản trị và bảo tồn bằng chứng của Cyber Range không được nới lỏng: tuyệt đối không cho phép arbitrary shell, dynamic actions, public targets, hoặc unapproved command execution.

## Decision

Xác lập kiến trúc quy hoạch tấn công Red Team theo trạng thái niềm tin (Belief-State Planning) và phân tách ranh giới an toàn:

1. **Phân quyền True State**: True State (trạng thái mạng thực tế, cấu hình dịch vụ, vị trí lỗ hổng thực, trạng thái ẩn của hệ thống phòng thủ) chỉ thuộc quyền sở hữu của Simulator và Evaluator. Planner tuyệt đối không được truy cập trực tiếp hoặc gián tiếp vào True State.
2. **Cơ chế kiến tạo Belief State**: Belief State của tác tử chỉ được xây dựng duy nhất từ chuỗi quan sát (observations) thực tế thu thập được qua các hành động hợp lệ đã chuẩn hóa. Belief State ước lượng phân bố niềm tin về các thực thể: máy chủ đã phát hiện, dịch vụ đang mở, thông tin xác thực đã thu thập, và quyền hạn hiện tại.
3. **Cách ly tuyệt đối Ground Truth**: Ground Truth chỉ thuộc về phân hệ Evaluation (chuẩn bị chuyển sang vị trí canonical dưới `evaluation/**` trong RT-01). Ground Truth chỉ được dùng để đánh giá độ chính xác của Belief State và kế hoạch sau khi kết thúc run đánh giá, không xuất hiện trong ngữ cảnh lập kế hoạch.
4. **Phân định Safety Scope và Planner-Visible Scope**: Ranh giới an toàn (Safety Scope) không đồng nhất với phạm vi hiển thị của planner (Planner-Visible Scope). Safety Gate nắm giữ canonical target allowlist và policy để thẩm định, nhưng Planner tuyệt đối không được nhận full target allowlist nhằm tránh rò rỉ tri thức oracle.
5. **Zero-Knowledge Target Boundary**: Planner bắt đầu từ seed hợp lệ được phê duyệt và mở rộng tầm nhìn qua discovery observations. Mọi mục tiêu ngoài vùng đã quan sát là ẩn đối với Planner, cho dù mục tiêu đó có nằm trong target allowlist của Safety Gate.
6. **Mô hình tam giác điều khiển (Planner – Safety Gate – Executor)**:
   - **Planner**: Chỉ sinh dữ liệu đề xuất (proposal data) tuân thủ nghiêm ngặt schema (`plan.schema.json`).
   - **Safety Gate**: Nắm giữ thẩm quyền tối cao, kiểm tra đề xuất với canonical allowlist, lab mode, rate limits, budgets và kill switch trước khi cấp quyền (authorization).
   - **Executor**: Thực thi bounded actions đã được duyệt và sinh observation cho normalizer/recorder.
7. **Thống nhất Contract giữa Simulator và Live Range**: Phân hệ mô phỏng (Simulation Backend) và phân hệ Cyber Range thực nghiệm (Mini Enterprise Live Range) bắt buộc dùng chung executor interface và result/observation contract. Simulator phải đi trước và được kiểm chứng độc lập trước khi kích hoạt live range.

## Alternatives Considered

- **Fully Observable Planning**: Cung cấp toàn bộ sơ đồ mạng và danh sách target cho planner. Bị bác bỏ vì vi phạm tiền đề nghiên cứu thực tế của Red Team và tạo ra rò rỉ oracle.
- **Planner sở hữu Full Target Allowlist**: Bị bác bỏ vì planner sẽ lợi dụng allowlist như một danh sách mục tiêu biết trước để đoán hướng đi thay vì khám phá dựa trên quan sát.
- **Mở rộng sang Arbitrary Shell / Live Exploitation**: Bị bác bỏ vì vi phạm nghiêm trọng chính sách an toàn, ranh giới lab cô lập và nguyên tắc bounded action catalog.
- **Xây dựng Live Range trước Simulator**: Bị bác bỏ vì simulator cần thiết để đào tạo, kiểm chứng thuật toán POMDP và so sánh công bằng trước khi triển khai mạng thật phức tạp và tốn kém tài nguyên.

## Consequences

- Khởi động lộ trình `RT-00` đến `RT-07`.
- `RT-01` sẽ di chuyển ground-truth schema sang `evaluation/**` và triển khai zero-knowledge assertions.
- `RT-02` thiết kế mô hình `BeliefState` và `BeliefStateManager` kế thừa `StateManager`.
- `RT-03` chuẩn hóa danh mục hành động doanh nghiệp có giới hạn (Enterprise Action Model).
- `RT-04` xây dựng Simulation Backend trước khi triển khai Live Range (`RT-06`).
- Tất cả các phương pháp planner (`RULE`, `LLM`, `RL`, `HYBRID`) đều được đánh giá dựa trên cùng không gian quan sát và ngân sách.

## Risks

- **Oracle Leakage**: Rủi ro rò rỉ thông tin ẩn từ hệ thống vào prompt của LLM hoặc vector state của RL. Giảm thiểu bằng boundary validation tests và redaction nghiêm ngặt.
- **Contract Drift**: Lệch chuẩn giữa kết quả simulator và kết quả live range. Giảm thiểu bằng bộ test suite hợp đồng chung (shared contract tests).

## Revisit Conditions

Chỉ xem xét lại khi có yêu cầu thay đổi nguồn từ người dùng, tài liệu đặc tả nhiệm vụ được phê duyệt, đánh giá an toàn mới và bằng chứng thực nghiệm kiểm chứng.
