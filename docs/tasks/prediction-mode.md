# Spec: chế độ dự đoán giá (mode prediction) — dùng lại mô hình ĐỒ ÁN 1

Người dùng yêu cầu 10/10/2026 (thay đổi phạm vi: prediction được làm lại sau khi recommendation xong).
Chỉ dùng **mô hình cũ + phương pháp cũ**; thiếu "số bệnh viện/trường/chợ trong 1 km, 3 km" so với đồ án 2 →
để **comment `TODO`** trong code, làm sau.

## 1. Nguồn đồ án 1 (chỉ đọc, không sửa)
`Data-Analysis-And-Predict-Housing-Price/`: `CHATBOT.md` (luồng chat), `test.py` (CLI chatbot, 899 dòng),
`src/web/app/retrain/retrain.py` (train), `src/web/app/service/predict_service.py` (dự đoán),
`src/web/app/data/data.csv` (24.880 dòng, tọa độ ×10⁹), `goong.py`, `prompt.txt`.
**Không có file .pkl** → phải train lại bằng chính phương pháp cũ.

## 2. Phương pháp cũ (giữ nguyên)
- Pipeline sklearn: `SimpleImputer(median)` + `RandomForestRegressor`; mục tiêu `log(giá/m²)` (triệu VND/m²), dự đoán `exp()`; tổng giá = giá/m² × diện tích.
- Đặc trưng theo thứ tự: loại nhà đất (0 chung cư, 2 nhà riêng, 3 biệt thự/liền kề, 4 mặt phố, 7 đất), địa chỉ = mã quận 0–23 (bảng trong retrain.py), diện tích, mặt tiền, phòng ngủ, tọa độ x (lat), tọa độ y (lon), số tầng, cách trung tâm (haversine tới Nhà thờ Đức Bà).
- Bắt buộc: loại, quận/địa chỉ, diện tích. Tùy chọn: mặt tiền, phòng ngủ, số tầng (thiếu → median của imputer). Chung cư tự điền số tầng/mặt tiền = thiếu; đất tự điền số tầng/phòng ngủ = thiếu.
- Tọa độ: Goong geocode (key `GOONG_API_KEY` trong `.env`); Goong lỗi/không có → tâm tọa độ các tin đăng của quận đó trong DB (`listings`), không bịa.
- `# TODO(đồ án 2): thêm đặc trưng số bệnh viện/trường học/chợ trong bán kính 1 km và 3 km (dùng bảng pois + hàm nearby()).` đặt đúng chỗ dựng đặc trưng.

## 3. Việc phải làm (trong `housing-backend/housing-backend/`)
1. `scripts/train_price_model.py`: copy `data.csv` sang `data/price_training.csv` (nếu chưa có), train đúng phương pháp cũ (chia train/test như retrain.py), in RMSE/MAE/R² (trên giá/m²), lưu `models/price_rf.joblib` (+ `models/price_rf.metrics.json`). `models/` thêm vào hướng dẫn, không commit.
2. `app/services/prediction/` (một class gọn mỗi file, theo phong cách `recommendation/`):
   - `predictor.py`: `PricePredictor` — nạp model một lần, `predict(fields) -> PriceEstimate(price_per_m2, total_price, distance_to_center_km, district_median_per_m2)`.
   - `geocoder.py`: `Geocoder` — Goong + dự phòng như trên.
   - `chat.py`: `PredictionChat` — hội thoại nhiều lượt: LLM (gpt-4o-mini, structured output, key trong `.env`) **chỉ trích xuất** trường; **code quyết định**: thiếu trường bắt buộc → hỏi đúng 1 câu; đủ → hỏi tùy chọn/"gõ ok"; "ok/xong/chốt…" → dự đoán; sửa thông tin sau dự đoán → dự đoán lại; reset; ngoài phạm vi (không phải định giá BĐS TP.HCM, tỉnh khác) → từ chối ngắn. Câu trả lời + giải thích kết quả do **code viết từ số liệu** (giá/m², tổng giá, khoảng cách trung tâm, so với median quận) — LLM không viết câu trả lời, không bịa lý do.
   - Kiểm tra biên: diện tích 10–2.000 m², số tầng 1–20, phòng ngủ 0–20, mặt tiền 1–50 m; ngoài biên → hỏi lại, không đoán.
   - Tổng ≤ 600 dòng cho thư mục `prediction/` (không tính test).
3. API: mở rộng `POST /api/v1/recommend/chat`? **Không** — thêm `POST /api/v1/chat` nhận `{conversation_id?, message, mode: "recommendation"|"prediction"}` điều phối theo `mode` (sai mode → 422); giữ nguyên `/api/v1/recommend/*` đang chạy và 227 test cũ vẫn xanh. Phản hồi prediction: `{conversation_id, mode, status: collecting|ready|predicted|out_of_scope, answer, summary, fields, missing, prediction?: {price_per_m2, total_price, distance_to_center_km, district_median_per_m2}}`. `POST /api/v1/reset` xoá hội thoại cả hai mode.
4. Test: `tests/prediction/unit/` (predictor với model nhỏ giả, chat với FakeExtractor, API bằng TestClient). Ruff sạch (`uvx ruff check app tests`).

## 4. Tiêu chí nghiệm thu (reviewer chấm bằng mã)
- [P1] `train_price_model.py` chạy được trên data.csv; R² test ≥ 0,5 (báo số thực; thấp hơn thì nêu rõ, không giấu); model lưu và nạp lại được.
- [P2] `PricePredictor`: đầu vào mẫu cho giá/m² trong khoảng hợp lý (5–500 triệu/m²); thiếu trường tùy chọn vẫn dự đoán; mã quận/loại lạ → lỗi rõ ràng, không crash.
- [P3] Geocoder: Goong thật trả tọa độ cho 3 địa chỉ mẫu; mô phỏng Goong lỗi → dùng tâm quận từ DB.
- [P4] Chat: ≥ 12 kịch bản **hội thoại nhiều lượt** do reviewer tự viết (nhập một lần đủ, nhập từng bước, sửa sau dự đoán, reset, địa chỉ mơ hồ, ngoài biên, off-topic, không dấu, "ok" quá sớm khi thiếu trường bắt buộc, đổi quận giữa chừng): 100% đúng quy tắc code (thiếu bắt buộc không được dự đoán; không hỏi lại trường đã có; không bịa số).
- [P5] Số trong câu trả lời khớp `prediction` (giá/m² × diện tích = tổng, làm tròn nhất quán).
- [P6] API thật qua uvicorn (cổng 8011): hội thoại 4 lượt mode prediction + 3 lượt mode recommendation chạy được; mode sai → 422; CORS giữ nguyên.
- [P7] Không hồi quy: 227 test cũ xanh; thư mục `recommendation/` vẫn ≤ 1.900 dòng.
- [P8] Code sạch theo chuẩn đã dùng (PEP 8, Google style, không rườm rà, comment tiếng Việt, TODO bán kính 1/3 km có mặt).
- [P9] Không lộ key; không ghi vào DB `housing` thật; không commit.
