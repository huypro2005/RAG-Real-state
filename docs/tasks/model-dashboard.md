# Dashboard mô hình giá — lưu biểu đồ theo phiên bản, hiển thị trên frontend

Mỗi lần train mô hình (mỗi dòng `price_model_runs`), Prediction Server lưu kèm **dữ liệu biểu đồ** của
phiên bản đó để frontend vẽ dashboard và so sánh giữa các phiên bản. Backend chatbot làm cầu nối
(frontend chỉ gọi backend, không gọi thẳng Prediction Server, không có khóa API ở trình duyệt).

```text
Prediction Server ──(train)──► price_model_runs.charts (jsonb, theo phiên bản)
        ▲ GET /api/v1/models[/{id}|/active]/charts
Backend chatbot  ── GET /api/v1/dashboard/models[/{id}] (proxy, giữ khóa API)
        ▲
Frontend ── tab "Dashboard": phân bố giá, scatter thực tế vs dự đoán, độ quan trọng đặc trưng, so sánh phiên bản
```

## 1. Dữ liệu biểu đồ lưu cùng mỗi phiên bản (`charts`, jsonb)

Tính **chỉ trên tập test cố định** của phiên bản đó (không dùng train cho scatter/độ quan trọng) và trên
bảng huấn luyện cho phân bố giá. Kích thước ≤ ~200 KB mỗi phiên bản.

```jsonc
{
  "schema_version": 1,
  "price_distribution": {            // giá/m² (triệu), toàn bộ bảng huấn luyện sau lọc
    "unit": "triệu/m²",
    "bins": [{"x0": 0, "x1": 20, "count": 311}, ...],      // 30–40 bin, trục giá cắt ở p99 (ghi `clipped_above`)
    "clipped_above": 12,                                    // số tin vượt p99 bị gộp/bỏ khỏi histogram
    "stats": {"n": 5198, "mean": 0, "median": 0, "p10": 0, "p90": 0},
    "by_type": {"0": {"label": "Căn hộ chung cư", "median": 0, "p10": 0, "p90": 0, "n": 0}, ...}
  },
  "scatter": {                       // thực tế vs dự đoán trên test (giá/m², triệu)
    "points": [{"actual": 0, "predicted": 0, "type": 0, "district": 3}, ...],  // ≤ 800 điểm, lấy mẫu có seed cố định
    "n_test": 1102, "r2_log": 0.8, "mae": 0, "mape": 0, "residual_q90_log": 0
  },
  "feature_importance": {            // permutation importance trên test, n_repeats=5, tính trên R² log
    "method": "permutation_r2_log",
    "items": [{"feature": "loại nhà đất", "importance": 0.43, "std": 0.01}, ...]   // sắp giảm dần, tên cột tiếng Việt như FEATURES
  },
  "district_type_median": [          // giá/m² trung vị theo quận × loại nhà trên bảng huấn luyện (nhóm có n >= 5)
    {"district": 3, "district_name": "Bình Thạnh", "property_type": 0, "label": "Căn hộ chung cư", "median": 0, "n": 0}, ...
  ],
  "geo_scatter": {                   // khóa tùy chọn (frontend cũ bỏ qua được): tin trên bản đồ, x = kinh độ, y = vĩ độ, màu = giá/m², cỡ = diện tích
    "points": [{"lat": 10.7942, "lon": 106.7346, "price_per_m2": 231.4, "area": 105.0, "type": 4}, ...],  // ≤ 1.200 điểm, mẫu phân tầng theo loại nhà, seed cố định, từ cả bảng huấn luyện; lat/lon 4 chữ số, giá/diện tích 1 chữ số
    "n_total": 5206,
    "bounds": {"lat": [0, 0], "lon": [0, 0]},               // p1–p99 của điểm trong mẫu
    "price_clip": {"p5": 0, "p95": 0},                      // ngưỡng cắt thang màu
    "center": {"name": "Nhà thờ Đức Bà", "lat": 10.7769, "lon": 106.7009}
  },
  "candidates": [{"name": "extra_trees", "cv_r2": 0.84, "cv_std": 0.01, "test_r2_log": 0.83, "mae": 31.6, "chosen": true}, ...]
}
```

- Không rò rỉ: dữ liệu test chỉ dùng để đo/vẽ, không dùng để fit.
- Phiên bản cũ chưa có `charts`: có thao tác dựng lại (`POST /api/v1/models/{id}/charts/rebuild`, cần khóa API,
  dựng từ artifact + dữ liệu hiện tại; nếu không dựng chính xác được vì tập test đã đổi thì ghi `approximate: true`).
  Khi khởi động, nếu phiên bản đang hoạt động thiếu `charts` thì tự dựng nền.

## 2. API

**Prediction Server** (cần `X-API-Key`):

| Đường | Việc |
|---|---|
| `GET /api/v1/models` | giữ nguyên + mỗi dòng có `has_charts` và tóm tắt metric, **không** nhúng cả `charts` |
| `GET /api/v1/models/{id}/charts` | `charts` của phiên bản; 404 nếu không có; `GET /api/v1/models/active/charts` cho bản đang chạy |
| `POST /api/v1/models/{id}/charts/rebuild` | dựng lại nền (202) |

