# Smart Parking Backend

Backend FastAPI + PostgreSQL. Giờ nghiệp vụ: Việt Nam UTC+7; các trường TIMESTAMP nhận giờ không có hậu tố Z hoặc offset.

## Khởi động (PowerShell)

```powershell
cd E:\DoAnChuyenNghanh\backend
.\venv\Scripts\python.exe -m pip install -r requirements.txt
.\venv\Scripts\python.exe -m uvicorn main:app --reload --port 8001
```

Swagger: http://127.0.0.1:8001/docs. Đăng nhập POST /auth/login, sao chép access_token vào Authorize (Bearer).
Giữ .env hiện tại. Máy mới: sao chép .env.example thành .env, đặt thông tin PostgreSQL, JWT_SECRET_KEY và IOT_API_KEY ngẫu nhiên. Tạo database và chạy database/schema.sql trước khi chạy server. Không commit .env.

## Quyền

- CUSTOMER: quản lý xe cá nhân, đặt/hủy chỗ, xem lượt gửi và thanh toán của mình.
- ADMIN: CRUD bãi/khu vực/ô đỗ, quản lý tài khoản /users và /users/{id}/access.
- ADMIN/MANAGER: bảng giá, báo cáo, chạy hết hạn thủ công.
- ADMIN/MANAGER/SECURITY: check-in/check-out và thu tiền mặt.
- Thiết bị IoT mới: đăng ký qua POST /iot/devices (ADMIN/MANAGER), gửi telemetry bằng khóa riêng từng thiết bị. API cũ /iot/sensor với khóa chung IOT_API_KEY chỉ dùng cho ô chưa đăng ký SENSOR. Xem ../iot/README.md.

Tạo ADMIN mới bằng .\venv\Scripts\python.exe scripts/create_admin.py. Script hỏi mật khẩu, không cấp quyền cho tài khoản có sẵn.

## Luồng thử

1. Tạo bãi, khu vực, ô đỗ và xe bằng các API hiện có.
2. Tạo POST /pricing-rules: {"parking_lot_id":1,"vehicle_type":"MOTORBIKE","first_hour_price":5000,"additional_hour_price":2000}.
3. Tùy chọn POST /reservations với vehicle_id, parking_spot_id, start_time, expiry_time trong tương lai. Chỉ check-in trong khoảng đã đặt; ô chuyển RESERVED. Nếu gửi trực tiếp thì bỏ qua đặt chỗ.
4. Nhân viên POST /parking-sessions/check-in: {"vehicle_id":1,"parking_spot_id":1}; thêm reservation_id nếu đã đặt. Ô chuyển OCCUPIED.
5. POST /parking-sessions/{id}/check-out với {}. Ô chuyển AVAILABLE, đặt chỗ chuyển COMPLETED, lượt gửi có total_amount.
6. POST /payments: {"parking_session_id":1,"payment_method":"CASH"}. Thu tiền được ghi SUCCESS, tiền lấy từ lượt gửi; chặn thu trùng.
7. GET /reports/summary xem số ô, lượt gửi, tổng doanh thu đã thu.

Giá: ít nhất một giờ; giờ phát sinh làm tròn lên. Ví dụ 2 giờ 1 phút: 5000 + 2 x 2000 = 9000. Không cho đổi bảng giá khi còn xe loại đó đang gửi trong bãi.
Đặt chỗ tự hết hạn mỗi 30 giây khi app chạy; cũng có POST /reservations/expire. Đặt chỗ có xe đã check-in không bị hết hạn/hủy.
Cảm biến lưu trạng thái vật lý vào sensor_logs; không ghi đè trạng thái của đặt chỗ/lượt gửi đang hoạt động hoặc ô MAINTENANCE.

## Kiểm tra

```powershell
.\venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\venv\Scripts\python.exe -m pytest tests -q
$env:TEST_POSTGRES='1'
.\venv\Scripts\python.exe -m pytest tests -q
Remove-Item Env:TEST_POSTGRES
```

PostgreSQL tests tạo schema test_backend_<random>, chạy dữ liệu riêng và xóa schema đó; không dùng dữ liệu bãi xe thật.
Bổ sung unique indexes: .\venv\Scripts\python.exe scripts/apply_integrity.py. Chạy trong một transaction; nếu dữ liệu đã trùng, transaction rollback và cần xử lý dữ liệu trước.

## Phạm vi

Thanh toán CASH đã triển khai. VNPAY/MOMO/VIETQR chưa kết nối: cần tài khoản merchant, chữ ký và callback xác thực; API không nhận các phương thức này để tránh ghi thành công giả.
Backend lưu đường dẫn ảnh và độ tin cậy biển số trong lượt gửi. AI nhận diện biển số đã tích hợp qua /ai/recognize, /ai/check-in và /ai/check-out/{session_id}; xem ../ai_engine/README.md. Phần cứng IoT và giao diện web là thành phần riêng.

## AI biển số

