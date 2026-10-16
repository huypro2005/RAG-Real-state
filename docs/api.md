# Tài liệu API và hướng dẫn sử dụng

Backend FastAPI của chatbot bất động sản TP.HCM (địa giới cũ). Kiến trúc và cách chatbot hoạt động
nằm ở [chatbot.md](chatbot.md); tài liệu này chỉ nói **cách gọi API**.

- Base URL (chạy local): `http://localhost:8000`, mọi endpoint nghiệp vụ dưới `/api/v1`.
- Swagger tự sinh: `http://localhost:8000/docs` (thử trực tiếp), `/openapi.json`.
- Định dạng: JSON, UTF-8. Không có xác thực (mức đồ án/demo).
- CORS: cho phép `http://localhost:5173` và `http://127.0.0.1:5173`; đổi bằng biến `CORS_ORIGINS`.
- Đơn vị: giá **triệu VND**, diện tích **m²**, khoảng cách **mét**.

## 1. Chạy server

```powershell
cd housing-backend
$env:DATABASE_URL = "postgresql+asyncpg://postgres:<mật khẩu>@localhost:5432/housing_dev"
..\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000
```

Cần trong `.env`: `OPENAI_API_KEY` (hiểu câu), `GOONG_API_KEY` (toạ độ địa chỉ/địa điểm, tuỳ chọn),
`EMBEDDING_API_URL` + `EMBEDDING_API_KEY` (embedding/rerank trên Kaggle, tuỳ chọn). Mode dự đoán cần
file mô hình `models/price_rf.joblib` (tạo bằng `scripts/train_price_model.py`).

Kiểm tra sống: `GET /health` → `{"status": "ok"}` (có truy vấn DB).

## 2. Danh sách endpoint

| Method | Đường dẫn | Việc |
|---|---|---|
| POST | `/api/v1/chat` | Một lượt chat, chọn chế độ bằng `mode` (**dùng cho giao diện**) |
| POST | `/api/v1/reset` | Xoá hội thoại ở cả hai chế độ |
| POST | `/api/v1/recommend/chat` | Một lượt chat chế độ gợi ý (kiểu trả về cố định) |
| POST | `/api/v1/recommend/reset` | Xoá hội thoại gợi ý |
| GET | `/api/v1/recommend/map` | GeoJSON cho bản đồ: tin gợi ý, POI, địa điểm đang lọc |
| GET | `/api/v1/listings/{listing_id}` | Chi tiết một tin |
| GET | `/api/v1/pois/nearby` | POI quanh một toạ độ |
| GET | `/health` | Kiểm tra server và DB |

## 3. Chat

### 3.1 `POST /api/v1/chat`

Body:

| Trường | Kiểu | Ghi chú |
|---|---|---|
| `mode` | `"recommendation"` \| `"prediction"` | **Bắt buộc.** Server không tự đoán chế độ; sai giá trị → 422 |
| `message` | string, 1–20.000 ký tự | Tin nhắn người dùng. Gợi ý chỉ đọc 1.000 ký tự đầu (báo lại trong câu trả lời) |
| `conversation_id` | string ≤ 100, tuỳ chọn | Bỏ trống ở lượt đầu; từ lượt sau gửi lại giá trị server trả về |
| `as_of` | `YYYY-MM-DD`, tuỳ chọn | Chỉ chế độ gợi ý: cố định "hôm nay" khi kiểm thử |

Hội thoại của hai chế độ độc lập nhau: mỗi chế độ giữ `conversation_id` riêng.

Lỗi:

| Mã | Khi nào |
|---|---|
| 422 | Thiếu/sai trường, `mode` lạ |
| 503 | Gọi OpenAI lỗi ("Trợ lý tạm thời không phản hồi…"), hoặc chế độ dự đoán khi chưa có mô hình |

### 3.2 Phản hồi chế độ `recommendation`

