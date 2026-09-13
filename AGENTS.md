# Context: Phân tích cấu trúc dữ liệu bài đăng bất động sản

## 1. Bối cảnh

Tôi đang xây dựng dataset bất động sản từ các bài đăng trên Batdongsan.com.vn.

Dự án cũ chỉ phục vụ bài toán **dự đoán giá**, nên parser cũ đã:

* Parse HTML.
* Chuẩn hóa dữ liệu ngay khi crawl.
* Encode quận và loại bất động sản thành số.
* Convert giá, diện tích, tọa độ...
* Chỉ giữ những field cần cho model dự đoán.

Ví dụ parser cũ thu thập:

* loại nhà đất
* địa chỉ
* giá
* diện tích
* giá/m²
* mặt tiền
* phòng ngủ
* pháp lý
* tọa độ
* số tầng

Dự án mới có scope lớn hơn.

Dataset raw sau này sẽ được dùng độc lập bởi hai pipeline:

```text
Raw dataset
    ├── Price Prediction pipeline
    └── RAG Recommendation pipeline
```

Vì vậy ở bước thu thập dữ liệu **không được tối ưu dữ liệu riêng cho prediction hoặc RAG**.

Mục tiêu của crawler/extractor là giữ lại tối đa dữ liệu gốc có trong bài đăng.

---

# 2. Mục tiêu hiện tại

HIỆN TẠI CHƯA VIẾT PARSER PRODUCTION.

Nhiệm vụ trước tiên là:

> Phân tích toàn bộ các file HTML mẫu để hiểu cấu trúc dữ liệu của Batdongsan.com.vn.

Cần xác định:

1. Field nào tồn tại trong từng HTML.
2. Field nào xuất hiện ổn định ở tất cả hoặc gần tất cả bài đăng.
3. Field nào chỉ xuất hiện ở một số loại bất động sản.
4. Field nào không có structured HTML nhưng có thể xuất hiện trong phần mô tả.
5. Field nào hoàn toàn không có.
6. Selector / HTML structure của từng field.
7. Một field có thể xuất hiện ở bao nhiêu vị trí khác nhau.
8. Structure có khác nhau giữa các loại bất động sản hay không.
9. Địa chỉ cũ và địa chỉ sau sáp nhập được website lưu như thế nào.
10. Có metadata / JSON / script nào chứa dữ liệu tốt hơn phần HTML hiển thị hay không.

---

# 3. Các field cần khảo sát

Phân tích sự tồn tại của các field sau:

## Location

* tỉnh / thành phố
* quận / huyện cũ
* phường / xã cũ nếu có
* quận / huyện mới nếu có
* phường / xã mới nếu có
* địa chỉ chi tiết cũ
* địa chỉ chi tiết mới
* tọa độ latitude
* tọa độ longitude

Đặc biệt phải kiểm tra kỹ:

```text
old_address
new_address
```

Không được tự suy luận địa chỉ mới từ địa chỉ cũ.

Chỉ đánh dấu `new_address` tồn tại nếu HTML thực sự cung cấp dữ liệu đó.

---

## Property information

* loại nhà đất
* diện tích
* mặt tiền
* phòng ngủ
* số phòng vệ sinh
* đường vào
* pháp lý
* nội thất
* số tầng

---

## Price

* giá
* giá/m²

---

## Listing information

* ngày đăng
* ngày hết hạn
* mã tin
* link bài đăng
* tiêu đề
* mô tả

---

# 4. Nguyên tắc phân tích

## Không normalize dữ liệu

Ví dụ nếu HTML chứa:

```text
8,6 tỷ
```

hãy ghi nhận raw value:

```text
8,6 tỷ
```

KHÔNG convert thành:

```text
8600
```

Tương tự:

```text
Quận 2
```

không được convert thành class `13`.

---

## Không suy đoán dữ liệu

Nếu HTML không có:

```text
Mặt tiền
```

thì:

```text
present = false
```

Không được đoán từ loại nhà hoặc dữ liệu khác.

---

## Phân biệt structured data và description

Ví dụ:

```text
Số phòng ngủ: 2 phòng
```

nằm trong section "Đặc điểm bất động sản"

khác với:

```text
Nhà gồm 2PN...
```

nằm trong description.

Phải ghi lại nguồn:

```text
structured
description
metadata
json_script
url
other
```

---

# 5. Với mỗi HTML cần tạo kết quả phân tích

Ví dụ:

