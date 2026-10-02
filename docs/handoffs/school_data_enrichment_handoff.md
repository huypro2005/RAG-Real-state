# Bàn giao công việc: dữ liệu trường học TP.HCM

Ngày cập nhật: 2026-09-20  
Workspace: `D:\my_project\DoAn2\Multi-Agent-RAG-and-Prediction-Housing-Price`

## 1. Mục tiêu của người dùng

Tạo một file Excel cho danh sách trường học trong `data_primiative/trường học.pdf`, trước mắt xử lý đến STT 1011, với các trường dữ liệu chính:

- Tên trường
- Địa chỉ cũ
- Phường/xã cũ
- Quận/huyện cũ
- Tỉnh/thành cũ
- Tọa độ latitude/longitude
- Cấp học
- Loại hình công lập/tư thục
- Thông tin nguồn, độ tin cậy và cờ cần kiểm tra thủ công

Người dùng muốn dùng Goong nhưng tài khoản chỉ có 1.000 request/ngày. Không tạo lịch chạy tự động; người dùng sẽ chủ động yêu cầu chạy tiếp.

## 2. Kết quả đã hoàn thành

### 2.1. Đọc và kiểm tra PDF

- File nguồn: `data_primiative/trường học.pdf`
- PDF có 158 trang.
- Danh sách trường bắt đầu ở trang PDF 15.
- Bảng có bốn cột: `STT`, `Địa bàn`, `Tên Đơn vị`, `Cấp học`.
- Đã trích xuất từ STT 1 đến STT 1011.
- Số trường thực tế: **1.009**.
- PDF nguồn bỏ trực tiếp STT **804 và 805**; không được tự tạo hai trường giả để lấp số thứ tự.
- Dòng đầu: STT 1, `Trường Mầm Non Sen Hồng`, `Đặc khu Côn Đảo`.
- Dòng cuối: STT 1011, `Trường Mầm non Phượng Hồng`, `Phường Tân Phú`.

### 2.2. Loại hình trường

Quyết định 5161/QĐ-UBND và tiêu đề phụ lục ghi rõ đây là mạng lưới cơ sở giáo dục **công lập**. Vì vậy toàn bộ 1.009 bản ghi trong phần đã trích xuất được gắn:

- `ownership_raw = Công lập`
- `ownership_group = Công lập`
- `ownership_basis = Phạm vi Quyết định 5161/QĐ-UBND: cơ sở giáo dục công lập`

Không suy luận loại hình từ tên trường.

### 2.3. Dữ liệu nguồn đã trích xuất

File:

`.codex_tmp/school_source_1_1011.json`

Mỗi bản ghi có:

- `source_index`
- `current_locality`
- `school_name`
- `school_level_raw`
- `school_level`
- `ownership_raw`
- `ownership_group`
- `ownership_basis`
- `source_pdf`
- `source_page`
- `source_table_row`

Script tạo dữ liệu:

`.codex_tmp/extract_school_pdf.py`

Lệnh chạy lại nếu thật sự cần:

```powershell
$py='C:\Users\huypro37\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
& $py '.codex_tmp\extract_school_pdf.py' 'data_primiative\trường học.pdf' '.codex_tmp\school_source_1_1011.json'
```

Không cần chạy lại nếu file JSON vẫn tồn tại và có 1.009 bản ghi.

### 2.4. Enrichment từ GIS giáo dục chính thức (hoàn thành 2026-09-20)

Pipeline:

`.codex_tmp/enrich_schools_gis.py`

Các file được tạo:

- Catalog vector tile + phường/xã: `.codex_tmp/gis_school_catalog.json`
- Checkpoint GIS (ghi nguyên tử sau từng trường): `.codex_tmp/schools_gis_checkpoint_1_1011.json`
- Output GIS có metadata/tổng hợp: `.codex_tmp/schools_gis_final_1_1011.json`

Kết quả kiểm tra cuối:

