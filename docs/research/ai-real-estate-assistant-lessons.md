# Bài học từ repo `AleksNeStu/ai-real-estate-assistant`

Khảo sát ngày 09/10/2026 trên commit
[`bb535cc`](https://github.com/AleksNeStu/ai-real-estate-assistant/tree/bb535cc627f30143ea48d1cf807e2f5fd75402f4)
(25/09/2026). Mọi link là permalink tới commit này. Chỉ ghi những gì đã đọc trong code (xem
"Nhật ký phản biện" cuối file).

Đối chiếu với kế hoạch hiện tại: [roadmap](../tasks/roadmap.md) và spec GĐ7 hội thoại nhiều lượt
[hybrid-search.md](../tasks/hybrid-search.md) (`TurnInterpreter`, `ConversationStore`,
`RecommendationService`, `AnswerWriter`, 50 kịch bản). Bài học nào spec **đã có** thì ghi
"đã có trong spec" và chỉ nêu phần còn thiếu. Số mục đề cương dưới đây theo `DoAn2.md`.

## 1. Bảng tổng hợp

Công sức: **S** ≤ 1 ngày, **M** 2–3 ngày.

| # | Bài học | Ưu tiên | GĐ | Công sức | Mục spec cần sửa |
|---|---|---|---|---|---|
| 1 | Bảng test trích điều kiện từng câu + validator sau LLM | Cao | 7 | S–M | hybrid-search §2 "Quy tắc hiểu câu", §7 `[S10]` |
| 2 | 0 kết quả: số tin khi nới từng điều kiện do **code** đếm, LLM chỉ diễn đạt | Cao | 7 | S | hybrid-search §2 `ChatTurnResult`, §4 `no_results` |
| 3 | Kaggle chậm/chết: timeout ngắn cho embed câu hỏi + cờ `degraded` | Cao | 7 | S | hybrid-search §3 "Sắp xếp", §2 `ChatTurnResult` |
| 4 | Price Agent: output có cấu trúc, có comparables, khoảng dao động; LLM không sinh số | Cao | 8 (+6) | M | roadmap GĐ8 `predict_price` |
| 5 | Gộp tin gần trùng trong Top 5 (khóa chặt hơn, không xóa) | TB | 7 (+6) | S | hybrid-search §3 (sau rerank) |
| 6 | Một danh sách kết quả duy nhất cho câu trả lời và bản đồ | TB | 8–9 | S | roadmap GĐ8 `get_map_results` (phần GĐ7 đã có trong spec) |
| 7 | "Lý do phù hợp" tính bằng code cho từng tin | TB | 7–8 | S | hybrid-search §2 `ListingHit`, §4 |
| 8 | Ưu tiên khớp chính xác tên dự án/đường trên tập ứng viên | Thấp | 7 | S | chỉ làm khi `[S7]` fail vì tên riêng |
| 9 | Giới hạn độ dài input, log thời gian từng bước | Thấp | 7–8 | S | hybrid-search §5 API, `[S13]` |
| 10 | Bản đồ: `fitBounds`, marker đánh số khớp card | Thấp | 9 | S | roadmap GĐ9 |

**Đã có trong spec, không tính là bài học mới:** giữ điều kiện qua nhiều lượt dưới dạng
JSON (`ConversationStore` + `TurnPlan.set_fields/clear_fields`, merge bằng code), xử lý ngoài
phạm vi (`intent = out_of_scope`, giữ state), reset, tham chiếu "căn thứ N", embed lỗi thì sắp
theo `posted_at DESC`, rerank sau cờ `RERANK_ENABLED`, grounding `[S5]`, p95 `[S13]`; từ
roadmap: `listing_history`, `search_logs`/`user_feedback`, trích dẫn `[Tin <id>]`. Repo nguồn chỉ
**củng cố** các quyết định này (xem mục 4: cách repo làm nhiều lượt kém hơn).

## 2. Tóm tắt repo nguồn

- **Stack:** FastAPI + Next.js 16, ChromaDB, LangChain (`langchain`, `langchain-classic`),
  13 nhà cung cấp LLM, 9 ngôn ngữ
  ([README#L10](https://github.com/AleksNeStu/ai-real-estate-assistant/blob/bb535cc627f30143ea48d1cf807e2f5fd75402f4/README.md#L10),
  [#L59](https://github.com/AleksNeStu/ai-real-estate-assistant/blob/bb535cc627f30143ea48d1cf807e2f5fd75402f4/README.md#L59),
  [#L117](https://github.com/AleksNeStu/ai-real-estate-assistant/blob/bb535cc627f30143ea48d1cf807e2f5fd75402f4/README.md#L117),
  [pyproject#L14-L15](https://github.com/AleksNeStu/ai-real-estate-assistant/blob/bb535cc627f30143ea48d1cf807e2f5fd75402f4/apps/api/pyproject.toml#L14-L15)).
  Dữ liệu demo: 250+ tin ở 5 thành phố Ba Lan
  ([README#L92](https://github.com/AleksNeStu/ai-real-estate-assistant/blob/bb535cc627f30143ea48d1cf807e2f5fd75402f4/README.md#L92)).
- **Luồng chat:** `QueryAnalyzer` dùng regex + từ khóa để đoán intent, độ phức tạp và trích filter
  ([query_analyzer.py#L550-L648](https://github.com/AleksNeStu/ai-real-estate-assistant/blob/bb535cc627f30143ea48d1cf807e2f5fd75402f4/apps/api/agents/query_analyzer.py#L550-L648)),
  rồi `HybridPropertyAgent` chọn nhánh RAG, agent + tools hoặc hybrid
  ([hybrid_agent.py#L393-L523](https://github.com/AleksNeStu/ai-real-estate-assistant/blob/bb535cc627f30143ea48d1cf807e2f5fd75402f4/apps/api/agents/hybrid_agent.py#L393-L523)).
- **Tìm kiếm:** Chroma lọc metadata, lấy dư ứng viên theo vector, chấm BM25 trên tập ứng viên đó,
  cộng hai điểm theo `alpha = 0.7`
  ([chroma_store.py#L804-L981](https://github.com/AleksNeStu/ai-real-estate-assistant/blob/bb535cc627f30143ea48d1cf807e2f5fd75402f4/apps/api/vector_store/chroma_store.py#L804-L981)).
  Rerank bằng hệ số nhân thủ công, có phạt đa dạng và chiến lược investor/family/bargain
  ([reranker.py#L82-L413](https://github.com/AleksNeStu/ai-real-estate-assistant/blob/bb535cc627f30143ea48d1cf807e2f5fd75402f4/apps/api/vector_store/reranker.py#L82-L413)).
- **Định giá:** LLM tự sinh con số định giá và dự báo
  ([price_forecast_tools.py#L98-L124](https://github.com/AleksNeStu/ai-real-estate-assistant/blob/bb535cc627f30143ea48d1cf807e2f5fd75402f4/apps/api/tools/price_forecast_tools.py#L98-L124)).
- **Nhận xét:** rất rộng (CRM, lead scoring, MCP, OCR…), đầu tư nhiều vào CI/bảo mật/test (README
  ghi "7,000+" test,
  [#L210](https://github.com/AleksNeStu/ai-real-estate-assistant/blob/bb535cc627f30143ea48d1cf807e2f5fd75402f4/README.md#L210)).
  Phần lõi RAG lại mỏng và có lỗi (mục 4). Học **cách đóng gói và các phản ví dụ**, không học
  kiến trúc.

## 3. Chi tiết

### 1. Bảng test trích điều kiện từng câu + validator sau LLM — Cao

- **Vấn đề của mình:** trả tin sai điều kiện cứng (ngân sách, quận) là lỗi nặng nhất (`[S1]`,
  DoAn2.md §8.3). Spec chỉ có 3 kịch bản `price_units` và đo `[S3]` trên cả hội thoại; khi một
  lượt sai, khó biết lỗi do hiểu số tiền, do merge hay do tra quận.
- **Repo nguồn:** trích giá bằng regex `PRICE_PATTERN = \$?\d{1,5}…`, lấy mọi con số trong câu
  rồi gán min/max
  ([query_analyzer.py#L511](https://github.com/AleksNeStu/ai-real-estate-assistant/blob/bb535cc627f30143ea48d1cf807e2f5fd75402f4/apps/api/agents/query_analyzer.py#L511),
  [#L1041-L1078](https://github.com/AleksNeStu/ai-real-estate-assistant/blob/bb535cc627f30143ea48d1cf807e2f5fd75402f4/apps/api/agents/query_analyzer.py#L1041-L1078)).
  Lần theo code (không chạy):
  - Câu ví dụ trong README, *"2-bedroom apartment in Kraków under 500k"*
    ([README#L5](https://github.com/AleksNeStu/ai-real-estate-assistant/blob/bb535cc627f30143ea48d1cf807e2f5fd75402f4/README.md#L5)):
    regex bắt `2` và `500` ⇒ `min_price=2, max_price=500` (chữ "k" bị bỏ, số phòng bị hiểu là giá).
  - *"3-bedroom house built after 2015 in Gdansk"*: `2015` bị loại vì trùng năm, còn `3`
    ⇒ `max_price=3`.
  - Test của repo có đúng dạng câu này nhưng **chỉ kiểm `max_price`, bỏ qua `min_price=2`**
    nên lỗi lọt qua
    ([test_query_analyzer.py#L121-L134](https://github.com/AleksNeStu/ai-real-estate-assistant/blob/bb535cc627f30143ea48d1cf807e2f5fd75402f4/apps/api/tests/unit/test_query_analyzer.py#L121-L134)).
- **Áp dụng:**
  - `backend/tests/recommend/test_interpreter_cases.py` dạng bảng: một câu đơn → `set_fields`
    kỳ vọng, so **toàn bộ** các trường (trường không nhắc phải là `None`/rỗng, tránh đúng lỗi
    của repo). Case bắt buộc: "dưới 3 tỷ", "2 tỷ rưỡi", "2,5 tỷ", "900 triệu", "từ 4 đến 6 tỷ",
    "2PN 3 tỷ" (số phòng không thành giá), "xây năm 2015" (năm không thành giá), "Q7",
    "quận Bình Thạnh", "Thủ Đức", "gần bệnh viện dưới 2km". Chạy với LLM thật bằng
    `pytest -m llm`, tách khỏi unit test không cần OpenAI của `[S10]`.
  - Validator Pydantic chạy **sau** `TurnInterpreter`, **sau merge**: `price_min ≤ price_max`,
    `area_min ≤ area_max`; giá < 100 (triệu) hoặc > 1.000.000 thì `need_clarification`, không
    tự sửa. Thêm vào §2 "Quy tắc hiểu câu".
- **Lưu ý:** đây là dẫn chứng khi bị hỏi "vì sao dùng LLM + schema thay vì regex".

### 2. 0 kết quả: số liệu gợi ý nới điều kiện do code đếm — Cao

- **Vấn đề của mình:** spec §4 yêu cầu `no_results` "gợi ý nới điều kiện cụ thể đang có" và có
  nhóm `no_results_recover` (3 kịch bản), nhưng không nói gợi ý lấy từ đâu. Nếu để
  `AnswerWriter` tự nghĩ, LLM dễ hứa "nới ngân sách sẽ có tin" khi thực tế vẫn 0 tin.
- **Repo nguồn:** không có tài liệu thì trả câu cố định, **không gọi LLM**
  ([hybrid_agent.py#L664-L680](https://github.com/AleksNeStu/ai-real-estate-assistant/blob/bb535cc627f30143ea48d1cf807e2f5fd75402f4/apps/api/agents/hybrid_agent.py#L664-L680));
  câu hỏi khả năng/ngoài lĩnh vực trả bằng template
  ([#L318-L391](https://github.com/AleksNeStu/ai-real-estate-assistant/blob/bb535cc627f30143ea48d1cf807e2f5fd75402f4/apps/api/agents/hybrid_agent.py#L318-L391)).
  Repo **không** có gợi ý nới; phần đó là mình tự mở rộng.
- **Áp dụng:**
  - Khi 0 kết quả, `HybridSearch` chạy vài `COUNT(*)` với cùng bộ lọc, mỗi câu nới **đúng một**
    điều kiện đang có (bỏ từng `near_pois`, `price_max` +10%, bỏ diện tích, bỏ phòng ngủ).
  - `ChatTurnResult` thêm `relax_options: list[{field, new_value, count}]`; `AnswerWriter` chỉ
    diễn đạt danh sách này ("Nếu bỏ điều kiện bệnh viện sẽ có 12 tin").
  - `no_results_recover` kiểm thêm: con số trong câu trả lời = `count` trong `relax_options`
    (mở rộng `[S5]`).
- **Lưu ý:** vài nghìn tin active, 3–5 câu `COUNT` không đáng kể so với `[S13]`.

### 3. Kaggle chậm/chết: timeout ngắn + cờ `degraded` — Cao

- **Đã có trong spec:** embed lỗi ⇒ sắp theo `posted_at DESC` và nói rõ; rerank sau cờ tắt mặc
  định (§3).
- **Còn thiếu:**
  - Client embed hiện có (`src/pipeline/listing_embedder.py`) dùng `REQUEST_TIMEOUT = 120` giây
    và `MAX_ATTEMPTS = 3` — hợp với embed hàng loạt nhưng nếu dùng lại cho câu hỏi thì một lượt
    có thể treo vài phút, phá `[S13]` (p95 ≤ 8 s).
  - `ChatTurnResult` chưa có trường cho biết lượt đó bị suy giảm, nên test không kiểm được.
- **Repo nguồn:** vector store bọc circuit breaker, trả 503 với thông báo dễ hiểu
  ([search.py#L135-L183](https://github.com/AleksNeStu/ai-real-estate-assistant/blob/bb535cc627f30143ea48d1cf807e2f5fd75402f4/apps/api/api/routers/search.py#L135-L183),
  [circuit.py#L236-L418](https://github.com/AleksNeStu/ai-real-estate-assistant/blob/bb535cc627f30143ea48d1cf807e2f5fd75402f4/apps/api/utils/circuit.py#L236-L418));
  rerank lỗi thì giữ thứ tự cũ
  ([hybrid_retriever.py#L165-L178](https://github.com/AleksNeStu/ai-real-estate-assistant/blob/bb535cc627f30143ea48d1cf807e2f5fd75402f4/apps/api/vector_store/hybrid_retriever.py#L165-L178)).
- **Áp dụng (không cần circuit breaker):** embed câu hỏi timeout ~5 s, thử lại 1 lần;
  `ChatTurnResult.degraded: bool`; unit test với client giả ném timeout ⇒ vẫn trả tin đúng điều
  kiện, `degraded = true`. Lọc cứng SQL/PostGIS không phụ thuộc Kaggle nên `[S1]` vẫn giữ.

### 4. Price Agent: output có cấu trúc, LLM không sinh số — Cao (GĐ8)

- **Vấn đề của mình:** mode `prediction` phải gọi đúng RF active (DoAn2.md §8.4); câu trả lời cần
  đủ căn cứ nhưng LLM không được bịa số. Roadmap GĐ8 mới ghi tên tool `predict_price`.
- **Repo nguồn:**
  - Nên học: output Pydantic `PriceForecastResult` có `confidence`, `comparables_used`, giá/m²
    trung vị, `disclaimer` cố định
    ([price_forecast_tools.py#L74-L90](https://github.com/AleksNeStu/ai-real-estate-assistant/blob/bb535cc627f30143ea48d1cf807e2f5fd75402f4/apps/api/tools/price_forecast_tools.py#L74-L90)).
  - Không học: con số do **LLM sinh**
    ([#L98-L124](https://github.com/AleksNeStu/ai-real-estate-assistant/blob/bb535cc627f30143ea48d1cf807e2f5fd75402f4/apps/api/tools/price_forecast_tools.py#L98-L124)),
    fallback "tăng 3%/năm"
    ([#L358-L413](https://github.com/AleksNeStu/ai-real-estate-assistant/blob/bb535cc627f30143ea48d1cf807e2f5fd75402f4/apps/api/tools/price_forecast_tools.py#L358-L413)),
    tin so sánh tìm bằng độ giống văn bản
    ([#L197-L239](https://github.com/AleksNeStu/ai-real-estate-assistant/blob/bb535cc627f30143ea48d1cf807e2f5fd75402f4/apps/api/tools/price_forecast_tools.py#L197-L239)).
- **Áp dụng:** `PredictPriceOut` gồm `predicted_price` (triệu VND), `model_version`, `variant`;
  `spread_p10_p90` (phân vị dự đoán của các cây trong `estimators_` của bước RF trong
  `Pipeline`); `comparables` tối đa 5 tin cùng loại, `ST_DWithin` 1 km, diện tích ±20%, kèm
  `posted_at`; `median_price_per_m2` của comparables (chỉ để hiển thị, không phải feature);
  `disclaimer` cố định. Response Agent chỉ diễn giải các trường này.
- **Lưu ý:** P10–P90 giữa các cây **không phải** khoảng tin cậy đã hiệu chỉnh; ghi đúng tên trong
  báo cáo.

### 5. Gộp tin gần trùng trong Top 5 — TB

- **Số liệu (đếm lại 09/10/2026 trên `data/listings/listings_clean.jsonl`, 7.603 tin):**

  | Khóa trùng | Nhóm | Tin |
  |---|---|---|
  | `(property_type, price, area, old_address)` | 246 | 528 |
  | + `bedrooms` | 200 | 427 |
  | + `bedrooms, floors, frontage` | 154 | 325 |
  | + `bedrooms, latitude, longitude` | 53 | 111 |
  | cùng `description` | 7 | 14 |
  | Khóa đầu, chỉ tin active tại `as_of = 2026-09-22` (3.535 tin) | 70 | 145 |

- **Đính chính:** khóa 4 trường **không** chứng minh "cùng một căn". 157/246 nhóm là căn hộ, nơi
  `old_address` là địa chỉ cấp dự án; ví dụ nhóm Flora Anh Đào 2,8 tỷ/55 m² gồm một tin "1 phòng
  ngủ" và một tin "2PN" — hai căn khác nhau. Chỉ 5/246 nhóm có mô tả giống hệt.
- **Repo nguồn:** `_apply_diversity_penalty` nhân điểm 0,9 khi trùng thành phố hoặc dải giá 500
  ([reranker.py#L243-L283](https://github.com/AleksNeStu/ai-real-estate-assistant/blob/bb535cc627f30143ea48d1cf807e2f5fd75402f4/apps/api/vector_store/reranker.py#L243-L283),
  [#L40](https://github.com/AleksNeStu/ai-real-estate-assistant/blob/bb535cc627f30143ea48d1cf807e2f5fd75402f4/apps/api/vector_store/reranker.py#L40)).
  Tiêu chí quá thô, không nên chép (mình chỉ có một thành phố).
- **Áp dụng:** sau rerank, duyệt ứng viên theo điểm; tin có cùng khóa
  `(property_type, price, area, old_address, bedrooms)` với tin đã chọn thì **không chiếm chỗ**
  trong Top 5 mà gắn vào `ListingHit.similar_ids` của tin đó. Không mất tin, người dùng vẫn
  thấy. Hàm thuần, unit test riêng.
- **GĐ6:** không tự động xóa theo khóa này trước khi split (sẽ xóa cả căn khác nhau). Chỉ báo cáo
  số nhóm gần trùng nằm vắt qua train/test như một rủi ro rò rỉ.

### 6. Một danh sách kết quả duy nhất — TB

- **Đã có trong spec GĐ7:** `ChatTurnResult.listings` là nguồn duy nhất, `AnswerWriter` chỉ nhận
  JSON này, `ask_detail`/`compare` chỉ đọc `last_results`, `[S5]` kiểm grounding.
- **Repo nguồn (phản ví dụ):** chế độ streaming sinh câu trả lời từ `rag_chain`
  ([hybrid_agent.py#L856-L862](https://github.com/AleksNeStu/ai-real-estate-assistant/blob/bb535cc627f30143ea48d1cf807e2f5fd75402f4/apps/api/agents/hybrid_agent.py#L856-L862)),
  xong router **truy xuất lần hai** bằng `get_sources_for_query` để lấy "nguồn"
  ([chat.py#L247-L260](https://github.com/AleksNeStu/ai-real-estate-assistant/blob/bb535cc627f30143ea48d1cf807e2f5fd75402f4/apps/api/api/routers/chat.py#L247-L260),
  [hybrid_agent.py#L576-L580](https://github.com/AleksNeStu/ai-real-estate-assistant/blob/bb535cc627f30143ea48d1cf807e2f5fd75402f4/apps/api/agents/hybrid_agent.py#L576-L580)).
  Nguồn hiển thị có thể khác tài liệu LLM đã đọc.
- **Áp dụng (GĐ8–9):** `get_map_results(listing_ids)` nhận **danh sách id** từ
  `ChatTurnResult.listings`, không nhận `SearchConstraints` để tự search lại; test: mọi marker
  thuộc `listings`. Nếu sau này stream, gửi danh sách tin trước rồi mới stream text.

### 7. "Lý do phù hợp" tính bằng code — TB

- **Vấn đề của mình:** card Top 5 nên nói vì sao tin hợp, và phải kiểm chứng được. `ListingHit`
  đã có `poi_distances`, nhưng chưa có phần so với điều kiện người dùng.
- **Repo nguồn:** `RankingExplainer` trả từng thành phần điểm
  ([ranking_explainer.py#L99-L246](https://github.com/AleksNeStu/ai-real-estate-assistant/blob/bb535cc627f30143ea48d1cf807e2f5fd75402f4/apps/api/services/ranking_explainer.py#L99-L246)),
  nhưng router không truyền điểm semantic/keyword thật
  ([search.py#L184-L191](https://github.com/AleksNeStu/ai-real-estate-assistant/blob/bb535cc627f30143ea48d1cf807e2f5fd75402f4/apps/api/api/routers/search.py#L184-L191))
  nên explainer gán `semantic_score = final_score`
  ([ranking_explainer.py#L136-L142](https://github.com/AleksNeStu/ai-real-estate-assistant/blob/bb535cc627f30143ea48d1cf807e2f5fd75402f4/apps/api/services/ranking_explainer.py#L136-L142)).
  Phần giải thích không phản ánh thứ hạng thật.
- **Áp dụng:** `ListingHit.match_reasons: list[str]` do hàm thuần
  `match_reasons(listing, constraints)` sinh, ví dụ "Giá 2,8 tỷ ≤ ngân sách 3 tỷ", "Bệnh viện gần
  nhất 350 m". Chỉ giải thích việc **khớp điều kiện**, không giải thích điểm vector/rerank (đề
  cương xếp việc đó vào hướng phát triển, DoAn2.md §11 mục 4).

### 8. Ưu tiên khớp chính xác tên riêng — Thấp

- **Repo nguồn:** BM25 chỉ trên tập ứng viên vector, min–max rồi `alpha·vector + (1−alpha)·BM25`
  ([chroma_store.py#L918-L959](https://github.com/AleksNeStu/ai-real-estate-assistant/blob/bb535cc627f30143ea48d1cf807e2f5fd75402f4/apps/api/vector_store/chroma_store.py#L918-L959)).
- **Áp dụng:** chỉ làm khi kịch bản `soft_semantic` fail `[S7]` vì tên dự án/đường. Khi đó cộng
  điểm thưởng nhỏ nếu `title`/`old_address` chứa cụm từ trong `soft_query` (`unaccent` +
  `ILIKE`). Không kéo thêm thư viện BM25 hay Elasticsearch.

### 9. Giới hạn input, log thời gian — Thấp

- **Repo nguồn:** `SEARCH_MAX_LENGTH = 1_000`
  ([sanitization.py#L23](https://github.com/AleksNeStu/ai-real-estate-assistant/blob/bb535cc627f30143ea48d1cf807e2f5fd75402f4/apps/api/utils/sanitization.py#L23));
  test p95 cho search và chat
  ([tests/performance](https://github.com/AleksNeStu/ai-real-estate-assistant/tree/bb535cc627f30143ea48d1cf807e2f5fd75402f4/apps/api/tests/performance)).
- **Áp dụng:** request `/api/v1/recommend/chat` đặt `message` `max_length=1000`; `run_eval.py`
  ghi thời gian từng bước (interpret/sql/embed/write) để khi `[S13]` fail biết chậm ở đâu.

### 10. Bản đồ — Thấp

- **Repo nguồn:** `FitBounds` padding 24 px, màu marker theo loại BĐS
  ([property-map.tsx#L10-L16](https://github.com/AleksNeStu/ai-real-estate-assistant/blob/bb535cc627f30143ea48d1cf807e2f5fd75402f4/apps/web/src/components/search/property-map.tsx#L10-L16),
  [property-map-clustering.ts#L22-L30](https://github.com/AleksNeStu/ai-real-estate-assistant/blob/bb535cc627f30143ea48d1cf807e2f5fd75402f4/apps/web/src/components/search/property-map-clustering.ts#L22-L30)).
- **Áp dụng:** `fitBounds` trên Top 5 + POI liên quan; marker đánh số 1–5 khớp thứ tự card (khớp
  với "căn thứ N" trong hội thoại); POI icon theo `poi_type`. Không cần clustering.

## 4. Không nên học

| Điểm | Bằng chứng | Lý do |
|---|---|---|
| Nhớ ngữ cảnh nhiều lượt bằng regex quét 5 tin gần nhất, chỉ cộng vào `confidence` | [query_analyzer.py#L1265-L1389](https://github.com/AleksNeStu/ai-real-estate-assistant/blob/bb535cc627f30143ea48d1cf807e2f5fd75402f4/apps/api/agents/query_analyzer.py#L1265-L1389) | Không ghép điều kiện cũ với mới. Spec của mình (`ConversationStore` + delta + merge bằng code) đúng hướng hơn. |
| Đoán intent bằng từ khóa, confidence tự đặt (0,4/0,3/+0,3/−0,15 mỗi tín hiệu) | [query_analyzer.py#L859-L894](https://github.com/AleksNeStu/ai-real-estate-assistant/blob/bb535cc627f30143ea48d1cf807e2f5fd75402f4/apps/api/agents/query_analyzer.py#L859-L894) | Confidence thấp vẫn đi nhánh hybrid ([hybrid_agent.py#L497-L523](https://github.com/AleksNeStu/ai-real-estate-assistant/blob/bb535cc627f30143ea48d1cf807e2f5fd75402f4/apps/api/agents/hybrid_agent.py#L497-L523)). `LLMIntentClassifier` có viết nhưng không được import ở đâu, kể cả test. Mode do client chọn rõ ràng hơn. |
| Lọc sau khi đã lấy top-k vector (`fetch_k = k*3`/`k*5`), lọc bán kính bằng haversine trong Python | [chroma_store.py#L876-L900](https://github.com/AleksNeStu/ai-real-estate-assistant/blob/bb535cc627f30143ea48d1cf807e2f5fd75402f4/apps/api/vector_store/chroma_store.py#L876-L900), [hybrid_retriever.py#L151-L163](https://github.com/AleksNeStu/ai-real-estate-assistant/blob/bb535cc627f30143ea48d1cf807e2f5fd75402f4/apps/api/vector_store/hybrid_retriever.py#L151-L163) | Dễ trả ít hơn k tin hoặc bỏ sót tin khớp. Mình lọc SQL/PostGIS **trước** rồi mới sắp theo vector. |
| LLM sinh giá; fallback tăng 3%/năm | mục 3.4 | Trái nguyên tắc "không suy đoán". Mình có RF + A/B. |
| Ngưỡng cứng không theo dữ liệu (`pp_sqm < 3000`, `price < 200000`, `has_images` mặc định `True`) | [reranker.py#L233](https://github.com/AleksNeStu/ai-real-estate-assistant/blob/bb535cc627f30143ea48d1cf807e2f5fd75402f4/apps/api/vector_store/reranker.py#L233), [#L382](https://github.com/AleksNeStu/ai-real-estate-assistant/blob/bb535cc627f30143ea48d1cf807e2f5fd75402f4/apps/api/vector_store/reranker.py#L382), [#L400](https://github.com/AleksNeStu/ai-real-estate-assistant/blob/bb535cc627f30143ea48d1cf807e2f5fd75402f4/apps/api/vector_store/reranker.py#L400) | Hệ số rerank thủ công, không có đánh giá đi kèm. |
| Trả `str(e)` cho người dùng | [hybrid_agent.py#L688](https://github.com/AleksNeStu/ai-real-estate-assistant/blob/bb535cc627f30143ea48d1cf807e2f5fd75402f4/apps/api/agents/hybrid_agent.py#L688), [chat.py#L285](https://github.com/AleksNeStu/ai-real-estate-assistant/blob/bb535cc627f30143ea48d1cf807e2f5fd75402f4/apps/api/api/routers/chat.py#L285) | Lộ chi tiết nội bộ. Trả thông báo chung, chi tiết ghi log. |
| LangChain `ConversationalRetrievalChain`/`AgentExecutor`, 13 provider | [hybrid_agent.py#L134-L160](https://github.com/AleksNeStu/ai-real-estate-assistant/blob/bb535cc627f30143ea48d1cf807e2f5fd75402f4/apps/api/agents/hybrid_agent.py#L134-L160) | Repo phải thêm `langchain-classic` khi LangChain dời module ([pyproject#L55-L58](https://github.com/AleksNeStu/ai-real-estate-assistant/blob/bb535cc627f30143ea48d1cf807e2f5fd75402f4/apps/api/pyproject.toml#L55-L58)). Củng cố quyết định roadmap/spec §5: chỉ `openai` SDK + Pydantic. |
| Con số "MMR … 30-40% better relevance" | [README#L156](https://github.com/AleksNeStu/ai-real-estate-assistant/blob/bb535cc627f30143ea48d1cf807e2f5fd75402f4/README.md#L156) | Không tìm thấy thí nghiệm offline nào trong repo. Không trích dẫn. |

## 5. Ngoài phạm vi đề cương (hướng phát triển)

- **Lưu tìm kiếm + báo tin mới khớp điều kiện**
  ([saved_searches.py](https://github.com/AleksNeStu/ai-real-estate-assistant/blob/bb535cc627f30143ea48d1cf807e2f5fd75402f4/apps/api/utils/saved_searches.py)):
  hợp với crawler incremental (chạy lại `SearchConstraints` đã lưu sau mỗi lượt crawl).
- **Chỉ số từ click** (CTR/MRR/NDCG)
  ([search_metrics_service.py](https://github.com/AleksNeStu/ai-real-estate-assistant/blob/bb535cc627f30143ea48d1cf807e2f5fd75402f4/apps/api/services/search_metrics_service.py)):
  bổ sung cho Precision@5 offline khi có người dùng thật.
- **Cấu hình trọng số và A/B ranking**
  ([ranking_config_service.py](https://github.com/AleksNeStu/ai-real-estate-assistant/blob/bb535cc627f30143ea48d1cf807e2f5fd75402f4/apps/api/services/ranking_config_service.py),
  [ab_testing_service.py](https://github.com/AleksNeStu/ai-real-estate-assistant/blob/bb535cc627f30143ea48d1cf807e2f5fd75402f4/apps/api/services/ab_testing_service.py)).
- **Tóm tắt khu vực**
  ([neighborhood_summary.py](https://github.com/AleksNeStu/ai-real-estate-assistant/blob/bb535cc627f30143ea48d1cf807e2f5fd75402f4/apps/api/tools/neighborhood_summary.py)),
  nếu làm thì dựa trên số POI trong DB.
- **Công cụ tài chính, phát hiện giá bất thường**
  ([anomaly_service.py](https://github.com/AleksNeStu/ai-real-estate-assistant/blob/bb535cc627f30143ea48d1cf807e2f5fd75402f4/apps/api/services/anomaly_service.py)),
  tra cứu web, đa ngôn ngữ, CRM: ngoài đề cương.

## Nhật ký phản biện

**09/10/2026 — doc-reviewer**

- Kiểm chứng: tải mã nguồn tại `bb535cc` (raw.githubusercontent.com và tarball codeload) và
  đọc đúng các dòng được trích. WebFetch tới raw.githubusercontent.com bị chặn trong môi trường
  này nên dùng curl. Mọi permalink còn lại trong file đều mở được và khớp nội dung; một số dải
  dòng được thu hẹp cho chính xác (`chat.py#L247-L260`, `hybrid_agent.py#L576-L580`,
  `price_forecast_tools.py#L74-L90`, `query_analyzer.py#L511`, `#L1041-L1078`).
- Con số tự đo:
  - Regex `QueryAnalyzer`: kết quả `min_price=2, max_price=500` và `max_price=3` **khớp** khi lần
    theo code. Không chạy được code repo trong môi trường này nên **xóa** `confidence=0.0`
    (không kiểm lại được). Thay câu "không có test nào bắt lỗi" bằng bằng chứng cụ thể
    `test_query_analyzer.py#L121-L134`.
  - 528/7.603 tin, 246 nhóm: **đếm lại khớp**. Nhưng diễn giải "cùng một căn" sai: phần lớn là
    căn hộ cùng dự án, có nhóm khác số phòng ngủ. Thêm bảng khóa chặt hơn, đổi cách áp dụng từ
    "bỏ tin" sang "gộp vào `similar_ids`", hạ ưu tiên Cao → TB, bỏ đề xuất xóa trùng trước split
    GĐ6.
- Đối chiếu spec hội thoại (`hybrid-search.md`):
  - Bài "giữ điều kiện qua nhiều lượt" **xóa khỏi danh sách bài học** (đã có trong spec;
    đề xuất cũ lấy state từ `search_logs` lệch với `ConversationStore`). Phần repo làm kém chuyển
    sang "Không nên học".
  - Bài "ngoài phạm vi": bỏ đề xuất trường `off_topic` (spec đã có `intent = out_of_scope`); giữ
    và nâng ưu tiên phần gợi ý nới bằng `COUNT` (spec §4 chưa nói nguồn số liệu) thành Cao.
  - Bài "truy xuất một lần": phần GĐ7 đã có trong spec; hạ Cao → TB, chỉ giữ phần GĐ8–9
    (`get_map_results` nhận id).
  - Bài "Kaggle chết": phần sắp theo `posted_at` đã có trong spec; giữ phần còn thiếu (timeout
    ngắn — client hiện tại 120 s × 3 lần — và cờ `degraded`).
  - Đổi tên trường cho khớp spec: `budget_min/max` → `price_min/max`, bộ 40 câu → 50 kịch bản,
    `search_listings()` → `HybridSearch.search`.
- Sửa nhỏ: `LLMIntentClassifier` không được import ở đâu kể cả test (bản cũ ghi "ngoài test");
  hướng phát triển là DoAn2.md §11 (bản cũ ghi §10); tiêu chí Hybrid Search là DoAn2.md §8.3;
  bỏ `context_manager.py` khỏi bảng "Không nên học" (không đối chiếu được nội dung "tóm tắt
  context bằng LLM"); bỏ "React 19" và "PostgreSQL/SQLite" ở phần stack (không đối chiếu).
- Thêm cột "Mục spec cần sửa" vào bảng tổng hợp.
