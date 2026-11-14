# AGENTS.md — Bản đồ dự án cho AI

Đồ án: chatbot tư vấn bất động sản **TP.HCM cũ** (trước sáp nhập 2025), dữ liệu tin đăng từ
batdongsan.com.vn. Hai pipeline độc lập dùng chung dữ liệu: **dự đoán giá** và **RAG gợi ý**.

Đọc file này trước, rồi chỉ mở tài liệu cần cho task đang làm.

---

> **Cập nhật 10/10/2026: xem STATUS mục 13 + docs/reports/senior-review-2026-10-10.md.** Tạm dừng 09/10/2026 — đọc [docs/tasks/STATUS.md](docs/tasks/STATUS.md) trước**: trạng thái, việc dở, lệnh áp DB thật, thứ tự việc tiếp theo.

## 1. Task hiện tại

> **Làm lại database địa chỉ theo dữ liệu Batdongsan, toàn bộ bảng ở schema `public`.**
> Spec + tiêu chí nghiệm thu: [docs/tasks/address-db.md](docs/tasks/address-db.md)

Quy trình hai agent (định nghĩa trong `.claude/agents/`):

```text
main ──> db-coder    : code theo spec, chạy thử trên DB housing_dev, báo cáo việc đã làm
     ──> db-reviewer : chỉ đọc + chạy kiểm tra, chấm PASS/FAIL theo mã tiêu chí [A1]...[D5]
     ──> có FAIL     : gửi nguyên báo cáo reviewer lại cho db-coder sửa (tối đa 3 vòng)
     ──> hết FAIL    : báo người dùng
```

Kế hoạch toàn đồ án (GĐ2b → GĐ9): [docs/tasks/roadmap.md](docs/tasks/roadmap.md). Mỗi giai đoạn
có spec riêng `docs/tasks/<gđ>.md` và chạy cùng vòng coder → reviewer ở trên.
GĐ7 Hybrid Search: [docs/tasks/hybrid-search.md](docs/tasks/hybrid-search.md) — vòng
`query-tester` (50 câu truy vấn + oracle SQL) → `db-coder` sửa → chạy lại, tối đa 6 vòng. Agent
`doc-reviewer` phản biện tài liệu nghiên cứu trong `docs/research/`.
Chatbot linh hoạt (hỏi đáp có căn cứ, what-if, chào hỏi, chuyển chế độ, so giá tin rao) + sơ đồ
hệ thống hai chatbot: [docs/tasks/chat-intelligence.md](docs/tasks/chat-intelligence.md).
Tìm "gần <địa điểm có tên>" (ĐH, bệnh viện, chợ, địa danh; trùng tên → hỏi lại; 5 km):
[docs/tasks/named-places.md](docs/tasks/named-places.md) — làm sau chat-intelligence.

Task đã xong: phân tích cấu trúc HTML tin đăng —
[docs/tasks/html-analysis.md](docs/tasks/html-analysis.md), kết quả ở `src/crawl/crawlProperties/analysis/`.

## 2. Bản đồ tài liệu

| Muốn biết | Đọc |
|---|---|
| Đề tài, mục tiêu, phạm vi, tiến độ | [DoAn2.md](DoAn2.md), [README.md](README.md) |
| Kiến trúc tổng thể | [docs/architecture.md](docs/architecture.md) |
| Quy ước dữ liệu, chất lượng | [docs/data-contract.md](docs/data-contract.md) |
| Giải thích bảng/cột database | [docs/database.md](docs/database.md), [docs/housing-database.drawio](docs/housing-database.drawio) |
| Chạy dự án, DB Docker, khôi phục/backup | [README.md](README.md), [docs/setup-docker-postgres.md](docs/setup-docker-postgres.md), [backup/README.md](backup/README.md) |
| Cài PostGIS / pgvector trên Windows (cách cũ) | [docs/setup-postgis-pgvector.md](docs/setup-postgis-pgvector.md) |
| Crawler tin đăng | [docs/crawler.md](docs/crawler.md), [src/crawl/crawlProperties/README.md](src/crawl/crawlProperties/README.md) |
| Pipeline làm sạch tin | [docs/huong-dan-pipeline-lam-sach.md](docs/huong-dan-pipeline-lam-sach.md) |
| Cấu trúc HTML batdongsan (field, selector, địa chỉ cũ/mới) | `src/crawl/crawlProperties/analysis/*.md` |
| Hai chatbot (kiến trúc, intent, API, chạy/test) | [docs/chatbot.md](docs/chatbot.md) |
| Cách gọi API (endpoint, request/response, ví dụ, sự cố) | [docs/api.md](docs/api.md) |
| Backlog | [docs/jira-backlog.md](docs/jira-backlog.md) |
| Bàn giao dữ liệu trường học | [docs/handoffs/](docs/handoffs/) |
| API địa chỉ batdongsan | [data/address_data/readme.md](data/address_data/readme.md) |

## 3. Bản đồ code và dữ liệu

