# IoT mô phỏng cho đồ án bãi xe

Đã triển khai bằng Python và HTTP REST, dùng cùng backend FastAPI/PostgreSQL. Không cần ESP32 hoặc cảm biến thật. Thư mục `iot` chứa chương trình mô phỏng; `docs` chứa tài liệu hướng dẫn.

## Quy mô theo cấu hình đã chọn

| Nhóm xe | Ô đỗ / cảm biến | Điểm sạc mô phỏng |
|---|---:|---:|
| Ô tô xăng | 30 | 0 |
| Ô tô điện | 20 | 20 trạm/cổng EV_CHARGER |
| Xe máy xăng | 70 | 0 |
| Xe máy điện | 50 | 50 ổ cắm SOCKET |
| Tổng | 170 | 70 |

Mỗi ô có một thiết bị SENSOR; mỗi ô điện có thêm một thiết bị CHARGER. Tổng cộng 240 thiết bị ảo. Các số đo điện chỉ phục vụ trình diễn, chưa dùng để tính tiền điện.

## 1. Chạy demo ngay — không cần đăng nhập

Máy hiện tại đã có các thư viện cần thiết. Khi cài sang máy khác, cài bằng `backend/venv/Scripts/python.exe -m pip install -r iot/requirements.txt` từ thư mục dự án.

Mở PowerShell:

```powershell
cd E:\DoAnChuyenNghanh
.\backend\venv\Scripts\python.exe .\iot\demo.py
```

PostgreSQL phải đang chạy và thông tin trong `backend/.env` phải đúng. Demo tự tạo schema PostgreSQL tạm, tài khoản quản trị tạm và server HTTP trên cổng localhost còn trống. Tài khoản database cần quyền tạo schema (máy hiện tại đã kiểm tra chạy được).

Demo thực hiện:

1. Tạo bãi thử đúng 170 ô và đăng ký 240 thiết bị.
2. Cho 70 điểm sạc của **bãi thử** vào trạng thái sẵn sàng.
3. Gửi 3 vòng dữ liệu: trống → có xe/đang sạc → trống; số chỗ có thể đặt lần lượt **170 → 0 → 170**.
4. Mô phỏng 70 điểm sạc báo lỗi: chỉ còn **100 chỗ xe xăng** có thể đặt.
5. Làm cũ thời gian báo tin của một thiết bị để kiểm tra OFFLINE; gửi heartbeat để chứng minh kết nối sống không có nghĩa số đo đã mới.
6. Tắt server và xóa schema/bộ khóa tạm sau khi hoàn thành hoặc Ctrl+C.

Đây là demo qua HTTP thật, không dùng dữ liệu bãi chính. 70 điểm sạc trong bãi chính vẫn giữ trạng thái PLANNED như đã cấu hình trước đó.

Lưu báo cáo bằng:

```powershell
.\backend\venv\Scripts\python.exe .\iot\demo.py --report .\iot\demo-report.json
```

## 2. Chạy mô phỏng trên bãi đã cấu hình trong backend

Dùng phần này khi muốn dữ liệu mô phỏng hiển thị trên bãi chính. Mô phỏng sẽ cập nhật trạng thái ô đỗ của bãi được chọn.

**Cửa sổ PowerShell thứ nhất — backend:**

```powershell
cd E:\DoAnChuyenNghanh\backend
.\venv\Scripts\python.exe scripts\migrate_iot.py
.\venv\Scripts\python.exe -m uvicorn main:app --reload --port 8001
```

Migration đã được áp dụng trên máy hiện tại; chạy lại được. Máy mới tạo database bằng `database/schema.sql` thì đã có các bảng IoT.

**Cửa sổ thứ hai — đăng ký và chạy mô phỏng:**

```powershell
cd E:\DoAnChuyenNghanh
.\backend\venv\Scripts\python.exe .\iot\simulator.py configure --lot-id 1
.\backend\venv\Scripts\python.exe .\iot\simulator.py run --scenario cycle --rounds 3 --interval 10
```

Lệnh configure hỏi email và mật khẩu ADMIN/MANAGER; mật khẩu được nhập ẩn. Tự đăng ký một cảm biến cho mỗi ô, thêm một thiết bị sạc cho mỗi ô điện và lưu khóa vào `iot/devices.local.json`. Chạy configure lại sẽ tái sử dụng cấu hình. File này được gitignore, chứa khóa riêng và số sequence, cần giữ lại để chạy tiếp.

Ngay khi đăng ký, thiết bị ở NEVER_SEEN và ô tương ứng chưa được nhận đặt chỗ mới cho đến khi có số đo hợp lệ. Khi dừng mô phỏng quá 90 giây, dữ liệu hết hạn và ô được chặn nhận đặt chỗ mới. Chạy lại mô phỏng để gửi dữ liệu mới. Không tự giải phóng ô đang có xe, đặt chỗ hoặc bảo trì khi thiết bị mất kết nối.

