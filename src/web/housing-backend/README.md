# housing-backend

Database cho chatbot tư vấn bất động sản TP.HCM.
PostgreSQL + PostGIS + pgvector · SQLAlchemy 2.0 (async) · Alembic · FastAPI.

**Mọi bảng nằm trong schema mặc định `public`.** Cấu trúc DB chỉ có một nguồn chuẩn: model
SQLAlchemy trong `app/db/models/` + migration Alembic. Thiết kế chi tiết: `docs/database.md` ở
thư mục gốc dự án.

## Cấu trúc thư mục

```
housing-backend/
├── app/
│   ├── db/
│   │   ├── base.py             # Base, quy ước tên constraint, map kiểu Python -> Postgres
│   │   ├── session.py          # kết nối async + get_session cho FastAPI
│   │   └── models/
│   │       ├── admin_units.py  #   7 bảng địa chỉ batdongsan + ward_mappings
│   │       ├── district.py     #   DistrictLabel
│   │       ├── poi.py          #   Poi (trường học, bệnh viện, chợ)
│   │       └── listing.py      #   Listing, ListingSpatialFeatures, ListingEmbedding
│   ├── repositories/           # hàm truy vấn DB
│   ├── schemas/                # Pydantic cho request/response API
│   ├── api/                    # router FastAPI
│   └── main.py
├── migrations/versions/
│   ├── 0001_baseline.py        # extension, toàn bộ bảng, 3 function SQL (bên dưới)
│   └── 0002 … 0006             # trgm tên POI, khóa chính thay thế, price_model_runs (+ charts)
├── docker-compose.yml          # service db (container housing-postgres, cổng 5433)
├── scripts/
│   ├── fetch_bds_address.py    # tải phường/đường SG từ API batdongsan -> data/address_data/*.json
│   ├── seed_address.py         # nạp data/address_data/ vào 7 bảng địa chỉ + ward_mappings
│   ├── migrate_legacy_data.py  # chuyển dữ liệu từ DB cũ `housing` (5 schema) sang bảng mới, gồm POI
│   ├── import_universities.py  # thêm ĐH/CĐ vào pois (đọc CrawUltilities/poi_master.csv, hiện không có trong repo)
│   ├── train_price_model.py    # train mô hình giá cục bộ (dự phòng khi không có Prediction Server)
│   ├── fix_backup.ps1 / .sh    # (cũ) sửa file backup 5 schema
└── db/legacy/                  # SQL/model cũ, chỉ để tham khảo, không còn dùng
```

## Bảng

| Bảng | Model | Khóa chính | Ý nghĩa |
|---|---|---|---|
| `provinces_old` / `provinces_new` | `ProvinceOld` / `ProvinceNew` | `code` (`'SG'`) | Tỉnh trước / từ 2025 (63 / 34) |
| `districts_old` | `DistrictOld` | `id` (districtId) | 24 quận/huyện cũ của SG |
| `wards_old` | `WardOld` | `id` (wardId) | Phường/xã cũ, FK `district_id` |
| `streets_old` | `StreetOld` | `(id, district_id)` | Đường theo quận cũ |
| `wards_new` | `WardNew` | `id` (wardId) | Phường/xã mới của SG, FK `province_code` |
| `streets_new` | `StreetNew` | `(id, ward_id)` | Đường theo phường mới |
| `ward_mappings` | `WardMapping` | `old_ward_id` | Phường cũ -> phường mới (từ `ward_mappings.sql`) |
| `district_label` | `DistrictLabel` | `(model_version, label)` | Nhãn quận cho model giá, FK `district_id` |
| `pois` | `Poi` | `id` (tự tăng) | Trường học / bệnh viện / chợ (`poi_type`) |
| `listings` | `Listing` | `listing_id` (mã tin) | Tin đăng, FK `old_district_id`, `old_ward_id`, `new_ward_id` |
| `listing_spatial_features` | `ListingSpatialFeatures` | `listing_id` | Số POI 1 km/3 km + POI gần nhất |
| `listing_embeddings` | `ListingEmbedding` | `listing_id` | Vector 1024 chiều (bge-m3) |

ID trong bảng địa chỉ là **ID của batdongsan**, không phải mã hành chính (`'79'`, `'760'`).
Cùng một `streetId` có thể xuất hiện ở nhiều quận/phường nên bảng đường dùng khóa ghép.

Cột có `Computed(...)` (`geom`) do Postgres tự tính từ `latitude/longitude`, **không gán** khi
insert.

Function (tạo trong migration 0001):

```sql
SELECT * FROM nearby(106.70, 10.77, 1000, 'truong_hoc');  -- (poi_id = pois.id, poi_type, name, distance_m)
SELECT refresh_spatial_features();                          -- tính lại listing_spatial_features
SELECT refresh_listing_address_ids();                       -- điền FK địa chỉ của listings (khớp đúng 1, NFC)
```

## Dựng DB và chạy backend

