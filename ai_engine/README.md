# AI nhận diện biển số – Smart Parking

Đã triển khai OCR cục bộ bằng RapidOCR 3.10.0 + ONNX Runtime CPU. Mô hình học sẵn phát hiện vùng chữ và đọc ký tự, sau đó ghép dòng/chuẩn hóa biển số dạng thông dụng ở Việt Nam. Đây là baseline dùng OCR tổng quát, chưa phải mô hình YOLO được huấn luyện riêng trên biển số Việt Nam.

## Chạy cùng backend

```powershell
cd E:\DoAnChuyenNghanh\backend
.\venv\Scripts\python.exe -m pip install -r requirements.txt
.\venv\Scripts\python.exe -m uvicorn main:app --reload --port 8001
```

Môi trường trên máy này đã cài thư viện và chạy mô hình thành công. Model ONNX nằm trong `backend/venv/Lib/site-packages/rapidocr/models`. Cài mới có thể cần mạng để tải mô hình lần đầu; ảnh được xử lý trên máy, không gửi tới dịch vụ OCR bên ngoài.

Mở http://127.0.0.1:8001/docs, đăng nhập tài khoản ADMIN/MANAGER/SECURITY tại `/auth/login`, đưa access_token vào Authorize. Nhóm **AI License Plate** có:

| API | Chức năng |
| --- | --- |
| GET /ai/status | Engine, đã nạp hay chưa, ngưỡng và giới hạn ảnh |
| POST /ai/recognize | Đọc biển số và trả các vùng chữ/candidate; không lưu ảnh hay thay đổi DB |
| POST /ai/check-in | Nhận ảnh, đối chiếu xe đã đăng ký, lưu ảnh/độ tin cậy và tạo lượt gửi |
| POST /ai/check-out/{session_id} | Đọc ảnh ra, so khớp biển số của lượt gửi, kết thúc lượt và tính phí |
| GET /ai/images/{filename} | Xem ảnh bằng token nhân viên; ảnh không công khai |

Các POST nhận **multipart/form-data**: chọn ảnh trong trường `file`, không nhập JSON/base64. Check-in cần thêm `parking_spot_id`; `reservation_id` nếu đã đặt. Check-out nhập `session_id` trên đường dẫn.

`roi` không bắt buộc, dạng `x,y,width,height`, đơn vị pixel sau khi ảnh được xoay theo EXIF. Ví dụ `100,200,600,300`. Dùng khi biển nhỏ trong khung cảnh hoặc có nhiều xe. Tọa độ box trả về là `[x_min,y_min,x_max,y_max]` trên ảnh gốc đã xoay.

JPEG/PNG/WebP, tối đa 8 MB và 16 triệu pixel. Hệ thống kiểm tra nội dung ảnh, không tin phần mở rộng. Ảnh bằng chứng được mã hóa lại JPEG bỏ metadata, lưu tại `backend/storage/plate_images`.

## Ví dụ thử nhận diện

```powershell
cd E:\DoAnChuyenNghanh
.\backend\venv\Scripts\python.exe -m ai_engine.cli ai_engine/examples/double.png
.\backend\venv\Scripts\python.exe -m ai_engine.evaluate ai_engine/examples/manifest.json
```

Ảnh mẫu trong examples do chương trình tạo để kiểm tra kỹ thuật, không phải dữ liệu đánh giá camera thực tế. `single.png` mong đợi `30A12345`, `double.png` mong đợi `59A112345`; `blank.png` phải trả `plate: null` và `needs_review: true`.

Để thử check-in bằng `double.png`: cần đăng ký xe `59A1-12345` loại MOTORBIKE, tạo ô MOTORBIKE AVAILABLE và bảng giá hoạt động. Kết quả chuẩn hóa bỏ dấu chấm, gạch và khoảng trắng nên khớp xe đã đăng ký. API không tự tạo xe lạ. Để check-out, dùng cùng ảnh mẫu với session_id vừa tạo.

## Quy tắc xử lý

