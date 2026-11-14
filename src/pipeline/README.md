# Pipeline tin đăng: dữ liệu thô → database

```text
src/pipeline/input/*.json ─► ListingCleaner ─► listings (upsert) ─► refresh_listing_address_ids()
                                   └► output/listings/*  ─► refresh_spatial_features()
                                                          ─► (--embed) listing_embeddings
```

Bảng ở schema `public` của `housing_dev`, do Alembic tạo. **Pipeline không tạo bảng**: trước khi chạy, DB phải đã
qua `alembic upgrade head`, có địa chỉ (`seed_address.py`) và POI (`pois`), xem
[docs/setup-docker-postgres.md](../../docs/setup-docker-postgres.md) mục 4B. Thiếu POI thì vẫn nạp được nhưng mọi
đặc trưng "số trường/bệnh viện/chợ quanh nhà" bằng 0.

## Cấu hình

**`src/pipeline/.env`** (copy từ `src/pipeline/.env.example`; không commit, pipeline không đọc `.env` khác):

```ini
DATABASE_URL=postgresql://postgres:<mật khẩu>@localhost:5433/housing_dev
EMBEDDING_API_URL=     # chỉ cần cho --embed / --embed-only, từ notebook Kaggle, đổi mỗi phiên
EMBEDDING_API_KEY=
```

Thứ tự chọn database: `--db-url`, rồi `DATABASE_URL` (biến môi trường của shell được ưu tiên hơn file `.env`; dạng
`+asyncpg` cũng được), rồi mặc định `housing_dev` ở `localhost:5433` (user `postgres`, mật khẩu từ `PGPASSWORD`).
Pipeline không tự ghi vào `housing`.

## Chạy

PowerShell, tại **thư mục gốc dự án**:

```powershell
$PY = (Resolve-Path .\.venv\Scripts\python.exe).Path
& $PY -m src.pipeline --input src\pipeline\input\data.json src\pipeline\input\data14-11.json   # làm sạch, nạp, FK địa chỉ, POI
```

| Lệnh thêm | Việc |
|---|---|
| `--input a.json b.json ...` | File JSON Lines từ crawler, nhiều file cách nhau dấu cách (ghép rồi bỏ trùng). **Luôn truyền**: mặc định `./input/data.json` tính theo thư mục đang đứng nên chạy từ gốc dự án sẽ không thấy file |
| `--embed` | Sau khi nạp, tạo embedding qua API Kaggle |
| `--embed-only` | Bỏ qua làm sạch + nạp, chỉ embed tin đã có trong DB |
| `--db-url postgresql://...` | Thay cho `DATABASE_URL` |
| `--output-dir <thư mục>` | Nơi ghi kết quả làm sạch (mặc định `output\listings` dưới thư mục đang đứng) |

- Embedding chạy trên Kaggle (`src/notebook/kaggle/embedding_server.ipynb`), máy này chỉ gọi API. Thiếu
  `EMBEDDING_API_URL/KEY` hoặc server tắt thì lệnh dừng ngay với thông báo, không chạy model cục bộ.
- Chạy lại hoặc nạp thêm file mới **không nhân đôi và không xóa tin cũ**: tin chưa có thì thêm, tin đổi nội dung thì
  cập nhật, tin y hệt thì bỏ qua.

## Các bước (mỗi bước in số dòng vào/ra)

| Bước | Việc | Chạy lại |
|---|---|---|
| 1 Làm sạch | Chuẩn hóa, sửa diện tích sai dấu nghìn, đặt `None` + gắn `quality_flags` cho giá trị bất khả thi, bỏ trùng `listing_id` (giữ `posted_at` mới nhất), loại tin lỗi. Ghi `output/listings/` | Ghi đè |
| 2 Nạp `listings` | `INSERT ... ON CONFLICT (listing_id) DO UPDATE ... WHERE <có cột khác>` | Không nhân đôi; tin không đổi thì không ghi, `updated_at` giữ nguyên |
| 3 FK địa chỉ | `refresh_listing_address_ids()` điền `old_district_id`, `old_ward_id`, `new_ward_id` (khớp chính xác đúng 1 dòng, không thì `NULL`) | Tất định |
| 4 POI | `refresh_spatial_features()` tính 6 biến đếm 1 km/3 km + POI gần nhất cho tin có tọa độ | Tính lại toàn bộ |
| 5 Embedding | Tin có `content_hash` mới (hoặc chưa có vector) mới gọi API; còn lại chỉ cập nhật `rag_document` | Tăng dần, đứt giữa chừng chạy lại sẽ tiếp tục |

Đầu ra bước 1 (`output/listings/`): `listings_clean.jsonl`, `listings_rejected.jsonl`
(`listing_id`, `listing_url`, `title`, `reason`), `cleaning_report.json` (lý do loại, cờ chất lượng,
số ô trống). Tin hết hạn **không** bị loại (lọc đang tắt, xem `ListingCleaner._reject_reasons`).
Không lưu bản ghi gốc, hash file hay tên file nguồn.

## Số liệu thực

10/10/2026, `housing_dev`, chỉ `data.json` (DB đã có sẵn 7603 tin nên `inserted=0`):

```text
1/5 Làm sạch: input_lines=8570, duplicates_removed=720, unique_listings=7850, rejected=247, clean=7603
2/5 Nạp listings: rows_in=7603, inserted=0, updated=0, unchanged=7603
3/5 FK địa chỉ: listings_in_db=7603, old_district_id=7603, old_ward_id=7597, new_ward_id=7603, fk_changed=0
4/5 Đặc trưng POI: listings_with_geom=7342, spatial_rows=7342, refreshed=7342
5/5 Embedding: model=BAAI/bge-m3, listings=7603, embedded=0, unchanged=7603, embeddings_in_db=7603
```

14/11/2026, cả hai file, nạp vào bản sao `housing_dev` đã xóa trắng `listings` (POI có sẵn), lệnh ở mục "Chạy":

```text
1/5 Làm sạch: input_lines=17408, duplicates_removed=1495, unique_listings=15913, rejected=3342, clean=12571
     lý do loại: district_outside_old_hcm=2943, price_equals_price_per_m2=337, area_too_small=48, price_per_m2_out_of_range=14
2/5 Nạp listings: rows_in=12571, inserted=12571, updated=0, unchanged=0
3/5 FK địa chỉ: listings_in_db=12571, old_district_id=12571, old_ward_id=12213, new_ward_id=12224, fk_changed=12571
4/5 Đặc trưng POI: listings_with_geom=12242, spatial_rows=12242, refreshed=12242
```

Bản backup `housing_dev_20261114.dump` có 12931 tin: 12571 tin trên cộng 360 tin từ các lần nạp trước, không có
trong hai file hiện tại (pipeline không xóa tin cũ).

## Test

```powershell
$PY = (Resolve-Path .\.venv\Scripts\python.exe).Path
$env:DATABASE_URL = 'postgresql+asyncpg://postgres:<mật khẩu>@localhost:5433/housing_dev'
& $PY -m pytest src/tests -q     # không có DATABASE_URL thì 2 test nạp DB bị skip
uvx ruff check src
```

`test_listing_loader.py` chạy trong transaction rollback và chỉ chạy trên database tên `housing_dev`.
