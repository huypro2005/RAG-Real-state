# Database `housing` — giải thích bảng và cột

Mô tả đúng hiện trạng database (khớp với `backup/data_ultilities.sql`), để làm đầu vào cho việc
thiết kế lại. Sơ đồ quan hệ và luồng dữ liệu: [housing-database.drawio](housing-database.drawio).

Các bảng được chia thành 4 cụm theo mục đích sử dụng:

| Cụm | Bảng | Làm việc gì |
|---|---|---|
| 1. Dữ liệu nền | `admin.unit`, `admin.ward_transition`, `amenities.poi_schools`, `amenities.poi_hospitals`, `amenities.poi_markets` | Danh mục đơn vị hành chính cũ/mới và danh sách tiện ích có tọa độ. Nạp một lần, không phụ thuộc tin đăng. |
| 2. Tin bất động sản (dùng chung) | `listing.listings`, `listing.listing_spatial_features` | Tin đăng đã làm sạch và đặc trưng tiện ích xung quanh từng tin. Là đầu vào cho cả Prediction và Recommendation. |
| 3. Prediction | `ml.district_label`, `ml.district_link` | Bảng mã hóa quận thành nhãn số cho model dự đoán giá. |
| 4. Recommendation (RAG) | `rag.listing_embeddings` | Văn bản và vector của từng tin để tìm kiếm ngữ nghĩa và đưa cho LLM. |

Cách đọc cột **Nguồn** bên dưới:
- **crawler**: `CrawlData/listing_extractor.py` lấy từ HTML Batdongsan.
- **cleaner**: `src/pipeline/listing_cleaner.py` tính hoặc sửa.
- **CSV POI**: các file `CrawUltilities/data/poi_*.csv`.
- **import_pois**: `tools/import_pois.py` tính khi nạp.
- **tự sinh**: cột `GENERATED` hoặc `DEFAULT` do PostgreSQL tự tính.

---

## Cụm 1 — Dữ liệu nền

Gồm hai nhóm bảng, đều do `tools/import_pois.py` nạp:

- **Đơn vị hành chính** (`admin.*`): bộ từ điển tỉnh/quận/phường trước và sau sáp nhập 2025.
  Nguồn là dữ liệu `vietnamadminunits/data/processed`, chỉ lấy các dòng có mã tỉnh 79 (TP.HCM).
- **Tiện ích** (`amenities.*`): trường học, bệnh viện, chợ, mỗi loại một bảng. Mỗi điểm tiện ích
  được gắn khóa ngoại tới đơn vị hành chính cũ và mới.

### `admin.unit` — đơn vị hành chính

Mỗi dòng là một tỉnh, quận hoặc phường của một phiên bản địa giới. Hai phiên bản nằm chung một
bảng và phân biệt bằng cột `version`. Cấp cha–con nối bằng `parent_id`:

```text
legacy_2025: province → district → ward     (3 cấp, trước sáp nhập)
from_2025:   province → ward                (2 cấp, không còn quận)
```

| Cột | Ý nghĩa | Nguồn |
|---|---|---|
| `id` | Khóa chính nội bộ. Các bảng khác trỏ tới cột này. | tự sinh (identity) |
| `version` | Phiên bản địa giới: `legacy_2025` (cũ) hoặc `from_2025` (mới) | import_pois, theo file nguồn |
| `level` | Cấp: `province` / `district` / `ward` | import_pois |
| `code` | Mã đơn vị hành chính chính thức (mã tỉnh, quận, phường) | file `vietnamadminunits` (`provinceCode`, `districtCode`, `wardCode`) |
| `name` | Tên đơn vị, giữ nguyên như nguồn (vd. `Phường 15`, `Quận Tân Bình`) | file `vietnamadminunits` |
| `parent_id` | Đơn vị cấp trên. Tỉnh có `NULL`. | import_pois |
| `source_file` | Tên file CSV nguồn | import_pois |
| `raw_record` | Nguyên dòng CSV nguồn (JSON) | import_pois |

`(version, level, code)` là duy nhất.

### `admin.ward_transition` — phường cũ chuyển sang phường mới

Mỗi dòng cho biết một phường cũ (`legacy_2025`) đã được gộp vào phường mới (`from_2025`) nào.
Đây là quan hệ ứng viên lấy từ nguồn: một phường cũ có thể ứng với nhiều phường mới. Vì vậy
bảng này **không đủ để đổi địa chỉ cũ sang địa chỉ mới một cách chắc chắn**.