- Mặc định `AI_MIN_CONFIDENCE=0.85`, có thể cấu hình trong backend/.env, phạm vi 0.5–1.
- Confidence là điểm mô hình OCR, **không phải xác suất đảm bảo biển số đúng**.
- Chỉ một candidate hợp lệ và đủ điểm mới được dùng cho check-in/out. Nhiều candidate, không có biển hoặc điểm thấp: HTTP 422 và không thay đổi lượt gửi.
- Xe chưa đăng ký: 404. Ảnh ra không khớp biển của lượt gửi: 409. Khi không rõ, chụp lại/chọn ROI hoặc nhân viên dùng API nghiệp vụ thủ công sau khi kiểm tra.
- Không tự đổi O thành 0 hoặc B thành 8 để tránh đoán sang xe khác.
- Giới hạn mẫu biển đang hỗ trợ: hai chữ số đầu, 1–2 chữ cái, 4–6 chữ số cuối; chưa bao phủ biển ngoại giao, quân sự và mọi biển đặc biệt.
- Kết quả OCR không chứng minh xe thực có mặt: ảnh chụp lại/màn hình vẫn có thể được đọc. Bản này hỗ trợ nhân viên, chưa điều khiển barrier tự động.

## Kiểm tra và đánh giá bằng ảnh thật

```powershell
cd E:\DoAnChuyenNghanh\backend
.\venv\Scripts\python.exe -m pytest tests -q
$env:TEST_POSTGRES='1'
$env:RUN_AI_MODEL_TESTS='1'
.\venv\Scripts\python.exe -m pytest tests -q
Remove-Item Env:TEST_POSTGRES
Remove-Item Env:RUN_AI_MODEL_TESTS
```

Tests PostgreSQL tạo schema riêng, gồm kiểm tra quyền, biển sai/không rõ, ảnh hỏng, ghép hai dòng, không ghép vùng chữ xa nhau, xóa ảnh khi check-in thất bại và OCR thật → check-in → check-out.

Đánh giá ảnh camera của bạn bằng manifest JSON:

```json
[
  {"image":"camera_01.jpg","plate":"59A1-12345","roi":[100,200,600,300]},
  {"image":"empty.jpg","plate":null}
]
```

Chạy `python -m ai_engine.evaluate path/to/manifest.json --output path/to/result.json` từ thư mục dự án. `wrong_accepts` là số lần hệ thống chấp nhận một biển sai. Cần ảnh ngày/đêm, mờ, nghiêng, nhiều xe và biển thực tế để đo chất lượng trước khi triển khai camera. Chưa có tập ảnh thật của bãi nên chưa có số liệu độ chính xác thực tế.

Tài liệu upstream: https://rapidai.github.io/RapidOCRDocs/main/en/install_usage/rapidocr/usage/
Model/license attribution: https://rapidai.github.io/RapidOCRDocs/main/en/model_licenses/


## Bổ sung sau rà soát

- So sánh ngưỡng bằng điểm OCR chưa làm tròn. Ví dụ 0.84999 không được coi là đạt ngưỡng 0.85.
- Ảnh có hơn 80 vùng chữ trả needs_review=true, reason=too_many_regions; dùng ROI để tập trung vào một xe. Không tự chấp nhận khi phải bỏ bớt vùng chữ.
- Ký tự OCR ngoài chữ Latin/chữ số và dấu phân cách cho phép không bị xóa âm thầm để tạo thành một biển số hợp lệ.
- Sau khi tìm xe, biển số được kiểm tra lại trong transaction có khóa trước khi ghi lượt gửi, tránh nhận diện xong nhưng dữ liệu xe đã bị sửa.
- Không xóa ảnh đã gắn với giao dịch thành công do lỗi refresh sau commit. Khi giao dịch thất bại trước commit, ảnh mới được dọn; lỗi không tạo được thư mục lưu ảnh trả 503.
- API AI dùng cùng services/session_service.py với API check-in/check-out thủ công.

Kết quả rà soát: 44 bài qua trên PostgreSQL khi bật RUN_AI_MODEL_TESTS=1, bao gồm OCR thật và yêu cầu đồng thời. Các trường hợp hỏng database/lưu ảnh dùng lỗi mô phỏng trong môi trường test riêng. Kết quả này không thay cho đo độ chính xác trên ảnh camera của bãi.


## Phân loại xe xăng/điện và quy mô bãi

Đã cập nhật: 50 ô tô (30 xăng + 20 điện), 120 xe máy (70 xăng + 50 điện). Tổng 170 chỗ, gồm 20 trụ sạc ô tô và 50 ổ cắm xe máy đang được khai báo PLANNED. Xe/ô đỗ/bảng giá dùng vehicle_type hoặc spot_type và energy_type (GASOLINE/ELECTRIC). Xem ../docs/vehicle_energy_and_capacity.md để cấu hình READY, bảng giá riêng và API sức chứa. OCR đọc biển số rồi tra loại xe/năng lượng trong hồ sơ đăng ký. Tổng kiểm thử mới nhất: 58 bài qua PostgreSQL.
