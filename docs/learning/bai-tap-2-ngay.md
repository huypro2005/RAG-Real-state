# Bài tập 2 ngày — lấp lỗ hổng từ bài kiểm tra 11/10/2026

Mục tiêu: hiểu **cơ chế** (code chạy ở đâu, khi nào, dữ liệu hành xử ra sao) chứ không chỉ "biết nó là gì".
Mỗi bài có: việc phải làm → câu phải trả lời → dấu hiệu đạt.

## Luật chơi

1. **Tự gõ code, không dùng AI sinh code.** Được đọc tài liệu chính thức (link cuối file).
2. Code của bạn để trong `docs/learning/lab/` (tạo mới). Không sửa code trong `app/`.
3. Chỉ dùng DB `housing_dev`. **Không động vào `housing`.**
4. Kẹt quá 20 phút → hỏi Claude **gợi ý**, không hỏi đáp án.
5. Ghi câu trả lời vào `docs/learning/lab/tra-loi.md` bằng lời của bạn, kèm số liệu bạn đo được.

Lệnh dùng chung (Git Bash, đứng ở `housing-backend/`):

```bash
PY=D:/my_project/DoAn2/Multi-Agent-RAG-and-Prediction-Housing-Price/.venv/Scripts/python.exe
export DATABASE_URL=postgresql+asyncpg://postgres:123456789@localhost:5432/housing_dev
```

---

## NGÀY 1 — Python async + SQLAlchemy

### Bài 1.1 — Event loop bị chặn (2 giờ) · lấp câu A2

**Làm:** viết `lab/async_lab.py` — một app FastAPI có 3 route, mỗi route in ra
`threading.current_thread().name` rồi chờ 3 giây:

| Route | Khai báo | Cách chờ |
|---|---|---|
| `/block` | `async def` | `time.sleep(3)` |
| `/nonblock` | `async def` | `await asyncio.sleep(3)` |
| `/thread` | `def` | `time.sleep(3)` |

Chạy `$PY -m uvicorn async_lab:app --port 8001` (đứng trong `lab/`), rồi bắn 3 request cùng lúc:

```bash
for i in 1 2 3; do ( time curl -s localhost:8001/block >/dev/null ) & done; wait
```

Lặp lại với `/nonblock` và `/thread`. Ghi bảng: route → thời gian 3 request → tên thread in ra.

**Thêm:** thêm 2 dependency in tên thread — một `def`, một `async def` — gắn vào `/nonblock`.

**Trả lời:**
1. Vì sao `/block` mất ~9 giây mà `/nonblock` chỉ ~3 giây? "Event loop" là gì?
2. `/thread` chạy trên thread nào? Ai tạo thread đó?
3. Dependency `def` chạy trên thread nào? Giờ đọc lại comment dòng 32–33 trong
   [app/api/deps.py](../../housing-backend/app/api/deps.py) và giải thích vì sao cần `threading.Lock`.
4. Nếu trong `RecommendationService` có ai gọi `requests.get(...)` thì hậu quả là gì? Sửa thế nào?

**Đạt khi:** giải thích được "concurrent ≠ parallel" bằng chính số liệu đo.

### Bài 1.2 — Vòng đời session (1 giờ) · lấp câu A1

**Làm:** trong `async_lab.py`, viết dependency `fake_session()` kiểu `async def ... yield` giống
[app/db/session.py](../../housing-backend/app/db/session.py), nhưng thay DB bằng `print`:
in "MỞ id=...", "ĐÓNG", "ROLLBACK" ở đúng chỗ. Tạo object bằng `object()` và in `id()`.
Viết 2 route: `/ok` trả bình thường, `/boom` ném `ValueError`.

**Trả lời:**
1. Thứ tự in ra khi gọi `/ok`? Khi gọi `/boom`?
2. Gọi `/ok` 2 lần — `id` có giống nhau không? Vậy session có phải singleton?
3. Trong `deps.py`, cái gì mới là singleton? Nó sống bao lâu, session sống bao lâu?

### Bài 1.3 — ORM: lazy load, N+1, expire_on_commit (2,5 giờ) · lấp câu B1, B2

Trước tiên kiểm tra DB có dữ liệu: `SELECT count(*) FROM listings` trên `housing_dev`
(viết bằng `psycopg`). Nếu 0 thì báo Claude trước khi làm tiếp.

**Làm:** viết `lab/orm_lab.py` dùng `asyncio.run(main())`, tạo engine riêng với `echo=True`
(để thấy SQL), import model `Listing` từ `app.db.models`. Bốn thí nghiệm:

