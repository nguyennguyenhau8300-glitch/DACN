# Kiểm thử Parkly

Các lệnh có đường dẫn `DACN` bắt đầu từ thư mục gốc repo. Cài và cấu hình backend theo [README dự án](../README.md) trước khi chạy.

## Backend PostgreSQL

```powershell
.\DACN\backend\venv\Scripts\python.exe -m pip install -r DACN/backend/requirements-dev.txt
$env:TEST_POSTGRES='1'
$env:RUN_AI_MODEL_TESTS='1'
.\DACN\backend\venv\Scripts\python.exe -m pytest kiem_thu/backend -q
```

Bộ chạy tạo schema kiểm thử riêng trong PostgreSQL và dọn sau mỗi ca. Tài khoản database cần quyền tạo schema.

## Web Playwright

Cài Node.js. Từ thư mục gốc repo, cài thư viện web và trình duyệt Chromium của Playwright.

```powershell
npm ci --prefix .\DACN\web_dashboard
.\DACN\web_dashboard\node_modules\.bin\playwright.cmd install chromium
.\DACN\backend\venv\Scripts\python.exe kiem_thu/web_dashboard/run_e2e.py
```

Bộ chạy khởi động API và Vite trên các cổng riêng và làm việc với schema kiểm thử.

## Flutter

```powershell
cd .\DACN\mobile_app
flutter pub get
flutter analyze
flutter test ../../kiem_thu/mobile_app/test
```

Để chạy tích hợp trên máy ảo Android, mở thiết bị trước và gọi từ thư mục gốc repo.

```powershell
.\DACN\backend\venv\Scripts\python.exe kiem_thu/mobile_app/tool/run_android_tests.py
```

Thư mục `advanced` dành cho kịch bản phát triển có cài các dịch vụ mô phỏng bổ sung.