| Cột | Ý nghĩa | Nguồn |
|---|---|---|
| `old_ward_id` | Phường cũ, trỏ tới `admin.unit.id` | import_pois, từ `wardCode` |
| `new_ward_id` | Phường mới, trỏ tới `admin.unit.id` | import_pois, từ `newWardCode` |
| `source_file` | `convert_legacy_2025_with_location_and_default_ward.csv` | import_pois |
| `raw_record` | Nguyên dòng CSV nguồn | import_pois |

Khóa chính là cặp `(old_ward_id, new_ward_id)`.

### `amenities.poi_schools` / `poi_hospitals` / `poi_markets` — tiện ích

Ba bảng có chung 18 cột và chỉ khác nhau ở vài cột riêng. Mỗi dòng là một điểm tiện ích. Số
dòng trong CSV: 4.660 trường, 376 cơ sở y tế, 231 chợ.

Pipeline tạo CSV (`.codex_tmp/poi_build`, step 1 → 5): lấy dữ liệu thô từ file Excel chợ, PDF
trường học, Wikipedia, OSM, rồi geocode bằng Goong để có `poi_master_old_hcm.csv`, sau đó tách
ra thành 3 file CSV.

**Cột chung:**

| Cột | Ý nghĩa | Nguồn |
|---|---|---|
| `poi_id` | Mã tiện ích kèm tiền tố nguồn (vd. `school:614108`, `osm:node/…`, `market:6`) | CSV POI |
| `poi_type` | Loại: `truong_hoc` / `benh_vien` / `cho`. Mỗi bảng chỉ nhận một giá trị. | CSV POI |
| `poi_subtype` | Loại chi tiết: trường có `Mầm non`, `Tiểu học`, `THCS`, `THPT`…; y tế có `Bệnh viện`, `Phòng khám đa khoa`…; chợ chỉ có `Chợ truyền thống` | CSV POI |
| `name` | Tên tiện ích | CSV POI |
| `address_old` | Địa chỉ theo địa giới cũ (có quận) | CSV POI |
| `address_new` | Địa chỉ theo địa giới mới | CSV POI |
| `old_province_id` | Tỉnh cũ, trỏ tới `admin.unit` | import_pois so khớp cột chữ `old_province` của CSV với tên trong `admin.unit` |
| `old_district_id` | Quận cũ, trỏ tới `admin.unit` | như trên, cột `old_district`, tìm trong các quận của tỉnh đã khớp |
| `old_ward_id` | Phường cũ, trỏ tới `admin.unit` | như trên, cột `old_ward` |
| `new_province_id` | Tỉnh mới, trỏ tới `admin.unit` | như trên, cột `new_province` |
| `new_ward_id` | Phường mới, trỏ tới `admin.unit` | import_pois: ưu tiên `new_ward_code` (kiểm tra cả tên và tỉnh cha), không có mã thì so khớp tên |
| `latitude`, `longitude` | Tọa độ WGS84. Hoặc có cả hai, hoặc cả hai đều trống. | CSV POI (phần lớn từ Goong/OSM) |
| `mapping_status` | Kết quả so khớp của 5 cột `*_id` ở trên. Mỗi khóa nhận `matched`, `missing`, `unmatched`, `ambiguous`, `parent_unresolved` (riêng `new_ward` có thêm `matched_code_and_name` / `code_name_or_parent_mismatch`). Cột `*_id` có giá trị `NULL` thì xem trạng thái ở đây. | import_pois |
| `source_file` | Tên file CSV | import_pois |
| `source_sha256` | Mã băm của file CSV lúc nạp, để biết dữ liệu đến từ phiên bản file nào | import_pois |
| `raw_record` | Nguyên dòng CSV. Các trường CSV không có cột riêng (`geocode_confidence`, `location_precision`, `source`, `source_url`, `updated_at`…) chỉ nằm ở đây. | import_pois |
| `imported_at` | Thời điểm nạp | tự sinh (`now()`) |
| `geom` | Điểm địa lý tạo từ `latitude`/`longitude`, có GiST index, dùng cho mọi truy vấn khoảng cách | tự sinh, thêm bởi `enable_postgis.sql` |

**Cột riêng của từng bảng** (đều tự sinh từ `raw_record`):

| Bảng | Cột | Ý nghĩa |
|---|---|---|
| `poi_schools` | `campus_name` | Tên cơ sở hoặc điểm trường |
| | `school_level_codes` | Mã các cấp học của trường |
| | `ownership` | Loại hình: công lập, tư thục… |
| | `student_count` | Số học sinh |
| | `old_address_confidence` | Độ tin cậy của địa chỉ cũ |
| `poi_hospitals` | `ownership` | Loại hình sở hữu |
| `poi_markets` | `manual_review_required` | Bản ghi cần kiểm tra lại bằng tay |

