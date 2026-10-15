# Frontend Parkly — Quản lý bãi xe

Frontend đã kết nối với backend, AI và IoT của dự án tại `E:\DoAnChuyenNghanh`. Giao diện tiếng Việt, có bố cục cho máy tính và điện thoại; không sử dụng dữ liệu giả trong ứng dụng đang chạy.

## Mở giao diện trên máy hiện tại

Đã cài thư viện và build sẵn. PostgreSQL cần hoạt động.

```powershell
& "E:\DoAnChuyenNghanh\backend\venv\Scripts\python.exe" "E:\DoAnChuyenNghanh\run_dashboard.py"
```

Sau đó mở **http://127.0.0.1:8001/dashboard/**. Một tiến trình phục vụ cả backend và frontend; không cần chạy thêm Vite. Giữ cửa sổ lệnh mở, Ctrl+C để dừng. Nếu cổng đang có ứng dụng khác, dùng `--port 8010` và mở URL tương ứng.

Đăng nhập bằng tài khoản đã có. Frontend không tự tạo hoặc đổi mật khẩu quản trị viên. Nếu chưa có ADMIN, tạo bằng:

```powershell
cd E:\DoAnChuyenNghanh\backend
.\venv\Scripts\python.exe scripts\create_admin.py
```

Tài khoản tự đăng ký từ giao diện luôn là CUSTOMER. ADMIN có thể phân quyền MANAGER/SECURITY qua màn hình Tài khoản. Không thể tự khóa hoặc hạ quyền ADMIN đang đăng nhập.

## Các màn hình

| Màn hình | Chức năng |
|---|---|
| Thông tin của tôi | Bổ sung/sửa họ tên, ngày sinh, quê quán; xem và quản lý xe thuộc tài khoản |
| Tổng quan | Chỗ có thể đặt, ô có xe, điểm sạc sẵn sàng, doanh thu đã thu, phân bổ sức chứa, lượt gửi gần đây |
| Sơ đồ bãi xe | 170 ô theo cấu hình; lọc 4 nhóm xe, trạng thái, mã ô; xem chi tiết, đặt chỗ, nhận xe và bảo trì |
| Xe vào / ra | Chọn xe đăng ký và ô phù hợp, check-in/check-out thủ công hoặc qua ảnh AI |
| Đặt chỗ | Tạo đặt chỗ theo giờ Việt Nam, xem trạng thái, hủy theo quyền, dùng đặt chỗ để check-in |
| Phương tiện | Đăng ký/chỉnh sửa xe của mình; nhân viên đăng ký xe khách vãng lai hoặc xe thuộc tài khoản khách hàng và tra cứu toàn hệ thống |
| Sạc & thiết bị IoT | Trạm sạc ô tô/ổ cắm xe máy; cấu hình vận hành, kết nối, số đo, lịch sử và bật/tắt thiết bị |
| Thanh toán | Thu tiền mặt cho lượt đã hoàn tất, lịch sử biên nhận và phí gửi xe; backend chặn thu trùng |
| Bảng giá & bãi xe | Giá riêng 4 nhóm, cấu hình sức chứa, tạo/bổ sung sơ đồ bãi, thêm bãi mới |
| Tài khoản | ADMIN xem hồ sơ, biển số/loại xe của khách, phân quyền và khóa/mở tài khoản |

Dữ liệu làm mới mỗi 15 giây khi tab đang hiển thị; có nút Làm mới. Lỗi mạng được báo rõ, giữ dữ liệu đã tải của cùng bãi; không coi đó là dữ liệu mới. Token lưu theo tab, đăng xuất hoặc token hết hạn sẽ trở về màn hình đăng nhập.

Lượt gửi, thanh toán và tài khoản có phân trang 25 dòng. Tìm biển số ở màn hình Xe vào/ra chỉ tìm trong trang hiện tại; dùng Trước/Sau để xem lịch sử. Danh sách xe và đặt chỗ phù hợp quy mô đồ án hiện tại. Lịch sử IoT trong hộp thoại hiển thị 100 sự kiện mới nhất.

Sơ đồ nhóm ô là bố cục quản lý theo loại xe, không phải bản vẽ mặt bằng tỷ lệ thực. Số liệu doanh thu là tổng tiền đã thu của bãi đang chọn, không tự gắn nhãn doanh thu hôm nay. Các số đo sạc từ simulator không dùng để tính tiền điện.

## Quyền sử dụng

