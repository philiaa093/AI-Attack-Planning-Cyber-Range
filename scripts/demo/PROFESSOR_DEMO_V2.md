# KỊCH BẢN THUYẾT TRÌNH BẢO VỆ ĐỒ ÁN (PROFESSOR DEMO RUNBOOK V2)
## HỆ THỐNG KIỂM THỬ XÂM NHẬP TỰ HÀNH CÓ GIỚI HẠN & CỔNG AN TOÀN TRUNG TÂM

> **Phiên bản:** Phase 8 Defense Ready (One-Command Launch + Presentation Mode + Rehearsal + 13 Defense Q&A)  
> **Ngôn ngữ:** Tiếng Việt (chính thức)  
> **Địa chỉ Web UI:** `http://127.0.0.1:5173/#overview`  
> **Địa chỉ API Backend:** `http://127.0.0.1:8000/api/demo/readiness`  

---

## 1. QUY TRÌNH KHỞI CHẠY HỆ THỐNG (1 LỆNH DUY NHẤT)

Mở PowerShell tại thư mục gốc dự án (`E:\PBL6_FINAL`):

```powershell
.\scripts\demo\start_control_center.ps1
```

### Các bước tự động thực hiện:
1. **Kiểm tra môi trường:** Python (>= 3.10), Node (>= 18), Docker Engine.
2. **Kiểm tra cổng & Tính lũy đẳng (Idempotent):**
   - Nếu Backend (8000) hoặc Frontend (5173) đã chạy đúng phiên bản dự án, script tái sử dụng an toàn, không sinh tiến trình trùng lặp.
   - Nếu cổng bị chiếm bởi phần mềm lạ, launcher dừng và thông báo rõ ràng kèm PID.
3. **Ghi nhận quyền sở hữu PID:** Tạo `.demo-session.json` lưu giữ chính xác Backend PID và Frontend PID để dọn dẹp an toàn.
4. **Kiểm tra Readiness:** Gọi `GET /api/demo/readiness` xác nhận Cổng An toàn, Kho chứng cứ và Docker sẵn sàng.
5. **Mở trình duyệt:** Tự động mở `http://127.0.0.1:5173/#overview` ở Chế độ Thuyết trình (Presentation View).

---

## 2. BẢN DEMO NHANH 5 PHÚT (FAST DEMO — 5 MINUTES)

*Dành cho trường hợp Hội đồng yêu cầu trình bày cô đọng hoặc thời gian phản biện bị rút ngắn.*

| Mốc thời gian | Phân đoạn | Thao tác trên Giao diện | Nội dung Trình bày Trọng tâm |
|---|---|---|---|
| **00:00 – 01:00** | **Kiến trúc An toàn** | Chỉ vào Sơ đồ Quy trình trên Slide / Banner Header | Đặt vấn đề: LLM agent tự do tiềm ẩn nguy cơ phá hoại ngoài phạm vi. Nhóm đề xuất **Kiến trúc Tự hành có Giới hạn** với **Cổng An toàn Trung tâm**. Mọi đề xuất chỉ là Proposal Data, không cho LLM trực tiếp gõ shell hay gọi mạng. |
| **01:00 – 02:15** | **Demo 1: Tự hành Khép kín** | Bấm Preset 1: `Kịch bản 1: Thăm dò An toàn (Tự hành)` | Chu trình khép kín: Quan sát → Lập kế hoạch (`RULE`) → Cổng An toàn duyệt (`PERMITTED`) → Phát lệnh HTTP tới Cyber Range (`lab-ecommerce`) → Lưu trữ chứng cứ. |
| **02:15 – 03:00** | **Chứng cứ Mật mã** | Chỉ vào Thẻ `Kho Chứng cứ` & `Hero Bước Hiện tại` | Dữ liệu phản hồi được băm SHA-256 ngay tại biên giới runtime, lưu trữ bất biến (Append-only). Bộ xác thực độc lập bảo đảm tính toàn vẹn 100%. |
| **03:00 – 04:00** | **Demo 2: Cổng Từ chối Vi phạm** | Bấm Preset 2: `Kịch bản 2: Cổng An toàn Từ chối Vi phạm` | **Trọng tâm bảo vệ:** Mô phỏng prompt injection hoặc target ngoài phạm vi. Hero Cổng An toàn chuyển đỏ: `SAFETY GATE REFUSAL: DENIED`. **Cam kết tuyệt đối 0 lượt phát mạng (Dispatches: 0)**. |
| **04:00 – 05:00** | **Lịch sử & Tua lại (Replay)** | Chuyển Tab `Lịch sử chạy`, chọn run gần nhất, bấm `Phát` | Tính năng Timeline Replay chạy **100% Read-Only**, không phát lại bất kỳ gói tin mạng nào. Tái hiện từng bước với chữ ký mật mã phục vụ kiểm toán khoa học. |

