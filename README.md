# DACN — Parkly Smart Parking

Đồ án quản lý bãi xe thông minh: FastAPI, PostgreSQL, React/Vite, AI nhận diện biển số và IoT mô phỏng.

## Chức năng

- Đăng ký tài khoản và hồ sơ khách hàng; quản lý phương tiện.
- Đặt/hủy chỗ, xe vào/ra, tính phí và thu tiền mặt.
- Sơ đồ bãi 170 chỗ: 50 ô tô (20 điện), 120 xe máy (50 điện).
- Nhận diện biển số từ ảnh; cảm biến và điểm sạc mô phỏng.
- Phân quyền quản trị viên, quản lý, nhân viên và khách hàng.

## Thư mục

| Thư mục | Nội dung |
|---|---|
| `backend` | API, phân quyền, nghiệp vụ và kiểm thử |
| `web_dashboard` | Giao diện React/Vite |
| `ai_engine` | Nhận diện biển số và ảnh mẫu kiểm thử |
| `iot` | Bộ mô phỏng thiết bị |
| `database` | SQL tạo bảng và migration |
| `docs` | Tài liệu các phần của đồ án |

## Cài đặt trên Windows

Cài Python, Node.js và PostgreSQL trước. Dự án đã được chạy với Python 3.14, Node.js 24 và PostgreSQL 18.

```powershell
git clone https://github.com/nguyennguyenhau8300-glitch/DACN.git
cd DACN
python -m venv backend/venv
.\backend\venv\Scripts\python.exe -m pip install -r backend/requirements.txt
Copy-Item backend/.env.example backend/.env
```

Sửa `backend/.env`: thông tin PostgreSQL, mật khẩu database, `JWT_SECRET_KEY` và `IOT_API_KEY` riêng. File mẫu chỉ chứa giá trị thay thế.

Tạo database `smart_parking_db` trong PostgreSQL, rồi chạy `database/schema.sql` bằng pgAdmin hoặc psql. Với database cũ, xem hướng dẫn migration trong tài liệu từng phần.

```powershell
cd web_dashboard
npm ci
npm run build
cd ..\backend
.\venv\Scripts\python.exe scripts/create_admin.py
cd ..
.\backend\venv\Scripts\python.exe run_dashboard.py
```

Mở http://127.0.0.1:8001/dashboard/ và đăng nhập bằng tài khoản quản trị vừa tạo. Tạo bãi, sơ đồ và bảng giá tại **Bảng giá & bãi xe**. Điểm sạc mới mặc định **Chưa vận hành**; chuyển sang **Sẵn sàng** trong **Sạc & thiết bị IoT** khi dùng mô phỏng.

Repository không chứa dữ liệu khách hàng, trạng thái bãi trên máy cá nhân, mật khẩu, môi trường `venv`, `node_modules` hoặc bản build `dist`. Cần cài thư viện và build khi lấy dự án sang máy khác.

## Tài liệu chi tiết

- [Backend và kiểm thử](backend/README.md)
- [Frontend và cách sử dụng](web_dashboard/README.md)
- [AI nhận diện biển số](ai_engine/README.md)
- [IoT mô phỏng](iot/README.md)
- [Cấu hình xe xăng/điện và sức chứa](docs/vehicle_energy_and_capacity.md)

Thanh toán hiện dùng tiền mặt. Chưa tích hợp thanh toán trực tuyến, camera livestream hoặc barrier thật.