DB chạy trong Docker (container `housing-postgres`, cổng 5433, `docker-compose.yml` ở thư mục này). Các bước bật
container, khôi phục từ `backup\` (đường nhanh) hoặc dựng từ đầu (Alembic → `seed_address.py` →
`migrate_legacy_data.py`): **[docs/setup-docker-postgres.md](../../../docs/setup-docker-postgres.md)** mục 3–4.
Cấu hình ở `.env` của thư mục này (copy từ `.env.example`).

Chạy backend (PowerShell, tại thư mục gốc dự án, sau khi DB và Prediction Server đã bật):

```powershell
$PY = (Resolve-Path .\.venv\Scripts\python.exe).Path
cd src\web\housing-backend; & $PY -m uvicorn app.main:app --port 8000     # http://127.0.0.1:8000/docs
```

- `scripts/fetch_bds_address.py` chỉ cần khi `data/address_data/` (ở gốc dự án) chưa có `sg_*_wards/streets.json`;
  nó gọi API batdongsan.
- `seed_address.py` và `migrate_legacy_data.py` đều upsert, chạy lại nhiều lần kết quả không đổi.
- `seed_address.py` ghi các dòng mapping không nối được vào
  `data/address_data/ward_mappings_unmatched.json` (kèm lý do).
- `migrate_legacy_data.py` chỉ đọc DB nguồn (`default_transaction_read_only`), in số dòng
  nguồn/đích và số tin khớp FK địa chỉ.
- Windows: `alembic.ini` chỉ được chứa ký tự ASCII (Alembic đọc file bằng encoding hệ điều hành).

Tin mới từ crawler nạp bằng `python -m src.pipeline` ở thư mục gốc dự án; embedding cho tin đã
có trong DB: `python -m src.pipeline --embed-only`.

## Khi cấu trúc DB thay đổi

1. Sửa model trong `app/db/models/`.
2. `alembic revision --autogenerate --rev-id 0002 -m "them cot xyz"`
3. **Đọc lại file migration vừa sinh.** Autogenerate không nhận ra:
   - Đổi tên cột: nó sinh lệnh xóa cột rồi thêm cột mới, làm mất dữ liệu. Sửa thành
     `op.alter_column(..., new_column_name=...)`.
   - Thay đổi function hoặc biểu thức `Computed`: phải tự viết `op.execute("CREATE OR REPLACE ...")`.
4. `alembic upgrade head`, rồi `alembic check` phải báo "No new upgrade operations detected".

## Gọi function từ Python

```python
await session.execute(select(func.refresh_spatial_features()))
rows = await PoiRepository(session).nearby(106.70, 10.77, radius_m=1000, poi_type="truong_hoc")
```

## Mode dự đoán giá (`mode: "prediction"`)

Dùng lại mô hình RandomForest của đồ án 1 (spec: `docs/tasks/prediction-mode.md`). Đồ án 1 không
có file `.pkl`, nên phải train lại một lần (khoảng 1 phút, cần `scikit-learn`):

```powershell
# tại src\web\housing-backend, $PY như mục "Dựng DB và chạy backend"
$env:PYTHONPATH = '.'; & $PY scripts\train_price_model.py
```

Script chép `data.csv` của đồ án 1 sang `data/price_training.csv`, in RMSE/MAE/R² (trên giá/m²) và
lưu `models/price_rf.joblib` + `models/price_rf.metrics.json`. Thư mục `models/` đã nằm trong
`.gitignore` (file ~110 MB, không commit). Chưa train thì `POST /api/v1/chat` với
`mode: "prediction"` trả 503, mode recommendation vẫn chạy bình thường.

Cần trong `src/web/housing-backend/.env`: `OPENAI_API_KEY` (trích xuất trường bằng gpt-4o-mini), `GOONG_API_KEY`
(geocode địa chỉ; lỗi thì dùng tâm các tin đăng của quận trong bảng `listings`).

```powershell
# tại src\web\housing-backend
& $PY -m uvicorn app.main:app --port 8011
& $PY tests\prediction\run_live.py http://localhost:8011   # kịch bản thật, tốn phí nhỏ (cửa sổ khác)
& $PY -m pytest tests\prediction                          # unit test, không gọi OpenAI/Goong
```

Lưu ý về độ tin cậy:

- Khung lọc toạ độ khi train mở rộng theo địa giới TP.HCM cũ (lat 10,37–11,17, lon 106,35–107,03,
  `constants.py`, dùng chung với khung chấp nhận điểm Goong). Gốc của đồ án 1 (lon ≤ 106,8) làm mất
  ~2.700 dòng của Quận 9 đông, Thủ Đức và Cần Giờ (nhãn quận của chúng đều hợp lệ). Đây là điểm duy
  nhất khác `retrain.py`; mô hình và cách làm giữ nguyên. Cần Giờ vẫn ít mẫu (79 dòng ở lon > 106,8)
  nên các cặp quận × loại thưa còn kém tin cậy, xem cảnh báo bên dưới.
- "Khoảng tham khảo" trong câu trả lời là phân vị 10–90 của dự đoán từng cây trong rừng, **không
  phải khoảng tin cậy**. Reviewer đo thực nghiệm trên tập test (vòng 2): khoảng này chứa giá thật ở 71,8% mẫu.
- R² trên giá/m² của tập test: xem `models/price_rf.metrics.json` (đồ án 1 gốc: 0,5635).

Quy tắc cảnh báo trong câu trả lời (`prediction.warnings`, dòng "Lưu ý"):

- "Dữ liệu huấn luyện ở khu vực/loại này rất ít": khi cặp quận + loại nhà có dưới 10 mẫu trong
  tập train (không có khoá `"<quận>|<loại>"` trong `models/price_rf.metrics.json`).
- "Các cây trong mô hình bất đồng nhiều": khi phân vị 90 / phân vị 10 của các cây > 3.
- Cảnh báo chỉ báo mức tin cậy, không chỉnh con số của mô hình.

Địa chỉ: code bỏ loại nhà, tên quận và từ đệm ("chung cư", "hẻm xe hơi", "trong"...) khỏi địa chỉ
LLM trích; không còn tên riêng (đường, dự án, số nhà) thì dùng tâm quận từ bảng `listings`.
Goong giới hạn 1.000 lượt/ngày; hết hạn mức thì toàn bộ tin dùng tâm quận.