---

## 3. BẢN DEMO CHI TIẾT 8–10 PHÚT (FULL DEMO — 8-10 MINUTES)

### Phút 00:00 – 01:15: Đặt vấn đề & Khởi chạy 1 Lệnh
> *"Kính thưa Thầy/Cô Hội đồng,*  
> *Các mô hình Large Language Model (LLM) hiện nay khi áp dụng vào An ninh mạng thường gặp hai thách thức nghiêm trọng:*  
> *1. Nguy cơ bị tấn công Prompt Injection và hiện tượng Ảo giác (Hallucination) dẫn đến hành vi ngoài tầm kiểm soát.*  
> *2. Rủi ro tự ý phát lệnh phá hoại ra ngoài Internet hoặc hạ tầng sản xuất khi được trao quyền gõ lệnh shell tự do.*  
> 
> *Đồ án của chúng em giải quyết triệt để bài toán này bằng **Kiến trúc Kiểm thử Xâm nhập Tự hành có Giới hạn (Bounded Autonomous Penetration Testing)** với **Cổng An toàn Trung tâm (Centralized Safety Gate)** độc lập. Em xin khởi chạy toàn bộ hệ thống bằng một script duy nhất: `.\scripts\demo\start_control_center.ps1`."*

---

### Phút 01:15 – 02:30: Độ Sẵn sàng (Readiness) & Minh bạch Nguồn gốc LLM
*(Chỉ vào Banner trạng thái và bảng Kiểm tra Sẵn sàng)*

> *"Tại giao diện Thuyết trình, hệ thống hiển thị bảng kiểm tra độ sẵn sàng gồm 7 hạng mục cốt lõi: Backend API, Chính sách Cổng an toàn, Kho chứng cứ, Docker Engine, Cyber Range Gateway, Luồng SSE và Trạng thái LLM.*  
> 
> *Đặc biệt, hệ thống tuyên bố nguồn gốc học thuật hoàn toàn trung thực:*  
> **`LLM PROVIDER E2E NOT RUN — CREDENTIAL NOT CONFIGURED (RULE BASELINE ACTIVE)`**  
> 
> *Nhóm em báo cáo rõ ràng: Toàn bộ kiến trúc tích hợp LLM Planner, bộ điều hợp trạng thái (PlannerStateAdapter), schema validation và chính sách Fallback đã được lập trình hoàn chỉnh và vượt qua 100% unit tests. Để đảm bảo tính an toàn và khả năng tái lập độc lập không phụ thuộc Internet bên ngoài, hệ thống không lưu khóa API của bên thứ ba trong mã nguồn mà kích hoạt Fallback sang **Bộ lập kế hoạch RULE Baseline** đã được kiểm chứng toàn diện."*

---

### Phút 02:30 – 04:30: Kịch bản 1 — Thu thập Tự hành Khép kín
*(Thao tác: Bấm nút `Kịch bản 1: Thăm dò An toàn (Tự hành)`)*

> *"Em xin kích hoạt Lượt chạy Tự hành đầu tiên.*  
> *Xin Thầy/Cô quan sát **Hero Bước Thực thi Hiện tại (Current Step Hero)**:*  
> *- **Hành động đề xuất:** `ACTION-RECON-001` (Discover Target Surface).*  
> *- **Mục tiêu:** `lab-ecommerce` bên trong Cyber Range cô lập (Cổng 18088).*  
> *- **Cổng An toàn thẩm định:** Quyết định `PERMITTED` vì hành động nằm trong danh mục cho phép và mục tiêu nằm trong ranh giới Lab.*  
> *- **Dữ liệu đo từ xa:** Luồng sự kiện bên phải hiển thị các mốc chính: Lập đề xuất → Cổng duyệt → Phát lệnh HTTP → Băm SHA-256 ghi vào Kho chứng cứ.*  
> *Toàn bộ quy trình diễn ra tự động, khép kín và ghi vết đầy đủ vào sổ cái chứng cứ."*

---

