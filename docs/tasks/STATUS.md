# Trạng thái dự án — tạm dừng lần 2, ngày 09/10/2026

> **PHẠM VI HIỆN TẠI (người dùng quyết 09/10/2026): chỉ làm RAG và gợi ý (mode recommendation).**
> **Tạm bỏ:** model dự đoán giá (GĐ6: Random Forest A/B, mode prediction, `predict_price`, Price Agent) và
> **khoảng cách tới Quận 1** (`dist_to_q1_m`). Mọi chỗ nhắc tới hai việc này bên dưới đều **không cần làm**
> cho tới khi người dùng yêu cầu lại. 6 biến đếm POI (1 km/3 km) vẫn dùng, vì tìm kiếm cần "gần bệnh viện/chợ/trường".


Phiên mới: đọc file này đầu tiên, rồi làm theo mục 2 "Lệnh để chạy tiếp". Bản đồ chung: [AGENTS.md](../../AGENTS.md). Kế hoạch: [roadmap.md](roadmap.md). Spec GĐ7: [hybrid-search.md](hybrid-search.md) (mục 9 = các quyết định #1–#30).

## 1. Đã xong

| Việc | Kết quả |
|---|---|
| Phân tích HTML batdongsan | Xong ([html-analysis.md](html-analysis.md)) |
| Database địa chỉ batdongsan (spec [address-db.md](address-db.md)) | **PASS** trên `housing_dev`: 15 bảng ở `public`, 7 bảng địa chỉ theo ID batdongsan, `ward_mappings` 270/273, `pois` gộp 1 bảng, 7.603 tin, 7.342 spatial features |
| Embedding | 7.603/7.603 tin, bge-m3 1024 chiều, **chỉ trong `housing_dev`** |
| Tài liệu học từ `AleksNeStu/ai-real-estate-assistant` | Đã phản biện ([research/](../research/ai-real-estate-assistant-lessons.md)) |
| Backup DB thật | `backup/housing_before_public_20261009.dump` |
| Chat gợi ý nhiều lượt (GĐ7) — code | Chạy được, **chưa PASS vòng chấm** (mục 3) |

## 2. Lệnh để chạy tiếp (theo thứ tự)

### 2.1 Người dùng làm (agent bị chặn hoặc không có quyền)

**a) Bật lại server embedding trên Kaggle.** Mở `src/kaggle/embedding_server.ipynb`, chạy, chép `EMBEDDING_API_URL` và `EMBEDDING_API_KEY` mới vào `.env` gốc (tunnel Cloudflare đổi URL mỗi lần). Kiểm: `curl <URL>/health` ⇒ 200. Không có nó, hệ thống chạy chế độ dự phòng (xếp theo ngày đăng) và **không chấm được [S7]** (sở thích mềm).

**b) Áp DB `housing` (thật) — chưa làm.** Vẫn 5 schema cũ (`admin, amenities, listing, ml, rag`). Chế độ auto chặn ghi lên `housing` (loại "production deploy"); người dùng tự chạy, hoặc cấp quyền Bash cho agent. Trong `housing-backend/housing-backend`:

```bash
export DATABASE_URL=postgresql+asyncpg://postgres:123456789@localhost:5432/housing
../../.venv/Scripts/python.exe -m alembic upgrade head
../../.venv/Scripts/python.exe scripts/seed_address.py
../../.venv/Scripts/python.exe scripts/migrate_legacy_data.py \
  --source-url postgresql://postgres:123456789@localhost:5432/housing \
  --target-url postgresql://postgres:123456789@localhost:5432/housing
# đối chiếu số dòng (listings 7603, listing_spatial_features 7342, pois 5267, district_label 24,
# ward_mappings 270, streets_new 34091, streets_old 9169), rồi:
#   DROP SCHEMA admin, amenities, listing, ml, rag CASCADE;
# rồi embed (từ thư mục gốc, Kaggle phải bật):
DATABASE_URL=postgresql+asyncpg://postgres:123456789@localhost:5432/housing ../../.venv/Scripts/python.exe -m src.pipeline --embed-only
```

Sau khi áp, đổi `DATABASE_URL` của code và test từ `housing_dev` sang `housing` (`src.pipeline` mặc định `housing_dev`, muốn ghi `housing` phải truyền `DATABASE_URL`/`--db-url`).

### 2.2 Agent làm (nói với Claude: "đọc STATUS.md và tiếp tục")