- ADMIN: tất cả màn hình; cấu hình bãi/ô và phân quyền.
- MANAGER: vận hành, IoT, bảng giá và báo cáo; không chỉnh cấu hình bãi hoặc tài khoản.
- SECURITY: xe vào/ra, nhận diện AI, thu tiền, xem xe/đặt chỗ/IoT; không chỉnh giá, trạng thái sạc hoặc tài khoản.
- CUSTOMER: xe của mình, đặt/hủy chỗ của mình, lịch sử gửi và thanh toán của mình; không có công cụ vận hành.

API vẫn kiểm tra quyền trên server. Việc ẩn nút trên giao diện không thay thế phân quyền backend. Các API GET `/dashboard-data/vehicles` và `/dashboard-data/reservations` cho nhân viên tra cứu dữ liệu vận hành. POST `/dashboard-data/vehicles` cho ADMIN/MANAGER/SECURITY đăng ký xe khách hàng; các vai trò này cũng có thể đặt chỗ thay khách. Quyền sửa xe, hủy đặt chỗ vẫn theo backend.

## Thiết lập trước lần nhận xe đầu tiên

1. Đăng nhập ADMIN/MANAGER, mở Bảng giá & bãi xe và nhập giá cho từng nhóm sẽ sử dụng. Không tự đặt giá vào database thật.
2. 70 chỗ điện của bãi chính đang PLANNED. Chỉ đổi điểm sạc sang Sẵn sàng khi bạn muốn đưa vào vận hành/mô phỏng.
3. Nếu đã đăng ký IoT vào bãi chính, chạy simulator để thiết bị có số đo mới. Chỗ mất kết nối hoặc điểm sạc lỗi sẽ không nằm trong danh sách có thể đặt.
4. Nhân viên mở Phương tiện → Đăng ký xe khách hàng. Chọn khách vãng lai nếu chưa có tài khoản, hoặc nhập email tài khoản khách hàng đã đăng ký. Khách vãng lai không bị gán xe vào tài khoản nhân viên. Nút “Thêm xe của tôi” luôn tạo xe thuộc tài khoản đang đăng nhập. Khách hàng tạo tài khoản từ màn hình đăng nhập nếu cần tự quản lý xe và đặt chỗ.
5. Xe không đặt trước: nhận xe tại cổng khi ô còn trống, rồi cảm biến báo xe vào ô. Xe đặt trước: dùng thao tác Xe vào ở dòng đặt chỗ.
6. Xe ra xong mới thu tiền. Xác nhận “Đã nhận tiền” sau khi nhận tiền mặt.

## Nhận diện AI trên giao diện

Chọn ảnh JPEG/PNG/WebP không quá 8 MB. Có thể nhập vùng x,y,rộng,cao để giới hạn phần ảnh cần đọc. Bấm Nhận diện ảnh để xem kết quả trước; thao tác này chưa tạo lượt gửi. Chỉ cho xác nhận sau khi AI nhận diện được một biển số đạt ngưỡng. Nếu cần kiểm tra ảnh, chọn ảnh rõ hơn hoặc dùng luồng thủ công.

Xe vào: chọn ô đúng loại/nguồn năng lượng, nhập mã đặt chỗ nếu có. Xe ra: mở nút biểu tượng AI ở dòng lượt đang gửi. Backend nhận diện lại và đối chiếu biển số trước khi ghi nhận, lưu bằng chứng ảnh theo cơ chế hiện có.

## Phát triển frontend

```powershell
cd E:\DoAnChuyenNghanh\web_dashboard
npm install
npm run dev
```

Mở `http://127.0.0.1:5173/dashboard/`. Chạy backend riêng ở cổng 8001. Vite chuyển tiếp `/api` tới backend để tránh phải cấu hình CORS riêng. Có thể đặt biến `API_PROXY_TARGET` khi backend chạy ở cổng khác.

Build sau mỗi lần sửa:

```powershell
npm run build
```

Khởi động lại backend để nạp frontend đã build nếu trước đó chưa có thư mục dist. Không cần Node khi chỉ chạy bản đã build bằng `run_dashboard.py`.

