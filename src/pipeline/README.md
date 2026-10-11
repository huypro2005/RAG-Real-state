# Pipeline tin đăng: dữ liệu thô → database

```text
CrawlData/data.json ─► ListingCleaner ─► listings (upsert) ─► refresh_listing_address_ids()
                                      └► data/listings/*     ─► refresh_spatial_features()
                                                              ─► (--embed) listing_embeddings
```

Bảng ở schema `public`, do Alembic tạo (`housing-backend/housing-backend`: `alembic upgrade head`,
rồi `scripts/seed_address.py` và bảng `pois`). Pipeline không tạo bảng.

## Chạy

Tại thư mục gốc dự án, dùng `.venv` gốc:

```powershell
$env:PYTHONIOENCODING = 'utf-8'
$env:DATABASE_URL = 'postgresql+asyncpg://postgres:<mật khẩu>@localhost:5432/housing_dev'
python -m src.pipeline                  # làm sạch, nạp, FK địa chỉ, POI
python -m src.pipeline --embed          # thêm embedding qua API Kaggle (cần EMBEDDING_API_URL/KEY trong .env)
python -m src.pipeline --embed-only     # chỉ embed tin đã có trong DB
python -m src.pipeline --input CrawlData/data.json CrawlData/data1.json   # ghép nhiều file crawl
python -m src.pipeline --db-url postgresql://...   # thay cho DATABASE_URL
```

- Database: `--db-url`, rồi `DATABASE_URL` (dạng `+asyncpg` của backend cũng được), rồi mặc định
  `housing_dev` trên localhost (user `postgres`, mật khẩu từ `PGPASSWORD`). Pipeline không tự ghi
  vào `housing`; muốn thì tự truyền URL.
- Embedding chạy trên Kaggle (`src/kaggle/embedding_server.ipynb`), máy này chỉ gọi API. Server tắt
  thì `--embed` dừng ngay với thông báo, không chạy model cục bộ.

## Các bước (mỗi bước in số dòng vào/ra)

| Bước | Việc | Chạy lại |
|---|---|---|
| 1 Làm sạch | Chuẩn hóa, sửa diện tích sai dấu nghìn, đặt `None` + gắn `quality_flags` cho giá trị bất khả thi, bỏ trùng `listing_id` (giữ `posted_at` mới nhất), loại tin lỗi. Ghi `data/listings/` | Ghi đè |
| 2 Nạp `listings` | `INSERT ... ON CONFLICT (listing_id) DO UPDATE ... WHERE <có cột khác>` | Không nhân đôi; tin không đổi thì không ghi, `updated_at` giữ nguyên |
| 3 FK địa chỉ | `refresh_listing_address_ids()` điền `old_district_id`, `old_ward_id`, `new_ward_id` (khớp chính xác đúng 1 dòng, không thì `NULL`) | Tất định |
| 4 POI | `refresh_spatial_features()` tính 6 biến đếm 1 km/3 km + POI gần nhất cho tin có tọa độ | Tính lại toàn bộ |
| 5 Embedding | Tin có `content_hash` mới (hoặc chưa có vector) mới gọi API; còn lại chỉ cập nhật `rag_document` | Tăng dần, đứt giữa chừng chạy lại sẽ tiếp tục |

Đầu ra bước 1 (`data/listings/`): `listings_clean.jsonl`, `listings_rejected.jsonl`
(`listing_id`, `listing_url`, `title`, `reason`), `cleaning_report.json` (lý do loại, cờ chất lượng,
số ô trống). Tin hết hạn **không** bị loại (lọc đang tắt, xem `ListingCleaner._reject_reasons`).
Không lưu bản ghi gốc, hash file hay tên file nguồn.

## Số liệu thực (10/10/2026, `housing_dev`, `data.json`)

Hai lần chạy `python -m src.pipeline --embed` liên tiếp cho cùng kết quả:

```text
1/5 Làm sạch: input_lines=8570, duplicates_removed=720, unique_listings=7850, rejected=247, clean=7603
     lý do loại: price_equals_price_per_m2=218, area_too_small=23, price_per_m2_out_of_range=6
2/5 Nạp listings: rows_in=7603, inserted=0, updated=0, unchanged=7603
3/5 FK địa chỉ: listings_in_db=7603, old_district_id=7603, old_ward_id=7597, new_ward_id=7603, fk_changed=0
4/5 Đặc trưng POI: listings_with_geom=7342, spatial_rows=7342, refreshed=7342
5/5 Embedding: model=BAAI/bge-m3, listings=7603, embedded=0, unchanged=7603, embeddings_in_db=7603
```

`housing_dev` đã có sẵn đúng 7603 tin từ trước nên lần chạy đầu `inserted=0`; toàn bộ 35 cột của 7603
dòng giống hệt trước khi chạy. Nạp từ bảng trống (DELETE trong transaction rồi rollback) cho
`inserted=7603`, `fk_changed=7603`, cùng số FK và `spatial_rows=7342` như trên. Embed lại 5 tin bị
xóa vector: `embedded=5`, vector mới lệch cosine < 3e-6 so với vector cũ.

`data1.json` (crawl cũ hơn, 13/09) trùng 3834/3901 `listing_id` với `data.json`; ghép cả hai cho 7671 tin sạch
(thêm 68). Mặc định chỉ dùng `data.json`.

## Test

```powershell
$env:DATABASE_URL = 'postgresql+asyncpg://postgres:<mật khẩu>@localhost:5432/housing_dev'
python -m pytest src/tests -q     # 20 passed; không có DATABASE_URL thì 2 test nạp DB bị skip
uvx ruff check src
```

`test_listing_loader.py` chạy trong transaction rollback và chỉ chạy trên database tên `housing_dev`.
