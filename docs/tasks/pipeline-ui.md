# Giao diện nạp dữ liệu cho pipeline (Pipeline UI)

Một trang web để **kéo thả file JSON crawl → pipeline tự chạy → dữ liệu vào DB**, mỗi bước hiện bằng một
**bánh răng**: xám (chờ/bỏ qua), quay (đang chạy), **xanh** (xong), đỏ (lỗi, kèm lý do).

## Quyết định đã chốt với người dùng

| Mục | Quyết định |
|---|---|
| Nơi chạy | Server FastAPI nhỏ, riêng cho pipeline, trong `src/pipeline/` (cổng **8200**), tự phục vụ trang HTML. Không đụng backend chatbot, frontend React, Prediction Server |
| Cấu hình | Bật/tắt từng bước; chế độ **chạy thử** (chỉ làm sạch, không ghi DB); **chọn DB đích**; **retrain mô hình giá** sau khi nạp |
| Embedding | Có ô bật, **mặc định tắt**. Bật thì kiểm tra server Kaggle trước; server tắt thì bánh răng đỏ kèm lý do, các bước trước giữ kết quả |
| DB đích | Danh sách cố định: các DB trên Postgres của `DATABASE_URL` (container `housing-postgres`, cổng 5433) **có bảng `listings`**, mặc định `housing_dev`. **Chặn `housing`** (DB cũ, chỉ đọc), cả ở server chứ không chỉ ở giao diện. Không có ô nhập URL tự do |
| Nhiều file | Kéo thả nhiều file một lần; gộp và bỏ trùng như `--input a.json b.json` |
| Lịch sử | Lưu **file trên máy**: mỗi lần chạy một thư mục `output/pipeline_runs/<run_id>/` (cấu hình, số liệu từng bước, báo cáo làm sạch). Không migration DB, không commit (thêm vào `.gitignore`) |
| Báo cáo | Nút tải `cleaning_report.json` và `listings_rejected.jsonl` của từng lần chạy |

## Các bước (bánh răng)

| # | Bước | Code dùng lại | Phụ thuộc |
|---|---|---|---|
| 1 | Làm sạch | `ListingCleaner` | luôn chạy |
| 2 | Nạp `listings` (upsert) | `ListingLoader.upsert` | 1 |
| 3 | Gắn địa chỉ (FK) | `ListingLoader.link_addresses` | 2 |
| 4 | Tiện ích quanh nhà (POI) | `ListingLoader.refresh_spatial` | 2 |
| 5 | Embedding (Kaggle) | `ListingEmbedder` | 2, mặc định tắt |
| 6 | Retrain mô hình giá | gọi `POST {PREDICTION_SERVER_URL}/api/v1/retrain` với `X-API-Key` | 2, mặc định tắt |

- **Chạy thử** = chỉ bước 1, không mở kết nối ghi DB; các bánh răng còn lại hiện "bỏ qua".
- Tắt bước 2 thì 3–6 tự khóa (không có gì mới để xử lý). Bước 3, 4 cho bật/tắt độc lập.
- Bước 6: thiếu `PREDICTION_SERVER_URL`/`PREDICTION_SERVER_API_KEY` trong `src/pipeline/.env`, hoặc server không phản hồi
  (Prediction Server hiện có thể bị Smart App Control chặn) → bánh răng đỏ kèm lý do rõ, không làm hỏng các bước trước.
  Ghi rõ retrain chạy nền ở Prediction Server: bánh răng xanh nghĩa là **đã gửi yêu cầu thành công** (hiện `job_id`), kèm
  link/ghi chú xem kết quả.
- Mỗi bánh răng hiện số liệu thật của bước (vd. `input_lines`, `clean`, `rejected`, `inserted/updated/unchanged`,
  `old_district_id`..., `refreshed`, `embedded`), y như CLI `python -m src.pipeline` in ra.

## Yêu cầu kỹ thuật

- **Một nguồn logic:** dùng lại `ListingCleaner`, `ListingLoader`, `ListingEmbedder`; không chép logic. Nếu cần, tách nhẹ
  `ListingPipeline` để cả CLI và server gọi chung, **CLI giữ nguyên hành vi** và test `src/tests` vẫn xanh.
