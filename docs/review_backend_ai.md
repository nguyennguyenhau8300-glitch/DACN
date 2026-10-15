# Báo cáo kiểm tra backend và AI

Đã rà soát mã nguồn tại E:\DoAnChuyenNghanh, hai hướng dẫn và cấu trúc database. Bản sao mã nguồn trước sửa lưu trong thư mục work của phiên làm việc, không chứa .env.

## Lỗi tái hiện và đã sửa

1. Tạo xe trùng biển số khi thay đổi dấu cách/chấm/gạch: chuẩn hóa kiểm tra và unique index.
2. Đặt chỗ ở bãi không hoạt động: chặn trước khi tạo reservation.
3. Một xe giữ nhiều ô hoặc check-in ô khác để bỏ qua đặt chỗ: chặn và bổ sung ràng buộc database.
4. Giá trị null/trống lọt qua các API cập nhật: trả 422 ở tầng kiểm tra dữ liệu.
5. Hủy/hết hạn đặt chỗ làm ô trống dù có bản tin cảm biến OCCUPIED mới: giữ trạng thái vật lý phù hợp; bỏ qua bản tin cũ trước lúc đặt.
6. Điểm OCR 0.84999 bị làm tròn thành 0.85 rồi chấp nhận: so sánh giá trị gốc.
7. Hơn 80 vùng chữ bị cắt bỏ làm mất biển số thứ hai: trả yêu cầu xem lại thay vì chấp nhận.
8. Sửa xe/ô đỗ trong lúc check-in: khóa hàng và kiểm thử bằng transaction đồng thời.
9. ADMIN đặt hộ nhưng chủ xe không thấy đặt chỗ: gán đúng chủ xe.
10. Đổi biển số/loại xe sau khi có lịch sử: chặn để bảo toàn danh tính của lượt gửi.
11. Phí vượt giới hạn lưu trữ: trả lỗi nghiệp vụ, không kết thúc lượt gửi.
12. Lỗi tạo thư mục ảnh/lỗi database: trả 503 và dọn ảnh chưa gắn vào giao dịch thành công.

## Kiểm chứng

- 44/44 bài kiểm tra qua trên PostgreSQL với DDL schema.sql, gồm 5 bài concurrent và OCR thật → check-in → check-out.
- 38 bài qua trên SQLite; 6 bài dành cho PostgreSQL/OCR thật được bỏ qua theo cấu hình.
- Bộ regression ban đầu tái hiện 11 trường hợp lỗi trước khi sửa; hiện đều qua.
- Kiểm tra phụ thuộc: pip check báo không có phụ thuộc hỏng.
- Đã kiểm tra không có nhóm biển số chuẩn hóa trùng hoặc nhiều đặt chỗ hoạt động cho cùng xe trước khi áp dụng hai index bổ sung trên database thật.
- Các tests PostgreSQL dùng schema test riêng và dọn sau khi chạy; không tạo lượt gửi/thanh toán thử trong bảng nghiệp vụ thật.

## Phạm vi còn lại

OCR mới kiểm chứng bằng ảnh mẫu tạo sẵn; cần ảnh camera thật để đo độ chính xác theo ngày/đêm, góc nghiêng và độ mờ. Thanh toán online cần thông tin merchant/callback từ nhà cung cấp. Phần AI hiện hỗ trợ nhân viên, chưa điều khiển barrier tự động.

Hai hướng dẫn đã được cập nhật đồng bộ với mã nguồn. Khởi động lại backend để nạp phiên bản mới.