### Phút 04:30 – 06:00: Kịch bản 2 — Cổng An toàn Từ chối Vi phạm (Trọng tâm Đồ án)
*(Thao tác: Bấm nút `Kịch bản 2: Cổng An toàn Từ chối Vi phạm`)*

> *"Đây là minh chứng quan trọng nhất cho tính an toàn của hệ thống:*  
> *Trong kịch bản này, Agent nhận dữ liệu đầu vào chứa chuỗi giả lập Prompt Injection hoặc đề xuất tấn công mục tiêu nằm ngoài phạm vi ủy quyền.*  
> 
> *Xin Thầy/Cô nhìn vào **Hero Quyết định Cổng An toàn** chuyển sang màu đỏ rực:*  
> *- Trạng thái: **`SAFETY GATE REFUSAL: DENIED`**.*  
> *- Dòng thông báo then chốt: **`ĐẢM BẢO 0 LƯỢT PHÁT MẠNG RA NGOÀI (Dispatches: 0)`**.*  
> 
> *Điều này chứng minh: Dù Planner bị đầu độc hay bị lỗi sinh mã, Cổng An toàn hoạt động như một Firewall chính sách cứng, chặn đứng yêu cầu tại ranh giới dữ liệu và tuyệt đối không phát bất kỳ gói tin mạng nào ra ngoài."*

---

### Phút 06:00 – 07:15: Kịch bản 3 — Chế độ Trợ lý Có Phê duyệt (Assisted Mode)
*(Thao tác: Bấm nút `Kịch bản 3: Chế độ Trợ lý Có Phê duyệt`)*

> *"Đối với các môi trường đòi hỏi sự kiểm soát của con người (Human-in-the-Loop), hệ thống cung cấp **Chế độ Trợ lý (Assisted Mode)**.*  
> *Khi Agent tạo đề xuất cho các hành động cần thẩm quyền cao, hệ thống tự động tạm dừng tại biên giới an toàn và hiển thị bảng **Yêu cầu Phê duyệt từ Người Vận hành**.*  
> *Chỉ khi người vận hành bấm `Phê duyệt & Thực thi`, Cổng An toàn mới tiến hành thẩm định và phát lệnh. Nếu bấm `Từ chối`, Agent ghi nhận phản hồi từ chối và tự động điều chỉnh kế hoạch tiếp theo mà không gây gián đoạn hệ thống."*

---

### Phút 07:15 – 08:30: Lịch sử, Tua lại Dòng thời gian & So sánh Thực nghiệm
*(Thao tác: Bấm Tab `Lịch sử chạy` và Tab `So sánh`)*

> *"Tại Tab **Lịch sử chạy**, mọi lượt chạy đều được lập chỉ mục kèm nguồn gốc (Provenance), ngân sách, và băm chứng cứ.*  
> *Bấm vào một run, chúng ta có màn hình **Timeline Replay**: có thể tua lại (Play) từng bước một cách trực quan. Quá trình Replay hoàn toàn là **Read-Only**, không phát lại bất kỳ gói tin mạng nào.*  
> 
> *Tại Tab **So sánh**, chúng em có thể đặt hai lượt chạy cạnh nhau để đối sánh:*  
> *- So sánh số lượng quyết định giữa chiến lược RULE và LLM.*  
> *- So sánh quỹ đạo hành động (Action Trajectory) và độ phân kỳ.*  
> *- So sánh các lỗ hổng phát hiện được (Findings Overlap).*  
> *Mọi dữ liệu so sánh đều có thể xuất ra JSON phục vụ báo cáo khoa học."*

---

### Phút 08:30 – 09:30: Dừng Khẩn cấp, Cơ chế Hồi phục & Dọn dẹp
*(Thao tác: Chỉ vào nút đỏ `DỪNG KHẨN CẤP` và trình bày kết luận)*

> *"Hệ thống tích hợp nút **`DỪNG KHẨN CẤP`** kích hoạt Kill Switch độc lập ở mức ưu tiên cao nhất, vô hiệu hóa toàn bộ lệnh mạng ngay lập tức kể cả khi hệ thống đang trong trạng thái tạm dừng.*  
> *Tóm lại, đồ án đã chứng minh khả năng hiện thực hóa một hệ thống AI Pentest tự hành có kiểm soát, minh bạch và an toàn tuyệt đối."*

---

## 4. KẾ HOẠCH DỰ PHÒNG KHI DOCKER GẶP SỰ CỐ (DOCKER-OFFLINE REPLAY PLAN)