- **(a)** Lấy 1 listing bằng `ListingRepository.get()` → đếm số câu `SELECT` trong log.
- **(b)** Tự viết query giống vậy nhưng **bỏ** `selectinload`, rồi truy cập `listing.spatial_features`.
  Ghi lại **tên lỗi** chính xác.
- **(c)** Lấy 20 listing không có `selectinload`; với mỗi cái gọi
  `await session.refresh(obj, ["spatial_features"])`. Đếm số câu SQL. Sau đó làm lại bằng
  `selectinload` cho cả 20. So sánh.
- **(d)** Tạo `async_sessionmaker(engine, expire_on_commit=True)`, lấy 1 listing, `await session.commit()`,
  rồi đọc `listing.title`. Ghi lỗi. Đổi sang `False`, chạy lại.

**Trả lời:**
1. `selectinload` sinh mấy câu SQL? Câu thứ hai trông thế nào (`IN (...)`)?
2. N+1 là gì — dùng đúng số liệu bạn đếm ở (c)?
3. Vì sao lazy load và expire gây lỗi **chỉ trong async**? (gợi ý: "implicit IO", "greenlet")
4. `autoflush=False` thay đổi gì? (đọc tài liệu, không cần thí nghiệm)

### Bài 1.4 — CORS (30 phút) · lấp câu C2

**Làm:** chạy backend thật (`$PY -m uvicorn app.main:app --port 8000`). Tạo `lab/cors.html` có
`fetch("http://localhost:8000/health").then(r => r.json()).then(console.log)`.
Phục vụ nó bằng `$PY -m http.server 5500` (trong `lab/`), mở `localhost:5500/cors.html`, xem Console
và tab Network. Sau đó `curl -i localhost:8000/health`.

**Trả lời:**
1. Request có **tới** server không (xem log uvicorn)? Vậy ai chặn?
2. `curl` có bị chặn không? Vậy CORS bảo vệ ai, chống lại kịch bản tấn công nào?
3. Đọc [config.py:35](../../housing-backend/app/core/config.py) — câu "đang mở all" của bạn đúng không?

---

## NGÀY 2 — SQL, index vector, ML

### Bài 2.1 — Logic 3 giá trị của NULL (1 giờ) · lấp câu B4

**Làm:** `lab/sql_lab.py` (psycopg, `housing_dev`). Chạy và ghi kết quả:

```sql
SELECT NULL = NULL, NULL <> 1, NULL >= DATE '2026-10-11', 1 IN (1, NULL), 2 NOT IN (1, NULL);
SELECT count(*) FROM listings;
SELECT count(*) FROM listings WHERE expired_at IS NULL;
SELECT count(*) FROM listings WHERE expired_at >= DATE '2026-10-11';
SELECT count(*) FROM listings WHERE NOT (expired_at < DATE '2026-10-11');
```

**Trả lời:**
1. Vì sao `2 NOT IN (1, NULL)` không trả `true`? Đây là bẫy gì?
2. Hai câu cuối có cùng kết quả không? Vì sao (dù trông như tương đương)?
3. Tin `expired_at IS NULL` bị [search.py:99](../../housing-backend/app/services/recommendation/search.py)
   loại hay giữ? Theo bạn **về nghiệp vụ** nên loại hay giữ? Viết 2 câu lý do.

### Bài 2.2 — EXPLAIN và index vector (2,5 giờ) · lấp câu B3

Thực tế đã kiểm tra: migration `0001_baseline.py` **không có index vector** trên
`listing_embeddings.embedding` (vector 1024 chiều).

**Làm:**
1. Lấy một vector có sẵn làm "câu hỏi" (khỏi gọi Kaggle):
   `SELECT embedding FROM listing_embeddings LIMIT 1 OFFSET 5`.
2. Chạy `EXPLAIN (ANALYZE, BUFFERS)` cho:
   `SELECT listing_id FROM listing_embeddings ORDER BY embedding <=> %s::vector LIMIT 10`.
   Ghi: kiểu scan, thời gian.
3. Ghi lại 10 `listing_id` (kết quả **chính xác**).
4. Trên `housing_dev`: `CREATE INDEX lab_hnsw ON listing_embeddings USING hnsw (embedding vector_cosine_ops);`
   Ghi thời gian tạo. Chạy lại bước 2 → kiểu scan có đổi không?
5. Đổi `<=>` thành `<->` → index còn được dùng không? Vì sao?
6. Lấy câu SQL đầy đủ trong `_rank_sql` (có JOIN `listings` + WHERE quận/giá), thay tham số bằng giá trị
   thật, EXPLAIN lại → planner có dùng `lab_hnsw` không?
7. So 10 id từ index với 10 id chính xác ở bước 3 → **recall@10** = bao nhiêu?
8. Xong thì `DROP INDEX lab_hnsw;`

