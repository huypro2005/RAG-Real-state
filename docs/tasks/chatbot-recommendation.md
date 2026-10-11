# Task GĐ8–9 (rút gọn): Chatbot chế độ gợi ý — API + giao diện + bản đồ

Phạm vi theo yêu cầu người dùng 09/10/2026: **chỉ chế độ `recommendation`** (không prediction, không khoảng cách Quận 1). Đề cương §5.9–§5.11, §7.4. Lõi tìm kiếm/hội thoại đã có: [hybrid-search.md](hybrid-search.md).
> **Mức độ (người dùng chốt 09/10/2026): giao diện chỉ ở mức DEMO; trọng tâm hoàn thiện là BACKEND.**
> - Backend (phần A, tiêu chí `[U6]`, `[U9]` và mọi tiêu chí GĐ7): làm chặt như các vòng trước.
> - Frontend (phần B): làm gọn, đủ để trình diễn luồng gợi ý: khung chat + thẻ Top 5 + bản đồ có marker đánh số. **Bỏ:** E2E tự động/Playwright, kiểm tiếp cận (`[U7]`), test component, tối ưu mobile, chip gợi ý nhập nhanh, bộ chọn mode (chỉ gửi `mode: "recommendation"`). **Giữ tối thiểu:** cảnh báo hết hạn/degraded (mục 3.4, chỉ 3 nhãn), nút "Tìm lại từ đầu", nút `relax_options` nếu rẻ (không bắt buộc). Test duy nhất bắt buộc: unit test `format.ts` (giá/ngày/khoảng cách/cảnh báo). Mỗi file ≤ 250 dòng, không `any`. `[U2]` kiểm bằng chạy mock + quan sát, `[U3]` chạy thật một lần; `[U4]`, `[U5]`, `[U7]` không chấm; `[U8]` chỉ cần README ngắn.
> - Vòng lặp frontend tối đa **1 vòng sửa**.

Chia hai phần việc độc lập: **A. Backend** (làm SAU khi vòng chấm GĐ7 xong, để không làm lệch kết quả chấm) và **B. Frontend** (làm ngay, thư mục riêng, phát triển trên mock theo hợp đồng ở mục 1).

## 1. Hợp đồng API (frontend bám đúng; backend cài đúng)

```text
POST /api/v1/recommend/chat      body  { mode: "recommendation", conversation_id?: str, message: str, as_of?: date }
                                  200   ChatTurnResult (mục dưới)         422 nếu mode khác "recommendation"
POST /api/v1/recommend/reset     body  { conversation_id: str }  ->  { conversation_id }  (xóa state; giữ mode)
GET  /api/v1/recommend/map       query ids=<listing_id,...>&radius_m=2000&poi_types=truong_hoc,benh_vien,cho
                                  200   GeoJSON FeatureCollection (mục dưới)
GET  /health                      200
```

`ChatTurnResult` = hiện có (`conversation_id, status, constraints, listings[≤5], referenced_ids, relax_options, degraded, answer`) **cộng**:
- `summary: str` — câu trả lời **không gồm khối từng tin** (điều kiện đang áp, số tin, thay đổi…); UI dùng `summary` ở bong bóng chat và vẽ tin bằng thẻ. `answer` giữ nguyên (đầy đủ, cho API khác/test).
- `ListingHit` thêm: `latitude: float|None`, `longitude: float|None`, `coords_reliable: bool` (False khi tin có cờ `coords_outside_hcm` hoặc thiếu tọa độ), `position: int` (1..5, khớp "căn thứ N" và số trên bản đồ), `days_left: int|None` (= `expired_at − as_of`).

`/map` trả GeoJSON:
- Feature `Point` cho mỗi tin có tọa độ: `properties = {kind: "listing", position, listing_id, title, price, area, reliable}`.
- Feature `Point` cho POI trong `radius_m` quanh các tin (tối đa 6 POI mỗi loại mỗi tin, tối đa 40 POI toàn bộ, sắp theo khoảng cách): `properties = {kind: "poi", poi_type, name, distance_m, near_listing_id}`.
- Tin không có tọa độ không có feature; response kèm `properties.missing_ids` ở cấp FeatureCollection (`{"type":"FeatureCollection","features":[...],"missing_ids":[...]}`).

