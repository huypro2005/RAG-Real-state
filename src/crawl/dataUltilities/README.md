# Database housing

Database dùng chung cho tiện ích, bất động sản và các phần khác của dự án.
Ba CSV nạp vào **ba bảng riêng trong database housing**:

- `amenities.poi_schools`: 4.660 trường học.
- `amenities.poi_hospitals`: 376 cơ sở y tế.
- `amenities.poi_markets`: 231 chợ.

`amenities.housing_poi` là **view UNION ALL**, không phải bảng lưu trữ thứ tư.
View dùng để đọc chung, truy vấn khoảng cách và liên kết mã huấn luyện.
INSERT/UPDATE phải thực hiện trên bảng tương ứng hoặc qua script import.
Mỗi bảng có khóa chính, khóa ngoại địa chỉ, ràng buộc loại POI và GiST index riêng.

## Danh mục độc lập và dữ liệu gốc

- Ba bảng tiện ích chứa tổng cộng 5.267 bản ghi.
  `raw_record` giữ mọi cột CSV dạng chuỗi, kể cả ô trống, độ tin cậy, nguồn,
  mã hành chính và thuộc tính riêng (`school_level_codes`, `student_count`,
  `ownership`, `manual_review_required`). CSV không bị sửa.
  Trường học có cột riêng `campus_name`, `school_level_codes`, `ownership`,
  `student_count`, `old_address_confidence`; bệnh viện có `ownership`;
  chợ có `manual_review_required`. Các cột này sinh tự động từ `raw_record`,
  không ghi trực tiếp; chuỗi gốc vẫn được giữ đầy đủ trong JSON.
- `admin.unit`: danh mục HCM từ snapshot `vietnamadminunits/data/processed`.
  `legacy_2025`: 1 tỉnh/TP, 22 quận/huyện/TP, 273 phường/xã.
  `from_2025`: 1 tỉnh/TP, 168 phường/xã. Không tạo quận/huyện mới giả định.
  Hai version có ID độc lập dù mã hoặc tên trùng nhau. Phạm vi HCM mới rộng hơn
  HCM cũ; danh mục mới không đồng nghĩa POI đã phủ các khu vực mới nhập vào.
  Đây là snapshot nguồn, chưa kiểm chứng pháp lý cập nhật.
- `admin.ward_transition`: 308 quan hệ ứng viên cũ–mới từ dataset có sẵn,
  giữ nguyên các cờ `isDividedWard`, `isDefaultNewWard`, v.v. Không tự chọn
  một phường mới và không dùng quan hệ này để tự điền địa chỉ tiện ích.
- `ml.district_label`: đúng 24 mã người dùng cung cấp, version `hcm_24_user_v1`.
  Đây là nhãn mô hình, không phải mã hành chính hoặc khóa chính danh mục.
- `ml.district_link`: liên kết quận trong snapshot với nhãn khi tên xác định.
- `ml.poi_district_features`: view tra mã huấn luyện, trạng thái mapping và chất lượng nguồn.

Mỗi POI liên kết tỉnh/quận/phường cũ và tỉnh/phường mới bằng khóa ngoại.
So tên dùng Unicode NFC, chữ thường và bí danh có phạm vi cha rõ ràng;
không sửa raw. Mã nguồn như `26743.0` dùng khóa tra cứu `26743`, giữ chuỗi gốc
trong raw. Mã phường mới phải khớp cả tên và tỉnh; mâu thuẫn thì không tự chọn.

## Các trường hợp cần rà soát

- 4.420 POI liên kết được nhãn theo tên quận cũ trong CSV; đây không phải xác
  nhận địa chỉ đúng với thực địa.
- 847 POI ghi **Thành phố Thủ Đức**: `district_label = NULL`, trạng thái
  `ambiguous_pre_2021_district`. Snapshot trước sáp nhập 2025 đã gộp Quận 2,
  Quận 9, quận Thủ Đức. Không gán cả TP Thủ Đức thành mã 21.
  Nhãn 13, 20, 21 vẫn tồn tại trong bảng nhãn. Để điền cần nguồn địa chỉ lịch sử
  hoặc polygon ranh giới đúng thời điểm bộ 24 mã.
- 178 phường cũ chưa khớp (150 trường, 1 cơ sở y tế, 27 chợ): `old_ward_id = NULL`;
  tên gốc và `mapping_status` giữ nguyên.
- `address_new` là tên cột nguồn, **không đảm bảo chuỗi đã là địa chỉ mới**.
  Một số chợ còn chứa quận cũ trong chuỗi. Không tự viết lại theo `new_ward`;
  giữ `address_new_precision` trong raw.
