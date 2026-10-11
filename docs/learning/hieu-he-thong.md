# Hiểu hệ thống trong 1 buổi — học theo kiểu "người phụ trách một phần"

Mục tiêu: hiểu **luồng** của hệ thống và làm chủ **một** phần (mode dự đoán giá), không đọc hết code.
Thời gian: khoảng 2–3 giờ. Mọi lệnh chạy trong `housing-backend/`, với:

```bash
export PYTHONPATH=. PYTHONIOENCODING=utf-8
export DATABASE_URL=postgresql+asyncpg://postgres:123456789@localhost:5432/housing_dev
PY=../.venv/Scripts/python.exe
```

---

## 0. Bạn đã biết 80% rồi — đối chiếu với dự án Django của bạn

| Dự án Restate (Django) | Dự án này (FastAPI) | Vai trò |
|---|---|---|
| `urls.py` + `views.py` | `app/api/v1/routes.py` | nhận request, trả response — **mỏng**, không chứa nghiệp vụ |
| `serializer.py` | `schemas.py` (Pydantic) | kiểm tra dữ liệu vào/ra |
| `models.py` | `app/db/models/` (SQLAlchemy) | bảng database |
| logic viết trong view | `app/services/` | **toàn bộ nghiệp vụ nằm ở đây** |
| `settings.py` | `app/core/config.py` + `.env` | cấu hình |
| (không có) | `app/api/deps.py` | "lắp ráp": tạo sẵn các service rồi đưa vào route |

Điểm khác lớn nhất: bên Django bạn viết logic trong view; ở đây view (`routes.py`) chỉ gọi **một** hàm của service.
Nên muốn hiểu hệ thống, **đọc service, không đọc route**.

## 1. Bức tranh lớn — chỉ cần nhớ hình này

```text
Người dùng ──► frontend (React) ──► POST /api/v1/chat  {message, mode, conversation_id}
                                         │  routes.py: chỉ xem mode rồi chuyển tiếp
                     ┌───────────────────┴────────────────────┐
           mode = "prediction"                       mode = "recommendation"
           PredictionChat.turn()                     RecommendationService.chat()
           (services/prediction/)                    (services/recommendation/)
                     │                                          │
   ① hiểu câu: LLM trích trường  ── giống nhau ──  ① hiểu câu: LLM đề xuất điều kiện
   ② code KIỂM LẠI + quyết định  ── giống nhau ──  ② code KIỂM LẠI + quyết định
   ③ tính: toạ độ → RandomForest                    ③ tìm: SQL + PostGIS + vector
   ④ code viết câu trả lời       ── giống nhau ──  ④ code viết câu trả lời
```

**Ý tưởng cốt lõi của cả dự án (một câu):** *LLM chỉ được "đọc hiểu" tin nhắn; mọi quyết định và mọi con số do code.*
Lý do: LLM hay bịa và mỗi lần trả lời một khác; code thì test được. Nếu bạn chỉ nhớ một điều, nhớ điều này —
giảng viên hỏi "sao chatbot không bịa?" thì đây là câu trả lời.

## 2. Cần biết gì TRƯỚC (và được phép bỏ qua gì)

Chỉ đọc 4 file của mode dự đoán, theo thứ tự, và chỉ đọc phần được chỉ:

| # | File | Đọc phần nào | Trả lời được câu hỏi |
|---|---|---|---|
| 1 | `services/prediction/schemas.py` | cả file (~60 dòng) | Dữ liệu đi qua hệ thống trông thế nào? (`Extraction` = LLM đọc được gì; `PredictionState` = bot đang nhớ gì; `PredictionTurn` = trả về gì) |
| 2 | `services/prediction/chat.py` | **chỉ hàm `turn()` và `_respond()`** (dòng ~91–141) | Một tin nhắn đi qua những bước nào? |
| 3 | `services/prediction/predictor.py` | class `PriceInput` + hàm `predict()` | Model nhận gì, trả gì? (đây chính là model đồ án 1 của bạn) |
| 4 | `services/prediction/text.py` | chỉ đọc **tên** các hàm trong `MessageRules` | Code tự kiểm những gì mà không cần LLM? |

**Tạm bỏ qua:** `geocoder.py` (chỉ cần biết: địa chỉ → toạ độ), `extractor.py` (chỉ cần biết: gọi OpenAI → `Extraction`),
toàn bộ `recommendation/` (học sau, cùng khuôn), `migrations/`, `scripts/`, các hàm bắt đầu bằng `_` mà chưa cần.

## 3. Bài học có đầu vào / đầu ra (chạy trong shell)

### Bài 1 — Xem từng tầng chạy (10 phút)

```bash
$PY playground/prediction_steps.py "nhà riêng 60m2 ở Gò Vấp, 3 tầng, ngang 4m"
```

Script in ra 4 bước: ① `MessageRules` (code) → ② `Extraction` (thứ LLM sẽ trả) → ③ `Geocoder` (toạ độ) → ④ `PricePredictor`.
Thử thêm, và **ghi lại bước nào làm câu bị dừng**:

