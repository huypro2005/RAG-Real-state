# Task: Làm lại database địa chỉ theo dữ liệu Batdongsan

Đây là **spec chung** cho hai agent: `db-coder` làm theo spec này, `db-reviewer` chấm theo
các mã tiêu chí `[A1]`, `[B2]`... ở mục 7. Đổi yêu cầu thì sửa file này trước.

Thư mục code: `housing-backend/housing-backend/` (gọi tắt là `backend/`).

---

## 1. Mục tiêu

1. Bảng địa chỉ lấy **đúng** dữ liệu và **đúng ID** của batdongsan.com.vn (thay bộ mã hành
   chính chính thức `79`, `760`... đang dùng trong `backend/app/db/models/admin_units.py`).
2. Toàn bộ bảng nằm trong schema mặc định `public`. Không `CREATE SCHEMA`, không
   `__table_args__ = {"schema": ...}`, không tiền tố `admin.`, `listing.`...
3. Database đơn giản, chỉ phục vụ đề tài. Không lưu `raw_record`, `source_file`,
   `source_sha256`, `mapping_status`, cột `jsonb` lưu nguyên bản ghi, hay mã nguồn kiểu
   `poi_id` / `source_poi_id`.
4. Alembic + SQLAlchemy model là nguồn chuẩn duy nhất của cấu trúc DB.

## 2. Phạm vi dữ liệu

| Cấp | Bộ cũ (trước 2025) | Bộ mới (từ 2025) |
|---|---|---|
| Tỉnh/TP | **tất cả** tỉnh trong `address_data/old_cities.json` | **tất cả** tỉnh trong `address_data/new_cities.json` |
| Quận/huyện | chỉ `SG` (`address_data/sg_old.json`) | — (bộ mới không có cấp quận) |
| Phường/xã | chỉ `SG`, theo từng quận cũ | chỉ `SG` |
| Đường | chỉ `SG`, theo từng quận cũ | chỉ `SG`, theo từng phường mới |

- Đề tài chỉ làm TP.HCM **cũ**. Nhưng bộ mới của `SG` gồm cả Bình Dương và Bà Rịa – Vũng Tàu
  cũ, và batdongsan không cho biết phường mới nào thuộc vùng nào. Vì vậy **nạp đủ toàn bộ
  phường mới của `SG`**, không tự lọc.
- Mapping phường cũ → phường mới lấy **duy nhất** từ `address_data/ward_mappings.sql` (mục 4b),
  chỉ các dòng `old_province_name = 'Thành phố Hồ Chí Minh'`. Không tự suy luận mapping từ
  tên, tọa độ hay nguồn nào khác.

## 3. Lấy dữ liệu từ API Batdongsan

Endpoint (xem `address_data/readme.md`):

```text
GET https://api.batdongsan.com.vn/bff-seller/locations/old-districts?city={city_code}
GET https://api.batdongsan.com.vn/bff-seller/locations/old-districts/{district_id}/old-wards
GET https://api.batdongsan.com.vn/bff-seller/locations/old-districts/{district_id}/streets
GET https://api.batdongsan.com.vn/bff-seller/locations/cities/{city_code}/wards
GET https://api.batdongsan.com.vn/bff-seller/locations/wards/{ward_id}/streets
```

Viết `backend/scripts/fetch_bds_address.py`:

- Một class (vd. `BdsAddressFetcher`) với `run()`; đọc `sg_old.json` để lấy danh sách quận cũ,
  gọi API phường mới của `SG` để lấy danh sách phường mới.
- Lưu **nguyên văn** response (không đổi tên field, không bỏ field) vào `address_data/`:

  | File | Nội dung |
  |---|---|
  | `sg_old_wards.json` | `{ "<district_id>": [ ...response... ], ... }` |
  | `sg_old_streets.json` | `{ "<district_id>": [ ...response... ], ... }` |
  | `sg_new_wards.json` | response của `cities/SG/wards` |
  | `sg_new_streets.json` | `{ "<ward_id>": [ ...response... ], ... }` |

  Khóa ngoài của object là ID cha dùng để gọi API, vì response có thể không chứa ID cha.