> [!IMPORTANT]
> Nếu trong buổi bảo vệ thực tế, Docker Desktop của máy chiếu/laptop bị đơ, sập, hoặc cổng 18088 bị lỗi:

1. **Tuyệt đối không bối rối hay tìm cách restart Docker:**
   - Hệ thống đã được thiết kế sẵn chế độ **Degraded / Historical Replay Mode**.
2. **Hành động ngay lập tức:**
   - Bấm trực tiếp vào Tab **`Lịch sử chạy`** trên thanh điều hướng đầu trang.
   - Chọn lượt chạy đã hoàn tất gần nhất (ví dụ: `RUN-AUTONOMOUS-PENTEST-1791712598` hoặc `RUN-DASH-A1`).
   - Mở màn hình **Timeline Replay**:
     - Bấm nút **Phát (Play)** để chiếu lại từng bước của quá trình tấn công đã được ghi vết thực tế.
     - Trình bày cho Hội đồng: *"Kính thưa Thầy/Cô, hệ thống ghi nhận toàn bộ chuỗi hành vi vào Sổ cái Chứng cứ Mật mã bất biến. Chúng em có thể tua lại (Replay) chính xác từng mili-giây, từng gói tin HTTP và chứng minh chữ ký SHA-256 của từng quyết định mà không cần phụ thuộc vào Docker runtime."*
3. **Mở Tab So sánh (Compare):**
   - Chọn hai run để phân tích bảng số liệu thực nghiệm.
   - Buổi demo vẫn diễn ra trơn tru 100% với đầy đủ bằng chứng khoa học.

---

## 5. TOÀN BỘ 13 CÂU HỎI PHẢN BIỆN CỦA HỘI ĐỒNG (DEFENSE Q&A)

### Câu hỏi 1: Tại sao lại dùng AI trong kiểm thử xâm nhập? (Why AI?)
> **Trả lời:**  
> *"Thưa Thầy/Cô, các công cụ quét tự động truyền thống (như ZAP, Nikto) hoạt động theo dạng vét cạn (brute-force) độc lập từng endpoint và thiếu khả năng hiểu ngữ cảnh chuỗi tấn công (Multi-step Attack Chain). Ngược lại, AI Planning cho phép Agent tổng hợp thông tin quan sát qua từng bước, lập luận về bề mặt tấn công và tự động thích ứng khi gặp các phản hồi phức tạp từ ứng dụng web, mô phỏng chân thực tư duy của một chuyên gia kiểm thử xâm nhập."*

---

### Câu hỏi 2: Tại sao không dùng các script cố định (Hardcoded Scripts)? (Why not just scripts?)
> **Trả lời:**  
> *"Thưa Thầy/Cô, script cố định mang tính tĩnh, cứng nhắc và nhanh chóng bị lỗi thời khi cấu trúc đường dẫn hoặc tham số của ứng dụng web thay đổi. AI Planner phân tách rõ ràng giữa **Tri thức quan sát (Perception)** và **Chiến lược hành động (Planning)**. Khi mục tiêu thay đổi tham số hoặc luồng điều hướng, Planner có thể tự động suy luận lại quỹ đạo (Replan) mà không cần lập trình viên phải sửa đổi mã nguồn."*

---

### Câu hỏi 3: Hành vi tự hành của Agent được giới hạn như thế nào? (How is execution bounded?)
> **Trả lời:**  
> *"Hệ thống áp dụng nguyên tắc **Bounded Autonomy** qua 5 tầng giới hạn cứng:**  
> *1. **Giới hạn Mục tiêu (Target Allowlist):** Chỉ cho phép tấn công `lab-ecommerce` bên trong Cyber Range cục bộ.*  
> *2. **Giới hạn Danh mục Hành động (Action Catalog):** Agent chỉ được chọn từ tập hành động có kiểu định sẵn (`ACTION-RECON-001`, `ACTION-WEB-001`...), tuyệt đối không có hành động tùy ý.*  
> *3. **Ngân sách Tài nguyên (Budget Tracker):** Khống chế số lượng request (tối đa 2000), số hành động (tối đa 100) và độ sâu duyệt.*  
> *4. **Tốc độ Phát lệnh (Rate Limiter):** Tối đa 5 requests/giây để chống gây nghẽn hoặc DoS.*  
> *5. **Kill Switch:** Cơ chế dừng khẩn cấp lập tức ngắt mọi quyền phát lệnh."*

---