```bash
$PY playground/prediction_steps.py "thuê nhà quận 1"          # dừng ở đâu? vì hàm nào?
$PY playground/prediction_steps.py "can ho q7 70m2 2pn"       # viết tắt, không dấu
$PY playground/prediction_steps.py "nhà ở Thuận An 80m2"      # tỉnh khác
$PY playground/prediction_steps.py "nhà riêng 60m2 Gò Vấp" --llm   # LLM thật: so bước 2 với bản dựng tay
```

Câu hỏi tự kiểm: vì sao bản `--llm` có `floors` và `frontage_m` còn bản dựng tay thì không?

### Bài 2 — Gọi thẳng một hàm trong Python (10 phút)

```bash
$PY -c "from app.services.prediction.text import MessageRules as R; print(R.districts('district 7'), R.districts('quận bảy'), R.out_of_domain('nhà đang cho thuê muốn bán'))"
```

Đây là cách bạn "test tay" bất kỳ hàm nào: import → gọi → in. Thử với `R.area_from_text('5x20')`, `R.confirms('chốt')`.

### Bài 3 — Cả hội thoại qua API thật (15 phút)

```bash
$PY -m uvicorn app.main:app --port 8000      # cửa sổ 1
# cửa sổ 2: mở http://localhost:8000/docs  → POST /api/v1/chat → "Try it out"
```

Gửi lần lượt (giữ nguyên `conversation_id` mà lượt 1 trả về):
1. `{"message": "nhà riêng Gò Vấp 60m2", "mode": "prediction"}` → `status` = ?
2. `{"message": "ok", "mode": "prediction", "conversation_id": "<id>"}` → `status` = ?
3. `{"message": "nếu 4 tầng thì sao", ...}` → để ý dòng "trước → sau".

Đối chiếu `status` với các nhánh `return` trong `_respond()` — mỗi `status` ứng với đúng một dòng code.

### Bài 4 — Đọc test như đọc tài liệu (10 phút)

```bash
$PY -m pytest tests/prediction/unit/test_text.py -q
$PY -m pytest tests/prediction/unit/test_chat.py -q -k "confirm"
```

Mở `test_chat.py`: mỗi test là một **ví dụ sống** "đầu vào X thì phải ra Y" — dễ hiểu hơn đọc code. Ở công ty,
người mới thường đọc test trước.

## 4. BÀI TẬP BẮT BUỘC — tự sửa một tính năng nhỏ, đi hết các tầng

**Yêu cầu:** khi diện tích > 500 m², câu trả lời dự đoán phải có thêm dòng
`- Lưu ý: Diện tích lớn, ít tin đăng tương tự nên giá có thể lệch.`

Gợi ý (đừng đọc vội, tự tìm trước):
1. Chạy `playground/prediction_steps.py "đất Củ Chi 800m2"` — ghi lại `warnings` hiện tại.
2. Tìm nơi tạo `warnings` (gợi ý: `predictor.py`, có sẵn `SPARSE_WARNING`, `WIDE_WARNING`). Thêm hằng mới + điều kiện.
3. **Viết test trước khi sửa** trong `tests/prediction/unit/test_predictor.py` (bắt chước test có sẵn), chạy cho nó đỏ, sửa code cho xanh.
4. Chạy lại bước 1 — `warnings` đã có dòng mới chưa?
5. Chạy Bài 3 với "đất Củ Chi 800m2" rồi "ok" — câu trả lời có "Lưu ý" mới không? (Bạn **không** phải sửa `chat.py`: tìm hiểu vì sao — xem dòng `lines += [f"- Lưu ý: ..."]`.)
6. Chạy toàn bộ: `$PY -m pytest tests -q` và `uvx ruff check app tests` — phải xanh.

Làm xong bài này, bạn đã đi qua: model → service → API → test. Đó chính là "hiểu hệ thống" ở mức người phụ trách một phần.

**Bài tập nâng cao (tuỳ chọn):** thêm từ xác nhận "chốt đơn" — tìm trong `text.py`, thêm test, kiểm qua API.

## 5. Sau khi xong mode dự đoán — học mode gợi ý cùng khuôn

`recommendation/service.py` hàm `chat()` có cùng 4 bước: `interpreter.py` (①) → `text_rules.py` (②) → `search.py` (③)
→ `writer.py` (④). Khi cần, nhờ AI viết một `playground/recommend_steps.py` tương tự để chạy từng bước.

## 6. Tự kiểm tra — trả lời được 5 câu này là đủ

1. Tin nhắn "ok" có gọi OpenAI không? (gợi ý: dòng `if not done` trong `turn()`)
2. Ai quyết định từ chối "thuê nhà": LLM hay code? Ở hàm nào?
3. Khi không gọi được Goong, toạ độ lấy từ đâu?
4. Sửa "3 tầng" thành "4 tầng" sau khi đã dự đoán thì vì sao bot tự dự đoán lại mà không cần "ok"?
5. `status` có những giá trị nào, mỗi giá trị ứng với tình huống gì?