> View `amenities.housing_poi` gộp 3 bảng trên bằng `UNION ALL`. Hàm `amenities.nearby()` và
> view `ml.poi_district_features` đọc từ view này.

---

## Cụm 2 — Tin bất động sản (dùng chung)

Nơi lưu tập dữ liệu tin đăng mà cả Prediction và RAG cùng đọc. Do `python -m src.pipeline` ghi:

```text
CrawlData/data.json → ListingCleaner → ListingLoader (UPSERT) → refresh_spatial_features()
```

Cleaner chỉ giữ tin **bán** thuộc **24 quận/huyện TP.HCM cũ**, có giá và diện tích hợp lệ.
Đơn vị giữ như crawler: giá tính bằng triệu VND, diện tích bằng m². Nạp lại không xóa tin cũ:
tin có cùng `listing_id` sẽ được cập nhật.

### `listing.listings` — tin đăng

Mỗi dòng là một tin, khóa chính là `listing_id`.

| Cột | Ý nghĩa | Nguồn |
|---|---|---|
| `listing_id` | Mã tin của Batdongsan | crawler: mục "Mã tin" trong `.js__pr-config` |
| `listing_url` | Link bài đăng | crawler: `<link rel="canonical">` |
| `title` | Tiêu đề | crawler: `h1.js__pr-title` |
| `description` | Mô tả gốc. Chỉ chuẩn hóa khoảng trắng, không xóa nội dung. | crawler `.re__detail-content`, cleaner gom khoảng trắng |
| `transaction_type` | Bán / Cho thuê. Sau cleaner, mọi dòng đều là `Bán`. | crawler: breadcrumb cấp 1, nếu không có thì đọc từ URL (`/ban-`, `/cho-thue-`) |
| `property_type` | Loại nhà đất (Căn hộ chung cư, Nhà riêng, Nhà mặt phố, Đất…) | crawler: breadcrumb cấp 4, lấy phần trước chữ "tại" |
| `price` | Giá, triệu VND (vd. 24900 = 24,9 tỷ) | crawler: mục "Mức giá" trong short-info, đổi sang số |
| `price_per_m2` | Giá/m² do website hiển thị, triệu/m² | crawler: phần phụ của mục "Mức giá" |
| `area` | Diện tích, m² | crawler (specs / short-info). Cleaner nhân 1000 khi crawler đọc nhầm dấu phân cách hàng nghìn (`1.437 m²` → `1.437`), chỉ khi kết quả khớp `price_per_m2`. |
| `frontage` | Mặt tiền, m | crawler: mục "Đặc điểm BĐS" (`.re__pr-specs-content-item`), không có thì tìm trong mô tả bằng regex. Cleaner đặt `NULL` nếu quá lớn hoặc lớn hơn diện tích. |
| `bedrooms` | Số phòng ngủ | như `frontage` (specs, short-info, rồi mô tả). Cleaner đặt `NULL` nếu > 50. |
| `bathrooms` | Số phòng vệ sinh | như trên |
| `road_width` | Độ rộng đường vào, m | như trên |
| `floors` | Số tầng | như trên |
| `legal` | Pháp lý, chữ gốc (vd. `Sổ hồng riêng`) | crawler: specs, không có thì lấy từ mô tả |
| `legal_group` | Nhóm pháp lý: `so_do_so_hong` / `dang_cho_so` / `hop_dong_mua_ban` / `khac` | cleaner, phân loại `legal` bằng regex |
| `interior` | Nội thất, chữ gốc | crawler: specs, không có thì lấy từ mô tả |
| `province_old` | Tỉnh/TP theo địa giới cũ | crawler: breadcrumb cấp 2 |
| `district_old` | Quận/huyện cũ, dạng chữ (vd. `Tân Bình`, `Quận 7`). **Không trỏ tới `admin.unit`.** | crawler: breadcrumb cấp 3 |
| `old_ward` | Phường cũ, dạng chữ | crawler: tách từ `old_address` |
| `old_address` | Địa chỉ cũ đầy đủ đúng như website hiển thị | crawler: `.re__address-line-1` |
| `old_address_detail` | Phần đầu của `old_address` (số nhà, đường, phường), bỏ quận và tỉnh | crawler: cắt từ `old_address` |
| `new_address` | Địa chỉ mới sau sáp nhập. Chỉ có khi website hiển thị dòng thứ hai, không tự suy ra từ địa chỉ cũ. Thường chỉ có phường + tỉnh. | crawler: `.re__address-line-2`, bỏ dấu ngoặc |
| `new_ward` | Phường mới, dạng chữ | crawler: tách từ `new_address` |
| `new_city` | Tỉnh/TP mới, dạng chữ | crawler: tách từ `new_address` |
| `latitude`, `longitude` | Tọa độ của tin | crawler: regex trong script khởi tạo bản đồ. Cleaner đặt `NULL` nếu nằm ngoài khung TP.HCM (website gán tọa độ trung tâm Hà Nội cho tin không có vị trí). |
| `posted_at` | Ngày đăng | crawler (dd/mm/yyyy), cleaner đổi sang kiểu date |
| `expired_at` | Ngày hết hạn | như trên |
| `quality_flags` | Danh sách cờ chất lượng, vd. `price_per_m2_mismatch`, `coords_outside_hcm`, `bedrooms_out_of_range`, `area_thousands_separator_fixed` | cleaner |
| `raw_record` | Nguyên bản ghi crawler trước khi làm sạch. Giá trị gốc của các cột đã bị đặt `NULL` vẫn nằm ở đây. | cleaner chép nguyên |
| `source_file` | File crawl đã nạp tin này | ListingLoader |
| `first_loaded_at` | Lần đầu tin vào database | tự sinh |
| `updated_at` | Lần gần nhất tin được ghi lại | ListingLoader đặt `now()` mỗi lần upsert |
| `geom` | Điểm địa lý từ tọa độ, `NULL` nếu không có tọa độ | tự sinh |

