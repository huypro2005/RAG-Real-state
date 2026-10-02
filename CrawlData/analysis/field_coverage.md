# Field coverage report

Phạm vi: 17 HTML mẫu trong `data/`. Coverage tính trên mọi nguồn; cột structured tách riêng dữ liệu có nhãn HTML.

| Field | Found | Coverage | Class | Structured | Description fallback |
|---|---:|---:|---|---:|---:|
| `province_city` | 17/17 | 100.00% | ALWAYS_PRESENT | 17/17 | 0/17 |
| `old_district` | 17/17 | 100.00% | ALWAYS_PRESENT | 17/17 | 0/17 |
| `old_ward` | 17/17 | 100.00% | ALWAYS_PRESENT | 17/17 | 0/17 |
| `new_district` | 0/17 | 0.00% | NEVER_FOUND | 0/17 | 0/17 |
| `new_ward` | 17/17 | 100.00% | ALWAYS_PRESENT | 17/17 | 0/17 |
| `old_address` | 17/17 | 100.00% | ALWAYS_PRESENT | 17/17 | 0/17 |
| `new_address` | 17/17 | 100.00% | ALWAYS_PRESENT | 17/17 | 0/17 |
| `latitude` | 17/17 | 100.00% | ALWAYS_PRESENT | 0/17 | 0/17 |
| `longitude` | 17/17 | 100.00% | ALWAYS_PRESENT | 0/17 | 0/17 |
| `property_type` | 17/17 | 100.00% | ALWAYS_PRESENT | 17/17 | 0/17 |
| `area` | 17/17 | 100.00% | ALWAYS_PRESENT | 17/17 | 0/17 |
| `frontage` | 6/17 | 35.29% | OPTIONAL | 5/17 | 1/17 |
| `bedrooms` | 15/17 | 88.24% | MOSTLY_PRESENT | 15/17 | 0/17 |
| `bathrooms` | 15/17 | 88.24% | MOSTLY_PRESENT | 15/17 | 0/17 |
| `road_width` | 9/17 | 52.94% | OPTIONAL | 6/17 | 3/17 |
| `legal` | 16/17 | 94.12% | MOSTLY_PRESENT | 15/17 | 1/17 |
| `interior` | 10/17 | 58.82% | OPTIONAL | 9/17 | 1/17 |
| `floors` | 12/17 | 70.59% | OPTIONAL | 10/17 | 2/17 |
| `price` | 17/17 | 100.00% | ALWAYS_PRESENT | 17/17 | 0/17 |
| `price_per_m2` | 14/17 | 82.35% | MOSTLY_PRESENT | 14/17 | 0/17 |
| `posting_date` | 17/17 | 100.00% | ALWAYS_PRESENT | 17/17 | 0/17 |
| `expiration_date` | 17/17 | 100.00% | ALWAYS_PRESENT | 17/17 | 0/17 |
| `listing_id` | 17/17 | 100.00% | ALWAYS_PRESENT | 17/17 | 0/17 |
| `listing_url` | 17/17 | 100.00% | ALWAYS_PRESENT | 0/17 | 0/17 |
| `title` | 17/17 | 100.00% | ALWAYS_PRESENT | 17/17 | 0/17 |
| `description` | 17/17 | 100.00% | ALWAYS_PRESENT | 17/17 | 0/17 |

## Bảng đề xuất

