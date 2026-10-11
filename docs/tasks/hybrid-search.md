# Task GĐ7: Hội thoại gợi ý nhà đất (mode recommendation) + Hybrid Search

Spec chung cho `db-coder` (cài đặt) và `query-tester` (viết 50 kịch bản hội thoại, chạy, báo
lỗi). Main session là người duyệt cuối: tự review code và tự chạy lại toàn bộ test sau mỗi
lần agent báo xong.

Điều kiện bắt đầu: [address-db.md](address-db.md) đã PASS (09/10). **Phát triển và test trên DB
`housing_dev`** (đủ dữ liệu schema mới + embedding) cho tới khi người dùng áp migration lên
`housing`. Kết nối: `postgresql://postgres:123456789@localhost:5432/housing_dev`; mọi code đọc
URL từ biến môi trường (`DATABASE_URL`), không hard-code tên DB. Thư mục code: `housing-backend/housing-backend/` (`backend/`).

Đề cương §5.8, §5.10 (mode recommendation), §7.3, §7.4: thu thập nhu cầu **qua nhiều lượt
hỏi**, trích thành JSON có schema, phân biệt điều kiện cứng/sở thích mềm, **hỏi bổ sung khi
thiếu**, lọc SQL + PostGIS → vector search → rerank → tối đa 5 tin active; hỏi thêm và so sánh
các tin đã trả về **trong cùng mode**.

---

## 1. Luồng một lượt hội thoại

```text
(conversation_id, message)
   │
   ▼
ConversationStore.get(conversation_id) ──> ConversationState
   │      constraints hiện tại, last_results (≤5 listing_id theo thứ tự), pending_question,
   │      6 lượt gần nhất (để LLM hiểu ngữ cảnh)
   ▼
TurnInterpreter (gpt-4o-mini, structured output) ──> TurnPlan
   │      intent + thay đổi điều kiện (delta) + tham chiếu tin ("căn thứ 2", "tin 4452...")
   ▼
RecommendationService (code, tất định) chọn nhánh theo intent:
   search / refine / relax / answer_clarification ─> merge delta vào constraints
        ─> thiếu điều kiện bắt buộc? ─> need_clarification
        ─> HybridSearch.search(constraints, as_of) ─> Top 5 ─> AnswerWriter
   ask_detail / compare ─> chỉ đọc DB cho các tin trong last_results ─> AnswerWriter
   reset ─> xóa constraints + last_results
   out_of_scope ─> từ chối lịch sự, giữ nguyên state
   │
   ▼
ConversationStore.save(state) ──> ChatTurnResult
```

LLM chỉ ở 2 chỗ: `TurnInterpreter` và `AnswerWriter`. LLM **không** sinh SQL, không tự chọn
bước, không tự đổi mode. Merge điều kiện là code thuần, test được không cần OpenAI.

## 2. Hợp đồng dữ liệu

```python
class PoiConstraint(BaseModel):
    poi_type: Literal["truong_hoc", "benh_vien", "cho"]
    max_distance_m: int                      # "dưới 2 km" -> 2000

class SearchConstraints(BaseModel):
    price_min: float | None = None           # triệu VND, như listings.price
    price_max: float | None = None
    property_types: list[str] = []           # giá trị nguyên văn của listings.property_type
    district_ids: list[int] = []             # districts_old.id
    new_ward_ids: list[int] = []             # wards_new.id
    area_min: float | None = None
    area_max: float | None = None
    bedrooms_min: int | None = None
    near_pois: list[PoiConstraint] = []
    soft_query: str | None = None            # sở thích mềm, dùng cho vector search

class TurnPlan(BaseModel):
    intent: Literal["search", "refine", "relax", "answer_clarification",
                    "ask_detail", "compare", "reset", "out_of_scope"]
    set_fields: ConstraintDelta              # trường cần đặt/ghi đè (tên quận dạng chữ)
    clear_fields: list[str] = []             # trường cần bỏ ("bỏ điều kiện bệnh viện")
    result_refs: list[int] = []              # vị trí 1..5 trong last_results
    listing_ids: list[str] = []              # khi người dùng gọi theo mã tin
    question: str | None = None              # câu hỏi chi tiết (ask_detail/compare)

class ChatTurnResult(BaseModel):
    conversation_id: str
    status: Literal["ok", "need_clarification", "out_of_scope", "no_results", "answered"]
    constraints: SearchConstraints           # trạng thái SAU lượt này
    listings: list[ListingHit]               # tối đa 5; rỗng với ask_detail/compare
    referenced_ids: list[str]                # tin được nói tới ở ask_detail/compare
    relax_options: list[RelaxOption] = []    # chỉ khi no_results, do CODE đếm (mục 4)
    degraded: bool = False                   # True khi embed/rerank lỗi và đã dùng phương án dự phòng
    answer: str

class RelaxOption(BaseModel):
    field: str                               # trường được nới, vd. "near_pois", "price_max"
    description: str                         # "bỏ điều kiện gần bệnh viện", "tăng ngân sách lên 3,5 tỷ"
    result_count: int                        # số tin có được nếu chỉ nới đúng điều kiện này
```