- Nghỉ giữa các request (≥ 0,5 giây), retry có giới hạn khi lỗi mạng/5xx, header `User-Agent`
  như trình duyệt, chạy lại được (bỏ qua ID cha đã có trong file).
- Không được sửa 3 file có sẵn: `old_cities.json`, `new_cities.json`, `sg_old.json`.
- **Agent không tự chạy script này.** Main session chạy một lần (người dùng đã cho phép) sau
  khi db-coder viết xong. Nếu file JSON chưa có, agent dừng ở bước seed và báo lại.
- Chạy: `python scripts/fetch_bds_address.py` từ `backend/`, không cần tham số.

## 4. Thiết kế bảng địa chỉ

7 bảng, mọi khóa chính là **ID của batdongsan** (không tự tăng):

```text
provinces_old (code PK) ── districts_old (id PK) ─┬─ wards_old   (id PK)
                                                  └─ streets_old (id PK)
provinces_new (code PK) ── wards_new (id PK) ──── streets_new (id PK)
```

| Bảng | PK | FK | Cột lấy từ JSON |
|---|---|---|---|
| `provinces_old` | `code` text = `cityCode` | — | `cityName`→`name`, `cityAlias`→`alias` |
| `provinces_new` | `code` text = `cityCode` | — | như trên |
| `districts_old` | `id` int = `districtId` | `province_code` → `provinces_old.code` | `districtName`→`name`, `districtPrefix`→`prefix`, `districtAlias`→`alias` |
| `wards_old` | `id` int = ID phường trong response | `district_id` → `districts_old.id` | tên, prefix, alias |
| `streets_old` | `id` int = ID đường | `district_id` → `districts_old.id` | tên, prefix, alias |
| `wards_new` | `id` int = ID phường | `province_code` → `provinces_new.code` | tên, prefix, alias |
| `streets_new` | `id` int = ID đường | `ward_id` → `wards_new.id` | tên, prefix, alias |

Quy tắc:

- Tên field của phường/đường chưa biết trước. Đọc JSON thật rồi map **1-1, đổi sang
  snake_case**. Mỗi cột phải chỉ ra được nó đến từ field nào. Chỉ thêm tọa độ nếu API có trả.
- Field luôn null/rỗng (`otherNames`...), mã vùng điện thoại (`areaCode`), `priority`,
  `countryCode` thì **bỏ**. Không thêm cột mà JSON không có.
- Giữ nguyên chữ như nguồn: không bỏ dấu, không ghép prefix vào name, không đổi hoa/thường.
- **Kiểm tra trùng ID trước khi chốt PK.** Nếu một ID đường xuất hiện ở nhiều quận/phường thì
  PK của bảng đường phải là cặp `(id, district_id)` / `(id, ward_id)`. Ghi rõ kết quả kiểm tra
  vào docstring của model.
- `provinces_*.code` dạng `'SG'` là mã batdongsan, **không** phải mã hành chính `'79'`.
- Model nằm ở `backend/app/db/models/admin_units.py`, theo phong cách đang có
  (`Mapped[...]`, docstring/comment tiếng Việt). `IntPk` hiện là cột tự tăng, nên PK bằng ID
  batdongsan phải khai báo `autoincrement=False`.

## 4b. Bảng mapping phường cũ → mới

Nguồn: `address_data/ward_mappings.sql` — dump **MySQL** (không nạp thẳng vào Postgres được),
10.039 dòng toàn quốc. Cột: `old_ward_code`, `old_ward_name`, `old_district_name`,
`old_province_name`, `new_ward_code`, `new_ward_name`, `new_province_name` (+ `id`,
`created_at`, `updated_at` không dùng). Mã ở đây là **mã hành chính chính thức** (`'26881'`),
không phải ID batdongsan; tên là tên đầy đủ (`'Phường 12'`, `'Quận Gò Vấp'`).

Số liệu đã khảo sát (TP.HCM cũ): **273 dòng**, 273 phường cũ khác nhau (mỗi phường cũ đúng
1 dòng), trỏ tới **102 phường mới**, không có giá trị NULL, 22 quận cũ.

Bảng `ward_mappings`:

