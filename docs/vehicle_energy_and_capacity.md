# Cấu hình bãi xe 170 chỗ

## Phân bổ đã chốt và đã tạo trong database

| Nhóm | Loại xe | Nguồn năng lượng | Số chỗ | Thiết bị tại chỗ |
|---|---|---|---:|---|
| Ô tô xăng | CAR | GASOLINE | 30 | Không có thiết bị sạc |
| Ô tô điện | CAR | ELECTRIC | 20 | 20 trụ sạc EV_CHARGER |
| Xe máy xăng | MOTORBIKE | GASOLINE | 70 | Không có thiết bị sạc |
| Xe máy điện | MOTORBIKE | ELECTRIC | 50 | 50 ổ cắm SOCKET |
| Tổng | | | 170 | 70 điểm sạc |

Sức chứa bãi id=1: car_capacity=50, motorbike_capacity=120, electric_car_capacity=20, electric_motorbike_capacity=50. Ô đỗ cũ được tính vào sức chứa, đã thêm 169 ô để đạt 170; không tạo lại xe hoặc thay đổi lịch sử gửi xe.

## Cách biểu diễn dữ liệu

Xe và ô đỗ dùng hai trường độc lập: vehicle_type/spot_type là CAR hoặc MOTORBIKE; energy_type là GASOLINE hoặc ELECTRIC. Mặc định GASOLINE để tương thích các yêu cầu cũ. Dữ liệu ELECTRIC_CAR cũ nếu có được chuyển thành CAR + ELECTRIC.

Ví dụ đăng ký xe máy điện:

```json
{"license_plate":"59A1-98765","vehicle_type":"MOTORBIKE","energy_type":"ELECTRIC","brand":"VinFast"}
```

Thông tin chỗ điện gồm charger_type, charging_station_code, charging_port_code, charging_power_kw và charger_status. Mã trạm/cổng do phần mềm tạo là nhãn quản lý dự kiến; công suất để null cho tới khi có thông số thiết bị thật.

## Trạng thái sạc và đặt chỗ

Các điểm sạc mới ở trạng thái PLANNED (chờ lắp đặt), chưa được tính là sẵn sàng đặt/check-in. ADMIN hoặc MANAGER cập nhật khi đã sẵn sàng:

```text
PATCH /parking-spots/{spot_id}/charging-status
```

```json
{"charger_status":"READY"}
```

Trạng thái khác: OFFLINE, MAINTENANCE; PLANNED để ghi nhận kế hoạch. Có thể báo OFFLINE khi đang có xe; xe đó vẫn check-out được, nhưng không nhận đặt chỗ/check-in mới khi điểm sạc chưa READY.

Cấu hình này quản lý vị trí và trạng thái thiết bị trong phần mềm. Chưa gửi lệnh đóng/ngắt điện, đo kWh hoặc thu phí điện qua phần cứng. Giá trong pricing-rules là phí gửi xe, không phải giá điện sạc.

## API xem và quản lý

- GET /parking-lots/1/capacity: sức chứa, số ô đã tạo, số ô đặt được, ô đang dùng và số điểm sạc sẵn sàng theo bốn nhóm.
- GET /parking-spots?parking_lot_id=1&vehicle_type=CAR&energy_type=ELECTRIC: ô tô điện.
- GET /parking-spots?parking_lot_id=1&vehicle_type=MOTORBIKE&energy_type=ELECTRIC&charging_ready=true&spot_status=AVAILABLE: xe máy điện có điểm sạc sẵn sàng.
- GET /vehicles?vehicle_type=MOTORBIKE&energy_type=ELECTRIC: xe máy điện của tài khoản.
- POST /parking-lots/1/initialize-layout: tạo bổ sung ô còn thiếu theo cấu hình, có thể gọi lại mà không nhân đôi ô. Chỉ ADMIN.
- PUT /parking-lots/1: chỉnh quy mô trong khoảng 30–50 ô tô và 90–120 xe máy; không giảm thấp hơn số ô đã tạo của bất kỳ nhóm nào.
- POST /pricing-rules: thêm energy_type để lập bốn bảng giá riêng. Chưa tự đặt giá vì chưa có mức phí được chốt.

Ví dụ cấu trúc bảng giá xe máy điện (giá chỉ minh họa, chưa thêm vào database):

```json
{"parking_lot_id":1,"vehicle_type":"MOTORBIKE","energy_type":"ELECTRIC","first_hour_price":5000,"additional_hour_price":2000}
```

## AI và đối chiếu xe

OCR đọc biển số; backend lấy loại xe và nguồn năng lượng từ hồ sơ đã đăng ký. AI không đoán xe xăng/điện từ biển số. Đặt chỗ và check-in thủ công/AI đều kiểm tra đúng loại, đúng nguồn năng lượng, đúng trạng thái điểm sạc. Sai nhóm trả 400; điểm sạc chưa sẵn sàng trả 409.

## Cập nhật máy khác

Máy hiện tại đã áp dụng migration và tạo sơ đồ. Máy mới chạy database/schema.sql; máy có database cũ chạy:

```powershell
cd E:\DoAnChuyenNghanh\backend
.\venv\Scripts\python.exe scripts/apply_energy.py
.\venv\Scripts\python.exe scripts/apply_integrity.py
.\venv\Scripts\python.exe scripts/initialize_layout.py --lot-id 1
```

Khởi động lại backend để nạp trường/API mới. Migration chạy trong transaction; chỉ bổ sung thông tin năng lượng/sạc và chuyển enum xe điện cũ, không xóa lịch sử.

## Kiểm tra

58 bài qua trên PostgreSQL, gồm OCR thật, bốn loại xe, trạm/ổ cắm, phân bổ chính xác 170 chỗ, khởi tạo lặp không trùng, chặn quá sức chứa khi gửi đồng thời, đặt chỗ xe điện và check-out khi trạm báo OFFLINE.