- `ownership` bệnh viện trống. Tọa độ có thể là centroid/ước lượng: xem
  `location_precision` và `geocode_confidence` trước khi dùng khoảng cách.

## Import

Cài PostGIS Bundle phù hợp PostgreSQL qua Stack Builder → PostgreSQL 18 →
Spatial Extensions. [Nguồn chính thức](https://postgis.net/documentation/getting_started/install_windows/released_versions/).
Chạy PowerShell tại thư mục dự án:

```powershell
python -m pip install -r data/postgres/requirements.txt
$env:PGHOST = 'localhost'
$env:PGPORT = '5432'
$env:PGDATABASE = 'housing'
$env:PGUSER = 'postgres'
$credential = Get-Credential -UserName postgres -Message 'PostgreSQL password'
$env:PGPASSWORD = $credential.GetNetworkCredential().Password
python tools/import_pois.py --create-database
python tools/verify_pois.py --require-spatial
Remove-Item Env:PGPASSWORD
```

Mật khẩu không nằm trong source. Script dùng PGPASSWORD hoặc pgpass theo libpq.
Import là một transaction, UPSERT theo poi_id; chạy lại không nhân bản.
Không DROP/TRUNCATE, không xóa POI ngoài CSV. CSV lỗi, ID trùng, tọa độ không hợp lệ
hoặc lỗi schema làm rollback lần import. Database mới tạo vẫn tồn tại nếu import
thất bại. Danh mục/quan hệ được upsert; bản ghi không còn trong snapshot mới
không tự bị xóa.

Chưa cài PostGIS có thể nạp trước với `--skip-spatial`. Khi cài xong:

```powershell
# Thiết lập PG* và mật khẩu như trên nếu ở phiên PowerShell mới.
python tools/import_pois.py --spatial-only
python tools/verify_pois.py --require-spatial
```

`--spatial-only` tạo extension, cột geography và index cho dữ liệu đã có.
`data/postgres/import_result.json` ghi lần import; `spatial_result.json` ghi riêng
lần kích hoạt không gian nếu thành công.
Không dùng `data/schema.sql` cũ (có DROP TABLE và thiếu danh mục địa chỉ độc lập).
Luồng mới dùng `data/postgres/schema.sql` qua importer.

Nếu nâng cấp từ thiết kế một bảng trước đó, sao lưu bằng pg_dump rồi chạy
`python tools/split_poi_tables.py` trước importer. Migration chuyển cả dữ liệu
đang có trong database, đối chiếu toàn bộ cột trước khi thay bảng cũ bằng view,
và rollback nếu có sai lệch hoặc dependency ngoài dự kiến. Không dùng CASCADE.
Lần chuyển trên máy này đã sao lưu tại `.codex_tmp/db_backups/housing_before_poi_split.dump`.

## Truy vấn sau khi kích hoạt PostGIS

Cột geom ở từng bảng sinh từ longitude/latitude, kiểu geography(Point,4326),
có GiST index riêng. View chung cho phép truy vấn xuyên ba bảng.
Thứ tự tham số: **kinh độ, vĩ độ, bán kính mét**.

```sql
SELECT * FROM amenities.nearby(106.7009, 10.7769, 1000);
SELECT * FROM amenities.nearby(106.7009, 10.7769, 3000, 'benh_vien') LIMIT 10;
SELECT p.poi_id, p.name, p.address_old, p.address_new,
       f.district_label, f.label_status, p.raw_record
FROM amenities.housing_poi p
JOIN ml.poi_district_features f USING (poi_id);
```

Ví dụ khác: `data/postgres/queries.sql`. Với geography, ST_DWithin dùng mét và
hỗ trợ spatial index: [tài liệu PostGIS](https://postgis.net/docs/ST_DWithin.html).

## Kiểm tra

```powershell
python -m unittest discover -s tools -p test_import_pois.py
python tools/verify_pois.py
python tools/verify_pois.py --require-spatial
```

Verifier đối chiếu từng raw_record, SHA256 file, tọa độ với CSV, nhãn, quan hệ
cha/con. Chế độ spatial kiểm tra SRID, thứ tự tọa độ, tự tìm đúng POI,
so kết quả bán kính với tính khoảng cách toàn bảng, tính khả dụng GiST và tham số sai.
Verifier hiện kỳ vọng DB chứa đúng bộ CSV này; cần mở rộng khi nhập thêm nguồn.
