# Selector report

Thống kê trên 17 file. Đếm file có field được lấy từ selector tương ứng.

## `province_city`

| Selector / structure | Files | Source |
|---|---:|---|
| `.re__address-line-1` | 17/17 | structured: 17 |

## `old_district`

| Selector / structure | Files | Source |
|---|---:|---|
| `.re__address-line-1` | 17/17 | structured: 17 |

## `old_ward`

| Selector / structure | Files | Source |
|---|---:|---|
| `.re__address-line-1` | 17/17 | structured: 17 |

## `new_district`

| Selector / structure | Files | Source |
|---|---:|---|
| — | 0/17 | never found |

## `new_ward`

| Selector / structure | Files | Source |
|---|---:|---|
| `.re__address-line-2` | 17/17 | structured: 17 |

## `old_address`

| Selector / structure | Files | Source |
|---|---:|---|
| `.re__address-line-1` | 17/17 | structured: 17 |

## `new_address`

| Selector / structure | Files | Source |
|---|---:|---|
| `.re__address-line-2` | 17/17 | structured: 17 |

## `latitude`

| Selector / structure | Files | Source |
|---|---:|---|
| `product map initialization: latitude` | 17/17 | json_script: 17 |

## `longitude`

| Selector / structure | Files | Source |
|---|---:|---|
| `product map initialization: longitude` | 17/17 | json_script: 17 |

## `property_type`

| Selector / structure | Files | Source |
|---|---:|---|
| `.re__breadcrumb a[level="1"]` | 17/17 | structured: 17 |

## `area`

| Selector / structure | Files | Source |
|---|---:|---|
| `.re__pr-specs-content-item (title="Diện tích")` | 17/17 | structured: 17 |

## `frontage`

| Selector / structure | Files | Source |
|---|---:|---|
| `.re__pr-specs-content-item (title="Mặt tiền")` | 5/17 | structured: 5, description: 1 |
| `.re__detail-content.js__pr-description` | 1/17 | structured: 5, description: 1 |

Fallback: description chỉ dùng khi có biểu thức tường minh; không suy luận.

## `bedrooms`

| Selector / structure | Files | Source |
|---|---:|---|
| `.re__pr-specs-content-item (title="Số phòng ngủ")` | 15/17 | structured: 15 |

## `bathrooms`

| Selector / structure | Files | Source |
|---|---:|---|
| `.re__pr-specs-content-item (title="Số phòng tắm, vệ sinh")` | 15/17 | structured: 15 |

## `road_width`

| Selector / structure | Files | Source |
|---|---:|---|
| `.re__pr-specs-content-item (title="Đường vào")` | 6/17 | description: 3, structured: 6 |
| `.re__detail-content.js__pr-description` | 3/17 | description: 3, structured: 6 |

Fallback: description chỉ dùng khi có biểu thức tường minh; không suy luận.

## `legal`

| Selector / structure | Files | Source |
|---|---:|---|
| `.re__pr-specs-content-item (title="Pháp lý")` | 15/17 | structured: 15, description: 1 |
| `.re__detail-content.js__pr-description` | 1/17 | structured: 15, description: 1 |

Fallback: description chỉ dùng khi có biểu thức tường minh; không suy luận.

## `interior`

| Selector / structure | Files | Source |
|---|---:|---|
| `.re__pr-specs-content-item (title="Nội thất")` | 9/17 | structured: 9, description: 1 |
| `.re__detail-content.js__pr-description` | 1/17 | structured: 9, description: 1 |

Fallback: description chỉ dùng khi có biểu thức tường minh; không suy luận.

## `floors`

| Selector / structure | Files | Source |
|---|---:|---|
| `.re__pr-specs-content-item (title="Số tầng")` | 10/17 | structured: 10, description: 2 |
| `.re__detail-content.js__pr-description` | 2/17 | structured: 10, description: 2 |

Fallback: description chỉ dùng khi có biểu thức tường minh; không suy luận.

## `price`

| Selector / structure | Files | Source |
|---|---:|---|
| `.re__pr-specs-content-item (title="Khoảng giá")` | 17/17 | structured: 17 |

## `price_per_m2`

| Selector / structure | Files | Source |
|---|---:|---|
| `.re__pr-short-info-item .ext` | 14/17 | structured: 14 |

## `posting_date`

| Selector / structure | Files | Source |
|---|---:|---|
| `.js__pr-config-item (title=Ngày đăng)` | 17/17 | structured: 17 |

## `expiration_date`

| Selector / structure | Files | Source |
|---|---:|---|
| `.js__pr-config-item (title=Ngày hết hạn)` | 17/17 | structured: 17 |

## `listing_id`

| Selector / structure | Files | Source |
|---|---:|---|
| `.js__pr-config-item (title=Mã tin)` | 17/17 | structured: 17 |

## `listing_url`

| Selector / structure | Files | Source |
|---|---:|---|
| `link[rel="canonical"]` | 17/17 | metadata: 17 |

## `title`

| Selector / structure | Files | Source |
|---|---:|---|
| `h1.js__pr-title` | 17/17 | structured: 17 |

## `description`

| Selector / structure | Files | Source |
|---|---:|---|
| `.re__detail-content.js__pr-description` | 17/17 | structured: 17 |

## Đánh giá nguồn trùng lặp

- Specs title/value là nguồn rõ nghĩa nhất cho giá, diện tích và thuộc tính; short-info dễ đọc nhưng ít field hơn.
- Canonical ổn định hơn URL suy ra từ breadcrumb/slug; `productId` có thêm trong tracking JSON và thuộc tính `prid`.
- Tọa độ có trong object khởi tạo bản đồ JavaScript và URL `iframe[data-src*='google.com/maps/embed']`; không thấy trong JSON-LD.
- JSON-LD trong cả 17 mẫu là `BreadcrumbList`, hữu ích cho taxonomy nhưng không thay thế specs.

## Dữ liệu ẩn/metadata đã rà soát

| Cấu trúc | Files | Nội dung hữu ích |
|---|---:|---|
| `script[type='application/ld+json']` | 17/17 | Breadcrumb taxonomy |
| `link[rel='canonical']` | 17/17 | Listing URL |
| `meta[name='description']`, OpenGraph | 17/17 | Title/description/image/URL bản rút gọn |
| Tracking JSON (`JSON.parse`) | 17/17 | productId, projectId, cateId, city/district/ward/street IDs, productType |
| Map initialization JS | 17/17 | latitude/longitude và old location IDs |
| Google Maps iframe | 17/17 | tọa độ lặp trong query URL |
| `data-*` attributes | 17/17 | media, save-listing JSON, tracking; nguồn phụ, layout-dependent |
| hidden inputs | 17/17 | UI/config phụ; không quan sát thấy field khảo sát tốt hơn nguồn chính |
