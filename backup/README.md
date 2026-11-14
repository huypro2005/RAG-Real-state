# Backup database (Postgres chạy trong Docker)

Thư mục này chứa file sao lưu PostgreSQL. **File dump không được commit** (`.gitignore` bỏ qua `*.dump`,
`*.sql`, `*.dat.gz`, `toc.dat`, `*.joblib`): chúng nặng và chứa dữ liệu thật. Chỉ `README.md` này nằm trong git.

**Quy ước tên duy nhất** (dùng cho cả backup định kỳ lẫn chuyển dữ liệu / khôi phục sang máy khác):

| DB | File |
|---|---|
| `housing_dev` (DB làm việc) | `backup\housing_dev_YYYYMMDD.dump` |
| `housing` (DB cũ, chỉ đọc) | `backup\housing_YYYYMMDD.dump` |
| file mô hình `models\` | thư mục `backup\models_YYYYMMDD\` |

`YYYYMMDD` là ngày backup. Backup lại trong cùng ngày sẽ ghi đè file của ngày đó.

> ⚠️ **Backup từ container Docker (`housing-postgres`, cổng 5433), không dùng `pg_dump` cài trên Windows.**
> `pg_dump` của Postgres cài trực tiếp đọc bảng `listing_embeddings` sẽ lỗi
> `could not load library ... vector.dll: An Application Control policy has blocked this file`.
> Postgres trong Docker không bị chặn, dump có đủ cả vector.

Mọi lệnh viết cho **PowerShell**, chạy tại **thư mục gốc dự án**.

## Yêu cầu BẮT BUỘC trước khi backup

Chưa đủ cả năm mục thì **không** backup.

1. **Container đang chạy:** `docker ps` thấy `housing-postgres ... (healthy)`. Chưa bật: xem
   [docs/setup-docker-postgres.md](../docs/setup-docker-postgres.md) mục 3.
2. **Dừng mọi thứ đang ghi vào DB:** tắt Prediction Server (8100) và backend (8000); không chạy
   `python -m src.pipeline`, `train_price_model.py`, `seed_address.py`. Kiểm tra:
   ```powershell
   docker exec housing-postgres psql -U postgres -d housing_dev -At -c "select count(*) from price_model_runs where status = 'running'"   # phải là 0
   docker exec housing-postgres psql -U postgres -d housing_dev -At -c "select count(*) from pg_stat_activity where datname in ('housing_dev', 'housing') and pid <> pg_backend_pid()"   # nên là 0
   ```
   Có dòng `running` còn sót (job bị ngắt) thì xử lý trước, kẻo khôi phục lại mang theo trạng thái sai.
3. **Schema ở phiên bản mới nhất:**
   ```powershell
   $PY = (Resolve-Path .\.venv\Scripts\python.exe).Path
   cd src\web\housing-backend; & $PY -m alembic current; & $PY -m alembic check; cd ..\..\..
   ```
   Phải in `0006 (head)` và `No new upgrade operations detected.` (Alembic đọc `DATABASE_URL` từ
   `src\web\housing-backend\.env`.)
4. **Đủ chỗ trống:** cần khoảng 1–2 lần kích thước DB (bản `housing_dev` 14/11/2026 nặng ~75 MB).
5. **Sao lưu kèm ngoài DB:** DB chỉ lưu đường dẫn mô hình (`price_model_runs.artifact_path`), không lưu file
   `.joblib`; sao lưu thư mục `models\` cùng lúc (lệnh dưới). File `.env` (khóa OpenAI/Goong/embedding) cất riêng
   ở nơi an toàn, **không bao giờ** đưa vào git.

## Cách backup

```powershell
$stamp = Get-Date -Format yyyyMMdd
docker exec housing-postgres pg_dump -U postgres -d housing_dev -Fc --no-owner -f /tmp/b.dump
docker cp housing-postgres:/tmp/b.dump "backup\housing_dev_$stamp.dump"
docker exec housing-postgres pg_dump -U postgres -d housing -Fc --no-owner -f /tmp/b.dump
docker cp housing-postgres:/tmp/b.dump "backup\housing_$stamp.dump"
docker exec housing-postgres rm -f /tmp/b.dump
New-Item -ItemType Directory -Force "backup\models_$stamp" | Out-Null
Copy-Item -Force models\* "backup\models_$stamp\"
```

- Container không có DB `housing` thì bỏ hai dòng `-d housing`.
- `docker cp` in `Successfully copied ...` là bình thường.
- Dump `-Fc` đã nén, chứa extension (`postgis`, `vector`...), hàm SQL, bảng `alembic_version` và dữ liệu mọi
  bảng, **kể cả vector**.

## Kiểm tra bản backup (bắt buộc sau khi backup)

Bản backup chưa kiểm chứng coi như chưa có. Khôi phục thử vào DB tạm `housing_test` rồi so số dòng với DB gốc.
Chạy ngay trong cửa sổ vừa backup (dùng lại `$stamp`):

```powershell
docker exec housing-postgres psql -U postgres -d postgres -c "CREATE DATABASE housing_test"
docker cp "backup\housing_dev_$stamp.dump" housing-postgres:/tmp/t.dump
docker exec housing-postgres pg_restore -U postgres -d housing_test --no-owner --exit-on-error /tmp/t.dump
docker exec housing-postgres psql -U postgres -d housing_test -At -c "select (select count(*) from listings), (select count(*) from pois), (select count(*) from listing_embeddings), (select count(*) from price_model_runs), (select count(*) from wards_new)"
docker exec housing-postgres psql -U postgres -d housing_dev -At -c "select (select count(*) from listings), (select count(*) from pois), (select count(*) from listing_embeddings), (select count(*) from price_model_runs), (select count(*) from wards_new)"
docker exec housing-postgres psql -U postgres -d postgres -c "DROP DATABASE housing_test"
docker exec housing-postgres rm -f /tmp/t.dump
```

Hai dòng số in ra (`listings|pois|listing_embeddings|price_model_runs|wards_new`) phải giống nhau. Bản `housing`:
thay `housing_dev_$stamp` bằng `housing_$stamp` và dùng câu đếm
`select (select count(*) from listing.listings), (select count(*) from amenities.housing_poi), (select count(*) from ml.district_label)`
cho cả `housing_test` lẫn `housing`.

## Khôi phục

Làm theo [docs/setup-docker-postgres.md](../docs/setup-docker-postgres.md) **mục 4A** (xóa và tạo lại DB trong
container rồi `pg_restore`). Sau đó chép lại mô hình:
`Copy-Item -Force backup\models_YYYYMMDD\* models\` (đổi `YYYYMMDD` thành ngày của bản bạn có), bật Prediction
Server, `GET http://localhost:8100/api/v1/health` phải báo có model đang hoạt động.