### `listing.listing_spatial_features` — tiện ích quanh mỗi tin

Mỗi tin **có tọa độ** có một dòng ở đây (quan hệ 1–0..1, xóa tin thì dòng này tự xóa theo). Toàn
bộ cột do hàm `listing.refresh_spatial_features()` tính bằng PostGIS, từ `listings.geom` và
`geom` của 3 bảng POI. Hàm chạy cuối mỗi lần nạp tin.

| Cột | Ý nghĩa | Nguồn |
|---|---|---|
| `listing_id` | Tin tương ứng, trỏ tới `listing.listings` | refresh_spatial_features |
| `school_count_1km`, `hospital_count_1km`, `market_count_1km` | Số trường / cơ sở y tế / chợ trong bán kính 1 km | refresh_spatial_features (`ST_DWithin` 1000 m) |
| `school_count_3km`, `hospital_count_3km`, `market_count_3km` | Như trên, bán kính 3 km | refresh_spatial_features (`ST_DWithin` 3000 m) |
| `nearest_school_name`, `nearest_school_m` | Tên trường gần nhất và khoảng cách (m), không giới hạn bán kính | refresh_spatial_features (toán tử `<->` dùng GiST index) |
| `nearest_hospital_name`, `nearest_hospital_m` | Như trên, cho cơ sở y tế | như trên |
| `nearest_market_name`, `nearest_market_m` | Như trên, cho chợ | như trên |
| `computed_at` | Thời điểm tính | refresh_spatial_features |

6 cột `*_count_*` là đặc trưng không gian cho model dự đoán giá. Các cột `nearest_*` được đưa vào
`rag_document` ở cụm 4.

---

## Cụm 3 — Prediction

Cụm này hiện chỉ có bảng mã hóa quận. Model dự đoán giá đọc dữ liệu đặc trưng trực tiếp từ cụm 2.
Cả hai bảng đều do `tools/import_pois.py` nạp.

### `ml.district_label` — nhãn số của quận

Danh sách 24 quận/huyện TP.HCM cũ, mỗi quận một nhãn số 0–23 dùng làm đặc trưng cho model.
Thứ tự nhãn là thứ tự trong danh sách `LABELS` viết cứng trong `import_pois.py`, trùng với cách
mã hóa của dự án cũ (vd. `quận 2` = 13). **Đây không phải mã hành chính chính thức.**

| Cột | Ý nghĩa | Nguồn |
|---|---|---|
| `model_version` | Phiên bản bộ nhãn. Hiện chỉ có `hcm_24_user_v1`. | import_pois (hằng `MODEL`) |
| `label` | Nhãn số 0–23 | import_pois (vị trí trong `LABELS`) |
| `district_name` | Tên quận, viết thường, không có tiền tố cấp (vd. `bình thạnh`, `quận 7`) | import_pois (`LABELS`) |

Khóa chính là `(model_version, label)`. `district_name` là duy nhất trong mỗi phiên bản.

### `ml.district_link` — nối quận hành chính với nhãn

Cho biết quận nào trong `admin.unit` (`legacy_2025`) mang nhãn nào.