| Field | Coverage | Structured source available? | Description fallback? | Recommended primary selector | Alternative selector | Notes |
|---|---:|---|---|---|---|---|
| `province_city` | 100.00% | Có | Không quan sát thấy/không áp dụng | `.re__address-line-1` | `—` | Raw value; không normalize. |
| `old_district` | 100.00% | Có | Không quan sát thấy/không áp dụng | `.re__address-line-1` | `—` | Raw value; không normalize. |
| `old_ward` | 100.00% | Có | Không quan sát thấy/không áp dụng | `.re__address-line-1` | `—` | Raw value; không normalize. |
| `new_district` | 0.00% | Không | Không quan sát thấy/không áp dụng | `—` | `—` | Không tìm thấy trong tập mẫu. |
| `new_ward` | 100.00% | Có | Không quan sát thấy/không áp dụng | `.re__address-line-2` | `—` | Raw value; không normalize. |
| `old_address` | 100.00% | Có | Không quan sát thấy/không áp dụng | `.re__address-line-1` | `—` | Raw value; không normalize. |
| `new_address` | 100.00% | Có | Không quan sát thấy/không áp dụng | `.re__address-line-2` | `—` | Raw value; không normalize. |
| `latitude` | 100.00% | Không | Không quan sát thấy/không áp dụng | `product map initialization: latitude` | `—` | Raw value; không normalize. |
| `longitude` | 100.00% | Không | Không quan sát thấy/không áp dụng | `product map initialization: longitude` | `—` | Raw value; không normalize. |
| `property_type` | 100.00% | Có | Không quan sát thấy/không áp dụng | `.re__breadcrumb a[level="1"]` | `—` | Raw value; không normalize. |
| `area` | 100.00% | Có | Không quan sát thấy/không áp dụng | `.re__pr-specs-content-item (title="Diện tích")` | `—` | Raw value; không normalize. |
| `frontage` | 35.29% | Có | Có | `.re__pr-specs-content-item (title="Mặt tiền")` | `.re__detail-content.js__pr-description` | Raw value; không normalize. |
| `bedrooms` | 88.24% | Có | Không quan sát thấy/không áp dụng | `.re__pr-specs-content-item (title="Số phòng ngủ")` | `—` | Raw value; không normalize. |
| `bathrooms` | 88.24% | Có | Không quan sát thấy/không áp dụng | `.re__pr-specs-content-item (title="Số phòng tắm, vệ sinh")` | `—` | Raw value; không normalize. |
| `road_width` | 52.94% | Có | Có | `.re__pr-specs-content-item (title="Đường vào")` | `.re__detail-content.js__pr-description` | Raw value; không normalize. |
| `legal` | 94.12% | Có | Có | `.re__pr-specs-content-item (title="Pháp lý")` | `.re__detail-content.js__pr-description` | Raw value; không normalize. |
| `interior` | 58.82% | Có | Có | `.re__pr-specs-content-item (title="Nội thất")` | `.re__detail-content.js__pr-description` | Raw value; không normalize. |
| `floors` | 70.59% | Có | Có | `.re__pr-specs-content-item (title="Số tầng")` | `.re__detail-content.js__pr-description` | Raw value; không normalize. |
| `price` | 100.00% | Có | Không quan sát thấy/không áp dụng | `.re__pr-specs-content-item (title="Khoảng giá")` | `—` | Raw value; không normalize. |
| `price_per_m2` | 82.35% | Có | Không quan sát thấy/không áp dụng | `.re__pr-short-info-item .ext` | `—` | Raw value; không normalize. |
| `posting_date` | 100.00% | Có | Không quan sát thấy/không áp dụng | `.js__pr-config-item (title=Ngày đăng)` | `—` | Raw value; không normalize. |
| `expiration_date` | 100.00% | Có | Không quan sát thấy/không áp dụng | `.js__pr-config-item (title=Ngày hết hạn)` | `—` | Raw value; không normalize. |
| `listing_id` | 100.00% | Có | Không quan sát thấy/không áp dụng | `.js__pr-config-item (title=Mã tin)` | `—` | Raw value; không normalize. |
| `listing_url` | 100.00% | Không | Không quan sát thấy/không áp dụng | `link[rel="canonical"]` | `—` | Raw value; không normalize. |
| `title` | 100.00% | Có | Không quan sát thấy/không áp dụng | `h1.js__pr-title` | `—` | Raw value; không normalize. |
| `description` | 100.00% | Có | Không quan sát thấy/không áp dụng | `.re__detail-content.js__pr-description` | `—` | Raw value; không normalize. |

## Kết luận

1. Deterministic trên tập mẫu: title, description, canonical URL, mã tin, ngày đăng, loại BĐS, giá, diện tích, địa chỉ cũ/mới và tọa độ.
2. Các thuộc tính vật lý tùy chọn cần specs-first; description chỉ là fallback có confidence thấp hơn và có thể chứa nhiều căn/giá trị.
3. Không có field khảo sát nào chỉ tồn tại trong description ở toàn bộ tập; một số giá trị bị thiếu structured nhưng xuất hiện rõ trong prose.
4. Không nên kỳ vọng frontage, road width, floors, interior, bedrooms/bathrooms và legal luôn có.
5. Layout selector chính không đổi theo loại BĐS; tập field thay đổi rõ theo loại.
6. Website hiển thị old/new address ở hai span riêng; new address chỉ là ward/xã + thành phố mới, không phải full address.
7. Rủi ro: flag script mang ngữ nghĩa location của truy vấn gợi ý, description đa thực thể, raw typo/đơn vị bất thường, và selector gắn với layout có thể đổi ngoài snapshot.