1. **Chạy vòng chấm 5** (đã bị tạm dừng; xem mục 3.2): giao `query-tester` chạy đủ 50 kịch bản + `--extra` (9 kịch bản hồi quy) + `pytest -m llm -k extraction` (44 câu) + 2 hội thoại khách thật mới (có tiếng lóng, viết tắt "2pn", "ko", "gần trg"). Nếu Kaggle đã bật thì chấm luôn [S7] (4 kịch bản C38–C41, cần ≥ 3/5).
2. Có lỗi ⇒ giao `db-coder` sửa, chấm lại. **Còn tối đa 2 vòng (5 và 6).** Hết vòng 6 mà chưa PASS ⇒ báo người dùng quyết, không tự chạy thêm.
3. PASS ⇒ main (người duyệt cuối) tự review code, tự chạy lại 50 kịch bản, tự đóng vai khách hàng; rồi áp DB thật (2.1b).
4. Sau GĐ7 (theo phạm vi mới, **không làm model giá, không làm khoảng cách Quận 1**):
   1. **GĐ3 crawler định kỳ — khẩn** (hôm nay chỉ còn 186/7.603 tin còn hạn, dữ liệu crawl đến 21/09; recommendation chỉ gợi ý tin còn hạn nên thiếu bước này thì hệ thống gần như rỗng).
   2. GĐ4 rút gọn: chỉ cần tên khu vực/phường mới khớp được (đã có); `normalize_address` + geocode chỉ làm nếu cần cho Geo Agent.
   3. GĐ8 chỉ **mode recommendation**: tách API (`search_listings`, `get_nearby_pois`, `get_map_results`), Mode Controller đơn giản, giao diện React.
   4. GĐ9: Map View (Leaflet + Goong) cho Top 5 + POI, kiểm thử end-to-end, báo cáo.

## 3. GĐ7 chat gợi ý — chi tiết

### 3.1 Code và test

- Code: `housing-backend/housing-backend/app/services/recommendation/` — `schemas, interpreter, text_rules, grounding, search, writer, service` (**1.895 dòng; trần 1.900, không được tăng**; vòng đầu 1.320, đỉnh 2.106). Route `POST /api/v1/recommend/chat`.
- Phân vai: LLM (gpt-4o-mini) **chỉ** ở `TurnInterpreter` (hiểu câu thành kế hoạch). Mọi quy tắc tất định và **toàn bộ câu trả lời do code viết** (từ "facts" của DB). Spec #13, #14, #28.
- Unit test (không OpenAI): `tests/recommend/unit/` — **176 passed**, `uvx ruff check app tests/recommend/unit` sạch, không hàm nào > 40 dòng.
- Bộ test của query-tester (không được sửa tay): `tests/recommend/` — `scenarios.json` (50 kịch bản/174 lượt, `as_of = 2026-09-22`), `scenarios_extra.json` (9 kịch bản hồi quy lỗi khách thật, `run_eval.py --extra`), `extraction_cases.json` (44 câu), `oracle.py` (SQL độc lập), `run_eval.py`, `report.md`, `last_run.json`.
- Chạy unit test: `cd housing-backend/housing-backend; DATABASE_URL=postgresql+asyncpg://postgres:123456789@localhost:5432/housing_dev ../../.venv/Scripts/python.exe -m pytest tests/recommend/unit -q`.
- Snapshot code trước đợt rút gọn (khôi phục nếu cần): `C:\Users\huypro37\AppData\Local\Temp\claude\d--my-project-DoAn2-Multi-Agent-RAG-and-Prediction-Housing-Price\960f0f8e-f6e7-43ce-a1ac-8cc8e5202e47\scratchpad\snapshot_before_trim` (có thể đã mất; code **không nằm trong git**).

### 3.2 Lịch sử chấm (query-tester, DB `housing_dev`)