| Cột | Ý nghĩa | Nguồn |
|---|---|---|
| `admin_district_id` | Quận cũ, trỏ tới `admin.unit` | import_pois |
| `model_version` | Phiên bản bộ nhãn | import_pois |
| `label` | Nhãn, trỏ tới `ml.district_label` cùng phiên bản | import_pois: so tên quận với `LABELS`, chỉ ghi khi khớp đúng một nhãn |
| `evidence` | Lý do gán nhãn (hiện là một câu cố định) | import_pois |

Bộ địa giới `legacy_2025` đã gộp Quận 2, Quận 9 và Thủ Đức thành *Thành phố Thủ Đức*. Vì vậy
thành phố này bị bỏ qua khi gán nhãn, và 3 nhãn `quận 2`, `quận 9`, `thủ đức` không có dòng
nào ở bảng này.

---

## Cụm 4 — Recommendation (RAG)

### `rag.listing_embeddings` — văn bản và vector của tin

Mỗi tin có tối đa một dòng (quan hệ 1–0..1 với `listing.listings`, xóa tin thì dòng này tự xóa
theo). Do `ListingEmbedder` ghi. Vector được tính bằng API embedding chạy trên Kaggle
(`BAAI/bge-m3`, 1024 chiều). Tin chỉ được embed lại khi `content_hash` thay đổi.

| Cột | Ý nghĩa | Nguồn |
|---|---|---|
| `listing_id` | Tin tương ứng, trỏ tới `listing.listings` | ListingEmbedder |
| `model_name` | Model đã tạo vector (`BAAI/bge-m3`) | ListingEmbedder |
| `content_hash` | sha256 của `model_name` + `embedding_text`, dùng để bỏ qua tin không đổi | ListingEmbedder |
| `embedding_text` | Phần đem đi embed: loại nhà, quận, tiêu đề, mô tả. Số điện thoại đã bị xóa. Không chứa giá hay diện tích, vì các số liệu này để SQL lọc. | ListingEmbedder, từ `listings` |
| `rag_document` | Văn bản đưa cho LLM: tiêu đề, giá, diện tích, chi tiết, pháp lý, địa chỉ cũ/mới, tiện ích 1 km/3 km và gần nhất, ngày đăng, link, mô tả. Được cập nhật lại ngay cả khi không cần embed lại. | ListingEmbedder, từ `listings` + `listing_spatial_features` |
| `embedding` | Vector 1024 chiều đã chuẩn hóa L2, so sánh bằng cosine (`<=>`) | API Kaggle |
| `embedded_at` | Thời điểm embed gần nhất | tự sinh / ListingEmbedder |

---

## Quan hệ giữa các cụm

```text
              Cụm 1: Dữ liệu nền
   admin.unit ◄──FK── admin.ward_transition
      ▲   ▲
      │   └──FK (5 cột *_id)── amenities.poi_* ──geom──┐
      │                                                 │ chỉ nối bằng khoảng cách,
      │FK                                               │ không có khóa ngoại
      │                                                 ▼
 Cụm 3: ml.district_link ──FK──► ml.district_label    Cụm 2: listing.listings ──1:1── listing_spatial_features
                                                               │
                                                               └──1:1 FK── Cụm 4: rag.listing_embeddings
```

- **Bên trong cụm 1 nối bằng khóa ngoại.** Mỗi điểm tiện ích trỏ tới tỉnh/quận/phường cũ và
  tỉnh/phường mới trong `admin.unit`.
- **Cụm 1 và cụm 2 chỉ nối bằng không gian.** `listing_spatial_features` được tính bằng khoảng
  cách giữa `listings.geom` và `poi_*.geom`. Địa chỉ của tin (`district_old`, `old_ward`,
  `new_ward`…) là chữ, không có khóa ngoại tới `admin.unit`. Hệ quả: hai phía biểu diễn địa chỉ
  theo hai cách khác nhau.
- **Cụm 3 nối với cụm 1, nhưng không nối với cụm 2.** `ml.district_link` trỏ tới quận trong
  `admin.unit`. Chưa có bảng nào gắn tin đăng với nhãn quận, nên nếu cần thì phải tự đổi
  `listings.district_old` (chữ) sang `district_label` theo tên.
- **Cụm 4 phụ thuộc cụm 2.** `rag.listing_embeddings` trỏ tới `listings`, và `rag_document`
  chép số liệu tiện ích từ `listing_spatial_features` vào dạng văn bản. Vì vậy khi đặc trưng
  tiện ích đổi, phải chạy lại embedder để `rag_document` cập nhật theo.
- **Thứ tự nạp:** cụm 1 (gồm cả bước `enable_postgis.sql` để có `geom`) phải có trước cụm 2,
  vì `refresh_spatial_features()` đọc `geom` của tiện ích. Cụm 4 chạy sau cụm 2.