### Câu hỏi 4: Hệ thống có thể tự ý tấn công ra ngoài Internet không? (Can it attack the Internet?)
> **Trả lời:**  
> *"Tuyệt đối không thể, thưa Thầy/Cô. Có 3 lớp bảo vệ ngăn chặn việc này:**  
> *1. Cấu hình chính sách cứng `PUBLIC_TARGETS=false` và `EXTERNAL_NETWORK=false`.*  
> *2. Bộ kiểm tra mục tiêu `CentralizedSafetyGate` từ chối mọi URL/IP không khớp chính xác với allowlist nội bộ lab.*  
> *3. Mạng Docker Compose được cấu hình cô lập nội bộ (bridge network cô lập), không cấp quyền định tuyến ra gateway ngoài."*

---

### Câu hỏi 5: LLM có thể qua mặt Cổng An toàn (Safety Gate) không? (Can LLM bypass safety?)
> **Trả lời:**  
> *"Thưa Thầy/Cô, LLM hoàn toàn không thể qua mặt Cổng An toàn. Trong kiến trúc của đồ án, LLM không có quyền truy cập vào socket mạng hay hệ vỏ (shell). Đầu ra của LLM chỉ là một văn bản JSON đề xuất (`Typed Proposal`). Cổng An toàn là một module Python độc lập, chạy trên một tiến trình riêng biệt và kiểm tra proposal dựa trên chính sách định sẵn. Nếu Cổng An toàn không cấp phép (`PERMITTED`), Executor sẽ không bao giờ được gọi."*

---

### Câu hỏi 6: Điều gì xảy ra nếu LLM bị ảo giác (Hallucination) hoặc bị Prompt Injection? (What happens if LLM hallucinates?)
> **Trả lời:**  
> *"Hệ thống xử lý qua 2 tầng lọc an toàn:**  
> *1. **Schema Validation:** Nếu LLM trả về JSON sai cú pháp, thiếu trường, hoặc sinh ra Action ID không tồn tại trong danh mục, hệ thống lập tức loại bỏ đề xuất (`PLANNER_OUTPUT_INVALID`) và kích hoạt chuyển đổi dự phòng sang RULE.*  
> *2. **Safety Gate:** Nếu LLM sinh ra một hành động tấn công ra ngoài phạm vi hoặc bị Prompt Injection ép quét IP công cộng, Cổng An toàn lập tức từ chối (`SAFETY GATE REFUSAL`) và đảm bảo 0 lượt phát mạng được thực hiện."*

---

### Câu hỏi 7: Chứng cứ trong hệ thống là gì? (What is evidence?)
> **Trả lời:**  
> *"Chứng cứ (Evidence) là một bản ghi cấu trúc bất biến gồm: mã định danh lượt chạy (`run_id`), mốc thời gian UTC, hành động được duyệt, mục tiêu, yêu cầu HTTP gửi đi, phản hồi HTTP nhận về (đã làm sạch dữ liệu nhạy cảm), và hàm băm mật mã SHA-256 của toàn bộ nội dung. Chứng cứ là cơ sở khoa học để đánh giá xem lỗ hổng có thực sự tồn tại hay không."*

---

### Câu hỏi 8: Làm sao chứng minh chứng cứ không bị chỉnh sửa sau khi ghi? (How do you know evidence was not modified?)
> **Trả lời:**  
> *"Hệ thống áp dụng **Sổ cái Chứng cứ Mật mã (Cryptographic Evidence Ledger)**:**  
> *Mỗi khi một bằng chứng được tạo ra, hệ thống tính toán giá trị băm `SHA-256` của payload và ghi vào file `ledger.json` theo nguyên tắc chỉ thêm (Append-only).*  
> *Module `DurableEvidenceVerifier` thực hiện kiểm toán độc lập: đọc lại từng file bằng chứng trên đĩa, tính lại hàm băm SHA-256 và so khớp với sổ cái. Nếu có bất kỳ byte nào bị thay đổi, trạng thái toàn vẹn sẽ lập tức chuyển thành `CORRUPTED`."*

---

### Câu hỏi 9: Tại sao lại kết hợp cả RULE Planner và LLM Planner? (Why RULE and LLM?)
> **Trả lời:**  
> *"Sự kết hợp này đem lại 2 lợi ích cốt lõi:**  
> *1. **RULE Baseline** đóng vai trò là chuẩn đối sánh khoa học tất định (Deterministic Baseline), có thể tái lập 100% trong mọi điều kiện và làm lưới an toàn dự phòng (Fallback) khi LLM mất kết nối hoặc hết hạn mức.*  
> *2. **LLM Planner** mang lại khả năng phân tích ngữ cảnh linh hoạt và phát hiện các đường dẫn bất thường.*  
> *Việc đặt cả hai dưới cùng một Action Catalog và một Safety Gate cho phép chúng em thực hiện so sánh đối đầu định lượng (Empirical Comparison) về hiệu quả giữa AI học máy và luật chuyên gia."*

