# Quy ước dữ liệu và chất lượng

## Mục đích

Dữ liệu tin đăng được dùng cho cả prediction và RAG. Các pipeline sau crawl tự quyết điều kiện sử dụng; crawler không loại tin chỉ vì một thuộc tính tùy chọn không tồn tại.

## Field chính

Nhóm vị trí gồm địa chỉ cũ/mới, phường/xã, quận/huyện, tỉnh/thành và `latitude`/`longitude`. Nhóm bất động sản gồm loại nhà đất, diện tích, mặt tiền, số phòng ngủ, số phòng vệ sinh, đường vào, pháp lý, nội thất và số tầng. Nhóm tin đăng gồm giá, giá/m², mã tin, URL, tiêu đề, mô tả, ngày đăng và ngày hết hạn.

Tên field hiện có trong crawler được khai báo tại `CrawlData/listing_extractor.py`.

## Giá trị thiếu

- Dùng `null` khi một field không xuất hiện hoặc không trích xuất được từ HTML.
- `legal: null` là hợp lệ và không làm bản ghi bị loại.
- Giá trị pháp lý có cụm “Hợp đồng mua bán” là dữ liệu hợp lệ, phải giữ nguyên.
- Không tự điền địa chỉ mới, tọa độ hoặc bất kỳ field nào từ suy đoán.

## Quy tắc chấp nhận hiện tại của crawler

Một record được lưu khi có cả `price` và `area` ở dạng số sau bước trích xuất. Record bị ghi vào file lỗi khi một trong hai field là `null`.

Do đó các giá như “Thỏa thuận” hiện không tạo được `price` số và bị xếp vào nhóm thiếu giá. Các pipeline tương lai nên lưu kèm raw snapshot để có thể phân biệt rõ “không hiển thị giá”, “thỏa thuận” và lỗi render.

## Tách dữ liệu raw và dữ liệu dùng cho pipeline

```text
Raw snapshot
    ├── kiểm tra selector / truy vết lỗi
    ├── chuẩn hóa và kiểm tra chất lượng
    ├── prediction dataset (cần giá + diện tích)
    └── RAG corpus (giữ nhiều field mô tả nhất có thể)
```

Các file dữ liệu crawl lớn và biến động (`data.json`, `data_errors.json`, `linkNhaDat.txt`) không được commit vào Git. Báo cáo selector và mẫu phân tích có chủ đích được giữ trong `analysis/`.
