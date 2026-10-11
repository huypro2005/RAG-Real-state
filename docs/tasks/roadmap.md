# Kế hoạch hoàn thiện đồ án (09/10/2026 → 03/01/2027)

> **PHẠM VI HIỆN TẠI (người dùng quyết 09/10/2026): chỉ làm RAG và gợi ý (mode recommendation).**
> **Tạm bỏ:** model dự đoán giá (GĐ6: Random Forest A/B, mode prediction, `predict_price`, Price Agent) và
> **khoảng cách tới Quận 1** (`dist_to_q1_m`). Mọi chỗ nhắc tới hai việc này bên dưới đều **không cần làm**
> cho tới khi người dùng yêu cầu lại. 6 biến đếm POI (1 km/3 km) vẫn dùng, vì tìm kiếm cần "gần bệnh viện/chợ/trường".


Bám đề cương `ĐỀ_CƯƠNG_ĐỒ_ÁN_2 (1).pdf` (bản text: [DoAn2.md](../../DoAn2.md)). Mỗi giai đoạn dưới
đây sẽ thành một spec riêng `docs/tasks/<gđ>.md` và chạy vòng **coder → reviewer/test → sửa**
cho tới khi reviewer PASS (xem [AGENTS.md](../../AGENTS.md)).

Nguyên tắc chung: **workflow cố định bằng code, LLM chỉ ở hai chỗ** (trích điều kiện và viết
câu trả lời). Không dùng LangChain/LangGraph: OpenAI SDK + Pydantic là đủ, ít phụ thuộc, dễ
giải thích khi bảo vệ.

---

## 0. Hiện trạng (đo ngày 09/10/2026)

| Hạng mục | Trạng thái |
|---|---|
| Crawler Selenium + extractor | Chạy một lượt, **chưa incremental**, chưa lưu snapshot |
| Làm sạch tin (`src/pipeline/listing_cleaner.py`) | Xong: 8.570 dòng → 7.603 tin sạch, 247 tin bị loại |
| Database | Đang chuyển sang schema `public` + địa chỉ batdongsan ([address-db.md](address-db.md)) |
| POI | 5.267 điểm (trường, bệnh viện, chợ), TP.HCM cũ |
| Spatial features | Có hàm `refresh_spatial_features()` và 7.342 dòng |
| Embedding | Có code + server Kaggle, **chưa embed** (0 dòng) |
| Model giá, Hybrid Search, API chat, React | **Chưa có** |

**Rủi ro số 1 — dữ liệu đã cũ:** 7.417/7.603 tin có `expired_at < 09/10/2026`; chỉ **186 tin
còn hiệu lực**. Đề cương yêu cầu chỉ gợi ý tin active ⇒ crawler định kỳ (GĐ3) là việc chặn mọi
thứ phía sau, phải bật **ngay tuần này**. Dữ liệu cũ vẫn dùng được để train model giá (giá rao
bán lịch sử) nhưng không dùng để gợi ý.

## 1. Lộ trình

| GĐ | Thời gian | Việc chính | Đầu ra / tiêu chí đề cương |
|---|---|---|---|
| 2b | 09/10–12/10 | Xong task database địa chỉ, áp lên DB thật, embed 7.603 tin | Reviewer PASS [address-db.md](address-db.md) |
| 3 | 12/10–25/10 | Crawler incremental + vòng đời tin + lịch chạy hằng ngày | §7.1: không trùng, phân biệt mới/cập nhật/inactive |
| 4 | 19/10–01/11 | `normalize_address`, độ tin cậy tọa độ, geocode Goong cho tin thiếu tọa độ | Báo cáo tỷ lệ geocode, mapping cũ–mới chạy được |
| 5 | 26/10–08/11 | Spatial features chỉ cho tọa độ tin cậy + khoảng cách Quận 1 + test | Test truy vấn khoảng cách/đếm POI |
| 6 | 02/11–22/11 | EDA, dataset versioned, Model A/B, báo cáo A/B | §7.2 |
| 7 | 09/11–29/11 | Constraint schema, Hybrid Search, rerank, bộ test 40 câu | §7.3 |
| 8 | 30/11–20/12 | FastAPI tools + chat 2 mode + React | §7.4 |
| 9 | 21/12–03/01 | Map View Leaflet + Goong, e2e test, báo cáo, slide, video | Demo hoàn chỉnh |

