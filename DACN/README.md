# DACN — Parkly

## Chạy backend và web

Các lệnh bên dưới bắt đầu trong thư mục DACN. Nếu vừa clone repo, hãy xem [hướng dẫn cài đặt và tạo bãi mẫu](../README.md).

```powershell
cd .\backend
python main.py
```

Backend tự chuẩn bị schema PostgreSQL và mở [Parkly Dashboard](http://127.0.0.1:8001/dashboard/). Dashboard và app dùng chung cổng `8001`. PostgreSQL cần đang chạy và đã cấu hình `backend/.env`. Nếu Python mặc định thiếu thư viện, lệnh sẽ dùng `backend/venv` khi môi trường này đã được cài.

## Chạy app Flutter

Mở PowerShell thứ hai tại thư mục DACN.

```powershell
cd .\mobile_app
flutter run
```

- Nếu Flutter liệt kê nhiều thiết bị, chọn Windows, Chrome hoặc Android. Dùng `flutter run -d windows` để mở thẳng ứng dụng Windows.
- Windows và Chrome trên máy chạy backend tự dùng cổng `8001`. Khi chỉ có một thiết bị ADB, bản Android debug tự chuyển tiếp cổng qua ADB. App cũng nhận địa chỉ của máy build để kết nối cùng mạng, và hỗ trợ máy ảo Android.
- Nếu app đã lưu địa chỉ riêng từ trước, chọn **Cấu hình máy chủ → Dùng kết nối tự động** để trở về thiết lập trên.

## Mã nguồn và file chạy

```text
DACN/
├── backend/                 FastAPI và nghiệp vụ
│   ├── ai_engine/           YOLOv8, OCR, model và công cụ AI
│   ├── iot/                 Công cụ IoT và firmware tham khảo
│   ├── database/            SQL tạo bảng và migration
│   ├── models/              Mô hình dữ liệu
│   ├── routers/             Các API
│   ├── schemas/             Kiểm tra dữ liệu đầu vào và đầu ra
│   ├── services/            Xử lý nghiệp vụ
│   ├── scripts/             Quản trị và migration
│   ├── storage/             Ảnh bằng chứng và file cục bộ
│   ├── test_data/           Ảnh mẫu cho giả lập camera
│   ├── venv/                Môi trường Python cục bộ
│   ├── database.py          Kết nối PostgreSQL
│   └── main.py              Ứng dụng FastAPI
├── web_dashboard/           React; src là nguồn, dist là bản build
├── mobile_app/              Flutter cho Android, Windows và web
├── tools/                   Công cụ demo nâng cao và tunnel Internet
├── CHAY_WEB.bat             Lối mở nhanh gọi backend/main.py
└── README.md
```

`backend/database/` chứa SQL; `backend/database.py` cung cấp kết nối Python. Hai thành phần có nhiệm vụ riêng. Không thêm `__init__.py` vào thư mục SQL.

Luồng chạy hằng ngày dùng `backend/main.py` và `flutter run`. Các lệnh cũ trong `tools/` phục vụ demo giao thức nâng cao và kết nối Internet tạm.

Bãi hiện có 95 chỗ: 20 ô tô xăng, 10 ô tô điện, 40 xe máy xăng, 25 xe máy điện.

## Dùng app Android qua Wi-Fi khác hoặc 4G/5G

Chạy `tools/CHAY_APP_ANDROID.bat` để mở API LAN ở cổng 8002, sau đó chạy `tools/CHAY_APP_KHAC_MANG.bat`. Công cụ tải và kiểm SHA-256 của cloudflared lần đầu, rồi mở URL HTTPS tạm cho API. Giữ máy tính bật và có Internet.

1. Cài app bằng `flutter run` hoặc tạo APK bằng `flutter build apk`. Để dùng đường dẫn `/mobile.apk`, chép APK vừa build vào `mobile_app/dist/Parkly-Android.apk` trên máy chủ.
2. Trong app, mở **Cấu hình máy chủ**, nhập URL HTTPS được in ra, không thêm `/dashboard`.
3. Bấm **Kiểm tra kết nối**, **Lưu địa chỉ**, rồi đăng nhập bằng tài khoản của hệ thống.

Hướng dẫn và URL hiện tại lưu tại `../work/internet-demo/KET_NOI_DIEN_THOAI.txt`. Chạy lại sẽ dùng tunnel hiện có nếu còn hoạt động. Khi dừng hoặc khởi động lại tunnel, URL có thể đổi; nhập lại địa chỉ trong app khi cần. Chạy `tools/DUNG_APP_KHAC_MANG.bat` để đóng đường dẫn Internet, giữ backend cục bộ tiếp tục chạy.

Đây là cách demo tạm bằng [Cloudflare Quick Tunnel](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/), không phải máy chủ chạy độc lập khi tắt máy tính. App vẫn yêu cầu đăng nhập và giữ phân quyền hiện có.

## Giả lập vận hành nội bộ

Đăng nhập ADMIN/MANAGER → **Giả lập vận hành**. Không cần bật RTSP, FFmpeg, MQTT broker, Redis hay Wokwi.

- **Xe vào / ra → Nhận diện AI**: chọn ảnh mẫu trong `backend/test_data`, bấm giả lập camera; YOLOv8/RapidOCR đọc ảnh thật, trả khung, crop, biển số và confidence. Ảnh mờ/không đọc được không tự tạo giao dịch.
- **Có xe / Trống**, **Đang sạc**, **Quá nhiệt 70 °C** cập nhật dữ liệu nghiệp vụ, cảnh báo và WebSocket ngay trong backend.
- Hai kịch bản một nút: ô tô điện vào đỗ/sạc; xe ra/tính phí/QR thử/xác nhận thanh toán. Có nhật ký từng bước, ảnh bằng chứng và chống thao tác trùng.
- Barie vào và ra hiển thị riêng, quay 90 độ và tự đóng sau 4 giây.
- Bãi chính vẫn 95 ô và 35 điểm sạc. Thanh toán thử không chuyển tiền, không cộng vào doanh thu thực.

Các bước cài đặt bãi mới và mở demo có trong [README ở gốc repo](../README.md).

## Chính sách đặt chỗ

- **Giữ ô ngay.** Chọn giờ đến trong hai giờ tới theo giờ Việt Nam. Ô được giữ khi xác nhận. Mốc tự hết hạn mặc định là hai giờ sau giờ đến.
- **Đặt theo khung giờ.** Chọn giờ đến và giờ rời dự kiến. Ô được giữ từ giờ đến. Hai khung liên tiếp có thể dùng cùng một ô. Hạn nhận mặc định là mốc sớm hơn giữa giờ đến cộng hai giờ và giờ rời dự kiến.
- Backend khóa xe và ô khi đặt và từ chối các lịch trùng giờ. Nhân viên chỉ nhận xe trong hạn khi ô đã sẵn sàng. Nếu xe trước ở quá giờ, lượt sau phải đợi ô được trả và vẫn còn hạn nhận.
- Người đứng tên hoặc quản trị viên có thể hủy trước hạn nếu xe chưa được nhận. Lượt đã nhận tiếp tục cho tới khi làm thủ tục trả xe.

## Tính phí và đối soát doanh thu

- Trong **Xe vào / ra**, chọn **Chi tiết phí** của lượt đã hoàn tất để xem thời lượng, số giờ tính phí và đơn giá đã dùng. Phụ phí sạc điện của bản demo là 0 đồng.
- Với vai trò ADMIN hoặc MANAGER, mở **Báo cáo**, chọn khoảng ngày rồi bấm **Đối soát** để xem biên nhận của ngày cần kiểm tra. Doanh thu lấy theo ngày thanh toán thành công ở giờ Việt Nam. Khoản mô phỏng nằm ở cột **Thử nghiệm**.
- `python main.py` tự áp dụng migration PostgreSQL cần thiết. Các lượt cũ tiếp tục dùng tổng phí đã lưu.

## Cài lại trên máy khác

Cài Python và PostgreSQL. Để phát triển app, cài Flutter cùng Android SDK hoặc Visual Studio có bộ công cụ C++ cho Windows. Cài Node.js khi cần build lại Dashboard React.

```powershell
python -m venv backend/venv
.\backend\venv\Scripts\python.exe -m pip install -r backend/requirements.txt -r backend/ai_engine/requirements-yolo.txt
Copy-Item backend/.env.example backend/.env
```

Điền thông tin riêng trong `backend/.env`, tạo database PostgreSQL, rồi chạy `python main.py` trong `backend` để tạo bảng. Tạo tài khoản quản trị bằng `backend/venv/Scripts/python.exe backend/scripts/create_admin.py` từ thư mục `DACN`. Bản Dashboard đã build nằm trong `web_dashboard/dist`. Sau khi sửa mã React, vào `web_dashboard` và chạy `npm ci` rồi `npm run build`.
Các trọng số dùng khi nhận diện nằm trong `backend/ai_engine/artifacts/`. Ảnh demo tổng hợp nằm trong `backend/test_data/`. Chạy `flutter build apk` từ `mobile_app/` khi cần bản cài Android.

Chạy công cụ AI dạng module từ thư mục `backend`, ví dụ:

```powershell
cd .\backend
.\venv\Scripts\python.exe -m ai_engine.cli --help
```

Từ thư mục `DACN`, công cụ IoT nằm ở `backend/iot/`; SQL nằm ở `backend/database/`. Cấu hình Docker tùy chọn được chuyển ra `../cong_cu_phat_trien/infrastructure/`, không cần cho demo nội bộ.

## Kiểm thử và dữ liệu

Xem [cách chạy bộ kiểm thử](../kiem_thu/README.md). SQL dùng để tạo và nâng cấp database nằm trong `backend/database/`. Các tệp cấu hình thực tế, dữ liệu vận hành và kết quả chạy thử được quản lý cục bộ.
