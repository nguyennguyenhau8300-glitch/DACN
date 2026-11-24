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

## Dữ liệu AI

### Ảnh thật từ Kaggle

Mở **Vietnamese License Plate Detection**, phiên bản **1** của Mia Huynh, rồi chọn **Download** để lấy tệp ZIP. Tạo thư mục `du_lieu_ai` ở gốc repo và lưu tệp với tên `vietnamese-license-plate-detection.zip`. [Nguồn dữ liệu trên Kaggle](https://www.kaggle.com/datasets/miahuynh04/vietnamese-license-plate-detection/versions/1)

SHA-256 của tệp ZIP dùng trong đồ án là `10554393d6daf331525b627926426417d33867d59a3dcc11c181008acfa7f66f`. ZIP chứa ảnh gốc cùng nhãn khung biển số định dạng YOLO. Parkly huấn luyện YOLOv8 để tìm khung biển số và dùng RapidOCR có sẵn để đọc ký tự.

| Tập ảnh thật | Train | Validation | Test |
| --- | ---: | ---: | ---: |
| V1 | 960 | 229 | 229 |
| V2 dùng trong ứng dụng | 3.058 | 229 | 229 |
| Thử nghiệm chia theo nhóm | 2.318 | 275 | 333 |

Danh sách ghi thư mục gốc trong ZIP (`source_split`) và phân hoạch đã dùng của từng ảnh. Ô trống nghĩa là ảnh được bỏ qua ở lần thử tương ứng. V1 và V2 dùng chung validation và test. Hai lần thử này lọc trùng hoặc gần trùng theo ảnh, nên cùng một biển số vẫn có thể xuất hiện ở nhiều tập. Thử nghiệm chia theo nhóm giữ các ảnh thuộc cùng nhóm biển số ước lượng bằng OCR trong một tập. Kết quả phản ánh tập ảnh nguồn Kaggle. [Danh sách phân hoạch](DACN/backend/ai_engine/dataset-splits.csv)

Từ gốc repo, chạy PowerShell để dựng lại ảnh, nhãn và `data.yaml` của V2. Đổi `$parklyExperiment` thành `'v1'` hoặc `'grouped'` để dựng hai tập còn lại.

```powershell
$parklyExperiment = 'v2'
$parklyRaw = '.\du_lieu_ai\kaggle-v1'
$parklySource = Join-Path $parklyRaw 'License Plate Detection Dataset'
$parklyOutput = ".\du_lieu_ai\anh-that-$parklyExperiment"

if (!(Test-Path -LiteralPath $parklySource)) {
    Expand-Archive -LiteralPath '.\du_lieu_ai\vietnamese-license-plate-detection.zip' -DestinationPath $parklyRaw -ErrorAction Stop
}

foreach ($parklySplit in 'train', 'val', 'test') {
    New-Item -ItemType Directory -Force -Path "$parklyOutput\images\$parklySplit", "$parklyOutput\labels\$parklySplit" | Out-Null
}

$parklyColumn = "split_$parklyExperiment"
Import-Csv -LiteralPath '.\DACN\backend\ai_engine\dataset-splits.csv' | ForEach-Object {
    $parklySplit = $_.$parklyColumn
    if ($parklySplit) {
        $parklyImage = $_.filename
        $parklyOrigin = $_.source_split
        $parklyLabel = [IO.Path]::ChangeExtension($parklyImage, '.txt')
        Copy-Item -LiteralPath (Join-Path $parklySource "images\$parklyOrigin\$parklyImage") -Destination "$parklyOutput\images\$parklySplit" -ErrorAction Stop
        Copy-Item -LiteralPath (Join-Path $parklySource "labels\$parklyOrigin\$parklyLabel") -Destination "$parklyOutput\labels\$parklySplit" -ErrorAction Stop
    }
}

$parklyDatasetPath = (Resolve-Path -LiteralPath $parklyOutput).Path.Replace('\', '/')
@"
path: "$parklyDatasetPath"
train: images/train
val: images/val
test: images/test
names:
  0: license_plate
"@ | Set-Content -LiteralPath "$parklyOutput\data.yaml" -Encoding utf8
```

### Ảnh tổng hợp

Sau khi cài các thư viện AI như phần chạy lần đầu, dùng PowerShell từ gốc repo trên Windows có font Arial Bold. Bộ sinh tạo **176 ảnh** gồm 128 train, 24 validation và 24 test, kèm nhãn và danh sách ảnh.

```powershell
Push-Location .\DACN\backend
.\venv\Scripts\python.exe -m ai_engine.synthetic_dataset --output ..\..\du_lieu_ai\synthetic
Pop-Location
```

Để thử nhận diện ngay, mở **Xe vào / ra → Nhận diện AI** và chọn ảnh mẫu. Ứng dụng dùng trọng số có sẵn trong repo. [Ảnh demo](DACN/backend/test_data/)