```text
.
├── data/address_data/       # Địa chỉ lấy từ batdongsan (nguồn chuẩn cho bảng địa chỉ)
│   ├── readme.md            #   các endpoint API phải tự gọi
│   ├── old_cities.json      #   tỉnh/TP trước 2025 (cityCode: 'SG', 'HN'...)
│   ├── new_cities.json      #   tỉnh/TP từ 2025
│   ├── sg_old.json          #   quận/huyện cũ của SG (districtId)
│   └── ward_mappings.sql    #   mapping phường cũ → mới (dump MySQL, mã hành chính chính thức)
├── src/web/housing-backend/   # Backend FastAPI + database (đích của task hiện tại)
│   ├── app/db/base.py       #   Base, IntPk, quy ước đặt tên constraint, map kiểu
│   ├── app/db/models/       #   model SQLAlchemy: admin_units, district, poi, listing, views
│   ├── migrations/          #   Alembic
│   ├── db/                  #   SQL cũ (schema.sql, functions.sql) — đang được thay
│   └── scripts/             #   script nạp/sửa dữ liệu
├── src/crawl/crawlProperties/  # Crawler tin đăng + listing_extractor.py + analysis/
├── src/crawl/dataUltilities/   # Dữ liệu POI (trường, bệnh viện, chợ)
├── src/pipeline/            # Làm sạch, nạp, embedding tin đăng (.env riêng)
├── src/pipeline/input/      #   dữ liệu crawl đầu vào (data.json, data14-11.json)
├── src/web/prediction_server/  # FastAPI dự đoán giá, nạp tin, tự retrain (.env riêng)
├── src/web/housing-frontend/   # React + Vite (.env riêng)
├── src/notebook/            # predictionEDA (EDA, thí nghiệm), kaggle (server embedding bge-m3)
├── tools/                   # Script POI cũ (lỗi thời), reverse-engineer HTML
├── backup/                  # Dump DB + models (không commit) + README: quy ước tên, yêu cầu trước khi backup
├── models/                  # File mô hình giá của Prediction Server (không commit)
└── output/listings/         # Đầu ra bước làm sạch của pipeline
```

Hướng dẫn chạy: [README.md](README.md) (tóm tắt), [docs/setup-docker-postgres.md](docs/setup-docker-postgres.md)
(DB Docker, khôi phục, dựng từ đầu), [backup/README.md](backup/README.md) (backup).

## 4. Môi trường

- Windows 11. Có Bash (Git Bash) và PowerShell. Không có `psql` trên Windows: dùng
  `docker exec housing-postgres psql -U postgres -d housing_dev ...` hoặc Python + `psycopg`. Git Bash cần
  `MSYS_NO_PATHCONV=1` trước `docker exec`/`docker cp` có đường dẫn `/tmp/...`.
- Python: dùng `D:/my_project/DoAn2/Multi-Agent-RAG-and-Prediction-Housing-Price/.venv/Scripts/python.exe` (`.venv` gốc). **Không dùng `uv run`/`uv sync`/`uv add`** — tạo `.venv` mới/làm mất gói và bị Application Control của Windows chặn. Ruff: `uvx ruff check <file>`.
- Database: Docker, container `housing-postgres` (`src/web/housing-backend/docker-compose.yml`), cổng **5433**,
  user `postgres`, mật khẩu trong `src/web/housing-backend/.env`. DB `housing_dev` = DB làm việc/thử nghiệm;
  `housing` = DB cũ, chỉ đọc — **không được phá**. Postgres cài trên Windows (cổng 5432) là bản cũ, không dùng.
- Backup: `backup\housing_dev_YYYYMMDD.dump`, `backup\housing_YYYYMMDD.dump` (một quy ước duy nhất, xem
  [backup/README.md](backup/README.md)).
- Mỗi thành phần có `.env` riêng (không commit, có `.env.example`): `src/pipeline/`, `src/web/housing-backend/`, `src/web/prediction_server/`, `src/web/housing-frontend/`. Code không đọc `.env` ở gốc (file đó nếu còn là bản cũ). `PREDICTION_SERVER_API_KEY` của backend và prediction server phải trùng nhau.
- Alembic chạy trong `src/web/housing-backend/` (tự đọc `DATABASE_URL` từ `.env` của backend):
  `D:/my_project/DoAn2/Multi-Agent-RAG-and-Prediction-Housing-Price/.venv/Scripts/python.exe -m alembic upgrade head`
- Backend và Prediction Server chạy trên Windows có thể bị Smart App Control chặn `.pyd` (`asyncpg`, `scikit-learn`).

## 5. Nguyên tắc chung

- **Đơn giản, đúng đề tài.** Không lưu `raw_record`, `source_file`, hash, JSON nguyên bản ghi,
  mã nguồn kiểu `poi_id` trong database.
- **Không suy đoán dữ liệu.** Không tự map địa chỉ cũ → mới, không tự điền field thiếu.
- **Không normalize khi lưu dữ liệu gốc** (giữ `8,6 tỷ`, `Quận 2` nguyên văn); chuẩn hóa là
  việc của pipeline phía sau.
- Code Python: một class gọn với vài phương thức có nghĩa nghiệp vụ, không rải nhiều hàm nhỏ.
  Comment, docstring tiếng Việt, theo phong cách file xung quanh.
- Phạm vi địa lý: TP.HCM cũ. Không mở rộng sang Bình Dương, Bà Rịa – Vũng Tàu.
- Không commit, không chạy lệnh tốn tiền/gọi API ngoài khi người dùng chưa yêu cầu.