- Đã xử lý: **1.009/1.009** bản ghi nguồn.
- Khớp GIS và có tọa độ: **1.000**.
- Có địa chỉ GIS: **999**.
- Độ tin cậy: **999 high**, **1 medium**, **9 low/unmatched**.
- Cần kiểm tra thủ công: **131**; chủ yếu do có nhiều điểm trường (**121**), ngoài ra có 9 unmatched, 1 medium và 1 địa chỉ GIS trống (các nhóm có thể giao nhau).
- Nguồn record: 968 từ endpoint detail, 32 từ endpoint search fallback theo đúng `id_truong`, 9 chỉ giữ chẩn đoán từ tile do không đủ tin cậy để chọn.
- Toàn bộ 1.000 trường đã khớp có loại hình GIS là `Công lập`.
- STT 804 và 805 vẫn không tồn tại, đúng như PDF nguồn.
- Các cột địa giới cũ vẫn để trống; **không gọi Goong** (`goong_called = false`).

Chín dòng chưa ghép chắc chắn: STT 13, 14, 209, 342, 416, 595, 802, 845 và 983. STT 490 là khớp mức `medium`. STT 393 có tọa độ nhưng GIS không cung cấp địa chỉ, kể cả qua search fallback.

Pipeline có thể chạy lại an toàn để resume:

```powershell
$py='C:\Users\huypro37\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
& $py '.codex_tmp\enrich_schools_gis.py' --workers 2 --delay 0.1
```

Không chạy lại pipeline chỉ để đọc kết quả; file checkpoint và final hiện đã đầy đủ. Pipeline không chứa hoặc sử dụng khóa Goong.

### 2.5. Mở rộng đến hết danh sách PDF (hoàn thành 2026-09-20)

PDF kết thúc ở STT 2188. Toàn bộ danh sách có 2.186 bản ghi thực tế vì không có STT 804 và 805.

Các file phần mở rộng:

- Nguồn STT 1012-2188: `.codex_tmp/school_source_1012_2188.json`
- Checkpoint GIS STT 1012-2188: `.codex_tmp/schools_gis_checkpoint_1012_2188.json`
- Output GIS STT 1012-2188: `.codex_tmp/schools_gis_final_1012_2188.json`
- File tổng hợp STT 1-2188: `.codex_tmp/schools_gis_final_1_2188.json`
- Script trích xuất phần còn lại: `.codex_tmp/extract_school_pdf_remaining.py`
- Script ghép hai phần: `.codex_tmp/merge_school_gis_results.py`

Kết quả toàn bộ STT 1-2188:

- Bản ghi nguồn: **2.186**.
- Khớp GIS và có tọa độ: **2.120**.
- Có địa chỉ GIS: **2.117**.
- Độ tin cậy: **2.106 high**, **14 medium**, **66 low/unmatched**.
- Cần kiểm tra thủ công: **327**.
- Tất cả 2.120 bản ghi đã khớp có loại hình GIS là `Công lập`.
- Có **245** dòng nguồn mang địa bàn `Trực thuộc Sở`; pipeline lưu đây là `source_management_scope`, không coi là địa chỉ.
- STT 2024 (`THPT Nguyễn Khuyến`) khớp GIS ID 613939, địa chỉ `50 Thành Thái`, Phường Hòa Hưng, tọa độ `10.769746, 106.666793`, confidence `high`.
- `old_district` và `old_province` vẫn trống cho toàn bộ dữ liệu; **không gọi Goong**.

## 3. Trạng thái Goong

### 3.1. Script hiện tại

File:

`.codex_tmp/enrich_schools_goong.py`

Checkpoint:

`.codex_tmp/schools_goong_checkpoint_1_1011_v2.json`

Output dự kiến của script:

`.codex_tmp/schools_goong_final_1_1011_v2.json`

API key Goong được đọc từ `.env` qua biến `GOONG_API_KEY`. **Không đưa khóa vào tài liệu, log hoặc commit.**

### 3.2. Luồng hiện tại của script

Script đang dùng:

1. `Place/AutoComplete`
2. `Place/Detail`

Như vậy cần khoảng **2 request/trường**. Với quota 1.000 request/ngày, không được chạy toàn bộ 1.009 trường bằng phiên bản này.