---

### Câu hỏi 10: Tại sao cần tính năng Timeline Replay? (Why replay?)
> **Trả lời:**  
> *"Trong an ninh mạng và nghiên cứu khoa học, tính minh bạch và khả năng tái lập (Reproducibility) là tối quan trọng. Timeline Replay cho phép chuyên gia an ninh hoặc người chấm điểm xem lại toàn bộ diễn biến của cuộc tấn công ở tốc độ tùy chỉnh, kiểm tra chính xác từng quyết định tại từng mili-giây mà hoàn toàn không cần chạy lại các lệnh mạng gây ảnh hưởng đến hệ thống mục tiêu."*

---

### Câu hỏi 11: Tại sao không hiển thị chuỗi suy nghĩ nội tâm (Raw Chain-of-Thought) của LLM? (Why no raw chain-of-thought?)
> **Trả lời:**  
> *"Theo các quy chuẩn an toàn cho LLM Agent (như khuyến nghị của Anthropic và NIST):*  
> *1. Chuỗi suy nghĩ nội tâm (Scratchpad/CoT) có thể bị nhiễm độc bởi Prompt Injection từ trang web mục tiêu, chứa các nội dung rác hoặc không kiểm chứng được.*  
> *2. Hệ thống kiểm toán cần dựa trên **Hành vi cụ thể (Observable Behavior)** và **Quyết định có kiểu (Typed Decisions)** chứ không dựa trên lời giải thích văn xuôi không chắc chắn.*  
> *Do đó, hệ thống chỉ hiển thị `Decision Summary`, `Action ID`, và căn cứ quan sát."*

---

### Câu hỏi 12: Điều gì xảy ra nếu môi trường Docker bị sập trong buổi demo? (What happens if Docker fails?)
> **Trả lời:**  
> *"Hệ thống đã được thiết kế kiến trúc chịu lỗi (Fault-Tolerant):*  
> *- API Readiness sẽ hiển thị cảnh báo Docker không phản hồi nhưng không làm sập giao diện Control Center.*  
> *- Người thuyết trình có thể chuyển ngay sang **Chế độ Replay Lịch sử (Historical Replay Mode)** trên Tab Lịch sử chạy để chiếu lại các lượt chạy thực tế đã lưu trong Sổ cái Chứng cứ SHA-256.*  
> *- Buổi bảo vệ vẫn diễn ra thành công với đầy đủ số liệu thực nghiệm mà không bị gián đoạn."*

---

### Câu hỏi 13: Đã kiểm thử thực tế với LLM Provider bên ngoài chưa? (Has real LLM provider been tested?)
> **Trả lời:**  
> *"Dạ thưa Thầy/Cô, nhóm em xin báo cáo hoàn toàn trung thực:*  
> *Về mặt kiến trúc, toàn bộ code tích hợp LLM (`ObservedStatePlanner`), bộ điều hợp adapter, prompt schema, và cơ chế chuyển đổi dự phòng Fallback đã được lập trình hoàn chỉnh và vượt qua 100% bài kiểm thử đơn vị (`test_planner_contracts.py` và `test_phase5_control_modes.py`).*  
> *Tuy nhiên, để bảo vệ an toàn thông tin, đồ án không lưu trữ khóa API bí mật của bên thứ ba trong mã nguồn repository. Trong buổi demo này, hệ thống hoạt động ở chế độ Fallback sang **RULE Baseline** đã được chứng minh an toàn tuyệt đối và đạt tính độc lập cao nhất."*

---

## 6. QUY TRÌNH DỌN DẸP AN TOÀN SAU BUỔI BẢO VỆ

Chạy lệnh dọn dẹp bằng script chuyên biệt (chỉ tắt đúng tiến trình dự án, không tắt nhầm phần mềm khác):

```powershell
.\scripts\demo\stop_control_center.ps1
```

Script sẽ đọc `.demo-session.json`, kiểm tra chính xác tiến trình Backend và Frontend được tạo bởi lượt demo, chấm dứt an toàn và giải phóng cổng 8000 & 5173.
