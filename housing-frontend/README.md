# housing-frontend

Giao diện DEMO cho chatbot gợi ý bất động sản TP.HCM: khung chat (trái), thẻ Top 5, bản đồ Leaflet (phải).
React 18 + TypeScript + Vite, CSS thuần. Hợp đồng API: `docs/tasks/chatbot-recommendation.md` mục 1.

## Chọn mock hay backend thật: biến VITE_API_URL

Mặc định `http://localhost:8000` (backend thật, đã bật CORS cho :5173). Đặt trong `.env.local`.

```bash
# Backend thật (trong housing-backend/housing-backend, PYTHONPATH=., DATABASE_URL=...housing_dev)
python -m uvicorn app.main:app --port 8000
npm install && npm run dev            # http://localhost:5173

# Mock (không cần backend): đặt VITE_API_URL=http://localhost:8001 trong .env.local
PORT=8001 npm run mock && npm run dev
```

Nút "Gợi ý | Dự đoán giá" đổi mode. Gợi ý: `POST /api/v1/recommend/chat`, `/recommend/map`, `/recommend/reset`.
Dự đoán giá: `POST /api/v1/chat` (mode `prediction`) và `POST /api/v1/reset`.
Thẻ định giá hiện các trường đã biết/còn thiếu, giá ước tính, khoảng tham khảo (từ `price_per_m2_low/high`), trung vị quận và cảnh báo; trạng thái `ready` có nút "Dự đoán giá ngay" (gửi "ok").
Bản đồ: bấm thẻ ⇒ bay tới marker; bấm marker ⇒ chọn và cuộn tới thẻ; bấm thẻ của lượt cũ ⇒ bản đồ đổi về bộ tin của lượt đó.
Câu thử với mock: "Căn hộ Quận 7 dưới 3 tỷ", "Mình muốn mua nhà", "so sánh căn 1 và 3", "tin hiếm", "degraded", "thuê"; mode giá: "Nhà 60m2 Gò Vấp".

## Biến môi trường (xem `.env.example`)

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `VITE_API_URL` | `http://localhost:8000` | Gốc của API (backend thật hoặc mock) |
| `VITE_GOONG_MAPTILES_KEY` | trống | Key map tiles Goong cho frontend. Trống = OpenStreetMap (tile.openstreetmap.de). Không dùng `GOONG_API_KEY` của backend |

## Lệnh khác

`npm run build` (tsc strict + vite build), `npm test` (Vitest cho `src/format.ts`).