## File hiện có trong thư mục này

| File | Ý nghĩa |
|---|---|
| `housing_dev_20261114.dump` | `housing_dev` đầy đủ, **có vector**. Kiểm chứng 14/11/2026: `listings` 12931, `pois` 5451, `listing_embeddings` 12931, `price_model_runs` 2, `wards_new` 169 |
| `housing_20261114.dump` | DB cũ `housing`. Kiểm chứng 14/11/2026: `listing.listings` 7603, `amenities.housing_poi` 5267, `ml.district_label` 24, `rag.listing_embeddings` 0 |
| `models_20261114\` | File mô hình `price_run_*.joblib` (thư mục con `models\` bên trong là bản chép trùng của lệnh cũ) |
| `housing_dev_for_docker.dump`, `housing_legacy_for_docker.dump` | **Bản cũ** (tên cũ), dump từ Postgres trên Windows, không có dữ liệu `listing_embeddings`. Giữ để tham khảo, không dùng trong hướng dẫn |
| `toc.dat`, `*.dat.gz` | **Bản cũ** dạng thư mục (thiết kế 5 schema), chỉ để tham khảo |

## Lưu ý an toàn

- Dump chứa dữ liệu thật: đừng gửi qua kênh công khai hay đưa vào git (lỡ commit thì phải xóa khỏi cả lịch sử).
- Dump cũ `housing_before_public_20261009.dump` và `data_ultilities.sql` từng có trong git nên vẫn nằm trong lịch
  sử; muốn gỡ hẳn phải viết lại lịch sử (`git filter-repo`), `git rm` là không đủ.
- Giữ ít nhất hai bản gần nhất, và một bản ở ổ khác máy.
- `docker compose down -v` xóa volume (toàn bộ dữ liệu DB): luôn backup và kiểm tra bản backup trước.
