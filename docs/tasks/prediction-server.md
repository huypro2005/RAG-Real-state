# Prediction Server (FastAPI) — dự đoán giá, nạp dữ liệu thô, tự retrain, tự chọn mô hình

Dịch vụ độc lập với backend chatbot, **dùng chung một PostgreSQL** (mặc định `housing_dev`; không
ghi vào `housing` thật). Backend chatbot chỉ cần gọi HTTP tới server này khi muốn dự đoán giá.

```text
batdongsan crawl ──POST /api/v1/ingest──► Prediction Server ──► DB dùng chung (listings, pois, price_model_runs)
                                              │  làm sạch → nạp listings → FK địa chỉ → POI
                                              │  đủ dữ liệu mới → retrain nền → chọn mô hình tốt nhất → kích hoạt
Backend chatbot ──POST /api/v1/predict───────►┘  (model nạp nóng, không restart)
```

## 1. Phạm vi và vị trí code

- Code ở `src/prediction_server/` (package Python; chạy từ thư mục gốc dự án bằng `.venv` gốc):
  `python -m uvicorn src.prediction_server.main:app --port 8100`.
- **Tái dùng**, không chép: `src/pipeline` (`ListingCleaner`, `ListingLoader`), logic dựng bảng huấn luyện
  ở `src/notebook/predictionEDA/db_to_training/build_training_csv.py` (chuyển vào/ import được từ package
  mới, giữ nguyên mã loại nhà/quận/pháp lý), đếm POI ở `src/web/housing-backend/app/services/prediction/schools.py`
  hoặc `src/notebook/predictionEDA/pipeline.py` — chọn một nguồn, không nhân bản logic.
- Không đổi hành vi của `src/pipeline` CLI và backend hiện có (test cũ vẫn xanh). Backend chỉ **thêm** client
  gọi server (mục 7); mô hình cục bộ giữ làm dự phòng.
- Phạm vi địa lý: TP.HCM cũ. Không lưu `raw_record`/hash/tên file nguồn trong DB (AGENTS.md mục 5).
- Một class gọn cho mỗi trách nhiệm, comment/docstring tiếng Việt, theo phong cách code quanh đó.

## 2. Database dùng chung

Cấu trúc DB chỉ có một nguồn chuẩn là model SQLAlchemy + migration Alembic của backend. Vì vậy:

- Thêm model `PriceModelRun` trong `src/web/housing-backend/app/db/models/` và migration **0005**
  (`alembic revision --rev-id 0005`), bảng `price_model_runs` ở schema `public`:

| Cột | Ý nghĩa |
|---|---|
| `id` | khóa thay thế tự tăng (quy ước migration 0004) |
| `created_at`, `finished_at` | thời điểm |
| `trigger` | `ingest` / `manual` / `schedule` / `bootstrap` |
| `status` | `running` / `succeeded` / `failed` / `skipped` |
| `train_rows`, `test_rows` | số dòng |
| `listings_snapshot` | số tin lúc train (để biết "dữ liệu mới" so với lần train trước) |
| `best_candidate` | tên ứng viên thắng (vd. `extra_trees+school`) |
| `metrics` | jsonb: R², R² log, MAE, MAPE, CV mean/std của ứng viên thắng |
| `candidates` | jsonb: bảng kết quả mọi ứng viên (để so sánh, không lưu model) |
| `artifact_path` | đường dẫn file `.joblib` (ngoài DB) |
| `is_active` | đúng một dòng `true` (partial unique index) |
| `error` | thông báo lỗi nếu `failed` |

- Server **không tự tạo bảng**: thiếu `price_model_runs` thì `/health` báo `db_schema_missing` rõ ràng.
- Dùng khóa tư vấn Postgres (`pg_try_advisory_lock`) để chỉ một tiến trình retrain chạy tại một thời điểm,
  kể cả khi chạy nhiều worker.

## 3. API (prefix `/api/v1`, header `X-API-Key` cho mọi đường ghi/ngoại trừ `/health`)

| Method + đường | Việc |
|---|---|
| `GET /health` | trạng thái DB, model đang hoạt động (id, ứng viên, R², thời điểm train), job đang chạy, `db_schema_missing` |
| `POST /predict` | một tin hoặc `items: [...]` (≤ 100): `property_code`, `district_code`, `area`, `latitude`, `longitude`, tùy chọn `frontage`, `bedrooms`, `floors`. Trả `price_per_m2`, `total_price`, khoảng tham khảo thấp/cao, `distance_to_center_km`, `schools_1km/3km`, `model_run_id`, `warnings`. Cùng ngữ nghĩa đầu vào/ra và biên hợp lệ như `PriceInput`/`PriceEstimate` ở backend; 422 khi sai đầu vào, 503 khi chưa có model |
| `POST /ingest` | nhận dữ liệu thô: body JSON `{records: [ {...tin crawl...}, ... ]}` (≤ 5.000 bản ghi/lần) **hoặc** upload file JSON Lines (`multipart`). Chạy nền pipeline: làm sạch → nạp `listings` (upsert, idempotent) → FK địa chỉ → POI. Trả `202 {job_id}` ngay. Định dạng bản ghi giống `src/crawl/crawlProperties/data.json` |
| `GET /jobs/{job_id}` | trạng thái + số liệu từng bước (dòng vào/ra, sạch, loại, inserted/updated/unchanged), lý do loại |
| `POST /retrain` | ép retrain ngay (nền), `202 {job_id}`; bỏ qua nếu đang có job retrain |
| `GET /models` | lịch sử `price_model_runs` (mới nhất trước), kèm bảng ứng viên |
| `POST /models/{id}/activate` | đặt lại model cũ làm model hoạt động (rollback), kiểm file còn tồn tại |