| Cột | Kiểu | Ghi chú |
|---|---|---|
| `old_ward_id` | int, PK, FK → `wards_old.id` | ID batdongsan của phường cũ |
| `new_ward_id` | int, FK → `wards_new.id` | ID batdongsan của phường mới |

Cách nối sang ID batdongsan (seed làm, không phải tay):

- Đọc file `.sql` bằng parser trong script seed (regex theo từng dòng `INSERT`), không sửa file
  gốc, không cần MySQL.
- Phường cũ: so khớp **chính xác** cặp (quận cũ, tên phường đầy đủ) giữa file mapping và
  `wards_old` + `districts_old`. Tên đầy đủ batdongsan = ghép prefix + tên theo đúng cách nguồn
  trả về (kiểm tra trên JSON thật, vd. prefix `Quận 1` của batdongsan đang rỗng).
- **Lệch quận đã biết:** file mapping gộp `Quận 2`, `Quận 9`, `Quận Thủ Đức` thành
  `Thành phố Thủ Đức`; batdongsan vẫn tách (`sg_old.json` có 24 quận). Với dòng
  `Thành phố Thủ Đức`, tìm phường trong cả 3 quận này; chỉ chấp nhận khi khớp **đúng 1** phường.
- Phường mới: so khớp chính xác tên đầy đủ trong `wards_new` của `SG`.
- Chỉ được bỏ dấu cách thừa và so sánh không phân biệt hoa/thường. Không bỏ dấu tiếng Việt,
  không fuzzy match, không đoán `Phường 1` = `Phường 01`. Nếu dữ liệu thật cần quy tắc khác thì
  dừng và báo lại, không tự thêm.
- Dòng nào không khớp hoặc khớp nhiều hơn 1 → **không insert**, ghi vào
  `address_data/ward_mappings_unmatched.json` (giữ nguyên các field gốc + lý do). Seed in số
  khớp / không khớp.

## 5. Đơn giản hóa các bảng khác

Thiết kế này bám theo **DB thật đang chạy** (`housing`, 5 schema cũ), không theo model
`housing-backend` do AI sinh trước đó. Hiện trạng DB thật (2026-10-09):

| Bảng cũ | Số dòng | Ghi chú |
|---|---|---|
| `listing.listings` | 7.603 | PK `listing_id` text = mã tin batdongsan (`'44521542'`) |
| `listing.listing_spatial_features` | 7.342 | PK `listing_id` |
| `rag.listing_embeddings` | 0 | PK `listing_id` |
| `amenities.poi_schools` / `poi_hospitals` / `poi_markets` | 4.660 / 376 / 231 | PK `poi_id` text |
| `ml.district_label` | 24 | `(model_version, label, district_name)`, tên viết thường (`'bình chánh'`) |
| `ml.district_link`, `admin.unit`, `admin.ward_transition` | 21 / 465 / 308 | thay bằng bảng địa chỉ mới → **bỏ** |
| view `amenities.housing_poi`, `ml.poi_district_features` | — | `poi_district_features` **bỏ** |
| function `amenities.nearby`, `listing.refresh_spatial_features` | — | giữ, chuyển sang `public` |

Bảng mới (tất cả trong `public`):