GĐ 6 và 7 chạy song song (hai người, chung dữ liệu sạch) — giống đề xuất trong
[jira-backlog.md](../jira-backlog.md).

## 2. Chi tiết từng giai đoạn

### GĐ3 — Crawler định kỳ và vòng đời tin

- Lượt crawl: trang danh sách (mới nhất trước) → so `listing_id` với DB → chỉ crawl trang chi
  tiết của tin mới **hoặc** tin active chưa kiểm tra > 3 ngày.
- Raw snapshot lưu **file** `data/raw/<run_id>/<listing_id>.json.gz` (không lưu vào DB, giữ DB
  gọn); đổi parser thì re-parse từ file.
- Bảng mới (tối thiểu):
  - `crawl_runs(id, started_at, finished_at, status, n_seen, n_new, n_updated, n_inactive, n_errors)`
  - `listing_history(listing_id, observed_at, price, status)` — **chỉ ghi khi giá hoặc trạng thái đổi**.
  - Cột thêm vào `listings`: `status` (`active`/`inactive`/`expired`), `first_seen_at`, `last_seen_at`.
- Quy tắc trạng thái: `expired` khi `expired_at < hôm nay`; `inactive` khi trang chi tiết 404
  hoặc 2 lượt liên tiếp không thấy; không xóa dòng.
- Lịch: Windows Task Scheduler chạy `python -m src.crawl` mỗi ngày; rate limit 1 trang/2–3 giây,
  retry 3 lần, log ra file.
- Sau mỗi lượt: clean → upsert → `refresh_spatial_features()` → embed tin mới/đổi nội dung.

### GĐ4 — Chuẩn hóa địa chỉ và tọa độ

- `normalize_address(text)`: tách quận/phường/đường → khớp tên với `districts_old`/`wards_old`/
  `streets_old` (hoặc bộ mới) → nếu là địa chỉ cũ thì tra `ward_mappings` ra phường mới.
  Khớp chính xác trước, sau đó chỉ cho phép khớp bỏ dấu; không khớp thì trả về "không xác định".
- Thêm `listings.geo_confidence` (`high` khi tọa độ batdongsan nằm trong ranh TP.HCM cũ và
  khớp quận; `low` khi ngoài ranh — hiện có 261 tin `coords_outside_hcm`).
- Tin thiếu/lệch tọa độ: geocode bằng Goong (`GOONG_API_KEY` đã có) từ địa chỉ chuẩn hóa.

### GĐ5 — Spatial features

- `refresh_spatial_features()` chỉ tính cho `geo_confidence = 'high'`; thêm `dist_to_q1_m`
  (tâm Quận 1, đặt hằng số tọa độ Nhà thờ Đức Bà hoặc chợ Bến Thành — ghi rõ trong báo cáo).
- Test: chọn 5 tin, đếm tay bằng `ST_DWithin` ⇒ khớp với bảng feature.

### GĐ6 — Model dự đoán giá

- **Chốt tiêu chí trước khi train** (ghi vào `docs/ml/ab-plan.md`): Model B được kích hoạt nếu
  MAE **hoặc** RMSE trên test giảm ≥ 2%.
- Dataset: tin sạch, `geo_confidence = 'high'`, target `price` (triệu VND); không dùng
  `price_per_m2`. Split theo `posted_at`: 80% cũ nhất train, 20% mới nhất test.
- Model A: `property_type`, nhãn quận (`district_label`), `area`, `frontage`, `bedrooms`,
  `floors`, `latitude`, `longitude`, `dist_to_q1_m`. Model B = A + đúng 6 biến đếm POI.
- Cùng `Pipeline` sklearn (impute + one-hot + RandomForest), cùng `RandomizedSearchCV` với
  `TimeSeriesSplit`, cùng seed.
- Báo cáo: MAE, RMSE, R² tổng + theo quận, loại BĐS, phân khúc giá; feature importance
  (permutation).
- Bảng `model_runs(model_version, variant A/B, features text[], params, train_end_date, mae,
  rmse, r2, is_active, artifact_path)` — gộp `model_runs/model_metrics/model_activation` của
  đề cương thành 1 bảng; unique index một dòng `is_active`.