## 2. Phần A — Backend (`db-coder`, sau khi vòng chấm GĐ7 xong)

1. `ChatRequest.mode: Literal["recommendation"]` bắt buộc ⇒ Mode Controller đúng đề cương §5.10 (client chọn mode, backend không đoán); sai ⇒ 422.
2. CORS cho `http://localhost:5173` và `http://127.0.0.1:5173` (danh sách nguồn lấy từ biến môi trường `CORS_ORIGINS`, mặc định hai nguồn trên).
3. Các trường mới ở mục 1; `summary` do code dựng (tách khối tin khỏi phần mở đầu trong `AnswerWriter.results`, không đổi `answer`).
4. `RelaxOption` thêm `message: str` — câu **sẵn sàng gửi lại** làm tin nhắn tiếp theo (vd. "tăng ngân sách lên 3,6 tỷ", "bỏ điều kiện gần bệnh viện", "mở rộng ra toàn TP.HCM"); frontend dùng thẳng `message`, không cắt chuỗi `description` (cách hiện tại mong manh). Mỗi `message` phải được `TurnInterpreter` hiểu đúng (có unit test/`--extra`: gửi `message` ⇒ `ok` với điều kiện đã nới).
5. `/reset` và `/map` trong file riêng `app/services/map.py` + route; **không làm tăng** `app/services/recommendation/` quá trần 1.900 dòng.
6. Unit test không OpenAI cho `/map` (DB `housing_dev`), CORS (preflight), mode sai ⇒ 422, `reset`, các trường mới. `uvx ruff check` sạch (E501 bật).

## 3. Phần B — Frontend (`housing-frontend/`, thư mục gốc dự án, ngang `housing-backend/`)

Công nghệ (tối thiểu, đúng đề cương): **React 18 + TypeScript (strict) + Vite**, **Leaflet** (`react-leaflet`), CSS thuần (không UI framework), test **Vitest + React Testing Library**. Không thêm thư viện khác nếu không bắt buộc (không Redux, không Tailwind).

Bố cục (§5.11): trái = khung chat, phải = bản đồ; điện thoại: bản đồ xuống dưới.
1. **Khung chat:** danh sách bong bóng (người dùng / trợ lý), ô nhập (Enter gửi, Shift+Enter xuống dòng), trạng thái "đang tìm…", nút **"Tìm lại từ đầu"** (gọi `/reset`), gợi ý nhập nhanh (chip) mẫu: "Căn hộ Quận 7 dưới 3 tỷ", "Nhà riêng Gò Vấp tầm 5 tỷ", "Gần bệnh viện dưới 2km".
2. **Bộ chọn mode:** hiển thị một mode duy nhất "Gợi ý bất động sản" (cố định `recommendation`); gửi `mode` trong mọi request.
3. **Thẻ Top 5** dưới tin nhắn trợ lý khi `listings` không rỗng: huy hiệu số 1–5 (= `position`), tiêu đề, giá (định dạng "2,65 tỷ" / "900 triệu"), diện tích, loại, số phòng ngủ, địa chỉ cũ (và "mới: …" nhỏ hơn), khoảng cách POI gần nhất (trường/bệnh viện/chợ, định dạng "166 m" / "1,6 km"), "Đăng dd/mm/yyyy", liên kết **"Xem tin gốc"** (mở tab mới, `rel="noopener noreferrer"`). Bấm thẻ ⇒ bản đồ bay tới marker và mở popup.
4. **Cảnh báo (§5.11):** nhãn "Sắp hết hạn (còn N ngày)" khi `days_left ≤ 3`, "Tin đã hết hạn" khi `< 0`, "Tọa độ chưa đáng tin" khi `coords_reliable = false`; banner "Kết quả chưa xếp theo ngữ nghĩa (dịch vụ embedding đang tắt)" khi `degraded`.
5. **Trạng thái đặc biệt:** `need_clarification` ⇒ bong bóng nhấn nhẹ + focus ô nhập; `no_results` ⇒ mỗi `relax_options` là nút bấm gửi tin nhắn tương ứng ("Nếu tăng ngân sách lên 3,6 tỷ: có 1 tin" ⇒ gửi "tăng ngân sách lên 3,6 tỷ"); `out_of_scope` ⇒ bong bóng thường.
6. **Bản đồ:** Leaflet; marker tin **đánh số 1–5**; marker POI khác màu theo loại (trường học / bệnh viện / chợ) + chú giải; tự `fitBounds`; chỉ vẽ tin có tọa độ; tải `/map` sau mỗi lượt có `listings`. Tile: Goong nếu có `VITE_GOONG_MAPTILES_KEY`, không thì OpenStreetMap (ghi rõ trong README). **Không** nhúng `GOONG_API_KEY` của `.env` backend.
7. **Cấu hình:** `VITE_API_BASE` (mặc định `/api` qua proxy dev tới `http://localhost:8000`); `conversation_id` lưu `sessionStorage` (bọc try/catch).
8. **Mock:** `npm run mock` chạy một server giả (Node thuần, không thêm thư viện) trả đúng hợp đồng mục 1 với 5 tin mẫu để phát triển/test không cần backend.
9. **Cấu trúc code** (dễ đọc, không rườm rà): `src/api.ts` (gọi API + kiểu), `src/format.ts` (giá, ngày, khoảng cách, cảnh báo — thuần túy, có test), `src/components/{ChatPanel,MessageBubble,ListingCard,MapView}.tsx`, `src/App.tsx`. Hook gom state hội thoại (`useChat`). Không file nào > 200 dòng; không `any`; không `// @ts-ignore`.
10. **Chuẩn code (để reviewer chấm có trích nguồn):** React Docs https://react.dev/learn (rules of hooks, keys, controlled inputs); Google TypeScript Style Guide https://google.github.io/styleguide/tsguide.html; Airbnb React/JSX Style Guide https://github.com/airbnb/javascript/tree/master/react.