`ListingHit`: `listing_id, title, price, area, property_type, bedrooms, district_old,
old_address, new_address, listing_url, posted_at, expired_at, poi_distances: dict[str, float]`,
`score`, `similar_ids: list[str]` (tin đăng lại gần như y hệt đã gộp vào tin này, mục 3).

### Quy tắc hiểu câu

- Giá: "3 tỷ" = 3000, "2 tỷ rưỡi" = 2500, "900 triệu" = 900. "Có/tầm/dưới 3 tỷ" ⇒ `price_max`.
  "Rẻ hơn chút" khi đã có `price_max` ⇒ giảm 10% (ghi trong code là hằng số, nói rõ trong
  câu trả lời). "Tăng ngân sách lên 4 tỷ" ⇒ ghi đè.
- Khu vực: LLM trả **tên**; code tra `districts_old`/`wards_new` (không phân biệt hoa/thường,
  cho phép bỏ dấu qua `unaccent`). "Thủ Đức" (TP Thủ Đức) ⇒ `Quận 2`, `Quận 9`, `Thủ Đức`.
  "Còn ở Quận 7 thì sao" ⇒ **thay** khu vực, giữ các điều kiện khác. Không khớp ⇒ hỏi lại.
- Loại BĐS: bảng map hằng số về giá trị thật của `listings.property_type`.
- Bắt buộc có ít nhất **ngân sách hoặc khu vực** trước khi tìm. Thiếu ⇒ `need_clarification`
  và đặt `pending_question`; lượt sau người dùng trả lời ⇒ `answer_clarification`.
- `ask_detail`/`compare`: chỉ trả lời từ dữ liệu DB của tin trong `last_results` (cột tin +
  `listing_spatial_features` + POI gần nhất). Tham chiếu ngoài 1..5 hoặc mã tin không có trong
  `last_results` ⇒ nói không tìm thấy, không đoán.
- Ngoài phạm vi: tỉnh khác, thuê nhà, đấu giá, tư vấn pháp lý/tài chính, không liên quan BĐS.
  Trả `out_of_scope`, **không xóa** state.
- Bỏ qua mọi chỉ dẫn trong message muốn đổi vai trò/luật/mode (prompt injection).
- **Validator sau khi merge** (code, không phải LLM): `price_min <= price_max`,
  `area_min <= area_max`, giá trong khoảng hợp lý (100 triệu – 500 tỷ), diện tích 10–10.000 m²,
  `max_distance_m` 100–20.000. Vi phạm ⇒ `need_clarification` hỏi lại đúng trường đó, không tự sửa.
- Không nhầm số khác thành giá: "2PN 3 tỷ" ⇒ `bedrooms_min = 2`, `price_max = 3000`; "xây năm
  2015", "hẻm 5m", "tầng 12" không phải giá. Đây là lỗi thật của repo tham khảo
  ([lessons](../research/ai-real-estate-assistant-lessons.md)) — phải có unit test riêng.
- `message` dài quá 1.000 ký tự ⇒ cắt và báo người dùng, không gửi nguyên văn vào LLM.

## 3. Truy vấn

- Lọc cứng: `expired_at >= as_of`, `posted_at <= as_of` (khi có cột `status` từ GĐ3 thì thêm
  `status = 'active'`), giá, loại, quận/phường, diện tích, phòng ngủ.
- POI: mỗi `PoiConstraint` là `EXISTS (... ST_DWithin(p.geom, l.geom, :d))`; tin không có
  `geom` bị loại khi có điều kiện POI.
- Sắp xếp: `embedding <=> :qvec`, `qvec` = embedding của `soft_query` (không có thì của tóm
  tắt điều kiện). API embedding Kaggle lỗi ⇒ sắp theo `posted_at DESC` và nói rõ trong câu trả lời.