| Bảng | Cột |
|---|---|
| `listings` | PK `listing_id` text (mã tin batdongsan, giữ như cũ — bỏ `id`/`source`/`source_listing_id` mà model AI sinh ra, vì chỉ có một nguồn). Giữ các cột dữ liệu tin: `listing_url, title, description, transaction_type, property_type, price, price_per_m2, area, frontage, bedrooms, bathrooms, road_width, floors, legal, legal_group, interior, province_old, district_old, old_ward, old_address, old_address_detail, new_ward, new_city, new_address, latitude, longitude, posted_at, expired_at, quality_flags, first_loaded_at, updated_at, geom`. **Bỏ** `raw_record`, `source_file`. **Thêm** FK nullable `old_district_id` → `districts_old.id`, `old_ward_id` → `wards_old.id`, `new_ward_id` → `wards_new.id`. Không thêm FK đường (tin không có cột tên đường riêng). |
| `property_types` | **Bỏ bảng.** `listings.property_type` là text nguyên văn (`'Nhà riêng'`). |
| `listing_spatial_features` | Giữ nguyên cột, PK `listing_id` → `listings.listing_id` ON DELETE CASCADE. |
| `listing_embeddings` | Giữ nguyên cột, PK `listing_id` → `listings.listing_id` ON DELETE CASCADE, vector 1024. |
| `pois` | **Một bảng** thay 3 bảng cũ (đúng Bảng 4.1 đề cương). PK `id` int tự tăng. Cột: `poi_type` (CHECK `'truong_hoc'`, `'benh_vien'`, `'cho'`), `poi_subtype, name, address_old, address_new, latitude, longitude, geom, ownership` (trường/bệnh viện), `school_level_codes` (trường). Index GiST `geom`, index `poi_type`. |
| (POI, bỏ) | Bảng `poi_schools`/`poi_hospitals`/`poi_markets`, `poi_id`, `mapping_status`, `source_file`, `source_sha256`, `raw_record`, `imported_at`, mọi FK hành chính (`old_*_id`, `new_*_id` — trỏ tới bộ mã cũ, không nối chắc chắn sang ID batdongsan; vị trí POI dùng `geom`), `campus_name`, `student_count`, `old_address_confidence`, `manual_review_required`. |
| `district_label` | PK `(model_version, label)`; cột `district_id` → `districts_old.id`; UNIQUE `(model_version, district_id)`; CHECK `label >= 0`. Bỏ `district_name`, `note`, bảng `district_link`. |
| view `housing_poi`, `poi_district_features` | **Bỏ** (đã có bảng `pois` chung). |
| function `nearby()`, `refresh_spatial_features()` | Viết lại cho bảng/cột mới, nằm ở `public`, tạo trong migration. Giữ chữ ký trả về mà `app/repositories/` đang dùng (sửa repo nếu bắt buộc). |

Model, schema Pydantic, repository, route trong `backend/app/` sửa cho khớp. Xóa code chỉ phục
vụ thứ đã bỏ (`PropertyType`, `PoiDistrictFeature`...).

## 6. Migration, seed, file cũ

- Viết lại `backend/migrations/versions/0001_baseline.py`: tạo extension (`postgis`, `vector`,
  `pg_trgm`, `unaccent`), tạo bảng từ model, tạo view và function. **Không** đọc
  `db/schema.sql` nữa. DB sẽ được dựng mới, dữ liệu nạp lại bằng script.
- Chuyển `db/schema.sql` và `db/move_to_public.sql` vào `backend/db/legacy/` (không xóa —
  thư mục `housing-backend/` chưa được commit vào git). `db/functions.sql` sửa cho khớp cột mới
  nếu còn dùng.
- Viết `backend/scripts/seed_address.py`: một class đọc JSON trong `address_data/`, nạp 7 bảng + `ward_mappings` (mục 4b)
  bằng `INSERT ... ON CONFLICT (pk) DO UPDATE`, chạy lại nhiều lần kết quả không đổi, in số
  dòng mỗi bảng ở cuối.
- Cập nhật `backend/README.md` và `docs/database.md` cho khớp thiết kế mới.

### Chuyển dữ liệu từ DB cũ

Viết `backend/scripts/migrate_legacy_data.py` (một class, chạy lại được, upsert):

- Tham số `--source-url` (DB có 5 schema cũ) và `--target-url` (DB đích đã `alembic upgrade`
  + `seed_address`). Hai URL có thể là cùng một DB.
- Copy `listing.listings` → `listings`, `listing.listing_spatial_features`,
  `rag.listing_embeddings`, 3 bảng POI gộp vào `pois` (chỉ các cột giữ lại ở mục 5; `school_level_codes`,
  `ownership` lấy từ cột cùng tên ở bảng cũ).
- Điền FK của `listings` **chỉ bằng khớp chính xác**:
  - `old_district_id`: `listings.district_old` = `districts_old.name` (của `SG`).
  - `old_ward_id`: (`old_district_id`, `old_ward`) khớp đúng 1 phường cũ theo tên đầy đủ.
  - `new_ward_id`: `new_ward` khớp đúng 1 phường mới của `SG` theo tên đầy đủ.
  - Không khớp hoặc khớp > 1 → để NULL. In thống kê khớp/không khớp từng cột.