**Trả lời:**
1. `<=>`, `<->`, `<#>` khác nhau thế nào? Vì sao operator class phải khớp toán tử?
2. Với số dòng hiện tại của bạn, index có đáng không? Từ khoảng bao nhiêu dòng thì đáng?
3. "Approximate" nghĩa là gì — dùng recall bạn đo được?
4. Ở bước 6, lọc cứng + index HNSW có thể gây ra chuyện gì với số kết quả? (đọc mục
   "Filtering" / "Iterative index scans" trong README pgvector)

### Bài 2.3 — Độ bất định của Random Forest (2,5 giờ) · lấp câu D1, D2, D3

**Làm:** `lab/ml_lab.py`, đứng ở `housing-backend/` để import được `app` và `scripts`:

1. Dùng `PriceModelTrainer` trong [scripts/train_price_model.py](../../housing-backend/scripts/train_price_model.py):
   gọi `clean` → `split` → `fill_missing` để có tập `test` **giống hệt lúc train** (`random_state=42`).
   **Không** gọi `fit`/`save` (không ghi đè model).
2. Nạp `models/price_rf.joblib`. Với tập test, tạo ma trận dự đoán từng cây ở **không gian log**
   (cách làm: xem `_tree_range` trong
   [predictor.py](../../housing-backend/app/services/prediction/predictor.py)), shape `(200, n_test)`.
3. Với mỗi dòng test tính 3 số: `exp(mean(log))`, `mean(exp(log))`, `median(exp(log))`.
   Ghi chênh lệch % trung bình giữa số 1 và số 2.
4. Đếm bao nhiêu dòng có `exp(mean(log))` nằm **ngoài** `[p10, p90]` → dòng clamp 136 có cần không?
5. **Coverage:** bao nhiêu % giá thật của test nằm trong `[p10, p90]`? Nếu "đúng" thì phải ~80%.
6. **Drift:** nhân giá thật của test với 1,2 → MAE và coverage đổi thế nào?
7. **Ngoại suy:** giá/m² lớn nhất trong train là bao nhiêu? Thử nhập 1 căn ở vị trí trung tâm, diện tích lớn,
   nhiều tầng → dự đoán có vượt được max train không?

**Trả lời:**
1. Bất đẳng thức Jensen nói gì? Giải thích kết quả bước 3 bằng nó.
2. Coverage đo được bao nhiêu %? Vậy câu "95% giá nằm trong khoảng này" sai ở đâu?
3. Phân vị các cây đo **cái gì**, **không** đo cái gì?
4. Data drift vs concept drift khác nhau thế nào? Bước 6 mô phỏng loại nào?
5. Kể 2 cách phát hiện drift khi hệ thống đang chạy thật.
6. (Đọc thêm, không code) Conformal prediction giải quyết bước 5 thế nào?

### Bài 2.4 — Tổng kết (1 giờ)

1. Không nhìn ghi chú, trả lời lại 12 câu hỏi A1→E1 ban đầu.
2. Vẽ tay (giấy hoặc draw.io) luồng một request `/api/v1/...` mode recommendation:
   route → dependency → service → `HybridSearch.search()` → SQL → embedding API → trả về.
   Đánh dấu chỗ nào có `await`, chỗ nào là IO, chỗ nào chạy trên threadpool.
3. Gửi `tra-loi.md` + hình cho Claude chấm.

---

## Lịch gợi ý

| | Sáng | Chiều |
|---|---|---|
| Ngày 1 | 1.1 Async (2h) · 1.2 Session (1h) | 1.3 ORM (2,5h) · 1.4 CORS (0,5h) |
| Ngày 2 | 2.1 NULL (1h) · 2.2 Index (2,5h) | 2.3 ML (2,5h) · 2.4 Tổng kết (1h) |

## Tài liệu (chỉ đọc mục liên quan)

- FastAPI — "Concurrency and async / await": https://fastapi.tiangolo.com/async/
- FastAPI — "Dependencies with yield": https://fastapi.tiangolo.com/tutorial/dependencies/dependencies-with-yield/
- SQLAlchemy — "Preventing Implicit IO when Using AsyncSession":
  https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html
- SQLAlchemy — "Relationship Loading Techniques": https://docs.sqlalchemy.org/en/20/orm/queryguide/relationships.html
- PostgreSQL — "Comparison Functions and Operators" (mục NULL): https://www.postgresql.org/docs/current/functions-comparison.html
- PostgreSQL — "Using EXPLAIN": https://www.postgresql.org/docs/current/using-explain.html
- pgvector README (Querying, Indexing, HNSW, Filtering): https://github.com/pgvector/pgvector
- MDN — CORS: https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS
- scikit-learn — RandomForestRegressor: https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.RandomForestRegressor.html