Công nghệ: React, Vite, CSS và Lucide. Các phiên bản đã cài được khóa trong package-lock.json. Máy hiện tại dùng Node 24; yêu cầu Node khi dựng dự án tham khảo [tài liệu Vite](https://vite.dev/guide/). Quản lý vòng đời tải dữ liệu và hủy yêu cầu cũ theo [tài liệu React](https://react.dev/reference/react/useEffect).

## Kiểm tra

```powershell
cd E:\DoAnChuyenNghanh\web_dashboard
npx playwright install chromium
npm run build
..\backend\venv\Scripts\python.exe tests\run_e2e.py
```

Script tạo schema PostgreSQL tạm, server backend và frontend trên cổng trống, chạy Chromium tự động, sau đó dọn dữ liệu thử. Tài khoản trong bộ test chỉ tồn tại ở schema tạm, không tạo trong bãi chính. Không chạy `npm run test:e2e` trực tiếp trừ khi đã thiết lập môi trường kiểm thử; ưu tiên script run_e2e.py.

Đã kiểm tra: 91 ca backend/AI/IoT đạt trên PostgreSQL; 16 ca trình duyệt đạt, gồm đăng nhập, xe vào/ra/thu tiền, chống thu trùng, phân quyền, đặt/hủy chỗ, lọc sơ đồ, cấu hình sạc/bảng giá, IoT, OCR thật, lỗi mạng, token hết hạn, bố cục điện thoại và bản build được FastAPI phục vụ.

Chưa triển khai thanh toán trực tuyến, camera livestream hoặc điều khiển barrier; giao diện dùng ảnh tải lên và thanh toán tiền mặt theo backend hiện tại.


## Cập nhật đặt chỗ ngày 13/10/2026

- Trong form đặt chỗ/xe vào, nhập vào “Tìm biển số” để lọc xe đã đăng ký; biển số trùng chính xác được tự chọn, không cần đúng dấu chấm/gạch hoặc chữ hoa.
- Chọn “Nhập biển số mới”, nhập biển số và nhóm xe, rồi bấm “Lưu xe và chọn”. Khách hàng lưu xe vào tài khoản của mình; nhân viên chọn khách vãng lai hoặc email tài khoản chủ xe. Bước này chưa tạo đặt chỗ. Tiếp tục bấm “Xác nhận đặt chỗ” để giữ ô.
- Ô đã chọn trên sơ đồ được giữ lại khi xe phù hợp. Nếu đổi sang nhóm xe khác, cần chọn ô phù hợp mới.
- Form đặt chỗ chỉ nhập giờ bắt đầu (giờ Việt Nam). Hạn tự hủy nếu chưa check-in hiện ngay dưới giờ bắt đầu, tự tính sau 2 giờ kể từ giờ bắt đầu, kể cả qua ngày mới.
- Ô đang giữ chỗ trên sơ đồ hiển thị “Hủy lúc …” khi tài khoản có quyền xem đặt chỗ đó. Xe đã check-in không bị tự hết hạn theo mốc giữ chỗ.
- Quy tắc 2 giờ áp dụng cho form frontend; backend tiếp tục lưu và kiểm tra expiry_time của từng đặt chỗ.

- Ví dụ biển số đổi theo Loại xe: ô tô hiển thị VD: 30F-222.22; xe máy hiển thị VD: 29-B1 555.55. Áp dụng cả form đăng ký xe và ô nhập biển số mới khi đặt chỗ/nhận xe; đổi loại xe không xóa biển số đã nhập.
- Xe đã lưu trong hệ thống là xe đã đăng ký trước đó. Nhập biển số mới dùng để đăng ký ngay rồi chọn xe cho thao tác hiện tại. Biển số đã thuộc khách khác không được chuyển chủ khi đăng ký lại.



## Hồ sơ khách hàng

Ở màn hình đăng nhập, chọn **Đăng ký** và nhập họ tên, ngày tháng năm sinh, quê quán, email, mật khẩu, biển số xe, loại xe (ô tô/xe máy), nguồn năng lượng (xăng/điện). Ví dụ biển số tự đổi theo loại xe. Hệ thống lưu tài khoản và xe cùng một lần; biển số trùng sẽ báo lỗi và không để lại tài khoản tạo dở.

Tài khoản đã có mở **Thông tin của tôi** để bổ sung hồ sơ. Bên dưới hiển thị xe đã đăng ký, nút thêm và chỉnh sửa xe. Ngày sinh không được nằm trong tương lai. ADMIN có thể xem hồ sơ cùng các xe của khách ở **Tài khoản**. Khách chỉ được sửa hồ sơ và xe của mình.

Máy hiện tại đã bổ sung cột ngày sinh và quê quán, giữ nguyên các tài khoản đang có. Khi cập nhật một database cũ trên máy khác, chạy trước khi khởi động backend:

```powershell
cd E:\DoAnChuyenNghanh\backend
.\venv\Scripts\python.exe scripts\migrate_customer_profile.py
```

Máy mới dùng `database/schema.sql` đã có hai cột này. Migration có thể chạy lại. API `POST /auth/register` nhận thêm `date_of_birth`, `hometown` và đối tượng `vehicle`; `PATCH /auth/me` cập nhật họ tên/ngày sinh/quê quán của người đang đăng nhập. Các trường mới trong API đăng ký vẫn tùy chọn để tương thích ứng dụng cũ; form đăng ký mới yêu cầu nhập đầy đủ.