- Server: `python -m src.pipeline.server` (hoặc `uvicorn src.pipeline.server:app --port 8200`) tại thư mục gốc, đọc
  `src/pipeline/.env`. Thêm vào `.env.example`: `PREDICTION_SERVER_URL`, `PREDICTION_SERVER_API_KEY` (tùy chọn).
- Chỉ lắng nghe `127.0.0.1`, không khóa truy cập (người dùng không chọn khóa).
- Upload: chỉ nhận `.json`/`.jsonl` (JSON Lines, như `data.json` crawl), giới hạn dung lượng hợp lý (vd. 100 MB tổng, cấu hình
  được), đọc theo khối; tên file không được dùng làm đường dẫn ghi (chống path traversal). File tải lên lưu tạm trong thư mục
  lần chạy và **xóa sau khi xong** (không giữ dữ liệu thô lâu dài), chỉ giữ tên file trong lịch sử.
- Chạy nền một job mỗi lúc (job thứ hai khi đang chạy → báo "đang bận"); trang cập nhật tiến độ bằng polling
  (`GET /api/runs/{id}`) hoặc SSE. Reload trang vẫn thấy job đang chạy.
- Lịch sử: `GET /api/runs` (mới nhất trước), mỗi lần chạy: thời điểm, file, DB đích, cấu hình, trạng thái từng bước, số liệu,
  thời lượng, lỗi. Đọc lại từ `output/pipeline_runs/` khi khởi động lại server.
- Giao diện: một trang HTML/CSS/JS thuần (không build, không CDN bắt buộc — chạy offline), tiếng Việt, gọn, không kiểu "AI
  chung chung" (không gradient tím, không bo tròn mọi thứ). Bánh răng vẽ bằng SVG; quay khi chạy (tắt khi
  `prefers-reduced-motion`), xanh khi xong, đỏ khi lỗi, xám khi bỏ qua; nối nhau bằng đường thể hiện luồng. Có vùng kéo thả,
  danh sách file đã chọn, khung cấu hình (công tắc từng bước, chạy thử, DB đích, embedding, retrain), nút Chạy, bảng lịch
  sử, nút tải báo cáo. Responsive tới 360px, dark mode, bàn phím dùng được, tương phản đạt AA.
- Không thêm thư viện nặng; FastAPI, uvicorn, python-multipart đã có trong `.venv`.

## Tiêu chí nghiệm thu

| Mã | Tiêu chí |
|---|---|
| U1 | Kéo thả 2 file (`src/pipeline/input/data.json`, `data14-11.json`) vào DB tạm (bản sao `housing_dev`) chạy đủ bước 1–4, số liệu khớp `python -m src.pipeline --input <2 file>` trên cùng DB |
| U2 | Chạy lại cùng file: `inserted=0`, không nhân đôi |
| U3 | Chạy thử: không có dòng nào thay đổi trong DB (đếm `listings`, `updated_at` không đổi) |
| U4 | Chọn `housing` bị server từ chối (4xx) kể cả khi gọi API trực tiếp; danh sách DB không chứa `housing` |
| U5 | Embedding bật khi server Kaggle tắt → bước 5 đỏ, lý do rõ; bước 1–4 vẫn xanh và dữ liệu đã nạp |
| U6 | Retrain bật khi Prediction Server tắt/thiếu cấu hình → bước 6 đỏ, lý do rõ, không ảnh hưởng bước trước |
| U7 | File lỗi (không phải JSON Lines, rỗng, quá dung lượng, đuôi sai) bị từ chối với thông báo rõ; tên file kiểu `..\x.json` không ghi ra ngoài thư mục lần chạy |
| U8 | Lịch sử còn sau khi khởi động lại server; tải được báo cáo làm sạch của một lần chạy cũ |
| U9 | Đang chạy mà bấm chạy tiếp → báo bận; reload trang vẫn thấy tiến độ |
| U10 | `pytest src/tests` vẫn xanh + test mới cho server (không cần Kaggle/Prediction Server); `uvx ruff check src/pipeline` sạch |
| U11 | Ảnh chụp giao diện (desktop + 360px, sáng + tối, trạng thái đang chạy và xong) đã được xem lại bằng mắt |
| U12 | README `src/pipeline/README.md` + một dòng trong README gốc: cách chạy, cấu hình, cổng |

Không gọi OpenAI/Goong; không gọi Kaggle thật (chỉ thử trường hợp server tắt); không ghi vào DB `housing`; không commit.