- `district_label`: `ml.district_label.district_name` so với `lower(districts_old.name)`; phải
  khớp đủ 24/24, nếu không thì dừng và báo lỗi.
- Thử trên `housing_dev`: tạo bản sao DB cũ bằng
  `CREATE DATABASE housing_legacy_copy TEMPLATE housing` (chỉ chạy được khi không ai đang kết
  nối `housing`) **hoặc** đọc thẳng từ `housing` ở chế độ chỉ đọc
  (`SET default_transaction_read_only = on`). Không ghi vào `housing`.

### Code ngoài backend đang dùng schema cũ

Sau khi xóa 5 schema cũ, các file này sẽ hỏng nên phải sửa cho khớp bảng/cột mới (`public`,
bỏ `raw_record`, `source_file`). Chỉ sửa đúng phần truy vấn/cột, không refactor thứ khác:

- `src/pipeline/listing_loader.py`, `src/pipeline/listing_embedder.py`, `src/pipeline/__main__.py`
  (docstring), `src/models/housing_repository.py`.
- `tools/import_pois.py`, `tools/verify_pois.py`, `tools/split_poi_tables.py` tạo/đọc schema cũ
  và đã được `migrate_legacy_data.py` thay thế → **không sửa**, thêm một dòng đầu docstring
  ghi "LỖI THỜI: dùng housing-backend/scripts/migrate_legacy_data.py".
- Thêm cờ `--embed-only` cho `python -m src.pipeline` (bỏ qua làm sạch + nạp, chỉ gọi
  `ListingEmbedder.embed_pending()`), để embed dữ liệu đã có trong DB.
- URL/key embedding **chỉ đọc từ `.env`**, không ghi giá trị vào code, log, docs.

### Áp dụng lên DB thật

Agent **không** làm bước này. Sau khi reviewer PASS, main session sẽ: backup `housing` bằng
`pg_dump` → `alembic upgrade head` → `seed_address.py` → `migrate_legacy_data.py` → đối chiếu
số dòng → xóa 5 schema cũ → `python -m src.pipeline --embed-only` (API Kaggle) → reviewer
kiểm tra lần cuối trên DB thật (chỉ đọc).

### An toàn database

- Chỉ chạy migration/seed trên DB thử **`housing_dev`** (tạo bằng Python + psycopg nếu chưa có,
  vì máy không có `psql`). Kết nối mặc định: `postgres:123456789@localhost:5432`.
- **Không** `DROP`, `TRUNCATE`, `alembic downgrade` hay `alembic upgrade` trên DB `housing`.
- Đặt URL bằng biến môi trường `DATABASE_URL` khi chạy lệnh, không sửa giá trị mặc định trong
  `config.py`.

## 7. Tiêu chí nghiệm thu (reviewer chấm theo mã)

**A. Cấu trúc**

- `[A1]` Mọi bảng/view nằm trong `public`; không có `schema=` hay `CREATE SCHEMA` ở code mới.
- `[A2]` Có đúng 7 bảng địa chỉ ở mục 4; PK/FK đúng như bảng ở mục 4.
- `[A3]` Không còn cột `raw_record`, `source_file`, `source_sha256`, `mapping_status`,
  `source_poi_id`, hay cột `jsonb` nào trong toàn DB.
- `[A4]` Mỗi cột bảng địa chỉ truy được về một field trong JSON; không có cột bịa thêm.
- `[A5]` Mapping cũ→mới chỉ đến từ `ward_mappings.sql`, đúng quy tắc khớp ở mục 4b
  (không fuzzy, không đoán); bảng `ward_mappings` đúng cột/PK/FK.
- `[A6]` Bảng khác được sửa đúng mục 5, FK trỏ tới bảng địa chỉ mới.

**B. Migration**

- `[B1]` `alembic upgrade head` chạy thành công trên `housing_dev` trống.
- `[B2]` `alembic check` (hoặc autogenerate) báo không có khác biệt giữa model và DB.
- `[B3]` Migration không còn phụ thuộc `db/schema.sql`.

**C. Dữ liệu** (chỉ chấm khi đã có đủ file JSON ở mục 3)