## 4. Tiêu chí nghiệm thu

| Mã | Tiêu chí |
|---|---|
| `[U1]` | `npm run build` (gồm `tsc --noEmit`) và `npm test` xanh; `npm audit --omit=dev` không có lỗ hổng mức cao/nghiêm trọng (nếu có, nêu rõ) |
| `[U2]` | Chạy với mock: gửi tin ⇒ thấy bong bóng, 5 thẻ, 5 marker đánh số 1–5 đúng thứ tự, POI có màu; bấm thẻ ⇒ bản đồ bay tới marker; "Tìm lại từ đầu" ⇒ xóa hội thoại và gọi `/reset`. Kiểm bằng E2E tự động (Playwright nếu cài được, nếu không thì RTL + chụp ảnh qua trình duyệt headless; nêu rõ phương pháp) |
| `[U3]` | Chạy với backend thật (`housing_dev`, Kaggle bật): cuộc hội thoại 5 lượt "Mình muốn mua nhà…" → hỏi lại → có Top 5 → "so sánh căn 1 và 3" → "tìm lại từ đầu" chạy đúng, không lỗi console, không lỗi CORS |
| `[U4]` | Cảnh báo hiển thị đúng: hết hạn / sắp hết hạn / tọa độ không đáng tin / degraded (test từng ca với dữ liệu mock) |
| `[U5]` | `relax_options` bấm được và gửi đúng tin nhắn; `need_clarification` focus ô nhập |
| `[U6]` | Mode sai ⇒ 422; CORS preflight OK; `/map` đúng GeoJSON, tin thiếu tọa độ nằm trong `missing_ids` |
| `[U7]` | Khả năng tiếp cận tối thiểu: nhãn cho ô nhập/nút, điều hướng bàn phím gửi được, tương phản chữ ≥ 4,5:1; bố cục không vỡ ở 360 px |
| `[U8]` | Code sạch theo mục 3.9–3.10; không dependency thừa; không key/secret trong repo front-end; `README.md` ở `housing-frontend/` (cách chạy mock, backend thật, biến môi trường) |
| `[U9]` | Backend: unit test mới xanh, `uvx ruff check` sạch, `app/services/recommendation/` ≤ 1.900 dòng |

## 5. Vòng lặp

`db-coder` (frontend, ngay) → `db-reviewer` nghiệm thu `[U1]–[U8]` bằng chạy thật → sửa. Backend (A) làm sau khi GĐ7 xong → reviewer chấm `[U6]`, `[U9]`, rồi ghép frontend với backend thật chấm `[U3]`. Tối đa 3 vòng; main duyệt cuối và đóng vai khách hàng trên giao diện thật.
