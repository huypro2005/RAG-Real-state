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
[docs/tasks/html-analysis.md](docs/tasks/html-analysis.md), kết quả ở `CrawlData/analysis/`.

## 2. Bản đồ tài liệu

| Muốn biết | Đọc |
|---|---|
| Đề tài, mục tiêu, phạm vi, tiến độ | [DoAn2.md](DoAn2.md), [README.md](README.md) |
| Kiến trúc tổng thể | [docs/architecture.md](docs/architecture.md) |
| Quy ước dữ liệu, chất lượng | [docs/data-contract.md](docs/data-contract.md) |
| Giải thích bảng/cột database | [docs/database.md](docs/database.md), [docs/housing-database.drawio](docs/housing-database.drawio) |
| Cài PostGIS / pgvector | [docs/setup-postgis-pgvector.md](docs/setup-postgis-pgvector.md) |
| Crawler tin đăng | [docs/crawler.md](docs/crawler.md), [CrawlData/README.md](CrawlData/README.md) |
| Pipeline làm sạch tin | [docs/huong-dan-pipeline-lam-sach.md](docs/huong-dan-pipeline-lam-sach.md) |
| Cấu trúc HTML batdongsan (field, selector, địa chỉ cũ/mới) | `CrawlData/analysis/*.md` |
| Hai chatbot (kiến trúc, intent, API, chạy/test) | [docs/chatbot.md](docs/chatbot.md) |
| Cách gọi API (endpoint, request/response, ví dụ, sự cố) | [docs/api.md](docs/api.md) |
| Backlog | [docs/jira-backlog.md](docs/jira-backlog.md) |
| Bàn giao dữ liệu trường học | [docs/handoffs/](docs/handoffs/) |
| API địa chỉ batdongsan | [address_data/readme.md](address_data/readme.md) |

## 3. Bản đồ code và dữ liệu

```text
.
├── address_data/            # Địa chỉ lấy từ batdongsan (nguồn chuẩn cho bảng địa chỉ)
│   ├── readme.md            #   các endpoint API phải tự gọi
│   ├── old_cities.json      #   tỉnh/TP trước 2025 (cityCode: 'SG', 'HN'...)
│   ├── new_cities.json      #   tỉnh/TP từ 2025
│   ├── sg_old.json          #   quận/huyện cũ của SG (districtId)
│   └── ward_mappings.sql    #   mapping phường cũ → mới (dump MySQL, mã hành chính chính thức)
├── housing-backend/housing-backend/   # Backend FastAPI + database (đích của task hiện tại)
│   ├── app/db/base.py       #   Base, IntPk, quy ước đặt tên constraint, map kiểu
│   ├── app/db/models/       #   model SQLAlchemy: admin_units, district, poi, listing, views
│   ├── migrations/          #   Alembic
│   ├── db/                  #   SQL cũ (schema.sql, functions.sql) — đang được thay
│   └── scripts/             #   script nạp/sửa dữ liệu
├── CrawlData/               # Crawler tin đăng + listing_extractor.py + analysis/
├── CrawUltilities/          # Dữ liệu POI (trường, bệnh viện, chợ)
├── src/pipeline/            # Làm sạch, nạp, embedding tin đăng
├── src/agent/               # Chatbot multi-agent
├── tools/                   # Script import/kiểm tra POI, reverse-engineer HTML
├── backup/                  # Dump DB cũ (5 schema) — chỉ tham khảo
└── outputs/                 # Kết quả trung gian của pipeline POI
```

## 4. Môi trường

- Windows 11. Có Bash (Git Bash) và PowerShell. **Không có `psql`/`pg_isready`**, Docker
  thường tắt → thao tác DB bằng Python + `psycopg`.
- Python: dùng `D:/my_project/DoAn2/Multi-Agent-RAG-and-Prediction-Housing-Price/.venv/Scripts/python.exe` (`.venv` gốc). **Không dùng `uv run` trong `housing-backend/`** — nó tạo `.venv` mới và bị Application Control của Windows chặn. Ruff: `uvx ruff check <file>`.
- Postgres 18 local: `postgres:123456789@localhost:5432`. DB `housing` là DB thật — **không
  được phá**. Thử nghiệm trên `housing_dev`.
- Alembic chạy trong `housing-backend/housing-backend/`:
  `DATABASE_URL=postgresql+asyncpg://postgres:123456789@localhost:5432/housing_dev D:/my_project/DoAn2/Multi-Agent-RAG-and-Prediction-Housing-Price/.venv/Scripts/python.exe -m alembic upgrade head`

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