- `[C1]` Số dòng mỗi bảng = số bản ghi trong JSON tương ứng (sau khi gộp trùng nếu có).
- `[C2]` Chạy seed 2 lần, số dòng và nội dung không đổi.
- `[C3]` Không có dòng con mồ côi (FK đều hợp lệ); chi tiết cấp dưới chỉ có của `SG`.
- `[C4]` Lấy ngẫu nhiên ≥ 5 bản ghi mỗi bảng, so từng cột với JSON: khớp nguyên văn.
- `[C5]` `ward_mappings`: số dòng khớp + số dòng trong `ward_mappings_unmatched.json` = 273.
  Lấy ngẫu nhiên ≥ 10 dòng, tra ngược tên phường cũ/mới trong DB đúng với dòng gốc trong file
  `.sql`. Mọi dòng không khớp phải có lý do rõ ràng.

**E. Chuyển dữ liệu** (chạy trên `housing_dev`, nguồn đọc từ `housing` chỉ đọc hoặc bản sao)

- `[E1]` Số dòng sau chuyển: `listings` 7.603, `listing_spatial_features` 7.342,
  `listing_embeddings` 0, `pois` 5.267 (4.660 trường + 376 bệnh viện + 231 chợ), `district_label` 24 (hoặc bằng số dòng nguồn
  tại thời điểm chạy).
- `[E2]` FK của `listings` chỉ điền khi khớp chính xác đúng 1; lấy ngẫu nhiên ≥ 10 tin có FK,
  tên trong bảng địa chỉ trùng nguyên văn với cột chữ của tin.
- `[E3]` `migrate_legacy_data.py` chạy 2 lần số dòng không đổi; không có lệnh ghi nào vào `housing`.
- `[E4]` `nearby()` và `refresh_spatial_features()` chạy được trên dữ liệu đã chuyển;
  `refresh_spatial_features()` cho ra số dòng bằng số tin có tọa độ.

**D. Code**

- `[D1]` Script fetch và seed mỗi file là một class gọn, ít hàm nhỏ; comment tiếng Việt như
  code đang có.
- `[D2]` `ruff check` sạch trên các file đã sửa.
- `[D3]` Script fetch không sửa 3 file JSON gốc, có delay, retry, chạy tiếp được.
- `[D4]` Không file nào ngoài `housing-backend/`, `address_data/` (file mới do fetch/seed tạo),
  `docs/database.md` và các file `src/`, `tools/` liệt kê ở mục 6 bị sửa.
- `[D5]` README và `docs/database.md` khớp với code.
- `[D6]` Không có URL/key embedding hay mật khẩu mới nào bị ghi cứng trong code/docs.

**F. Chạy được và dễ đọc** (chấm từng đầu việc: fetch, model, migration, seed, migrate,
repository/route, pipeline src, embed)

- `[F1]` Mỗi đầu việc có lệnh chạy thật và output thành công (route FastAPI: gọi bằng
  `TestClient` hoặc `uvicorn` + request thật trên `housing_dev`).
- `[F2]` Code dễ đọc, không rườm rà — chấm theo nguồn uy tín, **mỗi lỗi phải trích quy tắc
  cụ thể + link**, không chấm theo cảm tính:
  - PEP 8 / PEP 20: https://github.com/python/peps (`peps/pep-0008.rst`, `peps/pep-0020.rst`)
  - Google Python Style Guide: https://github.com/google/styleguide/blob/gh-pages/pyguide.md
  - Clean Code Python: https://github.com/zedr/clean-code-python
  - Cấu trúc FastAPI + SQLAlchemy + Alembic: https://github.com/fastapi/full-stack-fastapi-template
  - SQLAlchemy 2.0 ORM (`Mapped`, `mapped_column`): https://github.com/sqlalchemy/sqlalchemy
    (`doc/build/orm/declarative_tables.rst`)
- `[F3]` Không có code chết, tham số không dùng, lớp/hàm bọc thừa, comment lặp lại code.
- `[F4]` Embedding: `listing_embeddings` = số tin có `embedding_text`, vector 1024 chiều,
  `model_name` đúng; truy vấn cosine thử một câu hỏi trả về tin hợp lý.