Job chạy nền trong tiến trình (thread/executor), trạng thái job lưu trong bộ nhớ + `price_model_runs` cho retrain;
mất job đang chạy khi server restart là chấp nhận được nhưng `running` mồ côi phải được dọn khi khởi động.

## 4. Pipeline nạp dữ liệu (`ingest`)

- Dùng lại `ListingCleaner.clean(...)` (nhận records trong bộ nhớ, không bắt buộc ghi file) và `ListingLoader`.
  Nếu API hiện chỉ nhận đường dẫn file thì ghi tạm vào thư mục tạm của server rồi xóa; không lưu file thô lâu dài.
- Idempotent: gửi lại cùng dữ liệu cho `inserted=0, updated=0, unchanged=N`, không nhân đôi.
- Kết quả job gồm đủ số liệu để đối chiếu với `python -m src.pipeline` (cùng input cho cùng số dòng sạch).
- Embedding **không** thuộc server này (chạy trên Kaggle qua `src.pipeline --embed-only`); server không gọi API ngoài.

## 5. Retrain tự động

- Sau mỗi job `ingest` thành công, và theo lịch (mặc định mỗi 6 giờ, cấu hình được), kiểm tra điều kiện:
  số tin `listings` hiện tại − `listings_snapshot` của lần train thành công gần nhất ≥ `RETRAIN_MIN_NEW`
  (mặc định 200 **hoặc** ≥ 5% tổng), hoặc chưa có model nào (`bootstrap`). Không đủ thì ghi `skipped`.
- Dựng bảng huấn luyện từ `listings` (cùng mã hóa như `build_training_csv.py`), đếm POI trường học 1 km/3 km,
  tách train/test cố định (`StratifiedShuffleSplit` theo khoảng cách trung tâm, `random_state=42`, test 20%),
  lọc ngoại lai **chỉ trên train**, điền median **chỉ từ train**, mục tiêu `log(giá/m²)`.
- Không rò rỉ: mọi thống kê (median, mã hóa) tính trên train; test không dùng để fit.

## 6. Tự chọn mô hình tốt nhất

- Tập ứng viên cấu hình được (mặc định): ExtraTrees, RandomForest, HistGradientBoosting, và XGBoost/LightGBM
  nếu đã cài, mỗi cái với bộ đặc trưng `base` (9 cột) và `base+trường 1km/3km` (11 cột).
- Chấm mỗi ứng viên bằng CV 5-fold trên train (R² log, mean/std) **và** R² log/MAE/MAPE trên test.
  Chọn theo **CV R² mean**; test chỉ để kiểm chứng và báo cáo. Hòa (chênh < 1 độ lệch chuẩn CV) thì chọn
  mô hình đơn giản/nhỏ hơn (ưu tiên ExtraTrees/RF vì còn khoảng tham khảo theo từng cây).
- Chỉ **kích hoạt** model mới khi: tốt hơn model đang hoạt động trên **cùng test split mới** (đo lại model cũ trên
  test mới) hoặc hơn ít nhất `PROMOTE_MIN_GAIN` (mặc định 0,002 R² log), và không tệ hơn quá `PROMOTE_MAX_REGRESSION`
  về MAE. Ngược lại giữ model cũ, ghi `candidates` kèm lý do `not_promoted`.
- Model được ghi file `models/price_run_<id>.joblib` (thư mục cấu hình, không commit), ghi atomically (tệp tạm
  rồi rename), giữ tối đa `KEEP_ARTIFACTS` (mặc định 5) bản gần nhất + bản đang hoạt động.
- Model phải hỗ trợ khoảng tham khảo như backend hiện tại (phân vị theo cây) hoặc trả `price_per_m2_low/high`
  bằng cách khác có ghi chú; nếu thắng là mô hình không có cây, server trả khoảng dựa trên sai số test (ghi rõ nguồn).
- Nạp nóng: kích hoạt xong, `/predict` dùng model mới ở request kế tiếp, không restart; request đang chạy không
  bị lỗi (hoán đổi tham chiếu nguyên tử).