```jsonc
{
  "mode": "recommendation",
  "conversation_id": "9f2c…",
  "status": "ok",              // ok | need_clarification | out_of_scope | no_results | answered
  "answer": "…",               // câu trả lời đầy đủ, gồm khối từng tin
  "summary": "…",              // answer bỏ khối từng tin (UI vẽ tin bằng thẻ)
  "constraints": { … },        // điều kiện tìm SAU lượt này (xem 3.4)
  "listings": [ { … } ],       // ≤ 5 tin, xem bên dưới
  "referenced_ids": ["…"],     // tin được nhắc khi hỏi chi tiết/so sánh/so giá
  "relax_options": [ { "field": "near_places", "description": "mở rộng bán kính quanh … lên 7 km",
                       "result_count": 14, "message": "…" } ],
  "degraded": false,           // true: embedding/rerank lỗi, đã sắp theo ngày đăng
  "suggestions": ["1. …", "2. …"]   // chip trả lời nhanh (vd. danh sách địa điểm trùng tên)
}
```

Ý nghĩa `status`:

| `status` | Nghĩa | Giao diện nên |
|---|---|---|
| `ok` | Có tin phù hợp | Vẽ `listings` và bản đồ |
| `no_results` | Không có tin | Hiện `relax_options` thành nút; bấm thì gửi `message` của nút làm lượt tiếp theo |
| `need_clarification` | Bot hỏi lại (thiếu ngân sách/khu vực, giá ngoài biên, địa điểm trùng tên…) | Hiện `answer`; hiện `suggestions` thành chip nếu có |
| `answered` | Trả lời câu hỏi về tin đã gợi ý, chào hỏi, chuyển chế độ | Hiện `answer` |
| `out_of_scope` | Ngoài phạm vi (tỉnh khác, thuê nhà, pháp lý…) | Hiện `answer`; điều kiện cũ vẫn giữ |

Một phần tử của `listings`:

| Trường | Ghi chú |
|---|---|
| `listing_id`, `title`, `listing_url` | Mã tin batdongsan, tiêu đề, đường dẫn |
| `price`, `area`, `property_type`, `bedrooms` | Triệu VND, m², loại, phòng ngủ |
| `district_old`, `old_address`, `new_address` | Địa chỉ giữ nguyên văn |
| `posted_at`, `expired_at`, `days_left` | `days_left` âm = đã hết hạn |
| `poi_distances` | `{"truong_hoc": 350, "benh_vien": 1200, "cho": 800}` mét tới POI gần nhất mỗi loại |
| `place_distances` | `{"Trường Đại học …": 3993}` mét tới từng địa điểm có tên đang lọc |
| `latitude`, `longitude`, `coords_reliable` | `false` khi thiếu toạ độ hoặc toạ độ ngoài TP.HCM |
| `position` | 1–5, khớp "căn thứ N" và số trên bản đồ |
| `score`, `similar_ids` | Điểm ngữ nghĩa (null khi sắp theo ngày); tin đăng lại đã gộp |

### 3.3 Phản hồi chế độ `prediction`

```jsonc
{
  "mode": "prediction",
  "conversation_id": "ab41…",
  "status": "predicted",       // collecting | ready | predicted | out_of_scope
  "answer": "…",
  "summary": "căn hộ chung cư · Quận 9 · 60 m²",   // một dòng trường đã biết
  "fields": { "property_type": "căn hộ chung cư", "district": "Quận 9", "address": "Quận 9",
              "area": 60.0, "frontage": null, "bedrooms": null, "floors": null },
  "missing": [],               // trường bắt buộc còn thiếu: property_type | district | area
  "prediction": {              // null cho tới khi đã dự đoán
    "price_per_m2": 62.5, "total_price": 3750.0,                 // triệu VND/m², triệu VND
    "price_per_m2_low": 48.1, "price_per_m2_high": 80.2,         // phân vị 10–90 của các cây (KHÔNG phải khoảng tin cậy)
    "distance_to_center_km": 12.3,
    "district_median_per_m2": 55.0, "median_by_type": true,
    "warnings": []
  },
  "suggestions": ["Vì sao giá này?", "Mô hình dùng gì?", "Bắt đầu lại"]
}
```