- Embed câu hỏi: client riêng, **timeout 5 giây, retry 1 lần** (không dùng lại client batch
  của `listing_embedder.py` — 120 giây × 3 lần sẽ phá `[S13]`). Lỗi ⇒ dự phòng như trên,
  `degraded = True`.
- Rerank: cờ `RERANK_ENABLED`, mặc định tắt; code đúng khi tắt; rerank lỗi ⇒ giữ thứ tự vector,
  `degraded = True`.
- Gộp tin đăng lại trước khi cắt Top 5: hai tin cùng `property_type, price, area, bedrooms` và
  tọa độ cách nhau < 30 m coi là một; giữ tin có `posted_at` mới nhất, các tin còn lại vào
  `similar_ids`. (Không gộp chỉ theo `old_address`: căn hộ chỉ ghi địa chỉ cấp dự án — tập active
  ngày 22/09 có 70 nhóm/145 tin trùng theo khóa đầy đủ.)
- Ghi log thời gian từng bước (interpret, embed, SQL, write) để tìm nguyên nhân khi `[S13]` fail.
- `as_of`: mặc định hôm nay; **bộ test dùng `2026-09-22`** (dữ liệu crawl đến 21/09). Không
  hard-code ngày này trong code chính.
- Mọi giá trị qua placeholder SQL.

## 4. Trả lời

- `AnswerWriter` chỉ nhận JSON của tin trả về (hoặc tin được tham chiếu). Mỗi tin: giá, diện
  tích, địa chỉ, khoảng cách POI liên quan, ngày đăng, URL, `[Tin <listing_id>]`.
- Không được nhắc ID, giá, địa chỉ, URL không có trong dữ liệu đưa vào.
- `no_results`: **code** chạy `COUNT` cho từng phương án nới đúng một điều kiện (bỏ một POI,
  tăng ngân sách 20%, bỏ loại BĐS, mở rộng khu vực ra toàn TP), đưa vào `relax_options` các
  phương án có `result_count > 0`. `AnswerWriter` chỉ diễn đạt danh sách đó, kèm con số; không tự
  nghĩ ra phương án.
- Khi refine/relax: nói ngắn điều kiện đã đổi ("Đã giảm ngân sách xuống 2,7 tỷ").
- Cuối câu: "Giá là giá rao bán tham khảo".

## 5. Vị trí code và API

- `backend/app/services/recommendation/`: `schemas.py` (Pydantic), `interpreter.py`
  (`TurnInterpreter`), `search.py` (`HybridSearch`), `writer.py` (`AnswerWriter`),
  `service.py` (`RecommendationService`, `ConversationStore`). Mỗi file một trách nhiệm, không
  tách hàm vụn.
- `ConversationStore`: lưu trong bộ nhớ (dict theo `conversation_id`), giao diện `get/save/reset`
  để GĐ8 thay bằng bảng `chat_sessions` mà không đổi service.
- `POST /api/v1/recommend/chat {conversation_id?, message, as_of?}` → `ChatTurnResult`
  (không gửi `conversation_id` ⇒ tạo mới).
- OpenAI: `OPENAI_API_KEY`, `OPENAI_MODEL` từ `.env` gốc. Phụ thuộc mới duy nhất: `openai`.
  Không LangChain/LangGraph.

## 6. Bộ 50 kịch bản hội thoại (query-tester viết)

Vị trí: `backend/tests/recommend/scenarios.json`, `test_recommend.py`, `run_eval.py`,
`report.md`.

**Mỗi kịch bản là một chuỗi 2–6 lượt** liên tục trong cùng `conversation_id` (tổng ≥ 150
lượt). Ví dụ:

```json
{
  "id": "C01",
  "category": "progressive",
  "as_of": "2026-09-22",
  "turns": [
    {"user": "Mình muốn mua nhà cho gia đình",
     "expect_status": "need_clarification"},
    {"user": "Tầm 3 tỷ, khu Thủ Đức",
     "expect_status": "ok",
     "expect_constraints": {"price_max": 3000, "district_names": ["Quận 2", "Quận 9", "Thủ Đức"]}},
    {"user": "Ưu tiên căn hộ, gần bệnh viện dưới 2km",
     "expect_status": "ok",
     "expect_constraints": {"price_max": 3000, "property_types": ["Căn hộ chung cư"],
                            "near_pois": [{"poi_type": "benh_vien", "max_distance_m": 2000}]},
     "min_results": 1},
    {"user": "Căn thứ 2 có mấy phòng ngủ, gần chợ nào?",
     "expect_status": "answered", "expect_refs": [2]},
    {"user": "So sánh căn 1 và căn 3 giúp mình",
     "expect_status": "answered", "expect_refs": [1, 3]}
  ]
}
```