Xem `../ai_engine/README.md` để chạy OCR, chọn ROI, thử ảnh và luồng xe vào/ra bằng ảnh.


## Bổ sung sau rà soát backend và AI

- Biển số được so sánh sau khi bỏ dấu cách/chấm/gạch và đổi chữ hoa. Database có unique index tương ứng, tránh tạo hai xe khác ID cho cùng biển số.
- Mỗi xe chỉ giữ một đặt chỗ PENDING/CONFIRMED tại một thời điểm. Vì hệ thống giữ ô ngay khi đặt (không lập lịch chia ô theo nhiều khoảng), cần hủy đặt chỗ trước khi chọn ô khác. Xe có đặt chỗ cần dùng đúng reservation_id khi check-in.
- Bãi không hoạt động không nhận đặt chỗ/check-in mới. Xe đã vào vẫn được check-out.
- ADMIN đặt hộ xe sẽ gắn đặt chỗ với chủ xe, để chủ xe xem/hủy được.
- Thao tác sửa/xóa xe và sửa ô được khóa đồng bộ với check-in. Xe có lịch sử gửi không được đổi biển số/loại xe; vẫn sửa được brand/color khi không còn lượt gửi hoặc đặt chỗ hoạt động.
- Hủy/hết hạn đặt chỗ xét bản tin cảm biến kể từ lúc tạo đặt chỗ. Nếu cảm biến mới báo OCCUPIED, ô không bị trả về AVAILABLE. Bản tin cũ trước lúc đặt không được dùng để quyết định trạng thái này.
- Các trường bắt buộc không nhận null hoặc chuỗi chỉ có khoảng trắng. Phí vượt giới hạn DECIMAL(12,2) trả 409, giữ lượt gửi ACTIVE để nhân viên kiểm tra.
- GET /iot/sensor-logs chỉ dành cho nhân viên. GET /health là kiểm tra tiến trình; GET /health/ready kiểm tra kết nối database. Database tạm lỗi trả 503, xung đột transaction có thể thử lại trả 409.
- Logic check-in/check-out nằm trong services/session_service.py, dùng chung cho API thủ công và AI. API AI xác thực response trước khi commit, và xóa ảnh vừa tạo khi giao dịch thất bại.

Ràng buộc bổ sung nằm trong database/backend_integrity.sql và cũng có trong schema.sql khi tạo database mới. Đã áp dụng lên database trên máy sau khi xác nhận không có bản ghi trùng; không sửa/xóa dữ liệu nghiệp vụ cũ.

Kiểm thử PostgreSQL hiện dùng trực tiếp database/schema.sql để có cùng CHECK, FK và index với bản triển khai. Các bài concurrent dùng session/transaction riêng. Chạy đầy đủ cả OCR thật:

```powershell
$env:TEST_POSTGRES='1'
$env:RUN_AI_MODEL_TESTS='1'
.\venv\Scripts\python.exe -m pytest tests -q
Remove-Item Env:TEST_POSTGRES
Remove-Item Env:RUN_AI_MODEL_TESTS
```


## Phân loại xe xăng/điện và quy mô bãi

Đã cập nhật: 50 ô tô (30 xăng + 20 điện), 120 xe máy (70 xăng + 50 điện). Tổng 170 chỗ, gồm 20 trụ sạc ô tô và 50 ổ cắm xe máy đang được khai báo PLANNED. Xe/ô đỗ/bảng giá dùng vehicle_type hoặc spot_type và energy_type (GASOLINE/ELECTRIC). Xem ../docs/vehicle_energy_and_capacity.md để cấu hình READY, bảng giá riêng và API sức chứa. OCR đọc biển số rồi tra loại xe/năng lượng trong hồ sơ đăng ký. Tổng kiểm thử mới nhất: 58 bài qua PostgreSQL.


## IoT mô phỏng

Đọc `../iot/README.md` để chạy demo 170 cảm biến và 70 điểm sạc, hoặc kết nối simulator vào bãi đang dùng. Trước khi khởi động backend với database cũ, chạy `venv/Scripts/python.exe scripts/migrate_iot.py`. Database mới dùng schema.sql đã có bảng IoT.

Ô đã gắn thiết bị IoT chỉ nhận đặt chỗ/check-in mới khi dữ liệu còn mới; điểm sạc còn phải báo READY và được quản lý đưa vào phục vụ. Mất kết nối không cản check-out. GET /parking-lots/{id}/capacity trả available_for_booking theo cả trạng thái ô và dữ liệu IoT. Bộ lọc charging_ready của /parking-spots cũng kiểm tra dữ liệu thiết bị sạc; charger_status trong kết quả là cấu hình quản lý.


## Frontend Parkly

Đã có giao diện React trong `../web_dashboard`. Build bằng `npm run build`, chạy `../run_dashboard.py` bằng Python của venv để phục vụ giao diện tại `/dashboard/` cùng API. Hướng dẫn và kiểm thử: `../web_dashboard/README.md`.