- Model lưu `models/<version>.joblib`, nạp một lần khi API khởi động.

### GĐ7 — Hybrid Search và RAG

- `SearchConstraints` (Pydantic): `budget_min/max`, `property_types`, `district_ids`,
  `area_min/max`, `bedrooms_min`, `near_pois: [{poi_type, max_distance_m}]`, `soft_query` (phần
  mềm còn lại để vector search).
- Extractor: gpt-4o-mini + structured output theo schema trên; thiếu điều kiện bắt buộc
  (ngân sách hoặc khu vực) thì hỏi lại, không đoán.
- Truy vấn **một câu SQL**: lọc cứng (`status = 'active'`, giá, loại, quận, diện tích) → `EXISTS
  (... ST_DWithin(pois.geom, l.geom, d))` → sắp theo `embedding <=> :qvec` → 30 ứng viên.
  Với ~vài nghìn tin active, quét chính xác là đủ, chưa cần index HNSW.
- Rerank: thêm endpoint `/rerank` (bge-reranker-v2-m3) vào server Kaggle sẵn có → Top 5.
- Response: LLM chỉ nhận JSON Top 5 (giá, diện tích, địa chỉ, khoảng cách POI, ngày cập nhật,
  URL) và phải trích `[Tin <id>]`; không có kết quả thì nói không có.
- Đánh giá: 40 câu hỏi kiểm thử có nhãn tay ⇒ tỷ lệ vi phạm điều kiện cứng = 0, Precision@5.

### GĐ8 — API tools và chatbot hai mode

- Tool (mỗi cái 1 hàm + Pydantic in/out + unit test): `search_listings`, `predict_price`,
  `normalize_address`, `get_nearby_pois`, `get_map_results`.
- `predict_price` trả `PredictPriceOut` có cấu trúc: `predicted_price`, `model_version`,
  `variant` (A/B), `spread_p10_p90` (phân vị dự đoán giữa các cây RF), `comparables` (≤ 5 tin
  gần bằng `ST_DWithin`, cùng loại), `disclaimer`. LLM chỉ diễn đạt, **không sinh con số**.
- `get_map_results(listing_ids)` nhận đúng danh sách tin của lượt chat (không truy vấn lại);
  marker đánh số 1–5 khớp "căn thứ N".
- `POST /chat {mode, message, conversation_id}`: mode do client gửi, validate bằng enum. Đổi
  mode ⇒ tạo state mới. "Agent" là các bước trong workflow (Mode Controller, Extractor, Geo,
  Search/Price, Response, Map Formatter) — hàm Python, không để LLM tự gọi SQL hay đổi mode.
- Bảng theo dõi tối thiểu: `chat_sessions(id, mode, created_at)`, `search_logs(id, session_id,
  message, constraints, result_ids, latency_ms, created_at)`, `user_feedback(log_id, rating)`.
- React (Vite) + bộ chọn mode + card Top 5 + form prediction.

### GĐ9 — Bản đồ, kiểm thử, bàn giao

- Leaflet + tile Goong; marker Top 5 + POI liên quan (GeoJSON từ `get_map_results`).
- Cảnh báo tin sắp hết hạn và tọa độ độ tin cậy thấp.
- E2E: crawl → DB → embedding → search/predict → chat → map; báo cáo, slide, video.

## 3. Quyết định cần người dùng chốt

1. Raw snapshot lưu file (đề xuất) hay bảng `raw_listing_snapshots` như Bảng 4.1 đề cương.
2. Gộp `model_runs/model_metrics/model_activation` thành 1 bảng (đề xuất).
3. Không dùng LangChain (đề cương GĐ7 có nhắc) — đề xuất ghi rõ lý do trong báo cáo.
4. `search_logs.constraints` cần lưu JSON của điều kiện đã trích ⇒ là ngoại lệ hợp lý của quy
   tắc "không jsonb" (quy tắc đó nhắm vào việc lưu nguyên bản ghi nguồn).

## 4. Bài học từ dự án tham khảo

Xem [ai-real-estate-assistant-lessons.md](../research/ai-real-estate-assistant-lessons.md) (đã phản biện). Mục nào được
đánh giá "Cao" sẽ đưa vào spec của giai đoạn tương ứng.
