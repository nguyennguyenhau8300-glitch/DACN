# Parkly

Đồ án hệ thống theo dõi và quản lý bãi xe thông minh. Backend FastAPI và PostgreSQL phục vụ web React, ứng dụng Flutter, nhận diện biển số YOLOv8 và RapidOCR, đặt chỗ, IoT và thanh toán thử.

- [DACN](DACN/) chứa mã nguồn chạy hệ thống, các tệp SQL, bản web đã build, ảnh demo và trọng số AI.
- [kiem_thu](kiem_thu/) chứa mã kiểm thử backend, web, Flutter và dữ liệu thử.

## Chạy lần đầu trên Windows

Cài Python và PostgreSQL. Máy kiểm thử backend dùng Python 3.14.3. Tạo một database PostgreSQL trống. Từ thư mục gốc repo, mở PowerShell và chuẩn bị môi trường.

```powershell
cd .\DACN\backend
python -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements.txt -r ai_engine/requirements-yolo.txt
Copy-Item .env.example .env
```

Điền `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER` và `DB_PASSWORD` vào `DACN/backend/.env`. Đặt chuỗi ngẫu nhiên riêng cho `JWT_SECRET_KEY` và `IOT_API_KEY`. Từ thư mục backend, chạy lệnh sau.

```powershell
python main.py
```

Backend tạo các bảng hoặc áp dụng migration và mở [Dashboard](http://127.0.0.1:8001/dashboard/).

## Tạo tài khoản và bãi mẫu

Giữ backend đang chạy. Mở PowerShell khác tại thư mục gốc repo để tạo tài khoản quản trị viên.

```powershell
cd .\DACN\backend
.\venv\Scripts\python.exe .\scripts\create_admin.py
```

1. Đăng nhập Dashboard và bấm **Tạo bãi xe**. Để có mô hình 95 ô, nhập tổng 30 ô tô và 65 xe máy, trong đó 10 ô tô điện và 25 xe máy điện.
2. Vào **Bảng giá & bãi xe → Tạo / bổ sung sơ đồ**. Thiết lập giá cho các nhóm xe dùng trong demo.
3. Vào **Sạc & thiết bị IoT → Điểm sạc → Cập nhật**. Chuyển ít nhất một ô ô tô điện sang **Sẵn sàng**.
4. Vào **Giả lập vận hành**, bấm **Chuẩn bị xe mẫu** rồi chạy **Ô tô điện vào đỗ và sạc**.

## Chạy Flutter

Cài Flutter và công cụ cho thiết bị cần chạy. Android dùng SDK Android, Windows dùng bộ công cụ C++ của Visual Studio và Chrome chạy bản web Flutter. Giữ backend ở cổng 8001, rồi chạy từ thư mục gốc repo.

```powershell
cd .\DACN\mobile_app
flutter run
```

Chọn Android, Windows hoặc Chrome khi Flutter hỏi thiết bị. Có thể dùng `flutter run -d chrome` để mở ngay bản trên Chrome.

Xem thêm [hướng dẫn vận hành và build lại](DACN/README.md) hoặc [lệnh kiểm thử](kiem_thu/README.md).