Các kịch bản:

```powershell
# Tất cả cảm biến báo trống; thiết bị sạc báo READY.
.\backend\venv\Scripts\python.exe .\iot\simulator.py run --scenario idle --rounds 30 --interval 10

# Trống → có xe/đang sạc → trống; lặp theo chu kỳ 3 vòng.
.\backend\venv\Scripts\python.exe .\iot\simulator.py run --scenario cycle --rounds 6 --interval 10

# Cảm biến báo trống, các thiết bị sạc báo FAULT.
.\backend\venv\Scripts\python.exe .\iot\simulator.py run --scenario charger-fault --rounds 1

# Chỉ báo thiết bị còn kết nối; không thay thế số đo mới.
.\backend\venv\Scripts\python.exe .\iot\simulator.py heartbeat
```

Trạng thái `charger_status` của ô đỗ là cấu hình do quản lý quyết định. Thiết bị gửi READY không tự chuyển PLANNED hoặc MAINTENANCE thành READY. Để đưa điểm sạc mô phỏng vào phục vụ, quản lý dùng PATCH `/parking-spots/{id}/charging-status` với `{"charger_status":"READY"}`. Điểm sạc chỉ nhận xe mới khi cấu hình READY và dữ liệu thiết bị còn mới, báo READY.

Kịch bản cycle gửi công suất giả 7 kW cho ô tô, 0,5 kW cho xe máy khi CHARGING. Nếu đã nhập công suất giới hạn nhỏ hơn, backend sẽ từ chối bản tin vượt giới hạn; chỉnh số mô phỏng trong `make_payload` theo cấu hình. Bộ đếm kWh tăng giả 0,01 ở vòng CHARGING, không được xem là điện năng tính theo thời gian thực.

## 3. API đã bổ sung

Swagger khi backend chạy: http://127.0.0.1:8001/docs

| API | Quyền | Công dụng |
|---|---|---|
| POST `/iot/devices` | ADMIN/MANAGER | Đăng ký thiết bị, nhận api_key một lần |
| GET `/iot/devices?parking_lot_id=1` | Nhân viên | Xem thiết bị, số đo, ONLINE/OFFLINE/NEVER_SEEN/DISABLED |
| PATCH `/iot/devices/{code}/access` | ADMIN/MANAGER | Tắt/bật thiết bị, yêu cầu số đo mới sau khi bật |
| POST `/iot/devices/{code}/rotate-key` | ADMIN/MANAGER | Cấp khóa mới, khóa cũ hết hiệu lực, yêu cầu số đo mới |
| POST `/iot/devices/{code}/heartbeat` | Khóa riêng | Cập nhật thời gian kết nối |
| POST `/iot/devices/{code}/telemetry` | Khóa riêng | Gửi trạng thái cảm biến hoặc thiết bị sạc |
| GET `/iot/events` | Nhân viên | Lịch sử sự kiện, lọc device_code, limit ≤ 500, phân trang before_id |
| GET `/iot/sensor-logs` | Nhân viên | Nhật ký cảm biến tương thích backend trước đó |

Mẫu đăng ký:

```json
{"device_code":"SIM-SENSOR-1","parking_spot_id":1,"kind":"SENSOR","offline_after_seconds":90}
```

Thiết bị gửi header `X-API-Key` bằng api_key nhận khi đăng ký. Backend chỉ lưu hash SHA-256 của khóa ngẫu nhiên, danh sách thiết bị không trả khóa hoặc hash. Mỗi khóa chỉ được gửi tin cho đúng thiết bị và đúng ô đã gắn. Không cần token đăng nhập người dùng cho telemetry/heartbeat.

Mẫu cảm biến:

```json
{"sequence":1,"sensor_status":"OCCUPIED"}
```

Mẫu thiết bị sạc:

```json
{"sequence":1,"charger_status":"CHARGING","power_kw":0.5,"energy_kwh":0.01}
```

Trạng thái sạc nhận: READY, CHARGING, FAULT, OFFLINE. Khi không CHARGING, công suất chỉ được 0 hoặc bỏ trống. Công suất/điện năng không âm; nếu điểm sạc có công suất cấu hình thì không được báo vượt mức đó.

API cũ POST `/iot/sensor` và khóa chung IOT_API_KEY vẫn dùng được cho ô chưa đăng ký SENSOR mới. Khi đã đăng ký SENSOR, endpoint cũ từ chối để tránh bỏ qua khóa riêng và kiểm tra sequence.

## 4. Quy tắc nghiệp vụ và xử lý sự cố