**Backend chatbot** (không cần khóa ở frontend, CORS như hiện tại; server tắt/chưa cấu hình → 503 với thông điệp rõ):

| Đường | Việc |
|---|---|
| `GET /api/v1/dashboard/models` | danh sách phiên bản: `id`, `created_at`, `trigger`, `status`, `is_active`, `best_candidate`, `train_rows`, `test_rows`, `metrics` (R² log, MAE, MAPE), `has_charts` |
| `GET /api/v1/dashboard/models/{id}` | `charts` đầy đủ của phiên bản + thông tin phiên bản (id `active` = bản đang chạy) |

Backend chỉ proxy và validate (Pydantic), không tính lại. Có test (MockTransport) không cần server chạy.

## 3. Giao diện (frontend, React + TypeScript + Vite, không thêm thư viện biểu đồ nặng — vẽ bằng SVG/HTML)

- Thêm điều hướng cấp cao: **Chat** (như hiện tại: chat + bản đồ) và **Dashboard mô hình**. Giữ hành vi và test hiện có.
- Dashboard gồm: dải KPI (R² log, MAE, MAPE, số dòng train/test, ứng viên thắng, thời điểm train, trạng thái active),
  chọn phiên bản (+ so sánh hai phiên bản: bảng Δ metric), histogram phân bố giá (có median/p10/p90, chuyển theo loại nhà), so sánh giá trung vị theo quận × loại nhà (`district_type_median`), biểu đồ xu hướng metric qua các phiên bản (R² log, MAE từ danh sách phiên bản) và bảng lịch sử phiên bản có huy hiệu trạng thái (succeeded/running/failed/skipped/active),
  scatter thực tế vs dự đoán (đường y = x, tô đậm theo loại nhà với thứ tự màu cố định, tooltip, ẩn/hiện theo loại),
  thanh ngang độ quan trọng đặc trưng (sắp giảm dần, một màu, nhãn trực tiếp), bảng ứng viên (CV R², test R²).
- Có trạng thái rỗng/đang tải/lỗi rõ (server mô hình tắt, chưa có phiên bản, phiên bản thiếu charts).
- Cải thiện giao diện toàn app: hệ thiết kế nhất quán (token màu/khoảng cách/chữ trong `:root`, light + dark theo
  `prefers-color-scheme`), bố cục responsive tới 360 px, focus/hover/bàn phím, `prefers-reduced-motion`, tiếng Việt
  tự nhiên, độ tương phản đạt WCAG AA. Biểu đồ theo skill **dataviz** (xem dưới).
- Dùng skill `dataviz` đã cài (file ở `C:\Users\huypro37\AppData\Local\Temp\claude\bundled-skills\2.1.314\ec12546832170c54cefccb8e5ea96fff\dataviz\`):
  đọc `references/choosing-a-form.md`, `color-formula.md`, `marks-and-anatomy.md`, `interaction.md`, `components.md`,
  `anti-patterns.md`, `palette.md`; chạy `node scripts/validate_palette.js "<hex,...>" --mode light|dark` cho mọi bảng màu
  dùng (thay palette mặc định bằng của dự án nếu đổi màu chủ đạo), tooltip/hover mặc định, bảng dữ liệu thay thế cho
  từng biểu đồ, không dùng dual-axis, không cầu vồng, legend khi ≥ 2 series.

## 4. Tiêu chí nghiệm thu

| Mã | Tiêu chí |
|---|---|
| D1 | Migration 0006 thêm cột `charts` jsonb vào `price_model_runs`; `alembic check` sạch |
| D2 | Mỗi lần train thành công (bootstrap/ingest/manual) lưu `charts` đúng schema mục 1, ≤ 200 KB; dựng trên test cố định, không rò rỉ |
| D3 | `GET /models/{id}/charts`, `/models/active/charts`, `rebuild` hoạt động, cần khóa API; 404 khi không có |
| D4 | Phiên bản hiện có trong `housing_dev` được dựng `charts` (qua rebuild hoặc tự dựng khi khởi động) |
| D5 | Backend `/api/v1/dashboard/models[/{id}]` proxy đúng, 503 rõ khi server tắt; test không cần server |
| D6 | Frontend: tab Dashboard hiển thị đủ KPI + 3 biểu đồ + bảng ứng viên + chọn/so sánh phiên bản với dữ liệu thật |
| D7 | Trạng thái rỗng/tải/lỗi đúng; responsive 360 px không cuộn ngang; dark mode đúng; bàn phím/focus dùng được |
| D8 | Biểu đồ theo dataviz: validator palette PASS (light và dark), tooltip, bảng thay thế, không anti-pattern |
| D9 | `npm run build` (tsc strict) và `npm test` xanh; test backend/server hiện có vẫn xanh; ruff sạch |
| D10 | Chạy thật cả ba: Prediction Server + backend + frontend; chụp ảnh màn hình dashboard (light/dark, desktop/mobile) để xác nhận bố cục |

## 5. Ngoài phạm vi

Không đổi thuật toán chọn mô hình; không thêm đăng nhập; không commit.
