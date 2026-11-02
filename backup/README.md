# Backup database

Thư mục này chứa các bản sao lưu PostgreSQL của dự án. **File dump không được commit** (đã nằm trong
`.gitignore`: `*.dump`, `*.sql`, `*.dat.gz`, `toc.dat`) vì nặng và chứa dữ liệu thật.
Chỉ `README.md` này nằm trong git.

## Nội dung hiện có

| File | Ý nghĩa |
|---|---|
| `housing_before_public_20261009.dump` | Dump DB `housing` thật trước khi chuyển sang schema `public` (định dạng custom, `pg_dump -Fc`) |
| `data_ultilities.sql` | Dump SQL cũ của dữ liệu tiện ích |
| `toc.dat`, `*.dat.gz` | Dump cũ 5 schema dạng thư mục (`pg_dump -Fd`), chỉ để tham khảo |

## Yêu cầu BẮT BUỘC trước khi backup

Chưa đủ cả sáu mục thì **không** backup: bản sao lưu dở dang hoặc không khôi phục được còn nguy hiểm
hơn không có bản nào.

1. **Dùng đúng công cụ.** `pg_dump`/`pg_restore` cùng phiên bản (hoặc mới hơn) server: máy này là
   PostgreSQL 18, ở `C:\Program Files\PostgreSQL\18\bin\` (không có trong PATH). Kiểm tra bằng
   `pg_dump --version`.
2. **Dừng mọi thứ đang ghi vào DB.** Tắt Prediction Server (cổng 8100) và backend (cổng 8000), không chạy
   `python -m src.pipeline`, `train_price_model.py`, `seed_address.py`, `migrate_legacy_data.py`.
   Kiểm tra không còn job đang chạy:
   ```sql
   SELECT id, status FROM price_model_runs WHERE status = 'running';   -- phải trả 0 dòng
   SELECT count(*) FROM pg_stat_activity WHERE datname = 'housing' AND state <> 'idle' AND pid <> pg_backend_pid();  -- nên là 0
   ```
   Một dòng `running` còn sót (job bị ngắt) phải được xử lý trước, vì khôi phục lại sẽ mang theo trạng thái
   sai và khóa advisory retrain không còn ý nghĩa.
3. **Schema đã ở phiên bản mới nhất.** `alembic current` phải bằng `alembic heads` (hiện là `0006`), và
   `alembic check` báo "No new upgrade operations detected". Không backup khi migration đang dở.
4. **Đủ chỗ trống và thư mục đích đúng.** Dump của `housing` cần khoảng 1–2 lần kích thước DB; đặt vào
   `backup/` (đã ignore) hoặc ổ khác. Đặt tên có ngày: `housing_YYYYMMDD.dump`. Không ghi đè bản trước.
5. **Có sao lưu kèm ngoài DB.** DB chỉ lưu đường dẫn mô hình (`price_model_runs.artifact_path`), không lưu
   file `.joblib`. Sao lưu cả thư mục `models/` (gốc dự án) và `src/web/housing-backend/models/` cùng thời
   điểm, nếu không thì sau khôi phục các phiên bản mô hình sẽ trỏ vào file không còn. File `.env` (khóa
   OpenAI/Goong/embedding) cũng phải cất riêng ở nơi an toàn: dump không chứa nó và **không bao giờ** đưa
   nó vào git.
6. **Biết rõ DB nào đang sao lưu.** `housing` là DB thật; `housing_dev` là DB thử nghiệm. Kiểm tra
   `DATABASE_URL`/`-d` trước khi chạy, và không dùng mật khẩu gõ thẳng trong lệnh (dùng `PGPASSWORD` hoặc
   `pgpass`).

## Cách backup

PowerShell, tại thư mục gốc dự án:

```powershell
$env:PGPASSWORD = '<mật khẩu>'
$pg = 'C:\Program Files\PostgreSQL\18\bin'
$stamp = Get-Date -Format 'yyyyMMdd'
& "$pg\pg_dump.exe" -h localhost -U postgres -d housing -Fc --no-owner -f "backup\housing_$stamp.dump"
Copy-Item -Recurse models "backup\models_$stamp"                       # file mô hình (nếu có)
Remove-Item Env:PGPASSWORD
```

`-Fc` (custom) cho phép khôi phục chọn lọc và nén sẵn. Dump gồm các extension (`postgis`, `pgvector`,
`pg_trgm`, `unaccent`), hàm SQL (`nearby`, `refresh_*`) và dữ liệu mọi bảng, kể cả `listing_embeddings`.

## Kiểm tra bản backup (bắt buộc sau khi backup)

Bản backup chưa kiểm chứng coi như chưa có.

1. **Đọc được mục lục:** `pg_restore -l backup\housing_YYYYMMDD.dump` không lỗi, có đủ các bảng chính
   (`listings`, `pois`, `listing_embeddings`, `price_model_runs`, bảng địa chỉ).
2. **Khôi phục thử vào DB tạm**, không bao giờ vào `housing`:
   ```powershell
   & "$pg\createdb.exe" -h localhost -U postgres housing_restore_test
   & "$pg\pg_restore.exe" -h localhost -U postgres -d housing_restore_test --no-owner --exit-on-error backup\housing_YYYYMMDD.dump
   ```
   Cần PostGIS và pgvector đã cài trên máy khôi phục (xem `docs/setup-postgis-pgvector.md`); thiếu thì
   `pg_restore` dừng ở bước tạo extension.
3. **So số dòng** `listings`, `pois`, `listing_embeddings`, `price_model_runs` giữa DB gốc và DB tạm; chạy
   `alembic current` trên DB tạm phải ra đúng phiên bản.
4. Xóa DB tạm: `dropdb housing_restore_test`.

## Khôi phục

Luôn khôi phục vào DB **mới/trống** rồi đổi `DATABASE_URL`; không ghi đè `housing` đang chạy. Sau khi
khôi phục: chép lại `models/`, bật Prediction Server, `GET /api/v1/health` phải báo model đang hoạt động.

## Lưu ý an toàn

- Dump chứa dữ liệu thật: đừng gửi qua kênh công khai hay đưa vào git (nếu lỡ commit, phải xóa khỏi cả lịch sử).
- `housing_before_public_20261009.dump` và `data_ultilities.sql` trước đây có trong git nên vẫn nằm trong
  lịch sử cũ; muốn gỡ hẳn phải viết lại lịch sử (`git filter-repo`) chứ `git rm` là không đủ.
- Giữ ít nhất hai bản gần nhất, và một bản ở ổ khác máy.