Ý nghĩa `status`: `collecting` đang thiếu thông tin bắt buộc hoặc đang hỏi thêm; `ready` đủ thông tin,
chờ người dùng gõ `ok`; `predicted` đã có kết quả; `out_of_scope` ngoài phạm vi.

Số trong ví dụ chỉ để minh hoạ cấu trúc. Chế độ dự đoán không bao giờ tự bịa số: mọi con số trong
`answer` lấy từ `prediction`.

### 3.4 Điều kiện tìm (`constraints`, chế độ gợi ý)

Cộng dồn qua các lượt; gửi lại `conversation_id` là đủ, client không cần gửi lại điều kiện.

| Trường | Ghi chú |
|---|---|
| `price_min`, `price_max` | Triệu VND |
| `area_min`, `area_max`, `bedrooms_min` | m², số phòng ngủ tối thiểu |
| `property_types` | Giá trị nguyên văn của `listings.property_type` |
| `district_ids`, `new_ward_ids` | `id` của quận cũ / phường mới |
| `near_pois` | `[{"poi_type": "benh_vien", "max_distance_m": 2000}]` — loại chung chung, mặc định 2 km |
| `near_places` | Địa điểm có tên đã xác định: `name`, `address`, `latitude`, `longitude`, `max_distance_m` (mặc định 5.000), `poi_id` |
| `soft_query` | Sở thích mềm, chỉ để sắp xếp |

### 3.5 Ví dụ gọi

PowerShell:

```powershell
$base = "http://localhost:8000/api/v1"
$r1 = Invoke-RestMethod "$base/chat" -Method Post -ContentType "application/json; charset=utf-8" `
  -Body ([Text.Encoding]::UTF8.GetBytes((@{
    mode = "recommendation"
    message = "Tôi có 3 tỷ cần tìm căn hộ chung cư gần đại học công nghệ thông tin ở Thủ Đức, có 2 phòng ngủ"
  } | ConvertTo-Json)))
$r1.status; $r1.listings | Select-Object position, price, area, title

# lượt 2: gửi lại conversation_id
$r2 = Invoke-RestMethod "$base/chat" -Method Post -ContentType "application/json; charset=utf-8" `
  -Body ([Text.Encoding]::UTF8.GetBytes((@{
    mode = "recommendation"; conversation_id = $r1.conversation_id
    message = "căn 2 giá có hợp lý không?"
  } | ConvertTo-Json)))
$r2.answer
```

curl (Git Bash/Linux):

```bash
curl -s http://localhost:8000/api/v1/chat -H "Content-Type: application/json" \
  -d '{"mode":"prediction","message":"nhà riêng 60m2 Gò Vấp, 3 phòng ngủ"}'
```

Hội thoại mẫu chế độ dự đoán (4 lượt):

| Lượt | Người dùng | `status` | Bot |
|---|---|---|---|
| 1 | "hi" | `collecting` | Chào, hỏi loại nhà đất |
| 2 | "căn hộ chung cư, vinhome quận 9, 60 m2" | `ready` | Đủ thông tin bắt buộc, mời bổ sung phòng ngủ hoặc gõ `ok` |
| 3 | "ok" | `predicted` | Giá/m², tổng giá, khoảng tham khảo, so với median quận |
| 4 | "nếu thêm 1 phòng ngủ thì sao?" | `predicted` | Kết quả giả định "trước → sau", thông tin đã lưu không đổi |

### 3.6 Lệnh và mẹo cho giao diện

- Chế độ dự đoán nhận lệnh thuần `ok` (dự đoán), `reset` (làm lại), `bỏ qua` (bỏ trường đang hỏi) mà không gọi LLM.
- Hiện `suggestions` thành chip; bấm chip gửi **nguyên văn** chip làm `message`.
- Khi `status = need_clarification` vì trùng tên địa điểm, người dùng có thể đáp "số 2", tên quận,
  hoặc tên rút gọn của địa điểm.