- Sequence là số nguyên dương tăng theo từng thiết bị, được lưu cùng cấu hình mô phỏng. Gửi lại cùng sequence và cùng dữ liệu trả `duplicate: true`, không thêm log hoặc cập nhật ô lần nữa. Sequence trùng nhưng nội dung khác, hoặc bản tin cũ chưa từng được chấp nhận, trả 409.
- Mỗi bản tin được lưu vào file trước khi gửi. Nếu mất mạng/timeout, simulator thử gửi lại tối đa 3 lần; nếu vẫn lỗi thì giữ bản tin pending để lần chạy sau tiếp tục. Không tự bỏ qua bản tin chưa được xác nhận.
- Gửi lại bản tin đã xử lý không kéo dài tuổi số đo. Heartbeat chỉ làm mới kết nối, không làm mới telemetry. `connection_status=ONLINE` vẫn có thể có `telemetry_fresh=false`.
- Sau timeout (mặc định 90 giây, cấu hình 10–3600), tính OFFLINE trực tiếp khi đọc. Không cần chờ tác vụ nền.
- Thiết bị bị tắt, chưa gửi dữ liệu hoặc số đo quá cũ đều chặn nhận đặt chỗ/check-in mới. Các ô chưa gắn thiết bị vẫn hoạt động thủ công như trước.
- Ô có phiên gửi đang hoạt động giữ OCCUPIED dù cảm biến báo trống. Ô đã đặt giữ RESERVED; ô bảo trì giữ MAINTENANCE. Dữ liệu cảm biến vẫn được lưu để đối chiếu.
- Xe đã check-out nhưng cảm biến mới nhất vẫn báo có xe: chưa nhận đặt chỗ mới cho tới khi có số đo trống. Xe có đặt chỗ hợp lệ vẫn check-in được khi cảm biến của ô giữ chỗ đã báo có xe.
- Điểm sạc CHARGING/FAULT/OFFLINE hoặc quá hạn không nhận xe mới. Check-out và tính phí gửi xe vẫn thực hiện được khi thiết bị mất kết nối.
- Tín hiệu cảm biến không xác định chủ xe/biển số và không tự tạo lượt gửi. Nhân viên/AI vẫn thực hiện check-in/check-out bằng API hiện có. Với xe không đặt trước, thực hiện check-in ở cổng khi ô còn trống rồi mô phỏng xe vào ô.
- Chỉ cho một tiến trình simulator dùng cùng file cấu hình. Nếu tiến trình bị kết thúc cưỡng bức, xác nhận nó đã dừng rồi xóa file `devices.local.json.lock` trước khi chạy lại.
- Mất file khóa: quản lý dùng rotate-key, cập nhật api_key và sequence theo last_sequence từ GET `/iot/devices`; gửi sequence tiếp theo. Không đặt sequence trở về 1. Không chia sẻ file chứa khóa.

## 5. Các tệp chính

- `iot/simulator.py`: đăng ký thiết bị, lưu trạng thái, gửi dữ liệu, retry.
- `iot/demo.py`: demo độc lập qua server HTTP và PostgreSQL thật.
- `backend/routers/iot_devices.py`: API quản lý thiết bị và nhận telemetry.
- `backend/services/iot_service.py`: xác thực, độ mới dữ liệu, trạng thái ô đỗ.
- `backend/models/iot_device.py`: bảng thiết bị và sự kiện.
- `backend/schemas/iot_device.py`: kiểm tra dữ liệu đầu vào.
- `database/iot.sql`: migration thêm bảng; đã tích hợp vào schema.sql.
- `backend/scripts/migrate_iot.py`: áp dụng migration cho database hiện tại.
- `backend/tests/test_iot.py` và kiểm thử đồng thời trong `test_concurrency.py`.

## 6. Phạm vi hoàn thành

Hoàn thành phần IoT mô phỏng và tích hợp backend/AI. Chưa kết nối phần cứng, camera/barrier hoặc điều khiển nguồn điện; không cần các thiết bị đó để chạy demo. Chưa có giao diện dashboard riêng; xem trạng thái qua Swagger hoặc kết quả demo trên PowerShell. HTTP được chọn để dùng trực tiếp backend hiện có; chưa cần MQTT broker.


## Kết quả kiểm tra ngày 12/10/2026

- 78 kiểm thử backend, AI và IoT đều đạt trên PostgreSQL; có kiểm thử OCR thật và hai yêu cầu IoT đồng thời gửi cùng sequence chỉ ghi một sự kiện.
- Demo qua HTTP thật hoàn thành với 240 thiết bị và 960 bản tin telemetry trong 4 vòng, gồm lỗi điểm sạc và mất kết nối.
- Migration chạy lặp hai lần thành công; bãi chính vẫn có 170 ô, 70 điểm sạc PLANNED. Chưa tự đăng ký thiết bị mô phỏng vào bãi chính; dùng configure khi muốn chạy trên bãi này.
- Có một cảnh báo deprecation từ Starlette về httpx dùng cho TestClient; không làm kiểm thử thất bại.