- Giữ RAM thấp: không giữ cả loạt pipeline đã fit (chỉ giữ ứng viên thắng), `n_jobs ≤ 4`.

## 7. Backend gọi server

- Thêm vào backend (`app/core/config.py`): `PREDICTION_SERVER_URL` (mặc định trống), `PREDICTION_SERVER_API_KEY`,
  timeout ngắn (3 s). Thêm một client gọn (httpx) và nối vào `PricePredictor`/`deps.py` sao cho:
  nếu có URL thì gọi `/predict`; lỗi/timeout/503 thì **rơi về mô hình cục bộ** (nếu có) kèm cảnh báo. Không đổi
  schema `PriceEstimate` hiện có (thêm trường tùy chọn `model_run_id` được).
- Test backend hiện có vẫn xanh (không cần server chạy).

## 8. Cấu hình (`.env` gốc, thêm vào mẫu trong README)

`DATABASE_URL`, `PREDICTION_SERVER_API_KEY`, `MODELS_DIR`, `RETRAIN_MIN_NEW`, `RETRAIN_MIN_RATIO`,
`RETRAIN_INTERVAL_HOURS`, `PROMOTE_MIN_GAIN`, `PROMOTE_MAX_REGRESSION`, `KEEP_ARTIFACTS`. Mặc định hợp lý; không
hard-code mật khẩu; SecretStr cho khóa.

## 9. Tiêu chí nghiệm thu

Chạy thử trên **`housing_dev`** (hoặc DB tạm do reviewer tạo/xóa), `.venv` gốc, `PYTHONIOENCODING=utf-8`.

| Mã | Tiêu chí |
|---|---|
| P1 | Migration 0005 `alembic upgrade head` rồi `alembic check` báo không còn thay đổi; có partial unique index chỉ một `is_active = true` |
| P2 | `/health` hoạt động khi thiếu model (báo rõ) và khi thiếu bảng (`db_schema_missing`), không sập |
| P3 | `/predict` trả giá hợp lý cho ≥ 5 ca (căn hộ Bình Thạnh, nhà riêng Quận 7, đất Củ Chi...), cùng biên hợp lệ với backend; 422 khi sai quận/loại/diện tích/tọa độ ngoài TP.HCM; 503 khi chưa có model |
| P4 | `/predict` với `items` nhiều tin cho kết quả giống từng tin riêng lẻ |
| P5 | `/ingest` với `data.json` mẫu (≥ 500 bản ghi) trả 202; job xong với số liệu khớp `python -m src.pipeline` trên cùng input (clean, rejected) |
| P6 | Gửi lại cùng dữ liệu: `inserted=0, updated=0`, số dòng `listings` không đổi |
| P7 | Bản ghi hỏng/thiếu giá-diện tích bị loại có lý do, không làm hỏng cả job; không lưu `raw_record` |
| P8 | Khi chưa có model, `bootstrap` retrain chạy, tạo `price_model_runs`, kích hoạt đúng một model; `/predict` dùng được ngay không restart |
| P9 | Nạp thêm ≥ `RETRAIN_MIN_NEW` tin mới → retrain tự chạy; nạp ít hơn ngưỡng → `skipped` kèm lý do |
| P10 | Retrain chỉ kích hoạt model mới khi thỏa quy tắc mục 6; trường hợp không tốt hơn giữ model cũ và ghi `not_promoted` |
| P11 | Không rò rỉ: kiểm bằng test rằng median/mã hóa chỉ dùng dữ liệu train (vd. đổi nhãn test không đổi model) |
| P12 | Hai lệnh `/retrain` đồng thời chỉ chạy một job (advisory lock); job còn `running` mồ côi sau restart được dọn |
| P13 | `POST /models/{id}/activate` rollback được và `/predict` dùng lại model cũ ngay |
| P14 | Backend có `PREDICTION_SERVER_URL` gọi được server; tắt server thì rơi về model cục bộ với cảnh báo; test backend hiện có xanh |
| P15 | Sai/thiếu `X-API-Key` → 401 ở các đường ghi; `/health` không cần khóa |
| P16 | Test tự động trong `src/prediction_server/tests/` (không gọi dịch vụ ngoài; dùng DB `housing_dev` hoặc fake có đánh dấu), `ruff` sạch cho mọi file mới/sửa |
| P17 | RAM của server sau một vòng retrain không phình (không giữ ≥ 2 mô hình lớn trong bộ nhớ ngoài model đang phục vụ), `n_jobs ≤ 4`, không để worker treo |
| P18 | Có mục hướng dẫn chạy trong README.md gốc (mục 7 mới: prediction server) và mô tả ngắn trong `docs/chatbot.md` hoặc `docs/architecture.md` |

## 10. Ngoài phạm vi

- Không làm embedding, không chạy crawler, không tự gọi Goong/OpenAI trong server này.
- Không làm giao diện; không triển khai Docker (có thể thêm sau).
- Không commit.