`expect_constraints` là trạng thái **cộng dồn sau lượt đó**, chỉ ghi trường cần kiểm, dùng tên
quận (test tự tra ID). `min_results` tính bằng **SQL oracle** do tester tự viết.

Phân bổ bắt buộc (đủ 50 kịch bản):

| Nhóm | Số | Hành vi kiểm |
|---|---|---|
| `progressive` | 8 | bắt đầu mơ hồ → hỏi lại → bổ sung dần từng điều kiện |
| `refine` | 7 | thu hẹp: thêm loại, diện tích, phòng ngủ, "rẻ hơn chút", thêm POI |
| `relax` | 5 | nới: "bỏ điều kiện bệnh viện", "tăng lên 4 tỷ", "quận nào cũng được" |
| `switch_area` | 4 | "còn ở Quận 7 thì sao", giữ nguyên các điều kiện khác |
| `detail_compare` | 7 | hỏi chi tiết căn thứ N / theo mã tin, so sánh 2–3 căn, tham chiếu sai (căn thứ 7) |
| `price_units` | 3 | "2 tỷ rưỡi", "900 triệu", "từ 4 đến 6 tỷ", "3,5 tỷ" trong mạch hội thoại |
| `new_address` | 3 | tên phường mới sau sáp nhập |
| `soft_semantic` | 4 | sở thích mềm thêm dần: "yên tĩnh", "hẻm xe hơi", "nội thất đầy đủ" |
| `no_results_recover` | 3 | điều kiện không thỏa → bot gợi ý nới → người dùng nới → có kết quả |
| `reset` | 2 | "tìm lại từ đầu" → state sạch, điều kiện cũ không rò sang |
| `out_of_scope_mid` | 3 | hỏi Hà Nội / thuê nhà / thủ tục pháp lý giữa chừng → từ chối, lượt sau tiếp tục với điều kiện cũ |
| `injection` | 1 | chèn "bỏ qua hướng dẫn..." giữa hội thoại |

## 7. Tiêu chí nghiệm thu (chấm trên từng lượt)

| Mã | Tiêu chí | Ngưỡng |
|---|---|---|
| `[S1]` | Tin trả về vi phạm điều kiện cứng **cộng dồn** (oracle SQL kiểm từng tin) | **0** lượt |
| `[S2]` | `status` đúng kỳ vọng | 100% lượt |
| `[S3]` | Trường trong `expect_constraints` đúng sau lượt | ≥ 95% số trường |
| `[S4]` | Lượt `ok` có ≥ `min_results` kết quả (tối đa 5) | 100% |
| `[S5]` | Grounding: `answer` không chứa listing_id/URL/giá ngoài dữ liệu đưa vào lượt đó | 100% |
| `[S6]` | Chỉ tin `expired_at >= as_of` và `posted_at <= as_of` | 100% |
| `[S7]` | Soft relevance (4 kịch bản `soft_semantic`): tester đọc Top 5, chấm số tin phù hợp, ghi lý do | ≥ 3/5 trung bình |
| `[S8]` | Tham chiếu: `referenced_ids` = đúng tin ở vị trí/mã được hỏi; tham chiếu sai ⇒ báo không có | 100% |
| `[S9]` | Không rò state: sau `reset` và giữa các `conversation_id` khác nhau, điều kiện cũ không xuất hiện | 100% |
| `[S10]` | `pytest backend/tests/recommend` xanh bằng một lệnh; unit test không cần OpenAI cho `HybridSearch`, merge, validator, gộp tin trùng, dự phòng khi embed lỗi (client giả); bảng test trích điều kiện từng câu (≥ 30 câu, so **toàn bộ** trường, gồm "2PN 3 tỷ", "xây năm 2015") đánh dấu `pytest -m llm` | xanh |
| `[S14]` | Lượt `no_results`: mỗi `relax_options[i].result_count` khớp oracle SQL; câu trả lời chỉ nêu các phương án đó | 100% |
| `[S15]` | Không có 2 tin trong cùng Top 5 thuộc một nhóm tin đăng lại (khóa ở mục 3) | 100% |
| `[S11]` | Code sạch theo `[F2]` của [address-db.md](address-db.md); `uvx ruff check` sạch | — |
| `[S12]` | Không SQL ghép chuỗi giá trị người dùng; không key trong code/log | — |
| `[S13]` | p95 thời gian mỗi lượt ≤ 8 giây | — |

