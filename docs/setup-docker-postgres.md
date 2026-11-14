# Chạy PostgreSQL (PostGIS + pgvector) bằng Docker

Database chạy trong container Docker **`housing-postgres`**, **cổng 5433** trên máy (5432 trong container),
user `postgres`. Container giữ hai DB:

| DB | Vai trò |
|---|---|
| `housing_dev` | DB làm việc: backend, pipeline, Prediction Server đều dùng |
| `housing` | DB cũ (5 schema `listing`, `rag`, `amenities`, `ml`, `admin`), **chỉ đọc**; nguồn POI cho `migrate_legacy_data.py` |

Lý do dùng Docker: Windows Smart App Control chặn `vector.dll` (pgvector) khi cài Postgres trực tiếp; trong
container Linux thì không bị. Postgres cài sẵn trên Windows (cổng 5432) là bản cũ, các hướng dẫn dưới đây
**không đụng** tới nó.

> ✅ = **bỏ qua được nếu đã làm** (lệnh kiểm tra ngay dưới).
> Mọi lệnh viết cho **PowerShell**, chạy tại **thư mục gốc dự án** trừ khi ghi khác.
> (Git Bash: thêm `MSYS_NO_PATHCONV=1` trước `docker exec`/`docker cp` có đường dẫn `/tmp/...`.)

Tên file dump thống nhất: `backup\housing_dev_YYYYMMDD.dump` và `backup\housing_YYYYMMDD.dump`
(cách tạo: [backup/README.md](../backup/README.md)).

## 1. Bật Docker Desktop
✅ Bỏ qua nếu `docker info` không báo lỗi.

Mở Docker Desktop, chờ "Engine running".

## 2. Tạo `src/web/housing-backend/.env`
✅ Bỏ qua nếu file đã có và chứa `POSTGRES_USER=postgres`, `POSTGRES_DB=housing_dev`, `POSTGRES_PORT=5433`.

```powershell
Copy-Item src\web\housing-backend\.env.example src\web\housing-backend\.env
notepad src\web\housing-backend\.env
```

Đổi `POSTGRES_PASSWORD` và **cùng mật khẩu đó** trong `DATABASE_URL` (để nguyên giá trị mẫu cũng chạy được, chỉ
nên dùng trên máy cá nhân). Mật khẩu chỉ có tác dụng **lần đầu tạo volume**; đổi sau đó phải đổi bằng SQL
(`ALTER USER postgres PASSWORD '...'`) hoặc xóa volume (mục "Xóa sạch").

## 3. Bật container và chờ sẵn sàng
✅ Bỏ qua nếu `docker ps` thấy `housing-postgres ... (healthy)`.

```powershell
cd src\web\housing-backend
docker compose up -d db        # lần đầu tự build image (cần Internet), vài phút
cd ..\..\..
do { Start-Sleep 3 } until ((docker exec housing-postgres pg_isready -h 127.0.0.1 -U postgres -d housing_dev) -match 'accepting')
```

Lần đầu có dòng `pull access denied for housing-postgres` là bình thường (image không có trên Docker Hub nên
compose tự build). Vòng `do ... until` chờ tới khi Postgres nhận kết nối qua TCP, tức là đã chạy xong bước khởi tạo lần đầu
(tránh xóa/tạo DB trong lúc script khởi tạo của image còn chạy). Dữ liệu nằm trong volume
`housing-backend_pgdata`, tắt/bật container không mất.

## 4. Nạp dữ liệu: chọn **một** trong hai đường
✅ Bỏ qua cả mục 4 nếu lệnh này in số lớn hơn 0:
```powershell
docker exec housing-postgres psql -U postgres -d housing_dev -At -c "select count(*) from listings"
```
(Báo lỗi `relation "listings" does not exist` nghĩa là DB còn trống: làm tiếp.)

### 4A. Đã có backup trong `backup\` (nhanh, đủ dữ liệu kể cả vector)

Khôi phục `housing_dev` (bắt buộc) và `housing` (nếu có file `backup\housing_YYYYMMDD.dump`):

```powershell
$stamp = '20261114'   # ĐỔI thành ngày trong tên file bạn có (xem: ls backup\*.dump)
docker exec housing-postgres psql -U postgres -d postgres -c "DROP DATABASE IF EXISTS housing_dev WITH (FORCE)" -c "CREATE DATABASE housing_dev"
docker cp "backup\housing_dev_$stamp.dump" housing-postgres:/tmp/r.dump
docker exec housing-postgres pg_restore -U postgres -d housing_dev --no-owner --exit-on-error /tmp/r.dump
docker exec housing-postgres psql -U postgres -d postgres -c "DROP DATABASE IF EXISTS housing WITH (FORCE)" -c "CREATE DATABASE housing"
docker cp "backup\housing_$stamp.dump" housing-postgres:/tmp/r.dump
docker exec housing-postgres pg_restore -U postgres -d housing --no-owner --exit-on-error /tmp/r.dump
docker exec housing-postgres rm -f /tmp/r.dump
```