- Câu thuộc chế độ kia ("định giá nhà tôi…" ở tab Gợi ý) được bot chỉ sang tab còn lại; hội thoại hiện tại giữ nguyên.

## 4. Đặt lại hội thoại

`POST /api/v1/reset` body `{"conversation_id": "…"}` → `{"conversation_id": "…"}`. Xoá state ở cả hai
chế độ. `POST /api/v1/recommend/reset` cùng body, chỉ cho gợi ý. State chỉ lưu trong bộ nhớ server:
khởi động lại server thì mọi `conversation_id` cũ thành hội thoại mới.

## 5. Bản đồ — `GET /api/v1/recommend/map`

| Tham số | Mặc định | Ghi chú |
|---|---|---|
| `ids` | bắt buộc | `listing_id` cách nhau dấu phẩy, 1–10 mã; thứ tự = số trên bản đồ |
| `radius_m` | 2000 | Bán kính tìm POI quanh tin, 1–10.000 |
| `poi_types` | `truong_hoc,benh_vien,cho` | Lọc loại POI; giá trị lạ → 422 |
| `conversation_id` | — | Nếu có, trả thêm địa điểm có tên đang lọc của hội thoại |

Trả `FeatureCollection` (GeoJSON). Mỗi feature có `properties.kind`:

| `kind` | Nội dung |
|---|---|
| `listing` | `position`, `listing_id`, … — marker tin, đánh số |
| `poi` | `poi_type`, `name`, … — trường/bệnh viện/chợ quanh tin (không gồm đại học/cao đẳng) |
| `place` | `name`, `address`, `radius_m` — điểm địa điểm có tên để vẽ vòng tròn bán kính |

Geometry là `Point`, toạ độ theo thứ tự `[kinh độ, vĩ độ]`.

## 6. Tra cứu

- `GET /api/v1/listings/{listing_id}` — chi tiết một tin (giá, diện tích, quận, `quality_flags`,
  `spatial_features`: số trường/bệnh viện/chợ trong 1 km và 3 km, POI gần nhất). Không có → 404.
- `GET /api/v1/pois/nearby?lat=…&lon=…&radius_m=1000&poi_type=benh_vien&limit=50` — POI quanh toạ độ.
  `radius_m` ≤ 10.000, `limit` 1–200, `poi_type` ∈ `truong_hoc | benh_vien | cho` (bỏ trống = cả ba).
  Trả `[{poi_id, poi_type, name, distance_m}]`.

## 7. Xử lý sự cố

| Hiện tượng | Nguyên nhân thường gặp |
|---|---|
| 503 "Trợ lý tạm thời không phản hồi" | Thiếu/sai `OPENAI_API_KEY`, hết hạn mức hoặc mất mạng |
| 503 "Mô hình định giá chưa được huấn luyện" | Chưa có `models/price_rf.joblib` → chạy `scripts/train_price_model.py` |
| `degraded: true` | Dịch vụ embedding (Kaggle) tắt hoặc `EMBEDDING_API_URL` cũ; kết quả sắp theo ngày đăng |
| Dự đoán dùng "tâm quận" | Không có `GOONG_API_KEY`, hết hạn mức Goong hoặc không xác định được địa chỉ |
| "Mình không tìm thấy 'X' trên bản đồ" | Tên địa điểm không có trong DB và Goong không xác định được; chỉ ưu tiên tin nhắc tên đó |
| Mất hội thoại sau khi restart | State chỉ lưu trong bộ nhớ; bắt đầu lại không gửi `conversation_id` |
| Trình duyệt báo CORS | Thêm origin vào `CORS_ORIGINS` (cách nhau dấu phẩy) |
| 422 khi gửi tiếng Việt từ PowerShell | Gửi body dạng byte UTF-8 như ví dụ 3.5 |