Chi phí: ~150 lượt × 2 lần gọi gpt-4o-mini mỗi vòng (vài chục cent). Sửa nhỏ có thể chạy
lại riêng kịch bản FAIL bằng `--ids C03,C17`, nhưng **trước khi báo PASS phải chạy đủ 50**.

## 8. Vòng lặp và duyệt cuối

```text
query-tester: viết 50 kịch bản + oracle + harness
db-coder:     cài đặt theo spec, tự chạy unit test + vài kịch bản
loop:
  query-tester: chạy đủ 50 ──> báo cáo FAIL
  db-coder:     sửa code hệ thống (không sửa test) ──> tự chạy lại kịch bản FAIL
  (tối đa 6 vòng, dừng khi đạt mọi ngưỡng)
main (duyệt cuối): tự review code + tự chạy lại đủ 50 kịch bản + tự đóng vai khách hàng
  hỏi một chuỗi câu mới (không có trong bộ test) qua API để tìm nhà ưng ý; chưa đạt ⇒ trả về db-coder,
  sau khi sửa ⇒ main chạy lại toàn bộ lần nữa.
```

Test sai (kỳ vọng không hợp lý với dữ liệu) chỉ query-tester được sửa và phải ghi lý do trong
`report.md`; main kiểm lại mọi thay đổi bộ test. Không được hạ ngưỡng mục 7 để qua.

## 9. Quyết định bổ sung của main (09/10, trả lời câu hỏi của query-tester)