| Vòng | Kết quả | Ghi chú |
|---|---|---|
| 1–3 | FAIL | LLM tự quyết quy tắc ⇒ chuyển sang code; LLM bịa khi so sánh ⇒ bỏ LLM khỏi trả lời |
| 4 | FAIL | Dữ kiện đúng 26/26; hay **bỏ sót ý khách hỏi** (nhiều vế, "nhất", xác nhận ngân sách); 1 lượt vi phạm [S1] (C35#5 "cả khu Thủ Đức"); "tầm 3 tỷ lệch 10%" tính sai; 14 lỗi code sạch. p95 6,39 s (Kaggle tắt) |
| 4 → sửa | Xong #29 a–i | db-coder đã sửa, 176 unit test passed. **Chưa kiểm qua API** |
| 5 | **Bị tạm dừng giữa chừng** | query-tester có thể đã chạy một phần; `report.md`/`last_run.json` có thể lẫn vòng 4/5, xem đầu `report.md`; bản vòng 4 ở `scratchpad/round4/`. Chạy lại từ đầu cho chắc |

Tiêu chí chưa bao giờ chấm được: **[S7]** (sở thích mềm ≥ 3/5; vòng 3 từng đạt 3,75/5 khi Kaggle còn bật).

## 4. Quyết định và bài học đáng nhớ

- **Quy tắc tất định nằm trong code, LLM chỉ đề xuất** (reset, "căn thứ N"/mã tin, "phường X", "rẻ hơn", loại BĐS, giá xấp xỉ, xác nhận). Vòng 1–4 cho thấy LLM không ổn định ở các chỗ này.
- **Giá xấp xỉ** ("tầm/khoảng/cỡ/độ/xấp xỉ X") = `[X×0,8 ; X×1,05]` (người dùng quyết). "Dưới/tối đa/có X" chỉ `price_max`. Gốc X = số tiền **đầu tiên trong câu**.
- **Ngày dữ liệu ≠ hôm nay**: test dùng `as_of = 2026-09-22`; chạy với ngày thật chỉ còn 186 tin ⇒ kết quả thưa, không phải lỗi code.
- Dữ liệu nghi sai: tin `46230583` (nhà 3 tầng 3,3 tỷ, 13,1 m²) — bước làm sạch chưa bắt. Tin "trùng" gộp theo (loại, giá, diện tích, phòng ngủ, tọa độ < 30 m).
- **Môi trường:** `uv run` trong `housing-backend/` hỏng (Windows Application Control). Dùng `D:/my_project/DoAn2/Multi-Agent-RAG-and-Prediction-Housing-Price/.venv/Scripts/python.exe`; ruff qua `uvx ruff`; `python -m alembic`. Đã cài thêm vào `.venv`: openai, pytest, httpx, pandas, numpy, requests, psycopg_pool, coverage.
- **An toàn:** `.gitignore` đang bị comment toàn bộ ⇒ **đừng commit** trước khi khôi phục (nguy cơ lộ `.env`, `backup/*.dump`, `housing-backend.zip`). `.env` chứa key OpenAI, Goong, embedding — **nên đổi key OpenAI** (đã dán trong chat). `config.py` còn mật khẩu mặc định `postgres:123456789`.
- **Agent** (`.claude/agents/`, gọi theo tên sau khi khởi động lại Claude Code): `db-coder`, `db-reviewer`, `query-tester`, `doc-reviewer`. Trong phiên cũ gọi qua `general-purpose` kèm đường dẫn file vai trò; phiên mới gọi thẳng theo tên được. Agent đã chạy bị chặn khi `housing` bị ghi: đừng lách.
- **Tiết kiệm token ở phiên mới:** đừng đọc lại các báo cáo dài; chỉ đọc STATUS.md + `hybrid-search.md` mục 9 + đầu `tests/recommend/report.md`. Giao việc cho agent bằng đường dẫn file, không dán lại nội dung.
- Model embedding chạy trên Kaggle qua HTTP; `/rerank` server chưa có, `RERANK_ENABLED` mặc định tắt.


## 7. Chatbot chế độ gợi ý (GĐ8–9 rút gọn) — cập nhật cuối phiên 09/10

Spec: [chatbot-recommendation.md](chatbot-recommendation.md). **Giao diện chỉ mức demo, backend là trọng tâm** (người dùng chốt).

- **Frontend demo: XONG** (`housing-frontend/`, React+TS+Vite+Leaflet; `npm run build` xanh, 8 test Vitest, `npm audit` 0 lỗ hổng, 5 thẻ + 5 marker đánh số quan sát được trên mock bằng Chrome headless). Chạy: `cd housing-frontend && npm install && npm run mock` (terminal 1) và `npm run dev` (terminal 2, http://localhost:5173). **Chưa chạy với backend thật.** Chưa kiểm: URL tile Goong (đoán; mặc định dùng OpenStreetMap, sửa hằng `TILES` trong `MapView.tsx`).
- **Backend chatbot: CHƯA LÀM** (làm sau khi GĐ7 vòng chấm xong): `mode` bắt buộc, CORS, trường mới ở `ListingHit` (lat/lon, `coords_reliable`, `position`, `days_left`), `summary`, `RelaxOption.message`, `GET /recommend/map` (GeoJSON), `POST /recommend/reset`. Chi tiết mục 1–2 của spec. Trần dòng `app/services/recommendation/` vẫn 1.900; code mới đặt ở `app/services/map.py`.
- Sau đó: ghép frontend với backend thật (một hội thoại 5 lượt), db-reviewer nghiệm thu `[U6]`, `[U9]`, `[U3]`.

## 8. Vòng chấm 5 (cuối phiên 09/10, lúc nén ngữ cảnh)

- **Kaggle đã bật lại** (URL/key mới đã ghi vào `.env`, kiểm: health 200, /embed 1024 chiều) ⇒ vòng 5 chạy vector search thật và chấm được [S7].
- query-tester (vòng 5) **đang chạy khi nén ngữ cảnh**; file `housing-backend/housing-backend/tests/recommend/report.md` (18:45) có dòng đầu "KẾT LUẬN: PASS (174 lượt, [S7] chấm tay bên dưới)" và `report_extra.md` (18:46) — **đó là bản tạm, chưa được query-tester chốt bằng báo cáo cuối và main CHƯA kiểm lại**. Việc đầu tiên ở phiên mới: đọc đầu `report.md` + `report_extra.md`, kiểm tỷ lệ lượt degraded (phải 0%), [S7] ≥ 3/5, [S1] = 0, rồi tự chạy lại một số kịch bản (ví dụ `run_eval.py --ids C01,C35,C38,C45` và `--extra --ids X01`) để xác nhận trước khi tuyên bố PASS.
- Nếu vòng 5 thật sự PASS: main tự review code, tự chạy lại 50 kịch bản, tự đóng vai khách hàng ⇒ chốt GĐ7 ⇒ làm backend chatbot (mục 7) ⇒ áp DB thật.
- Nếu còn FAIL: giao db-coder sửa, chấm vòng 6 (vòng cuối), hết vòng 6 chưa PASS thì báo người dùng quyết.

### 8.1 KẾT QUẢ CUỐI VÒNG 5 (đã nhận báo cáo cuối của query-tester — thay thế mục 8 ở trên)

**FAIL (vòng 5/6)** — chữ "PASS" ở đầu `report.md` lúc đó chỉ là bản tạm; báo cáo cuối: harness tự động xanh (S1–S4, S6, S8–S10, S12–S15 đạt; **[S7] 4,13/5 đạt** với Kaggle bật, 0% lượt degraded; p95 3,25 s) nhưng chấm tay có **4 lỗi chặn**:
- **B1** câu hỏi chi tiết: "Chi tiết căn thứ 4 đi" mất toàn bộ chi tiết (từ "đi" thành chủ đề); "còn hạn" bị tách mất "còn"; vế không khớp thuộc tính trích sai câu (khớp từ khóa đã bỏ dấu: "bán"="ban", "sống"="sông", "thượng"="thương") và khẳng định sai "tin không ghi" khi từ khóa nằm ở tiêu đề.
- **B2** mất vế khi hỏi "rộng hơn/rẻ hơn" (chưa có so sánh hơn cho diện tích/giá khi không nói tên thuộc tính).
- **B3** giá "2ty5", "3tỷ2", "tầm 3tỷ8" bị bỏ im (regex cần ranh giới từ sau đơn vị).
- **B4** "loại nào cũng được / không nhất thiết" vẫn lọc căn hộ.
Cải thiện (không chặn): "gần trg", `referenced_ids` của câu "nhất" (bộ extra X05), 7 lỗi code sạch (staticmethod → hàm module, docstring service sai, side effect trong `_plan`, magic number, STOP_WORDS gộp NUMBER_WORDS làm mất "nam/sau/bay/tam", kiểu `Renderer`).
Kết quả chi tiết: `housing-backend/housing-backend/tests/recommend/report.md` (mục "Chấm tay vòng 5", hội thoại F, G), `report_extra.md`.
**Vòng sửa 5 đã giao db-coder; sau đó vòng chấm 6 là vòng CUỐI** (hết vòng 6 chưa PASS thì báo người dùng quyết). Quyết định mới: spec mục 9 #31–#33.

### 8.2 KẾT QUẢ VÒNG 6/6 (vòng cuối) — FAIL vì đúng 1 lỗi chặn nhỏ; CHỜ NGƯỜI DÙNG QUYẾT

Vòng 6 (Kaggle bật, 0% degraded, 50 kịch bản + 9 hồi quy + 44 câu trích + 23 câu thăm dò + 4 hội thoại khách thật F,G,H,I): **mọi tiêu chí đạt** — [S1]=0, [S3] 542/542, [S7] 4,0/5, [S8]/[S9] 100%, [X1]–[X3] đạt, p95 3,57 s, 238 test passed, code 1.900 dòng. **4 lỗi chặn B1–B4 của vòng 5 đã hết.**
**Lỗi chặn còn lại (1):** sau khi đã có ngân sách, "thôi giảm xuống 3tỷ2" / "giảm xuống 3 tỷ" / "giảm còn 3 tỷ nhé" bị hiểu là "rẻ hơn 10%" (kết quả 2,88 tỷ thay vì 3,2 tỷ). Nguyên nhân: `text_rules.py:68` `CHEAPER_PATTERN_FOLDED` có "giam" nên cờ `cheaper` của LLM được giữ; `service.py:146-149` nhân 0,9 lên giá tối đa vừa đặt. Sửa: bỏ cờ `cheaper` khi câu đã có số tiền (price_max/price_min trong delta) — spec #16 "giảm xuống X" = giá tối đa mới X. ~5 dòng.
Cải thiện không chặn (6 mục): "chỗ đậu ô tô" mất vì STOP_WORDS loại "đậu/ô/tô" khi bỏ dấu (`grounding.py:198`); "thương lượng" ≠ "còn bớt" (đồng nghĩa); dòng "đường: tin không ghi" thừa; sở thích mềm mất khi câu không có dấu phẩy ("hẻm xe hơi", "hồ bơi") do LLM; G8 đất nền giữ `bedrooms_min` cũ ⇒ 0 tin, relax chưa có phương án bỏ phòng ngủ; trình bày lặp ("rộng hơn" in 2 lần, "các căn bằng nhau" khi chỉ 1 căn, thông báo lỗi giá "3tr8" khó hiểu). Code sạch 3 lỗi nhẹ (`except Exception` có log, docstring `_openai_client` 2 dòng tóm tắt, `MessageRules.correct` ghi `self.ignored`).
**Đề xuất của main:** KHÔNG chạy vòng 7 đầy đủ. Giao db-coder sửa lỗi chặn (+ các mục cải thiện rẻ: STOP_WORDS "đậu/ô/tô", bỏ `bedrooms_min` khi đổi sang đất nền, 3 lỗi code sạch), rồi **chỉ** chạy lại H lượt 7 + 6 câu thăm dò "giảm xuống/giảm còn" (`scratchpad/r6_conv3.json`) + bộ 50 để xác nhận không hồi quy; main tự đóng vai khách hàng; sau đó chốt GĐ7. Kết quả chi tiết: `housing-backend/housing-backend/tests/recommend/report.md` (mục "Chấm tay vòng 6", hội thoại H, I).

## 9. TẠM DỪNG LẦN 3 (09/10/2026) — đọc mục này trước khi làm tiếp

**Quyết định người dùng:** phương án "sửa lỗi chặn + lỗi nhỏ rẻ, kiểm tra gọn" cho GĐ7 (không chạy vòng 7 đầy đủ).
**Đang dở lúc dừng:** db-coder làm vòng sửa 6 (đã yêu cầu dừng ở trạng thái ổn định; xem báo cáo cuối của nó nếu có). Phạm vi vòng sửa 6: (1) lỗi chặn "giảm xuống 3tỷ2" bị trừ thêm 10% (bỏ cờ `cheaper` khi câu có số tiền); (2) lỗi nhỏ rẻ: STOP_WORDS loại nhầm "đậu/ô/tô", đổi sang đất/đất nền thì bỏ `bedrooms_min`, bỏ dòng thừa "đường: tin không ghi", không in lặp khối "rộng hơn", thông báo lỗi giá "3tr8"; (3) 3 lỗi code sạch nhẹ.
**Làm tiếp (theo thứ tự):**
1. Kiểm trạng thái code: `cd housing-backend/housing-backend; DATABASE_URL=postgresql+asyncpg://postgres:123456789@localhost:5432/housing_dev ../../.venv/Scripts/python.exe -m pytest tests/recommend/unit -q` + `uvx ruff check app tests/recommend/unit` + `wc -l app/services/recommendation/*.py` (trần 1.900). Nếu vòng sửa 6 chưa xong, giao lại db-coder (đọc mục 8.2 + mục này).
2. Kiểm gọn bằng query-tester (`subagent_type: query-tester`): chạy lại bộ 50 kịch bản + `--extra` + hội thoại H lượt 7 và các câu "giảm xuống/giảm còn" (`scratchpad/r6_conv3.json` nếu còn); **cần Kaggle bật** (`curl $EMBEDDING_API_URL/health` = 200, nếu không nhờ người dùng chạy lại notebook và cập nhật `.env`).
3. Main tự đóng vai khách hàng (script nhỏ gọi `RecommendationService().chat(...)` với `as_of=2026-09-22`, nhiều hội thoại mới), rồi **chốt GĐ7**.
4. Backend chatbot (mục 7 + spec [chatbot-recommendation.md](chatbot-recommendation.md) phần A): `mode` bắt buộc, CORS, `ListingHit` thêm lat/lon/coords_reliable/position/days_left, `summary`, `RelaxOption.message`, `GET /recommend/map`, `POST /recommend/reset` (file `app/services/map.py`). Rồi ghép `housing-frontend/` với backend thật (một hội thoại 5 lượt).
5. DB thật (STATUS 2.1b): người dùng tự chạy hoặc cấp quyền; sau đó chuyển code/test sang `housing`.
6. Việc khẩn cuối: crawler định kỳ (GĐ3).
**Phạm vi (đừng đề xuất lại):** chỉ RAG + chatbot gợi ý; KHÔNG dự đoán giá, KHÔNG khoảng cách Quận 1; giao diện mức demo.
**Mẹo tiết kiệm token ở phiên mới:** chỉ đọc STATUS.md (mục 8.2, 9) và đầu `tests/recommend/report.md`; giao việc cho agent bằng đường dẫn file, đừng dán lại báo cáo dài.

**Trạng thái code đo được lúc dừng (19:46):** `tests/recommend/unit` **216 passed**, `uvx ruff check app tests/recommend/unit` sạch, `app/services/recommendation` đúng **1.900** dòng ⇒ vòng sửa 6 đã làm được phần lớn (unit test tăng từ 199 lên 216), **nhưng chưa có báo cáo cuối và chưa được chấm lại qua API**. db-coder đã nhận lệnh dừng; nếu báo cáo cuối của nó có trong thông báo thì đọc, nếu không thì kiểm từng mục vòng sửa 6 bằng `grep`/test (đặc biệt: câu "thôi giảm xuống 3tỷ2" phải ra giá tối đa 3,2 tỷ). `tests/recommend/report.md`, `last_run.json` có thể đã bị run_eval của db-coder ghi đè một phần (report.md 19:31, last_run.json 19:20) — **chạy lại bộ 50 bằng query-tester** để có kết quả sạch (bước 2 ở trên).

**Báo cáo cuối của db-coder (vòng sửa 6, đã dừng):** xong cả ba mục — (1) lỗi chặn: "giảm xuống/giảm còn <số tiền>" đặt giá tối đa mới (cờ `cheaper` bỏ khi câu có số tiền), đã tái hiện 6 cách nói + H6 đều đúng, "rẻ hơn chút/giảm bớt" vẫn hạ 10%; (2) 5 lỗi nhỏ a–e (từ đệm so khớp dạng có dấu, đổi sang đất bỏ số phòng ngủ cũ, "đường nào" là câu hỏi địa chỉ, không in lặp xếp hạng/"các căn bằng nhau" khi 1 căn, báo lỗi giá bằng số khách gõ), đều có test; (3) code sạch: `MessageRules.correct` trả `Correction(plan, ignored, typed_price)` không ghi state ngầm, docstring `_openai_client` một dòng. **216 unit test passed, ruff sạch, 1.900 dòng.** `report.md`/`last_run*.json` của tester đã được chép trả từ backup (không bị ghi đè). **Chưa có kết quả 50 kịch bản cho vòng sửa 6** (db-coder hủy lần chạy giữa chừng) ⇒ bước 2 mục 9 (query-tester chạy lại bộ 50 + extra + câu "giảm xuống") là việc kế tiếp. Lưu ý: một thông báo lỗi giá được chỉnh câu chữ sau lần chạy dở, chỉ đổi lời không đổi logic.

## 10. Phiên 10/10/2026 — đang kiểm gọn sau vòng sửa 6 (nén ngữ cảnh lúc này)

- Đã xác nhận lúc tiếp tục: code ổn (**216 unit test passed**, ruff sạch, **1.900** dòng), Kaggle bật (health 200), DB `housing` thật vẫn 5 schema cũ.
- **Đã giao query-tester kiểm gọn** (chạy nền): bộ 50 kịch bản (174 lượt) + `--extra` (9) + `pytest -m llm -k extraction` (44 câu) + các ca vòng 6 (6 cách nói "giảm xuống/giảm còn", H lượt 7, "chỗ đậu ô tô", "thương lượng", "đường nào", đất nền sau "1pn", "3tr8"). Kết quả sẽ nằm ở `housing-backend/housing-backend/tests/recommend/report.md` và `report_extra.md`; bản trước backup ở scratchpad `round6b/`. **Nếu phiên mới thấy report.md có kết luận mới (ngày 2026-10-10) thì đọc; nếu báo cáo chưa có hoặc dở thì chạy lại bằng query-tester theo mục 9 bước 2.**
- Quy tắc khi kết quả về: PASS ⇒ main tự đóng vai khách hàng (script gọi `RecommendationService().chat(...)`, `as_of=2026-09-22`) rồi chốt GĐ7 ⇒ backend chatbot (mục 7, spec chatbot-recommendation.md phần A) ⇒ ghép `housing-frontend/`. FAIL ⇒ báo người dùng quyết (đã hết 6 vòng; không tự chạy thêm).
- Cách chạy dự án hiện tại: backend `cd housing-backend/housing-backend; $env:DATABASE_URL="postgresql+asyncpg://postgres:123456789@localhost:5432/housing_dev"; ..\..\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000` (đã kiểm: /health 200, chat trả 5 tin); test `... -m pytest tests/recommend/unit -q`; giao diện `cd housing-frontend; npm install; npm run mock; npm run dev` (chỉ chạy với mock; backend chưa có `summary`/`/map`/`/reset`).

## 11. KẾT QUẢ KIỂM GỌN 10/10/2026: **PASS** (query-tester) — GĐ7 gần chốt

Kaggle bật, 0% lượt degraded. **50 kịch bản (174 lượt): [S1] 129/129, [S2] 174/174, [S3] 542/542, [S4], [S5], [S6], [S8], [S9], [S14], [S15] đều 100%, [S7] ~3,75–4,4/5 (≥ 3), p95 3,79 s; bộ extra [X1] 5/5, [X2] 3/3, [X3] 2/2, p95 3,08 s; `pytest -m llm -k extraction` 44 passed.** Lỗi chặn duy nhất của vòng 6 ("giảm xuống/giảm còn <số tiền>") đã hết (6 cách nói đều đúng; "rẻ hơn chút" vẫn hạ 10%); 5 lỗi nhỏ vòng 6 đã xác nhận; không có hồi quy. [S10]–[S12] **chưa đo lại bởi tester** (số 216 unit test/ruff/1.900 dòng do main đo ngày 10/10 trước đó: đạt).
Kết quả: `housing-backend/housing-backend/tests/recommend/report.md`, `report_extra.md`, `last_run*.json` (đã ghi mới 2026-10-10). Mục "Chấm tay vòng 6" cũ nằm ở scratchpad `round6b/` (không còn trong report.md).
**Cải thiện (không chặn, chưa làm):** (1) hỏi "chủ nhà có thương lượng không?" mà không nói căn nào thì hệ thống tìm lại 5 tin thay vì hỏi lại/trả lời theo cả danh sách; (2) "3tr8" đứng riêng bị hiểu 380 triệu, còn "khoảng 3tr8 thôi nha" báo 3,8 triệu — không nhất quán; (3) trích bằng chứng "đậu ô tô" đôi khi lỏng ("đường ô tô thông"); (4) "thương lượng" ≠ "còn bớt"; (5) sở thích mềm mất khi câu không có dấu phẩy.
**Việc tiếp theo (đúng thứ tự):**
1. **Main duyệt cuối** (còn thiếu): tự đóng vai khách hàng với 3–4 hội thoại MỚI qua `RecommendationService().chat(conversation_id, message, as_of=date(2026,9,22))`, tự chạy lại vài kịch bản (`run_eval.py --ids C01,C35,C38,C45` và `--extra --ids X01`), tự đo `pytest tests/recommend/unit` + ruff + `wc -l`. Chỉ khi đó mới chốt GĐ7. Nếu muốn, sửa nhanh cải thiện (1) bằng db-coder (hỏi lại "căn nào?" khi câu chi tiết không có tham chiếu và không phải so sánh cả danh sách).
2. **Backend chatbot** (mục 7 + `chatbot-recommendation.md` phần A): `mode` bắt buộc, CORS, `ListingHit` thêm `latitude/longitude/coords_reliable/position/days_left`, `summary`, `RelaxOption.message`, `GET /recommend/map` (GeoJSON), `POST /recommend/reset` trong `app/services/map.py`; giữ `app/services/recommendation/` ≤ 1.900 dòng. Giao `db-coder`; nghiệm thu `[U6]`, `[U9]` bằng `db-reviewer`.
3. Ghép `housing-frontend/` với backend thật (hội thoại 5 lượt, `[U3]`). Sửa URL tile Goong nếu người dùng có key trình duyệt.
4. DB thật (mục 2.1b): người dùng tự chạy hoặc cấp quyền ⇒ chuyển code/test từ `housing_dev` sang `housing`.
5. Crawler định kỳ (GĐ3, khẩn: chỉ còn 186/7.603 tin còn hạn).

## 12. Cập nhật 10/10/2026 — main duyệt cuối GĐ7 + backend chatbot phần A xong
- Main đóng vai khách (3 hội thoại mới) → thấy 3 lỗi nhỏ → db-coder đã sửa; main chạy lại: 227 unit test xanh, ruff sạch, recommendation/ 1.898 dòng, C01/C35/C38/C45 và X01/X10 đạt (p95 ≈3,6 s).
- Backend phần A xong: `mode` bắt buộc, CORS, `summary`, lat/lon, `RelaxOption.message`, `GET /recommend/map`, `POST /recommend/reset` (`app/services/map.py`); `EmbeddingClient` chuyển sang `app/services/embedding.py`.
- Còn: ghép `housing-frontend/` với backend thật (uvicorn) → áp DB thật (người dùng chạy lệnh mục 2.1b) → crawler định kỳ.
- Mode prediction (10/10/2026): spec docs/tasks/prediction-mode.md; coder+frontend agents chạy, chờ reviewer.
- Bước cuối đã yêu cầu (10/10/2026): sau khi prediction + ghép frontend PASS → 1 agent dùng skill (simplify/clean code) + nguồn internet (PEP 8, Google style, clean-code-python, fastapi template) rà toàn bộ code; được refactor nhưng phải giữ xanh toàn bộ test (227 unit recommend, test prediction, eval 50 kịch bản, ruff).
- Hàng đợi (10/10/2026, theo thứ tự): (1) reviewer chấm lại prediction vòng 2 → (2) tester 20 ca thực tế cho dự đoán giá, vòng lặp tester↔coder đến khi pass 20/20 → (3) agent pipeline src/pipeline (dữ liệu thô → làm sạch → nạp housing_dev, idempotent) → (4) agent clean code (skill + nguồn internet, refactor giữ xanh test) → (5) main tự chạy lại + báo cáo senior dev.

## 13. Kết thúc đợt 10/10/2026 (prediction + pipeline + clean code)
- Prediction: spec `prediction-mode.md`, reviewer PASS vòng 3; 20 ca thực tế: 18 PASS + 1 PASS-biên (R07) + 1 KNOWN-LIMIT (R12 Cần Giờ); khung train đã mở (R² 0,5695). Goong hết hạn mức ngày → 8 ca địa chỉ cụ thể chưa xác nhận bằng Goong thật.
- Pipeline `src/pipeline` chạy thật 2 lần trên housing_dev (xem src/pipeline/README.md). Clean code xong, mọi test xanh (481 backend, 20 src, 8 frontend).
- Báo cáo senior dev: `docs/reports/senior-review-2026-10-10.md` (việc tiếp theo ở mục 4 của báo cáo).


## 14. Tạm dừng 15/10/2026 — chatbot thông minh hơn + địa điểm có tên
- Tài liệu: [docs/chatbot.md](../chatbot.md) (kiến trúc, intent, API). Spec: [chat-intelligence.md](chat-intelligence.md) (**nghiệm thu PASS** I1–I12 sau vòng 2), [named-places.md](named-places.md) (**chưa PASS**).
- named-places: đã qua 3 lượt chấm. Vòng 3 FAIL N1, N5, N6 (nhẹ), N10 (còn 12/15 hội thoại, cần ≥ 14). Danh sách lỗi và 9 mục sửa đã giao cho db-coder (vòng sửa 2/3) nhưng **bị dừng giữa chừng — code có thể dang dở**: chạy `pytest tests -q` + `uvx ruff check .` trước khi làm tiếp; lần chạy cuối coder báo 641 test xanh (trước vòng sửa 2).
- Trần dòng đã nới: `recommendation/` ≤ 2.100, `places.py` ≤ 360 (hiện 2.008 và 217 trước vòng sửa 2).
- Việc tiếp: (1) xem `git status`/chạy test để biết coder đã sửa tới đâu → (2) cho db-coder làm nốt 9 mục (xem báo cáo reviewer vòng 3: Dĩ An cơ sở 2 ĐH Bách khoa trong `pois`, ưu tiên ĐH khi tên bắt đầu "đại học", NAME_STOP "tu"/"nha", GENERIC_NAME "đa khoa", `kind` theo từ loại, `choose()` dùng `district`, Goong chặt hơn Bình Dương, fallback bán kính, bỏ alias `dhqg`) → (3) db-reviewer chấm lại N1/N5/N6/N10 (tối đa vòng 3/3; FAIL tiếp thì báo người dùng quyết) → (4) cập nhật docs/chatbot.md mục 7–8 và lệnh áp DB thật.
- DB thật `housing`: **chưa có** `alembic_version` hay `public.pois` (vẫn 5 schema cũ) nên chưa áp migration 0002, 0003 và `scripts/import_universities.py` được. Thứ tự khi áp: `alembic upgrade head` rồi nạp ĐH/CĐ. Mọi thay đổi mới chỉ ở `housing_dev`. Không commit.
- Chi phí: mỗi vòng chấm tốn 60–230 lượt OpenAI/Goong. Đặt ngân sách tổng cho reviewer (≤ 90) và tự đếm bằng hook httpx.
- R13 (realistic) phụ thuộc Goong thật; baseline 362,38 là tâm quận.