Delay hiện tại là `0.5` giây sau mỗi request; có retry/backoff 3, 8, 20 và 45 giây khi gặp 429 hoặc lỗi máy chủ. Delay chỉ giúp hạn chế tốc độ, không khắc phục quota ngày.

### 3.3. Kết quả thử nghiệm đã lưu

Checkpoint hiện có 5 dòng:

- STT 1: có tọa độ và địa giới cũ, độ tin cậy thấp, cần kiểm tra.
- STT 2: có tọa độ và địa giới cũ, độ tin cậy cao.
- STT 3: có tọa độ và địa giới cũ, độ tin cậy thấp, cần kiểm tra.
- STT 4: chưa có kết quả vì Goong trả 429.
- STT 5: chưa có kết quả vì Goong trả 429.

Tổng hiện tại:

- Checkpoint: 5 dòng
- Có tọa độ: 3
- Có địa chỉ cũ: 3
- API `OK`: 3
- `unmatched`: 2

Ba kết quả thành công đều ở Côn Đảo, tỉnh cũ là `Tỉnh Bà Rịa - Vũng Tàu`.

### 3.4. Quota

Ngày 2026-09-19, Goong trả:

`429 OVER_RATE_LIMIT`

Người dùng xác nhận tài khoản chỉ có **1.000 request/ngày** và quota ngày đã hết. Không tiếp tục gọi Goong cho đến khi người dùng yêu cầu sau khi quota được làm mới.

## 4. Google API

Người dùng đã cung cấp một Google Maps API key để thử. Một request tới Google Geocoding API trả:

- `REQUEST_DENIED`
- `The provided API key is expired.`

Không lưu khóa đó trong file này và không dùng lại. Nếu người dùng cung cấp khóa mới, nhắc họ bật Geocoding API/Billing và giới hạn khóa theo API/IP.

## 5. Nguồn GIS giáo dục chính thức đã phát hiện

Website:

`https://gis.hcm.edu.vn/`

Nguồn này có thể giúp lấy tên trường, loại hình, địa chỉ và tọa độ trước, sau đó chỉ dùng Goong một lần/trường để xác nhận địa giới cũ.

Các endpoint đã xác nhận:

- TileJSON trường học: `https://gis.hcm.edu.vn/martin/v_school_tiles`
- Vector tile: `https://gis.hcm.edu.vn/martin/v_school_tiles/{z}/{x}/{y}`
- Tìm trường: `https://gis.hcm.edu.vn/api/data/schools/search?q=<query>`
- Chi tiết trường: `https://gis.hcm.edu.vn/api/data/schools/detail?id_truong=<id>`

Các thuộc tính trong `v_school_tiles`:

- `id_truong`
- `id_diem_truong`
- `id_xa`
- `ten_truong`
- `ten_diem_truong`
- `loai_hinh`
- `lat`
- `lng`
- `is_cap_mn`
- `is_cap_th`
- `is_cap_thcs`
- `is_cap_thpt`
- `is_cap_gdtx`
- `tong_so_hoc_sinh`
- `tong_so_lop`

Endpoint chi tiết có thể trả thêm:

- `dia_chi`
- `ten_xa_tinh`
- `ten_loai_hinh`
- `co_quan_quan_ly`
- `ma_truong`
- `lat`, `lng`
- thông tin liên hệ và quy mô trường

Gói Python `mapbox-vector-tile` đã được cài vào:

`.codex_tmp/python_libs`

Chưa viết xong script tải và giải mã toàn bộ vector tile. Đây là bước tiếp theo nên làm trước khi tiêu quota Goong.

## 6. Chiến lược tiếp tục được khuyến nghị

### Giai đoạn A: không dùng Goong

1. Tải toàn bộ vector tile trường học ở zoom phù hợp, dự kiến zoom 8 bao phủ toàn vùng TP.HCM sau sáp nhập.
2. Giải mã MVT bằng `mapbox-vector-tile` trong `.codex_tmp/python_libs`.
3. Khử trùng lặp bằng cặp `id_truong` và `id_diem_truong`.
4. Ghép 1.009 dòng PDF với dữ liệu GIS bằng:
   - tên trường đã chuẩn hóa;
   - cấp học;
   - địa bàn sau sáp nhập;
   - loại hình công lập;
   - ưu tiên khớp duy nhất và đánh cờ trường tên phổ biến.