```json
{
  "file": "001.html",

  "fields": {
    "price": {
      "present": true,
      "raw_value": "8,6 tỷ",
      "source": "structured",
      "selector": ".re__pr-short-info-item",
      "confidence": "high"
    },

    "frontage": {
      "present": false
    },

    "old_address": {
      "present": true,
      "raw_value": "The Privé, Đường Song Hành, Phường An Phú, Quận 2, Hồ Chí Minh",
      "source": "structured"
    },

    "new_address": {
      "present": true,
      "raw_value": "Phường Bình Trưng, Hồ Chí Minh mới",
      "source": "structured",
      "complete": false
    }
  }
}
```

---

# 6. Sau khi phân tích toàn bộ HTML

Tạo một `field_coverage_report`.

Ví dụ:

```text
Field                 Found       Coverage
------------------------------------------------
title                 100/100     100%
price                 98/100       98%
area                  97/100       97%
bedrooms              65/100       65%
frontage              32/100       32%
road_width            28/100       28%
old_address           100/100     100%
new_address            74/100      74%
floors                 41/100      41%
```

Phân loại:

```text
ALWAYS_PRESENT
MOSTLY_PRESENT
OPTIONAL
RARE
NEVER_FOUND
```

---

# 7. Phân tích selector

Với mỗi field phải thống kê:

```text
field
possible selectors
number of files using selector
fallback source
```

Ví dụ:

```text
price
├── .re__pr-short-info-item
│      95/100 files
│
└── .re__pr-specs-content-item
       100/100 files
```

Nếu cùng một dữ liệu tồn tại nhiều chỗ, phải chỉ ra nguồn nào:

* ổn định nhất
* rõ nghĩa nhất
* ít phụ thuộc layout nhất

Nhưng CHƯA viết extractor production.

---

# 8. Phân tích theo loại bất động sản

Kiểm tra xem structure có khác nhau giữa:

```text
căn hộ
nhà riêng
biệt thự/liền kề
nhà mặt phố
đất
đất nền dự án
shophouse
...
```

Ví dụ có thể:

```text
Căn hộ:
- bedrooms
- bathrooms
- interior

Đất:
- frontage
- road_width
- legal

Nhà riêng:
- floors
- bedrooms
- frontage
```

Không coi một field là lỗi chỉ vì nó không phù hợp với một loại bất động sản.

---

# 9. Phân tích địa chỉ cũ / mới

Đây là phần quan trọng.

Cần xác định:

### Old address

HTML có thể chứa:

```text
Đường
Phường cũ
Quận cũ
Tỉnh/TP
```

### New address

Kiểm tra:

```text
new ward
new district
new province/city
full new address
```

Và trả lời:

1. Có bao nhiêu bài có địa chỉ mới?
2. Địa chỉ mới có đầy đủ hay chỉ có phường/tỉnh?
3. Có class/selector riêng cho địa chỉ mới không?
4. Có flag như `isNewLocation`, `isDisplayNewAddress` hay metadata tương tự không?
5. Có location ID cũ và mới trong JavaScript/JSON không?
6. Website lưu old/new address ở HTML visible hay trong script?
7. Có thể xác định old/new address một cách deterministic hay không?

---

# 10. Tìm dữ liệu ẩn trong HTML

Không chỉ phân tích text đang hiển thị.

Phải kiểm tra:

```text
<script>
JSON
JSON-LD
data-* attributes
hidden inputs
JavaScript objects
tracking metadata
Google Maps iframe
canonical URL
breadcrumbs
meta tags
```

Ví dụ những thứ như:

```text
productId
cityCode
districtId
wardId
streetId
latitude
longitude
```

cũng phải được ghi nhận nếu tồn tại.

---

# 11. Không làm trong bước này

KHÔNG:

* thiết kế model prediction
* tạo embedding
* xây RAG
* normalize price
* encode category
* map district thành integer
* clean description
* train model
* thiết kế recommendation
* viết parser production
* thay đổi code crawler hiện tại

Mục tiêu duy nhất:

> Reverse-engineer cấu trúc dữ liệu của tập HTML.

---

# 12. Output cuối cùng cần có

Sau khi phân tích tất cả HTML, tạo:

```text
analysis/
├── field_coverage.json
├── field_coverage.md
├── selector_report.md
├── address_analysis.md
├── property_type_analysis.md
└── sample_extractions/
    ├── 001.json
    ├── 002.json
    └── ...
```

Trong `field_coverage.md`, cuối cùng đưa ra bảng đề xuất:

```text
Field
Coverage
Structured source available?
Description fallback?
Recommended primary selector
Alternative selector
Notes
```

Cuối report đưa ra kết luận:

1. Những field nào có thể extract deterministic.
2. Những field nào cần fallback.
3. Những field nào chỉ tồn tại trong description.
4. Những field nào không nên kỳ vọng luôn có.
5. Structure nào thay đổi theo property type.
6. Cách website biểu diễn địa chỉ cũ và mới.
7. Các rủi ro cần biết trước khi bắt đầu viết extractor.
