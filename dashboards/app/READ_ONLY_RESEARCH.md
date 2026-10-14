# Giao diện tiếng Việt và trang tiến độ

Giao diện có bốn mục: Tổng quan, Lịch sử phiên, So sánh và Tiến độ đề tài.
Tiếng Việt là mặc định; nút đổi ngôn ngữ giữ tùy chọn tiếng Anh.
Mã phiên, mã hành động, tên mô hình và JSON nguồn được giữ để đối chiếu.

## Kết nối dữ liệu

Trang Tiến độ đề tài đọc `GET /api/research/overview` từ dịch vụ xem dữ liệu
riêng tại `127.0.0.1:8001`. Dịch vụ chỉ đọc các đường dẫn cố định trong dự án:

- Bảng 35 nhiệm vụ chính trong `TASKS.md`, kèm thời điểm đọc và SHA-256.
- Danh sách mô-đun liên quan đã định sẵn; có tệp không chứng minh thực thi.
- Các gói trong `runtime/evaluation-runs`, kèm kiểm tra toàn vẹn và chỉ số
  tổng hợp của dữ liệu mô phỏng. Mã băm manifest được tính từ lần đọc hiện tại,
  không phải chữ ký xác thực bên tạo gói. Đây không phải xác nhận kết quả khoa học.

Luồng này không tạo phiên, không gọi bộ lập kế hoạch/công cụ quét, không thay đổi
bằng chứng và không nâng trạng thái nhiệm vụ. TASK-026 và TASK-032 giữ `DEFERRED`.
Các chức năng lịch sử, xem bằng chứng và so sánh dùng API hiện có tại cổng 8000.
Việc theo dõi đủ 35 nhiệm vụ không có nghĩa đã nối thực thi toàn bộ nhiệm vụ.

## Mở dịch vụ xem dữ liệu

Từ thư mục gốc dự án, có thể chạy riêng dịch vụ chỉ đọc:

```powershell
python -B -m uvicorn dashboards.app.backend.research_overview:app --host 127.0.0.1 --port 8001
```

Sau đó mở `http://127.0.0.1:5173/#research` trên giao diện đang chạy.
Không cần khởi động lại máy chủ điều khiển để dùng dịch vụ này.
Biến `VITE_RESEARCH_API_URL` cho phép đổi địa chỉ dịch vụ xem dữ liệu khi khởi động
frontend; CORS của dịch vụ hiện chỉ cho phép frontend localhost/127.0.0.1 cổng 5173.
API chính cũng có route đọc này sau lần khởi động lại bình thường; có thể đặt biến
trên thành địa chỉ API chính khi muốn dùng cùng máy chủ.

Nếu dịch vụ không phản hồi, trang hiển thị lỗi và giữ nhãn dữ liệu cũ khi có.
Không biến lỗi đọc dữ liệu thành số đếm 0 hoặc xác nhận nhiệm vụ hoàn tất.

## Kiểm tra tập trung

```powershell
python -B -m unittest tests.backend.test_research_overview -v
```

Trong `dashboards/app/frontend`: `npm test` và `npm run build`.
Các kiểm tra này không chạy môi trường mục tiêu hoặc kiểm chứng vòng thực thi.