5. Gọi endpoint chi tiết GIS cho các trường đã khớp để lấy `dia_chi`, `ten_xa_tinh`, `lat`, `lng`, `ten_loai_hinh`.
6. Lưu checkpoint riêng cho GIS.

### Giai đoạn B: dùng tối đa một request Goong/trường

Khi đã có tọa độ GIS, dùng một request reverse geocode Goong theo `lat,lng` để lấy:

- địa chỉ cũ;
- phường/xã cũ;
- quận/huyện cũ;
- tỉnh/thành cũ.

Không dùng lại `Autocomplete + Detail` cho những trường đã có tọa độ GIS.

Do có 1.009 trường nhưng quota chỉ 1.000 request/ngày, nên mỗi ngày chỉ chạy khoảng **950–980** request để chừa dung lượng kiểm thử và retry. Phần còn lại chạy ngày tiếp theo. Luôn checkpoint sau từng trường.

### Giai đoạn C: kiểm tra chất lượng

Các trường cần cờ `manual_review_required` khi:

- tên trường trùng nhiều nơi;
- địa chỉ GIS trống;
- tọa độ nằm ngoài vùng TP.HCM sau sáp nhập;
- tỉnh cũ không thuộc Hồ Chí Minh, Bình Dương hoặc Bà Rịa - Vũng Tàu;
- kết quả Goong không có `compound.district` hoặc `compound.province`;
- độ tương đồng tên thấp;
- nhiều điểm trường cho cùng một trường.

## 7. Cấu trúc file Excel cuối cùng

Nên có ba sheet:

1. `Tong quan`
2. `School master`
3. `Codebook`

Cột khuyến nghị trong `School master`:

- `source_index`
- `school_name`
- `school_level_raw`
- `school_level`
- `ownership_raw`
- `ownership_group`
- `current_locality`
- `source_current_address`
- `address_old_normalized`
- `old_ward`
- `old_district`
- `old_province`
- `latitude`
- `longitude`
- `location_precision`
- `gis_school_id`
- `gis_campus_id`
- `gis_address`
- `gis_current_ward_province`
- `goong_query`
- `goong_place_id`
- `goong_candidate_name`
- `goong_detail_address`
- `match_score`
- `match_confidence`
- `manual_review_required`
- `review_reason`
- `api_status`
- `location_source`
- `source_pdf`
- `source_page`
- `source_table_row`
- `fetched_at`

Chưa có file Excel cuối cùng. Không tạo Excel hoàn chỉnh cho đến khi đã có dữ liệu GIS/Goong đủ để tránh một workbook gần như trống.

## 8. Các lưu ý quan trọng cho context mới

- Đọc file này trước khi làm tiếp.
- Không chạy lại trích xuất PDF nếu không cần.
- Không xóa hoặc ghi đè checkpoint Goong.
- Không chạy toàn bộ `.codex_tmp/enrich_schools_goong.py` vì script hiện tiêu thụ hai request/trường.
- Trước tiên hoàn thành pipeline GIS và ghép trường.
- Giữ nguyên dữ liệu gốc; không bịa STT 804/805.
- Giữ cả giá trị raw và giá trị chuẩn hóa.
- Không ghi API key vào mã nguồn, workbook hoặc tài liệu.
- Khi tạo Excel phải dùng skill `spreadsheets:Spreadsheets`, `@oai/artifact-tool`, kiểm tra trực quan tất cả sheet và xuất file vào thư mục `outputs`.

## 9. Câu lệnh gợi ý cho context mới

Người dùng có thể bắt đầu context mới bằng câu:

> Đọc `docs/handoffs/school_data_enrichment_handoff.md`, kiểm tra các checkpoint hiện có, sau đó tiếp tục xây pipeline GIS để ghép 1.009 trường và giảm Goong xuống một request/trường. Không chạy Goong cho đến khi tôi xác nhận quota đã làm mới.
