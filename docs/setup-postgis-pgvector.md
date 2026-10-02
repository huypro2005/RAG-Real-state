# Cài PostGIS và pgvector (Windows, PostgreSQL 18)

Database `housing` cần hai extension: **PostGIS** (truy vấn không gian, POI) và **pgvector** (lưu embedding cho RAG).

## 1. PostGIS

1. Mở **Stack Builder** (cài kèm PostgreSQL) → chọn `PostgreSQL 18 on port 5432`.
2. **Spatial Extensions** → tick **PostGIS 3.x Bundle for PostgreSQL 18** → Next và cài mặc định.
3. Bật trong database:

```sql
CREATE EXTENSION IF NOT EXISTS postgis;
```

## 2. pgvector

pgvector không có trong Stack Builder, phải build từ mã nguồn.

**2.1. Cài trình biên dịch C++** (PowerShell chạy bằng quyền Administrator):

```powershell
winget install --id Microsoft.VisualStudio.2022.BuildTools --override "--quiet --wait --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended"
```

**2.2. Build và cài:** mở **x64 Native Tools Command Prompt for VS 2022** bằng *Run as administrator* (phải là bản **x64**, cửa sổ cmd):

```bat
set "PGROOT=C:\Program Files\PostgreSQL\18"
cd %TEMP%
git clone --branch v0.8.6 https://github.com/pgvector/pgvector.git
cd pgvector
nmake /F Makefile.win
nmake /F Makefile.win install
```

**2.3. Bật trong database:**

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

## 3. Kiểm tra

```bat
"C:\Program Files\PostgreSQL\18\bin\psql.exe" -h localhost -U postgres -d housing
```

```sql
SELECT extname, extversion FROM pg_extension WHERE extname IN ('postgis', 'vector');
SELECT postgis_version();
SELECT '[1,2,3]'::vector <=> '[1,2,4]'::vector;   -- trả về khoảng 0.008
```

Phía Python:

```powershell
pip install "psycopg[binary]" pgvector
```

## Lỗi thường gặp

| Lỗi | Cách sửa |
|---|---|
| `'nmake' is not recognized` | Mở lại bằng **x64 Native Tools Command Prompt**, không dùng cmd/PowerShell thường |
| `Cannot open include file: 'postgres.h'` | Kiểm tra `PGROOT` trỏ đúng thư mục PostgreSQL 18, giữ dấu ngoặc kép |
| `Access is denied` khi `install` | Chạy cửa sổ bằng quyền Administrator |
| `could not load library ... vector.dll` | Đã build bằng prompt x86 → xóa thư mục `pgvector`, build lại bằng prompt x64 |
| `extension "vector" is not available` | Bước `install` chưa thành công; kiểm tra có `vector.control` trong `C:\Program Files\PostgreSQL\18\share\extension` |
| `extension "postgis" is not available` | Chưa cài PostGIS Bundle qua Stack Builder, hoặc cài nhầm bản cho PostgreSQL khác |

> Khi nâng PostgreSQL lên phiên bản chính mới, cần cài lại PostGIS Bundle tương ứng và build lại pgvector.