- `DROP DATABASE` chỉ xóa DB **trong container**, không đụng Postgres cài trên Windows. Nó cần thiết vì
  container mới đã tạo sẵn `housing_dev` có extension PostGIS, `pg_restore` vào đó sẽ báo `already exists`.
- `pg_restore` không in gì là thành công. Không có file `housing_*.dump` thì bỏ 3 dòng `housing` (DB cũ chỉ cần
  cho `migrate_legacy_data.py` và notebook).

Kiểm tra (so với số đã ghi lúc backup, xem [backup/README.md](../backup/README.md)):

```powershell
docker exec housing-postgres psql -U postgres -d housing_dev -At -c "select (select count(*) from listings), (select count(*) from pois), (select count(*) from listing_embeddings), (select count(*) from price_model_runs), (select count(*) from wards_new)"
docker exec housing-postgres psql -U postgres -d housing -At -c "select (select count(*) from listing.listings), (select count(*) from amenities.housing_poi), (select count(*) from ml.district_label)"
```

Dump đã chứa bảng `alembic_version` nên **không** cần chạy `alembic upgrade head` sau khi khôi phục (chạy cũng
không sao). Nhớ chép lại thư mục `models\` từ `backup\models_YYYYMMDD\` nếu có (DB chỉ lưu đường dẫn mô hình).

### 4B. Chưa có backup: dựng từ đầu

Thứ tự: tạo bảng → địa chỉ → POI → tin đăng (pipeline) → (tùy chọn) embedding. Bước POI phải xong **trước**
pipeline vì pipeline tính đặc trưng "số trường/bệnh viện/chợ quanh nhà" từ bảng `pois`.

**B1. Tạo bảng, extension, hàm SQL** ✅ bỏ qua nếu `alembic current` in `0006 (head)`.

```powershell
$PY = (Resolve-Path .\.venv\Scripts\python.exe).Path
cd src\web\housing-backend
$env:DATABASE_URL = ((Get-Content .env) -match '^DATABASE_URL=')[0] -replace '^DATABASE_URL=', ''
& $PY -m alembic upgrade head
& $PY -m alembic current          # phải in 0006 (head)
```

Dòng `$env:DATABASE_URL = ...` lấy `DATABASE_URL` từ `.env` của backend (Alembic tự đọc `.env`, còn các script ở
B2–B3 chỉ đọc biến môi trường).

**B2. Nạp địa chỉ** ✅ bỏ qua nếu `select count(*) from wards_new` ra `169`.

```powershell
& $PY scripts\seed_address.py     # vẫn ở src\web\housing-backend, cùng cửa sổ với B1
cd ..\..\..
```

In số dòng từng bảng (`provinces_old` 63, `districts_old` 24, `wards_new` 169, `ward_mappings` 270...).

> ⚠️ **Lỗi đã biết (14/11/2026):** script đang tìm dữ liệu ở `src/web/address_data` (đường dẫn cũ) nên báo
> `FileNotFoundError`; dữ liệu thật ở `data/address_data`. Cần sửa `AddressSeeder.DATA_DIR` trong
> `scripts/seed_address.py` thành `Path(__file__).resolve().parents[4] / "data" / "address_data"` (đã thử bằng
> cách gán `DATA_DIR` lúc chạy: nạp đủ, số dòng khớp bản backup).

**B3. Nạp POI (trường học, bệnh viện, chợ) vào `pois`**

Cách duy nhất đang chạy được là chép từ DB `housing` cũ (cần file `backup\housing_YYYYMMDD.dump`, khôi phục như
3 dòng `housing` ở mục 4A):

```powershell
cd src\web\housing-backend
$src = $env:DATABASE_URL -replace '/housing_dev$', '/housing'
& $PY scripts\migrate_legacy_data.py --source-url $src --target-url $env:DATABASE_URL
cd ..\..\..
```

Script chép từ `housing` cũ: tin đăng (7603), đặc trưng không gian, POI (`pois` 5267 dòng), nhãn quận
`district_label` (24 dòng), rồi nối FK địa chỉ. Chạy lại không nhân đôi. (Bản backup `housing_dev` có 5451 POI: thêm
184 trường ĐH/CĐ từ `scripts/import_universities.py`, script này đọc `CrawUltilities/poi_master.csv` hiện không có
trong repo.)

> ⚠️ **Chưa có cách nạp POI khi không có DB `housing` cũ.** CSV gốc ở `src/crawl/dataUltilities/*.csv` nhưng
> `tools/import_pois.py` đã lỗi thời (ghi vào schema `amenities` của thiết kế cũ, đọc thư mục
> `vietnamadminunits/` không còn trong repo). Không có POI thì pipeline vẫn nạp được tin nhưng mọi đặc trưng
> "số trường/bệnh viện/chợ quanh nhà" bằng 0 và bảng `district_label` trống.

**B4. Nạp tin đăng** bằng pipeline: [src/pipeline/README.md](../src/pipeline/README.md) (lệnh ở README gốc, bước 5).

## 5. Kiểm tra đủ PostGIS và pgvector
✅ Bỏ qua nếu đã thấy kết quả này ở lần chạy trước.

```powershell
docker exec housing-postgres psql -U postgres -d housing_dev -c "select '[1,2,3]'::vector <=> '[1,2,4]'::vector as cosine, postgis_version()"
```

In ra một số và phiên bản PostGIS là đúng. Lỗi `type "vector" does not exist`: DB chưa có extension, làm lại
mục 4 (4A hoặc B1).

## 6. Trỏ ứng dụng sang DB trong Docker
✅ Bỏ qua nếu ba file `.env` dưới đây đã chứa `localhost:5433/housing_dev` với cùng mật khẩu.

| File | `DATABASE_URL` |
|---|---|
| `src/web/housing-backend/.env` | `postgresql+asyncpg://postgres:<mật khẩu>@localhost:5433/housing_dev` |
| `src/pipeline/.env` | `postgresql://postgres:<mật khẩu>@localhost:5433/housing_dev` |
| `src/web/prediction_server/.env` | `postgresql://postgres:<mật khẩu>@localhost:5433/housing_dev` |

Sửa xong thì khởi động lại các dịch vụ đang chạy.

---

## Backup và khôi phục

- **Backup** (định kỳ hoặc trước khi xóa container): [backup/README.md](../backup/README.md) — có điều kiện bắt
  buộc, lệnh backup cả hai DB và lệnh kiểm tra bản backup.
- **Khôi phục:** mục **4A** ở trên.

## Vận hành

```powershell
cd src\web\housing-backend
docker compose up -d db      # bật
docker compose stop db       # tắt (giữ dữ liệu)
cd ..\..\..
docker exec -it housing-postgres psql -U postgres -d housing_dev    # vào psql
```

## Xóa sạch để làm lại từ đầu

⚠️ Xóa **toàn bộ dữ liệu** trong container. Backup trước ([backup/README.md](../backup/README.md)).

```powershell
cd src\web\housing-backend
docker compose down -v                               # xóa container housing-postgres + volume housing-backend_pgdata
docker rmi housing-postgres:18-postgis-pgvector      # (tùy chọn) xóa image, lần bật sau build lại
cd ..\..\..
```

Chỉ xóa đồ của dự án này; không ảnh hưởng container/volume khác hay Postgres cài trên Windows. Dựng lại: mục 3
rồi 4A.

## (Tùy chọn) Chuyển dữ liệu từ Postgres cài trên Windows (cổng 5432)
✅ Bỏ qua nếu đã có file trong `backup\` (dùng 4A) hoặc dựng từ đầu (4B).

```powershell
$stamp = Get-Date -Format yyyyMMdd
$env:PGPASSWORD = Read-Host 'Mật khẩu Postgres trên Windows'
& 'C:\Program Files\PostgreSQL\18\bin\pg_dump.exe' -h localhost -p 5432 -U postgres -d housing_dev -Fc --no-owner --exclude-table-data=listing_embeddings -f "backup\housing_dev_$stamp.dump"
Remove-Item Env:PGPASSWORD
```

`--exclude-table-data=listing_embeddings` là bắt buộc: Postgres trên Windows không đọc được kiểu `vector`
(Smart App Control). Bản dump này **không có vector**: sau khi khôi phục (4A) phải tạo lại embedding (README gốc,
bước 6). DB `housing` cũ: đổi `-d housing_dev` thành `-d housing`, `--exclude-table-data=rag.listing_embeddings`,
tên file `housing_$stamp.dump`.

## Sự cố thường gặp

| Triệu chứng | Cách xử lý |
|---|---|
| `port is already allocated` | Cổng 5433 bận: đổi `POSTGRES_PORT` và ba `DATABASE_URL` |
| `failed to connect to the docker API` / `error during connect` | Docker Desktop chưa chạy (mục 1) |
| `password authentication failed` | Mật khẩu trong `DATABASE_URL` khác `POSTGRES_PASSWORD` lúc tạo volume |
| `pg_restore: error: ... already exists` | DB đích chưa trống: chạy đúng dòng `DROP DATABASE ... CREATE DATABASE` của mục 4A |
| `database "housing_dev" is being accessed by other users` | Tắt backend/Prediction Server/notebook đang kết nối (lệnh 4A đã có `WITH (FORCE)`) |
| Python báo `DLL load failed ... Application Control policy has blocked this file` khi chạy backend / Prediction Server | Smart App Control chặn file `.pyd` không chữ ký trong `.venv` (14/11/2026: `scikit-learn` của Prediction Server bị chặn). Docker cho DB không giải quyết phần này; xem README gốc, mục "Sự cố" |