| # | Tình huống | Quyết định |
|---|---|---|
| 1 | Lượt `reset` ("tìm lại từ đầu") | Xóa constraints + last_results. Nếu cùng câu không có điều kiện mới ⇒ `need_clarification`, state trống. Nếu có ("tìm lại, căn hộ Q3 dưới 4 tỷ") ⇒ áp điều kiện mới lên state trống rồi tìm như `search`. |
| 2 | Tham chiếu sai ("căn thứ 7", mã tin không có trong last_results) | `answered`, `referenced_ids = []`, câu trả lời nói rõ chỉ có N căn. State không đổi. |
| 3 | Validator vi phạm (vd. `price_min` 8000 > `price_max` 6000) | `need_clarification`; **không áp delta** — constraints sau lượt = constraints trước lượt. Tester chấm điều này. |
| 4 | Prompt injection thuần | `out_of_scope`, state giữ nguyên. |
| 5 | `RelaxOption.field` | Đúng 4 giá trị: `near_pois` (bỏ **một** điều kiện POI; nhiều POI ⇒ mỗi POI một option, `description` nói rõ POI nào), `price_max` (× 1,2, không làm tròn), `property_types` (bỏ lọc loại), `location` (bỏ `district_ids` + `new_ward_ids`). `result_count` = số tin **sau khi gộp tin đăng lại** (đúng số người dùng sẽ thấy). |
| 6 | Quận cũ và phường mới cùng lúc | Lọc AND. Tên trùng giữa quận cũ và phường mới (Thủ Đức, Bình Thạnh, Gò Vấp, Bình Tân, Nhà Bè): có chữ "phường"/"xã" đi trước ⇒ phường mới; còn lại (kể cả "quận X" hay tên trần) ⇒ quận cũ. Tester thêm lượt kiểm quy tắc này vào kịch bản `new_address` có sẵn (không tăng số kịch bản). |
| 7 | Giao diện Python | `RecommendationService()` (không tham số bắt buộc, đọc settings) với `chat(conversation_id: str \| None, message: str, as_of: date \| None = None) -> ChatTurnResult`. API là đường chấm chính. |
| 8 | Unit test `[S10]` | db-coder viết (cần giao diện nội bộ) trong `tests/recommend/unit/`; bảng trích điều kiện do query-tester giữ (`extraction_cases.json`). |
| 9 | `[S5]` với giá | ID/URL chấm tự động. Giá: harness tự tách số "tỷ/triệu" và so với giá các tin đưa vào + điều kiện + relax_options (sai số 1%); không khớp ⇒ đưa vào danh sách chấm tay, main xem cuối cùng. |
| 10 | "Ưu tiên căn hộ" | Loại BĐS được nhắc tới luôn là điều kiện cứng (`property_types`), dù có chữ "ưu tiên". Tính từ (yên tĩnh, thoáng, đẹp) là sở thích mềm (`soft_query`). "Mua nhà" chung chung không đặt `property_types`. |
| 11 | POI không nói khoảng cách ("gần bệnh viện") | Mặc định **2.000 m** (hằng số trong code), câu trả lời nói rõ "trong bán kính 2 km". Tester sửa 1–2 lượt có sẵn để kiểm mặc định này. |
| 12 | Cách tính `[S7]` | Chấm trên **mọi lượt `ok`** của 4 kịch bản `soft_semantic` (không chỉ lượt cuối). Ngưỡng giữ ≥ 3/5 trung bình. |
| 13 | Ai viết lời ở lượt `ok` (sau vòng chấm 1) | **Code** viết toàn bộ (điều kiện đang áp, số tin, thay đổi, khối 5 tin). LLM chỉ viết ở `ask_detail`/`compare`, và chỉ diễn đạt "facts" do code dựng sẵn (gồm các so sánh lớn/nhỏ/rẻ/đắt đã tính). Lý do: vòng 1 LLM tự khẳng định thuộc tính không có trong dữ liệu (C41) và so sánh sai số (C01#5). |
| 14 | Quy tắc tất định | Reset, tham chiếu "căn thứ N"/mã tin, "phường/xã <tên>", "rẻ hơn", số đi với "lầu/tầng/trệt" — **code** quyết định; đầu ra LLM chỉ được dùng khi code không nhận diện được và phải qua kiểm tra. |
| 15 | Giá "xấp xỉ" (người dùng quyết 09/10) | "tầm / khoảng / cỡ / độ / xấp xỉ / gần X tỷ" ⇒ khoảng giá `price_min = X × (1 − 20%)`, `price_max = X × (1 + 5%)` (vd. "tầm 3 tỷ" ⇒ 2.400–3.150 triệu). Hai tỷ lệ là hằng số cấu hình `PRICE_APPROX_LOW = 0.20`, `PRICE_APPROX_HIGH = 0.05`; người dùng nói rõ tỷ lệ ("tầm 3 tỷ, lệch 10%") thì dùng tỷ lệ đó cho cả hai phía. **Code** tính (không để LLM tự nhân), LLM chỉ gắn cờ `price_approx = true` kèm giá gốc X. "Dưới/tối đa/có X tỷ" vẫn là `price_max = X`; "trên/từ X" là `price_min = X`; "từ A đến B" giữ nguyên. Câu trả lời nói rõ khoảng đã áp ("giá khoảng 2,4 – 3,15 tỷ"). Khi đã có khoảng, "rẻ hơn chút" hạ cả hai biên 10%. Nới điều kiện `price_max` (×1,2) dùng biên trên. |
| 16 | Đổi giá sau khoảng xấp xỉ | "Nâng/giảm ngân sách lên/xuống X" = giá tối đa mới X; `price_min` **do xấp xỉ sinh ra** bị bỏ (vì khoảng cũ dựng quanh giá cũ); `price_min` người dùng nói rõ ("từ 2 tỷ") thì giữ. Cần cờ `price_min_derived` trong state. |
| 17 | "6 tỷ đổ lại", "tam 3 ty" | "X đổ lại" = `price_max = X`. "tam/tầm" không dấu đi liền số tiền = xấp xỉ (so khớp sau khi bỏ dấu). |
| 18 | Địa điểm ngoài 3 loại POI (trung tâm thương mại, công viên, siêu thị, metro…) | Không bao giờ thành `near_pois` (chỉ `truong_hoc`, `benh_vien`, `cho`, và chỉ khi message nhắc "trường/bệnh viện/chợ"); đưa vào `soft_query`. |
| 19 | `[S7]` | Chấm riêng các lượt có sở thích mềm mới (8 lượt của 4 kịch bản), ngưỡng ≥ 3/5 trung bình. Phải đạt — chưa đạt thì cải thiện xếp hạng (xem mục 20). |
| 20 | Xếp hạng sở thích mềm | Điểm = điểm vector + cộng thêm theo **từ khóa**: mỗi cụm sở thích (tách từ `soft_query`, bỏ dấu) xuất hiện trong tiêu đề/mô tả thì +`LEXICAL_BOOST` (0,10; hằng số cấu hình). Lý do: embedding một cụm ngắn ("yên tĩnh") xếp tin có chữ này thấp hơn tin dài không liên quan (C38#2). Áp dụng trên các ứng viên đã lọc cứng. Lượt không có `soft_query` giữ nguyên thứ tự cũ. |
| 21 | Reset | Xóa state ngay khi người dùng đòi tìm lại, kể cả nếu phần điều kiện mới sau đó bị hỏi lại (khu vực lạ, validator). Ghi rõ trong câu trả lời "Đã xóa các điều kiện cũ". |
| 22 | Câu hỏi thuộc tính ở `ask_detail`/`compare` | Câu hỏi khớp đúng một thuộc tính (`Metric.keywords`: phòng tắm, diện tích, pháp lý…) ⇒ **code trả lời thẳng** từ facts (không qua LLM). Địa chỉ cũ + mới (nếu có) và `[Tin <id>]` cho mỗi "Căn N" do code nối, LLM không viết. Câu trả lời LLM bị cắt (`finish_reason == "length"`) hoặc vi phạm grounding ⇒ bản code. |
| 23 | Loại BĐS khi LLM không trả | **Code** suy từ từ khóa (kể cả không dấu): "đất nền" ⇒ `Đất nền dự án`; "đất" (không kèm "nền") ⇒ `Bán đất`; "căn hộ/chung cư" ⇒ `Căn hộ chung cư`; "nhà riêng/nhà phố"… theo bảng map hiện có. LLM trả rỗng mà message có từ khóa ⇒ code điền (lỗi C37). |
| 24 | `price_min` | Chỉ nhận khi message có "trên/từ/ít nhất/tối thiểu <số> tỷ\|triệu" hoặc do xấp xỉ sinh ra. Số đi với "m2/m²/phòng/tầng" không bao giờ thành giá. |
| 25 | Tham chiếu không rõ | Message không có tham chiếu tường minh ("căn thứ N", mã tin) ⇒ coi là hỏi **cả các tin vừa trả** (bỏ hẳn `result_refs` của LLM). "Căn nào gần chợ nhất trong 5 căn này?" phải xét cả 5. |
| 26 | Nâng/giảm ngược chiều | "Nâng ngân sách lên X" mà X < `price_max` hiện tại (hoặc "giảm xuống X" mà X > hiện tại) ⇒ `need_clarification` hỏi lại "Bạn muốn đặt ngân sách tối đa X (thấp hơn mức 6 tỷ hiện tại) đúng không?", **không áp**. |
| 27 | Trải nghiệm | (a) `no_results` mở đầu bằng điều kiện đang áp; (b) hỏi tham chiếu khi chưa có tin nào ⇒ "Mình chưa gợi ý tin nào để hỏi chi tiết"; (c) hai lượt liên tiếp cùng `pending_question` ⇒ câu hỏi khác nhau, có ghi nhận phần khách vừa nói; (d) lượt `ok` có < 5 tin và còn phương án nới có `result_count` lớn hơn số tin hiện có ⇒ thêm tối đa 2 dòng gợi ý nới (không đổi `status`); (e) sở thích "gần trung tâm" chưa hỗ trợ khoảng cách ⇒ câu trả lời nói rõ "mình chưa lọc theo khoảng cách tới trung tâm, chỉ xếp theo mô tả"; (f) chênh lệch khoảng cách/giá hiển thị tính từ số **đã làm tròn** hiển thị; không lặp nhãn. |
| 28 | Rút gọn: bỏ LLM khỏi `ask_detail`/`compare` (main duyệt 15:xx, sau khi db-coder đo: code chỉ giảm được 2,8% nếu không bỏ tính năng) | **Code viết toàn bộ** câu trả lời hỏi chi tiết/so sánh từ "facts" (đã có `build_facts` + so sánh tính sẵn): chỉ in các thuộc tính được hỏi (hoặc bộ thuộc tính chính khi không khớp thuộc tính nào), kèm địa chỉ cũ+mới và `[Tin <id>]` của mỗi "Căn N". Câu hỏi không khớp thuộc tính nào (vd. "yên tĩnh không?", "view đẹp không?") ⇒ in facts chính + trích **nguyên văn** 300 ký tự đầu của mô tả tin và nói "mình chưa đánh giá được ngoài dữ liệu tin ghi". Xóa `_compose`, prompt writer, mọi kiểm tra grounding so sánh (`_unsupported_comparison`, `_clause_refs`, `_comparatives`, `_is_supported`…) vì không còn LLM viết. **Giữ** LLM ở `TurnInterpreter` (hiểu câu). Giữ rerank (đề cương yêu cầu), vòng thử lại của interpreter, `LEXICAL_BOOST`. |
| 29 | Vòng 4: lỗi từ khách thật | (a) Khu vực: khi LLM trả khu vực rỗng mà câu có tên quận/phường trong danh mục (bỏ dấu, theo quy tắc #6) ⇒ **code** thêm tên đó (C35#5). (b) Xấp xỉ lệch %: gốc = số tiền **đầu tiên trong câu**, không tin giá LLM trả. (c) Reset: chỉ bỏ loại BĐS khi câu không nhắc loại nào (B6 "đất nền Quận 9"). (d) Xác nhận: state có `pending_value`; "ừ/đúng/ok/vâng/chuẩn" ⇒ áp giá trị đang chờ, "không/thôi/giữ nguyên" ⇒ hủy; không phải câu xác nhận ⇒ bỏ giá trị chờ (B4). (e) `ask_detail`/`compare`: tách câu hỏi thành các vế (dấu phẩy/"và"/"còn"); vế khớp thuộc tính ⇒ trả lời từ facts; vế KHÔNG khớp (hẻm xe hơi, trệt, view…) ⇒ tìm trong mô tả tin **câu đầu tiên chứa từ khóa của vế đó** và trích nguyên văn, không có ⇒ "tin không ghi mục này" (D4, D6). (f) Cấp cao nhất: "nhất" (rộng/rẻ/đắt/lớn/nhỏ/gần/xa nhất) ⇒ trả lời đúng một căn + giá trị, kèm bảng xếp hạng một dòng. So sánh "rẻ hơn/ít hơn" sinh cả hai chiều (chủ ngữ là căn rẻ hơn). (g) Yêu cầu "chi tiết" ⇒ in đủ mọi thuộc tính có dữ liệu (tầng, mặt tiền, nội thất, phòng tắm, ngày đăng, link), không kèm câu "chưa đánh giá được". (h) Trích mô tả cắt ở ranh giới từ + "…". (i) "lô đầu" không phải "ở đâu" (regex `\bo\sdau\b` trên bản có dấu). |
| 30 | Bộ test mở rộng | Giữ đúng 50 kịch bản trong `scenarios.json`. Lỗi khách thật mới ghi vào `scenarios_extra.json` (hồi quy, không tính vào bộ 50), `run_eval.py --extra` chạy chúng; mọi tiêu chí áp dụng như bộ 50. |
| 31 | Vòng 5: câu hỏi chi tiết | (a) Nhận diện "chi tiết/thêm về/nói thêm" **trước** khi tách chủ đề; từ đệm thật (đi, ko, k, nhé, hỏi, nói, thêm, giúp…) vào STOP_WORDS, **không** gộp NUMBER_WORDS (mất "nam/sau/bay/tam"). (b) Không tách vế tại "còn" khi theo sau là "hạn". (c) Trích mô tả/tiêu đề cho vế không khớp thuộc tính: so khớp **theo từ nguyên vẹn, giữ dấu** (không bỏ dấu để so khớp), tìm trong **tiêu đề + mô tả**; vế ≥ 2 từ khóa phải khớp ≥ 2 (hoặc ≥ nửa); không khớp ⇒ "tin không ghi mục này" (chỉ khi cả tiêu đề lẫn mô tả đều không có). (d) So sánh hơn "rộng/lớn/to/nhỏ ⇒ diện tích; rẻ/đắt/mắc ⇒ giá" xử lý như cấp cao nhất nhưng cho 2+ căn ("căn 2 với căn 3 cái nào rộng hơn"). (e) Câu "nhất" ⇒ `referenced_ids` = căn thắng. |
| 32 | Vòng 5: giá và loại | (a) Số tiền viết liền: "2ty5" = 2,5 tỷ, "3tỷ2" = 3,2 tỷ, "3tỷ8", "900tr", "1ty" (cho phép chữ số ngay sau đơn vị). (b) "loại nào cũng được / loại gì cũng được / không nhất thiết (căn hộ|nhà…)" ⇒ bỏ `property_types` và **không** suy lại loại từ chữ trong câu. (c) "nhà phố" ⇒ nhất quán ở mọi lượt (cùng bảng map). (d) "gần trg" = trường (thêm viết tắt "trg" vào POI mention); điều kiện POI/giá bị bỏ vì không hiểu ⇒ câu trả lời nói rõ điều kiện nào chưa hiểu. |
| 33 | Bỏ yêu cầu log thời gian từng bước (spec mục 3) | Để giữ code gọn (người dùng ưu tiên đơn giản); p95 vẫn đo bằng harness. Sửa các comment/docstring đang nói LLM viết câu trả lời (đúng ra chỉ `TurnInterpreter` dùng LLM). Code sạch: staticmethod ⇒ hàm cấp module (Google Python Style §2.17), `_plan` không sửa `state` ngầm, đặt tên hằng cho số ma thuật, `Renderer = Callable[[Any], str]`. Trần dòng vẫn 1.900. |
