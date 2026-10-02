# Backlog Jira – Đồ án 2: Spatial RAG & AI dự đoán giá bất động sản

Tài liệu chuyển phần công việc **còn lại** của đề cương (Giai đoạn 2 → 9) thành backlog Jira cho nhóm hai người: một thành viên phụ trách **Price Prediction + A/B Testing** (`owner-prediction`), một thành viên phụ trách **RAG + Hybrid Search** (`owner-rag`).

## 1. Hiện trạng tính đến 20/09/2026

| Hạng mục | Trạng thái | Ghi chú |
| --- | --- | --- |
| Khảo sát HTML, data dictionary sơ bộ | Xong | `analysis/`, `docs/data-contract.md` |
| Crawler MVP (Selenium + extractor) | Xong một luồng | `CrawlData/`, chưa incremental, chưa lưu raw snapshot |
| Dữ liệu tin đăng thô | 3.993 bản ghi | `CrawlData/data1.json` (NDJSON), đã có old/new address và lat/lon |
| Kho POI | 5.267 điểm | 4.660 trường học, 376 cơ sở y tế, 231 chợ; phạm vi TP.HCM cũ |
| Schema PostGIS cho POI | Bản nháp | `data/schema.sql`, ba bảng rời, cần gộp về `pois` |
| DB thật, crawler định kỳ, spatial feature, model, RAG, API, UI | **Chưa làm** | Toàn bộ backlog bên dưới |

## 2. Cấu hình Jira đề xuất

- **Project**: Scrum, key `BDS`, sprint hai tuần trùng đúng mốc giai đoạn trong Bảng 6.2 của đề cương.
- **Issue type**: Epic → Story → Sub-task, thêm `Spike` cho việc nghiên cứu và `Bug` cho lỗi.
- **Component**: đặt theo tên epic để lọc nhanh theo mảng kỹ thuật.
- **Label bắt buộc**: `owner-prediction`, `owner-rag`, `owner-both`, kèm `phase-2` … `phase-9` để đối chiếu ngược với đề cương khi báo cáo với GVHD.
- **Board**: hai swimlane theo label chủ sở hữu, mỗi người thấy luồng của mình mà vẫn nhìn được bối cảnh chung.
- **Definition of Ready**: story có acceptance criteria, có người nhận, rõ phụ thuộc và dữ liệu đầu vào đã tồn tại.
- **Definition of Done**: code đã merge vào `main`, có test hoặc báo cáo số liệu kèm theo, tài liệu trong `docs/` được cập nhật, và tiêu chí tương ứng ở §7 đề cương đã được kiểm chứng.

## 3. Sprint plan

| Sprint | Thời gian | Thành viên Prediction | Thành viên RAG |
| --- | --- | --- | --- |
| Sprint 1 | 21/09 – 04/10 | Làm sạch trường số và địa chỉ trên dump sẵn có | Dựng DB, migration, nạp POI và tin thô |
| Sprint 2 | 05/10 – 18/10 | Mapping hành chính cũ–mới, geocoding, báo cáo chất lượng | Crawler incremental, vòng đời tin, **bật lịch chạy định kỳ** |
| Sprint 3 | 19/10 – 01/11 | Spatial index, 6 biến POI, khoảng cách Quận 1 | Retry/rate limit, định nghĩa document RAG, chốt embedding model |
| Sprint 4 | 02/11 – 15/11 | EDA, dataset versioned, split theo thời gian | Sinh embedding, pgvector index, cập nhật incremental |
| Sprint 5 | 16/11 – 29/11 | Model A, Model B, báo cáo A/B, quy tắc kích hoạt | Hybrid Search: JSON schema → SQL → PostGIS → vector → rerank |
| Sprint 6 | 30/11 – 13/12 | Tool predict_price, normalize_address, endpoint chat | Bộ test RAG, tool search/nearby_pois/map_results |
| Sprint 7 | 14/12 – 25/12 | Mode Controller, Price Agent, Geo Agent, khung React | Constraint Extractor, Search/Response Agent, Map Formatter |
| Sprint 8 | 26/12 – 03/01 | Cảnh báo tin cũ và tọa độ yếu, kiểm thử e2e, báo cáo | Card Top 5, Map View Leaflet + Goong, kiểm thử e2e |

**Ba điều chỉnh so với Bảng 6.2 của đề cương.** Đề cương viết theo thứ tự tuần tự, phù hợp khi một người làm hết; với hai người thì nên đổi như sau:

1. **Giai đoạn 6 (model) và 7 (RAG) chạy song song** ở Sprint 5 thay vì nối tiếp, vì hai mảng này thuộc hai người và chỉ dùng chung phần dữ liệu đã chuẩn hóa. Việc này giải phóng khoảng hai tuần làm đệm cho giai đoạn tích hợp cuối tháng 12.
2. **Chuẩn hóa dữ liệu và địa chỉ bắt đầu ngay Sprint 1**, không chờ crawler, vì 3.993 tin thô đã nằm sẵn trong repo. Nhờ vậy thành viên Prediction không bị chặn bởi hạ tầng do thành viên RAG dựng.
3. **Lịch crawl định kỳ phải bật từ Sprint 2**, sớm hơn đề cương. `listing_history`, quy tắc tin hết hạn và tiêu chí §7.1 "phân biệt tin mới / tin cập nhật / tin inactive" chỉ có dữ liệu chứng minh khi thời gian thực tế trôi qua; bật muộn thì đến tháng 12 không có gì để demo.

## 4. Epic

| Key | Epic | Chủ sở hữu | Đầu ra cần bàn giao |
| --- | --- | --- | --- |
| BDS-E1 | Hạ tầng dữ liệu & Database | TV-RAG | DB chạy được, migration up/down sạch, ERD, 5.267 POI + 3.993 tin thô đã nằm trong DB. |
| BDS-E2 | Crawler định kỳ & vòng đời tin đăng | TV-RAG | Crawler chạy theo lịch, có crawl_runs + raw snapshots + listing_history, báo cáo mỗi lượt. |
| BDS-E3 | Chuẩn hóa dữ liệu, địa chỉ cũ–mới & geocoding | TV-Prediction | Bảng property_locations, bảng mapping cũ–mới, báo cáo chất lượng tọa độ. |
| BDS-E4 | Spatial features | TV-Prediction | Bảng listing_spatial_features + job cập nhật + test truy vấn khoảng cách. |
| BDS-E5 | Model dự đoán giá & A/B Testing | TV-Prediction | Báo cáo MAE/RMSE/R², feature importance, model_activation ghi model đang active. |
| BDS-E6 | RAG corpus & embedding pipeline | TV-RAG | Bảng listing_embeddings có index vector, pipeline cập nhật khi tin mới/đổi/hết hạn. |
| BDS-E7 | Hybrid Search (SQL + PostGIS + vector + rerank) | TV-RAG | API search trả Top 5 đúng điều kiện + bộ câu hỏi kiểm thử có số đo. |
| BDS-E8 | API & tool nền (FastAPI) | Cả hai | OpenAPI schema đầy đủ, unit test từng tool xanh trước khi nối LLM. |
| BDS-E9 | Chatbot multi-agent & giao diện | Cả hai | Web chạy được hai luồng prediction/recommendation, không rò state giữa hai mode. |
| BDS-E10 | Kiểm thử end-to-end, đánh giá & bàn giao | Cả hai | Test report, báo cáo đồ án, slide, video demo, hướng dẫn vận hành. |

## 5. Story chi tiết

### BDS-E1 – Hạ tầng dữ liệu & Database

*Chủ sở hữu:* TV-RAG · *Mục tiêu:* Dựng PostgreSQL + PostGIS + pgvector, migration đủ bảng theo Bảng 4.1, nạp dữ liệu thô hiện có.

**BDS-1 – Dựng PostgreSQL + PostGIS + pgvector bằng Docker Compose**  
`Story` · TV-RAG · Sprint 1 · 3 điểm

- `docker compose up` dựng được DB local, có script init và hướng dẫn trong README.
- `SELECT postgis_version()` và `SELECT extname FROM pg_extension` trả về cả postgis và vector.
- Cấu hình kết nối đọc từ .env, không hardcode mật khẩu trong code.

**BDS-2 – Thiết kế ERD và viết migration cho toàn bộ bảng theo Bảng 4.1**  
`Story` · TV-RAG · Sprint 1 · 8 điểm · phụ thuộc: BDS-1

- Đủ nhóm bảng: crawl_runs, raw_listing_snapshots, listings, listing_history, property_locations, pois, listing_spatial_features, listing_embeddings, model_runs/model_metrics/model_activation, search_logs/chat_sessions/user_feedback.
- Migration (Alembic hoặc SQL tuần tự) chạy up và down sạch trên DB trống.
- ERD export ra file ảnh và commit vào docs/.

**BDS-3 – Gộp ba bảng POI hiện có về bảng `pois` chuẩn và nạp 5.267 điểm**  
`Story` · TV-RAG · Sprint 1 · 5 điểm · phụ thuộc: BDS-2

- Nạp từ data/poi_schools.csv, poi_hospitals.csv, poi_markets.csv; giữ nguyên poi_id, source, updated_at.
- Số bản ghi theo poi_type khớp poi_master_quality_report.json (4.660 / 376 / 231).
- Có GIST index trên cột geography; truy vấn ST_DWithin bán kính 1 km trả kết quả dưới 100 ms.

**BDS-4 – Nạp 3.993 tin đăng thô hiện có vào raw_listing_snapshots và listings v0**  
`Story` · TV-RAG · Sprint 1 · 5 điểm · phụ thuộc: BDS-2

- Mỗi dòng của CrawlData/data1.json lưu nguyên payload vào raw_listing_snapshots.
- Sinh bản ghi listings v0 theo listing_id nguồn, không mất bản ghi nào.
- Ghi một crawl_run tương ứng cho lần nạp lịch sử này.

**BDS-5 – Data dictionary và data contract cho bảng listings**  
`Story` · Cả hai · Sprint 1 · 3 điểm · phụ thuộc: BDS-4

- Mỗi trường có kiểu dữ liệu, đơn vị, nguồn (structured/description/metadata), quy tắc null và ví dụ.
- Ghi rõ đơn vị của `price` và `price_per_m2` sau khi có kết luận của BDS-6.
- Tài liệu nằm ở docs/data-contract.md và được cả hai thành viên review.

**BDS-6 – SPIKE: xác nhận đơn vị và độ tin cậy của price / price_per_m2 trong dump hiện có**  
`Spike` · TV-Prediction · Sprint 1 · 2 điểm · phụ thuộc: BDS-4

- Kiểm tra trên mẫu ít nhất 50 tin: đối chiếu price, area, price_per_m2 với text trong title/description.
- Kết luận đơn vị (triệu VND hay tỷ) và tỷ lệ bản ghi không nhất quán.
- Ghi kết luận vào data dictionary; nếu sai lệch trên 5% thì mở bug cho parser.

### BDS-E2 – Crawler định kỳ & vòng đời tin đăng

*Chủ sở hữu:* TV-RAG · *Mục tiêu:* Tách raw khỏi parse, crawl incremental, deduplicate, theo dõi tin mới/đổi giá/hết hạn.

**BDS-7 – Tách bước thu thập raw khỏi bước parse trong crawler**  
`Story` · TV-RAG · Sprint 2 · 5 điểm · phụ thuộc: BDS-4

- Crawler ghi HTML/payload thô trước, parser chạy trên raw và có thể chạy lại độc lập.
- Parse lỗi không làm mất raw snapshot.
- Có thể re-parse toàn bộ raw cũ bằng một lệnh.

**BDS-8 – Crawl trang danh sách để phát hiện URL/ID tin mới (incremental)**  
`Story` · TV-RAG · Sprint 2 · 5 điểm · phụ thuộc: BDS-7

- Chỉ crawl trang chi tiết với URL/ID chưa có hoặc cần refresh.
- Ghi crawl_runs: thời gian chạy, số tin mới, số lỗi, trạng thái job.
- Chạy lại hai lần liên tiếp không tạo bản ghi trùng (tiêu chí §7.1).

**BDS-9 – Deduplicate theo source_id và canonical URL**  
`Story` · TV-RAG · Sprint 2 · 3 điểm · phụ thuộc: BDS-8

- Unique constraint trên (source, source_listing_id); URL được chuẩn hóa trước khi so sánh.
- Báo cáo số bản ghi gần trùng phát hiện được trên dump hiện có.

**BDS-10 – Theo dõi vòng đời tin: first_seen_at, last_seen_at, posted_at, expired_at**  
`Story` · TV-RAG · Sprint 2 · 5 điểm · phụ thuộc: BDS-9

- Lưu đủ bốn mốc thời gian khi nguồn cung cấp.
- Khi nguồn không có ngày hết hạn: đánh inactive sau N lần kiểm tra liên tiếp không thấy tin (N cấu hình được), không xóa lịch sử.
- Phân biệt được tin mới / tin cập nhật / tin inactive (tiêu chí §7.1).

**BDS-11 – Ghi listing_history mỗi lần quan sát có thay đổi giá hoặc trạng thái**  
`Story` · TV-RAG · Sprint 2 · 3 điểm · phụ thuộc: BDS-10

- Chỉ ghi dòng mới khi giá hoặc trạng thái khác lần quan sát trước.
- Truy vấn được lịch sử giá của một tin theo thời gian.

**BDS-12 – Bật lịch crawl định kỳ sớm để tích lũy lịch sử quan sát**  
`Story` · TV-RAG · Sprint 2 · 3 điểm · phụ thuộc: BDS-10

- Job chạy tự động hằng ngày (cron hoặc Task Scheduler) ngay từ Sprint 2, không chờ các epic khác.
- Lý do: listing_history và quy tắc hết hạn cần thời gian thực tế trôi qua mới có dữ liệu demo tháng 12.
- Mỗi lượt sinh báo cáo: tin mới, tin cập nhật, tin hết hạn, lỗi.

**BDS-13 – Retry, rate limit, logging và giám sát lỗi crawler**  
`Story` · TV-RAG · Sprint 3 · 5 điểm · phụ thuộc: BDS-12

- Có rate limit cấu hình được và exponential backoff khi lỗi mạng.
- Log theo từng link, phân loại lỗi, có báo cáo tỷ lệ lỗi crawl (tiêu chí §7.1).
- Selector thay đổi thì parser báo lỗi rõ ràng thay vì ghi dữ liệu rỗng.

### BDS-E3 – Chuẩn hóa dữ liệu, địa chỉ cũ–mới & geocoding

*Chủ sở hữu:* TV-Prediction · *Mục tiêu:* Làm sạch trường số và phân loại, giữ raw_address, mapping hành chính cũ–mới, geocode + confidence.

**BDS-14 – Rule làm sạch giá, diện tích, giá/m², phòng ngủ, số tầng, loại BĐS, pháp lý**  
`Story` · TV-Prediction · Sprint 1 · 8 điểm · phụ thuộc: BDS-6

- Mỗi rule có unit test với ca biên (giá thỏa thuận, diện tích 0, số tầng dạng chữ).
- Giữ nguyên giá trị raw song song với giá trị đã chuẩn hóa.
- Báo cáo phân bố giá trị sau khi làm sạch.

**BDS-15 – Phát hiện và loại bản ghi sai đơn vị, thiếu trường bắt buộc, trùng lặp hoặc outlier**  
`Story` · TV-Prediction · Sprint 1 · 5 điểm · phụ thuộc: BDS-14

- Quy tắc loại được viết thành tài liệu, không loại ngầm trong code.
- Báo cáo số lượng và tỷ lệ bị loại theo từng lý do.
- Bản ghi bị loại được đánh cờ, không xóa khỏi DB.

**BDS-16 – Giữ raw_address và sinh normalized_address**  
`Story` · TV-Prediction · Sprint 1 · 5 điểm · phụ thuộc: BDS-2

- raw_address luôn được lưu nguyên văn, không mã hóa thành số khi crawl.
- normalized_address dùng chung cho tìm kiếm, geocoding và hiển thị.
- Ghi vào bảng property_locations.

**BDS-17 – Bảng mapping địa chỉ hành chính cũ – mới**  
`Story` · TV-Prediction · Sprint 2 · 8 điểm · phụ thuộc: BDS-16

- Dùng bộ vietnamadminunits đã có trong repo làm nguồn, ghi rõ phiên bản dữ liệu.
- Người dùng nhập địa chỉ cũ thì hệ thống chuyển sang tên hiện hành rồi mới geocode hoặc truy vấn.
- Không suy luận địa chỉ mới nếu nguồn không cung cấp; có cờ đánh dấu trường hợp không map được.

**BDS-18 – Geocoding fallback và geocode_confidence**  
`Story` · TV-Prediction · Sprint 2 · 5 điểm · phụ thuộc: BDS-17

- Tin có tọa độ chính xác thì dùng trực tiếp, thiếu thì geocode từ normalized_address (Goong).
- Lưu geocode_confidence; tọa độ confidence thấp không được dùng cho spatial feature.
- Có cache để không gọi lại API cho cùng một địa chỉ.

**BDS-19 – Báo cáo chất lượng vị trí**  
`Story` · TV-Prediction · Sprint 2 · 3 điểm · phụ thuộc: BDS-18

- Báo cáo tỷ lệ tin có tọa độ gốc, tỷ lệ geocode thành công, phân bố confidence, phân bố theo quận cũ.
- Đáp ứng tiêu chí §7.1 về tỷ lệ geocode thành công.

### BDS-E4 – Spatial features

*Chủ sở hữu:* TV-Prediction · *Mục tiêu:* Spatial index, khoảng cách tới trung tâm Quận 1, 6 biến đếm POI trong 1 km/3 km.

**BDS-20 – Spatial index và hàm truy vấn đếm POI theo bán kính**  
`Story` · TV-Prediction · Sprint 3 · 5 điểm · phụ thuộc: BDS-3, BDS-18

- Hàm SQL hoặc Python nhận (lat, lon, radius, poi_type) và trả về số POI.
- Kiểm chứng với ít nhất 10 điểm tính tay bằng haversine, sai khác bằng 0.

**BDS-21 – Tính 6 spatial feature đếm POI trong 1 km và 3 km**  
`Story` · TV-Prediction · Sprint 3 · 5 điểm · phụ thuộc: BDS-20

- Đúng 6 biến: school_count_1km, hospital_count_1km, market_count_1km, school_count_3km, hospital_count_3km, market_count_3km.
- Chỉ tính cho tin có tọa độ đạt ngưỡng confidence.
- Lưu vào listing_spatial_features kèm phiên bản bộ POI đã dùng.

**BDS-22 – Tính khoảng cách tới trung tâm Quận 1**  
`Story` · TV-Prediction · Sprint 3 · 3 điểm · phụ thuộc: BDS-20

- Chốt và ghi tài liệu tọa độ điểm mốc trung tâm Quận 1.
- Giá trị khớp với dataset Đồ án 1 trên mẫu đối chiếu.

**BDS-23 – Job cập nhật lại spatial feature khi tọa độ BĐS hoặc POI thay đổi**  
`Story` · TV-Prediction · Sprint 4 · 3 điểm · phụ thuộc: BDS-21

- Chỉ tính lại những bản ghi bị ảnh hưởng, không tính lại toàn bộ.
- Có log số bản ghi được cập nhật mỗi lượt.

**BDS-24 – Thí nghiệm phụ: khoảng cách tới POI gần nhất theo từng loại**  
`Story` · TV-Prediction · Sprint 4 · 3 điểm · phụ thuộc: BDS-21

- Tính distance_to_nearest cho ba loại POI, lưu riêng, không đưa vào Model B chính thức.
- Ghi rõ đây là thí nghiệm phụ để giữ đúng cam kết Model B chỉ thêm 6 biến.

### BDS-E5 – Model dự đoán giá & A/B Testing

*Chủ sở hữu:* TV-Prediction · *Mục tiêu:* EDA, dataset versioned, Model A baseline vs Model B (+6 spatial), quyết định kích hoạt.

**BDS-25 – EDA: phân phối giá, diện tích, giá/m², thiếu dữ liệu, outlier, loại BĐS, khu vực**  
`Story` · TV-Prediction · Sprint 4 · 5 điểm · phụ thuộc: BDS-15, BDS-21

- Notebook hoặc report có biểu đồ và nhận xét cho từng nhóm.
- Chỉ ra rủi ro dữ liệu ảnh hưởng tới model (mất cân bằng quận, loại BĐS hiếm).

**BDS-26 – Tạo dataset ML versioned và feature schema**  
`Story` · TV-Prediction · Sprint 4 · 5 điểm · phụ thuộc: BDS-25

- `price` là target; `price_per_m2` bị loại khỏi feature để tránh target leakage nhưng vẫn giữ để EDA.
- Feature schema có version, lưu cùng dataset; tọa độ x/y chuẩn hóa thành longitude/latitude.
- Dataset và schema được lưu tham chiếu trong model_runs.

**BDS-27 – Chia train/test theo thời gian**  
`Story` · TV-Prediction · Sprint 4 · 3 điểm · phụ thuộc: BDS-26

- Split theo posted_at hoặc first_seen_at để mô phỏng dự đoán dữ liệu tương lai.
- Cùng một split dùng cho cả Model A và Model B.

**BDS-28 – Huấn luyện và tuning Model A (baseline)**  
`Story` · TV-Prediction · Sprint 5 · 8 điểm · phụ thuộc: BDS-27

- Feature gồm loại nhà đất, đặc trưng vị trí từ địa chỉ, diện tích, mặt tiền, phòng ngủ, longitude, latitude, số tầng và khoảng cách tới trung tâm Quận 1.
- Random Forest có hyperparameter tuning trên train set, quy trình tuning được ghi lại.

**BDS-29 – Huấn luyện Model B = Model A + đúng 6 spatial feature**  
`Story` · TV-Prediction · Sprint 5 · 5 điểm · phụ thuộc: BDS-28

- Cùng train/test split, cùng tiền xử lý, cùng quy trình tuning, cùng thời điểm đánh giá.
- Khác biệt có chủ đích duy nhất là 6 biến đếm POI.

**BDS-30 – Báo cáo A/B Testing: MAE, RMSE, R² và phân tích chi tiết**  
`Story` · TV-Prediction · Sprint 5 · 5 điểm · phụ thuộc: BDS-29

- Báo cáo cả hai model, phân tích thêm theo quận/huyện, loại BĐS và phân khúc giá.
- Giải thích feature importance của cả hai model.

**BDS-31 – Quy tắc kích hoạt model và bảng model_activation**  
`Story` · TV-Prediction · Sprint 5 · 3 điểm · phụ thuộc: BDS-30

- Chỉ kích hoạt Model B nếu MAE hoặc RMSE cải thiện tối thiểu 2%, tiêu chí công bố trước khi chạy.
- Nếu không đạt thì giữ Model A làm model active và báo cáo trung thực.
- model_runs/model_metrics/model_activation ghi đủ version dataset, tham số và file model.

### BDS-E6 – RAG corpus & embedding pipeline

*Chủ sở hữu:* TV-RAG · *Mục tiêu:* Định nghĩa document RAG, làm sạch mô tả, sinh embedding, lưu pgvector, cập nhật incremental.

**BDS-32 – Định nghĩa cấu trúc document RAG**  
`Story` · TV-RAG · Sprint 3 · 3 điểm · phụ thuộc: BDS-4

- Document gồm tiêu đề, mô tả, giá, diện tích, loại BĐS, vị trí, thông tin POI, ngày cập nhật, URL nguồn.
- Chốt phần nào đưa vào embedding, phần nào chỉ là metadata dùng để lọc.

**BDS-33 – Làm sạch mô tả phục vụ embedding**  
`Story` · TV-RAG · Sprint 3 · 5 điểm · phụ thuộc: BDS-32

- Bỏ số điện thoại, ký tự rác, emoji lặp; giữ nguyên mô tả gốc trong listings.
- Có unit test trên mẫu mô tả thật lấy từ dump hiện có.

**BDS-34 – SPIKE: chọn embedding model tiếng Việt**  
`Spike` · TV-RAG · Sprint 3 · 5 điểm · phụ thuộc: BDS-33

- So sánh ít nhất hai lựa chọn trên khoảng 20 truy vấn mẫu về chi phí, tốc độ và chất lượng retrieve.
- Chốt model và số chiều vector, ghi vào docs/ trước khi tạo cột vector.

**BDS-35 – Sinh embedding và lưu vào pgvector kèm index**  
`Story` · TV-RAG · Sprint 4 · 5 điểm · phụ thuộc: BDS-34, BDS-2

- Bảng listing_embeddings có index vector (HNSW hoặc IVFFlat) và lưu version của embedding model.
- Chạy xong cho toàn bộ tin active hiện có.

**BDS-36 – Pipeline cập nhật incremental khi tin mới hoặc mô tả thay đổi**  
`Story` · TV-RAG · Sprint 4 · 5 điểm · phụ thuộc: BDS-35, BDS-11

- Luồng chuẩn hóa → geocode → tính spatial feature → embedding → cập nhật pgvector.
- Tin hết hạn giữ lịch sử nhưng bị loại khỏi tập retrieve mặc định (tiêu chí §7.1).
- Chỉ sinh lại embedding khi nội dung ngữ nghĩa thực sự thay đổi.

### BDS-E7 – Hybrid Search (SQL + PostGIS + vector + rerank)

*Chủ sở hữu:* TV-RAG · *Mục tiêu:* Trích điều kiện thành JSON có schema, lọc cứng, vector search, reranking, trả Top 5 tin active.

**BDS-37 – Schema JSON điều kiện truy vấn và validator**  
`Story` · TV-RAG · Sprint 5 · 5 điểm · phụ thuộc: BDS-5

- Schema phân biệt điều kiện cứng (ngân sách, khu vực, khoảng cách) và sở thích mềm.
- Validator từ chối JSON sai schema, LLM không được tự chế field mới.

**BDS-38 – Lọc cứng bằng SQL: giá, loại BĐS, diện tích, khu vực, trạng thái active**  
`Story` · TV-RAG · Sprint 5 · 5 điểm · phụ thuộc: BDS-37

- Query dùng tham số hóa, không ghép chuỗi SQL từ output của LLM.
- Kết quả chỉ gồm tin active.

**BDS-39 – Lọc khoảng cách bằng PostGIS tới bệnh viện, chợ, trường học**  
`Story` · TV-RAG · Sprint 5 · 5 điểm · phụ thuộc: BDS-38, BDS-3

- Hỗ trợ truy vấn kiểu "cách bệnh viện dưới 2 km".
- Kết quả trả về kèm khoảng cách thực tế để hiển thị.

**BDS-40 – Vector search trên tập ứng viên còn lại**  
`Story` · TV-RAG · Sprint 5 · 5 điểm · phụ thuộc: BDS-39, BDS-35

- Vector search chỉ chạy sau khi đã lọc cứng, không quét toàn bảng.
- Có ngưỡng số ứng viên tối đa đưa vào bước rerank.

**BDS-41 – Reranking và trả về Top 5**  
`Story` · TV-RAG · Sprint 5 · 5 điểm · phụ thuộc: BDS-40

- Trả tối đa 5 tin active, mỗi tin kèm giá, diện tích, địa chỉ, khoảng cách liên quan, lý do phù hợp, thời gian cập nhật và URL nguồn.
- Tiêu chí rerank được ghi tài liệu, không phải hộp đen.

**BDS-42 – Bộ câu hỏi kiểm thử RAG và đo precision**  
`Story` · TV-RAG · Sprint 6 · 5 điểm · phụ thuộc: BDS-41

- Ít nhất 30 truy vấn tiếng Việt phủ các kiểu điều kiện: ngân sách, khu vực, khoảng cách POI, loại BĐS.
- Có nhãn kỳ vọng và báo cáo Precision hoặc tỷ lệ kết quả phù hợp (tiêu chí §7.3).

### BDS-E8 – API & tool nền (FastAPI)

*Chủ sở hữu:* Cả hai · *Mục tiêu:* 5 tool theo §5.9 và endpoint chat(mode, message, conversation_id), mỗi tool có schema và unit test.

**BDS-43 – Khung FastAPI: cấu hình, logging, health check, cấu trúc thư mục**  
`Story` · Cả hai · Sprint 6 · 3 điểm · phụ thuộc: BDS-2

- Chạy được bằng một lệnh, có /health và log request.
- Cấu trúc tách rõ router / service / tool.

**BDS-44 – Endpoint chat(mode, message, conversation_id) và quản lý state**  
`Story` · TV-Prediction · Sprint 6 · 5 điểm · phụ thuộc: BDS-43

- mode là đầu vào được kiểm tra bằng schema, backend không để LLM tự đoán mode.
- State của hai mode tách riêng, đổi mode thì reset hoặc tách state.
- Lưu chat_sessions và search_logs.

**BDS-45 – Tool predict_price(property_features)**  
`Story` · TV-Prediction · Sprint 6 · 5 điểm · phụ thuộc: BDS-31, BDS-43

- Gọi đúng model đang active theo feature schema đúng version.
- Có schema đầu vào/đầu ra rõ ràng và unit test độc lập trước khi tích hợp LLM.

**BDS-46 – Tool normalize_address(address)**  
`Story` · TV-Prediction · Sprint 6 · 3 điểm · phụ thuộc: BDS-17, BDS-43

- Xử lý được cả địa chỉ cũ và địa chỉ mới, trả về normalized_address, tọa độ và confidence.
- Unit test phủ ca địa chỉ cũ, địa chỉ mới và địa chỉ không map được.

**BDS-47 – Tool search_listings(filters)**  
`Story` · TV-RAG · Sprint 6 · 5 điểm · phụ thuộc: BDS-41, BDS-43

- Bọc toàn bộ luồng Hybrid Search, trả Top 5 kèm metadata hiển thị.
- Unit test chạy độc lập với LLM.

**BDS-48 – Tool get_nearby_pois(location, radius)**  
`Story` · TV-RAG · Sprint 6 · 3 điểm · phụ thuộc: BDS-3, BDS-43

- Trả POI theo loại và bán kính, kèm khoảng cách.
- Unit test đối chiếu với truy vấn PostGIS trực tiếp.

**BDS-49 – Tool get_map_results(listing_ids)**  
`Story` · TV-RAG · Sprint 6 · 3 điểm · phụ thuộc: BDS-47

- Trả marker/GeoJSON cho BĐS và POI liên quan.
- Output validate được bằng schema GeoJSON.

### BDS-E9 – Chatbot multi-agent & giao diện

*Chủ sở hữu:* Cả hai · *Mục tiêu:* Mode Controller và các agent theo Bảng 5.1, React 2 mode, Map View Leaflet + Goong.

**BDS-50 – Mode Controller: kiểm tra mode và điều phối workflow**  
`Story` · TV-Prediction · Sprint 7 · 5 điểm · phụ thuộc: BDS-44

- Chỉ nhận đúng hai giá trị prediction hoặc recommendation.
- Đổi mode không làm rò state hoặc field giữa hai workflow (tiêu chí §7.4).

**BDS-51 – Feature Extractor cho mode prediction**  
`Story` · TV-Prediction · Sprint 7 · 5 điểm · phụ thuộc: BDS-50, BDS-45

- Thu thập loại nhà đất, diện tích, địa chỉ, mặt tiền, phòng ngủ, số tầng và hỏi bổ sung field bắt buộc còn thiếu.
- Nếu Model B đang active thì backend tự tính 6 biến POI, người dùng không phải nhập.

**BDS-52 – Constraint Extractor cho mode recommendation**  
`Story` · TV-RAG · Sprint 7 · 5 điểm · phụ thuộc: BDS-50, BDS-37

- Trích ngân sách, loại BĐS, khu vực, khoảng diện tích, POI muốn ở gần và khoảng cách tối đa thành JSON đúng schema.
- Phân biệt điều kiện cứng với sở thích mềm, hỏi bổ sung khi thiếu điều kiện cần thiết.

**BDS-53 – Geo Agent: chuẩn hóa địa chỉ và gọi truy vấn không gian**  
`Story` · TV-Prediction · Sprint 7 · 3 điểm · phụ thuộc: BDS-46

- Xử lý được địa chỉ cũ và mới do người dùng nhập.
- Thông báo rõ khi dữ liệu vị trí có độ tin cậy thấp.

**BDS-54 – Price Agent: geocode, tính feature và gọi model active**  
`Story` · TV-Prediction · Sprint 7 · 5 điểm · phụ thuộc: BDS-51, BDS-53

- Trả giá rao dự đoán kèm cảnh báo đây là giá tham khảo, không phải giá giao dịch thực tế.
- Không trả kết quả nếu thiếu feature bắt buộc.

**BDS-55 – Search Agent: gọi Hybrid Search và lấy Top 5**  
`Story` · TV-RAG · Sprint 7 · 3 điểm · phụ thuộc: BDS-52, BDS-47

- Chỉ gọi tool đã định nghĩa, không tự sinh SQL.
- Hỗ trợ hỏi thêm và so sánh các tin đã trả về trong cùng mode.

**BDS-56 – Response Agent: tổng hợp câu trả lời có căn cứ từ tool output**  
`Story` · TV-RAG · Sprint 7 · 5 điểm · phụ thuộc: BDS-55

- Câu trả lời chỉ dựa trên Top 5 đã retrieve, có giá, vị trí, khoảng cách, thời gian cập nhật và link gốc.
- Test đối kháng: hỏi thông tin không có trong DB thì bot phải nói không có, không được bịa.

**BDS-57 – Map Formatter: sinh marker/GeoJSON cho Top 5 và POI liên quan**  
`Story` · TV-RAG · Sprint 7 · 3 điểm · phụ thuộc: BDS-49, BDS-55

- Output khớp với dữ liệu Top 5 trả về, không lệch bản ghi.

**BDS-58 – React: khung chat, bộ chọn mode và form nhập liệu theo mode**  
`Story` · TV-Prediction · Sprint 7 · 8 điểm · phụ thuộc: BDS-50

- Client gửi đúng một trong hai mode cho backend.
- Form hoặc gợi ý nhập liệu thay đổi theo mode đang chọn.

**BDS-59 – React: danh sách Top 5 dạng card**  
`Story` · TV-RAG · Sprint 8 · 5 điểm · phụ thuộc: BDS-56

- Mỗi card hiển thị giá, diện tích, địa chỉ, khoảng cách POI, thời gian cập nhật và link gốc.

**BDS-60 – Map View bằng Leaflet + Goong đặt cạnh chatbot**  
`Story` · TV-RAG · Sprint 8 · 8 điểm · phụ thuộc: BDS-57, BDS-59

- Hiển thị marker BĐS và POI liên quan cho Top 5, click marker đồng bộ với card.
- Map View hiển thị đúng Top 5 (tiêu chí §7.4).

**BDS-61 – Cảnh báo tin cũ/hết hạn và cảnh báo tọa độ thiếu tin cậy trên UI**  
`Story` · TV-Prediction · Sprint 8 · 3 điểm · phụ thuộc: BDS-59

- Tin quá N ngày chưa cập nhật hiển thị badge cảnh báo.
- Kết quả dựa trên tọa độ confidence thấp có cảnh báo riêng.

### BDS-E10 – Kiểm thử end-to-end, đánh giá & bàn giao

*Chủ sở hữu:* Cả hai · *Mục tiêu:* Test e2e crawl→DB→embedding→search/predict→chatbot→map, tổng hợp kết quả, báo cáo/slide/demo.

**BDS-62 – Kiểm thử end-to-end: crawl → DB → embedding → search/predict → chatbot → map**  
`Story` · Cả hai · Sprint 8 · 8 điểm · phụ thuộc: BDS-60, BDS-54

- Kịch bản chạy được từ đầu đến cuối trên môi trường sạch.
- Có test report ghi lại từng bước và lỗi phát hiện.

**BDS-63 – Bộ test chatbot hai mode và kiểm tra rò state**  
`Story` · Cả hai · Sprint 8 · 5 điểm · phụ thuộc: BDS-62

- Kịch bản đổi mode giữa phiên không làm lẫn dữ liệu giữa hai workflow.
- Mode prediction gọi đúng model active, mode recommendation chỉ trả tin active.

**BDS-64 – Tổng hợp báo cáo kết quả theo §7 đề cương**  
`Story` · Cả hai · Sprint 8 · 5 điểm · phụ thuộc: BDS-63

- Gộp đủ báo cáo crawler (trùng lặp, lỗi, geocode), báo cáo A/B model và báo cáo precision RAG.
- Nêu rõ model nào được kích hoạt và vì sao.

**BDS-65 – Báo cáo đồ án, slide và video demo**  
`Story` · Cả hai · Sprint 8 · 8 điểm · phụ thuộc: BDS-64

- Báo cáo bám đúng cấu trúc đề cương, slide và video demo thể hiện cả hai mode và Map View.

**BDS-66 – Hướng dẫn cài đặt và vận hành hệ thống**  
`Story` · Cả hai · Sprint 8 · 3 điểm · phụ thuộc: BDS-65

- Người ngoài nhóm dựng lại được hệ thống từ README trong một buổi.
- Ghi rõ biến môi trường, API key cần có và cách chạy crawler định kỳ.

## 6. Cân đối khối lượng

| Sprint | Prediction | RAG | Cả hai |
| --- | --- | --- | --- |
| Sprint 1 | 20 | 21 | 3 |
| Sprint 2 | 16 | 24 | 0 |
| Sprint 3 | 13 | 18 | 0 |
| Sprint 4 | 19 | 10 | 0 |
| Sprint 5 | 21 | 25 | 0 |
| Sprint 6 | 13 | 16 | 3 |
| Sprint 7 | 26 | 16 | 0 |
| Sprint 8 | 3 | 13 | 29 |
| **Tổng** | **131** | **143** | **35** |

Tổng cộng 66 story/spike và 309 điểm. Story point ở đây là độ phức tạp tương đối; nhóm nên chạy hết Sprint 1 rồi lấy velocity thực tế để hiệu chỉnh các sprint sau.

## 7. Việc dùng chung và điểm dễ giẫm chân nhau

Bốn epic đầu là nền móng cho cả hai luồng. Nếu không chốt trước, hai người sẽ cùng sửa một chỗ:

| Hạng mục dùng chung | Ai làm | Ai phụ thuộc | Chốt ở story |
| --- | --- | --- | --- |
| Schema DB và migration | RAG | Cả hai | BDS-2 |
| Data dictionary và đơn vị giá | Prediction đề xuất, cả hai duyệt | Cả hai | BDS-5, BDS-6 |
| Bảng `pois` | RAG nạp | Prediction dùng cho spatial feature | BDS-3 |
| Chuẩn hóa địa chỉ và geocode confidence | Prediction | RAG dùng cho lọc PostGIS | BDS-17, BDS-18 |
| Khung FastAPI | Cả hai làm chung một buổi | Cả hai | BDS-43 |
| Trạng thái active / expired | RAG | Prediction lọc tập train, RAG lọc retrieve | BDS-10 |

Quy ước đề xuất: mọi thay đổi schema DB đi qua migration có review chéo, không ai sửa trực tiếp bảng trên DB dùng chung.

## 8. Rủi ro cần theo dõi trên Jira

| Rủi ro | Dấu hiệu sớm | Hướng xử lý | Story liên quan |
| --- | --- | --- | --- |
| 3.993 tin có thể không đủ hoặc lệch phân bố theo quận và loại BĐS | EDA cho thấy nhiều quận chỉ có vài chục mẫu | Crawl bổ sung sớm, hoặc thu hẹp phạm vi đánh giá và nói rõ trong báo cáo | BDS-25, BDS-12 |
| Đơn vị `price` và `price_per_m2` chưa được xác nhận | Một bản ghi có price 22500 và price_per_m2 64.97 | Spike xác nhận đơn vị trước khi train | BDS-6 |
| Model B không cải thiện đủ 2% | Kết quả A/B report | Giữ Model A làm model active và báo cáo trung thực, đúng như đề cương cho phép | BDS-31 |
| Website đổi giao diện giữa kỳ | Tỷ lệ lỗi parse tăng | Raw snapshot đã tách khỏi parse nên chỉ cần sửa parser rồi re-parse | BDS-7, BDS-13 |
| Phạm vi multi-agent phình to | Sprint 7 trễ | Hoàn thiện từng tool độc lập trước, chỉ triển khai số agent cần thiết | BDS-43 → BDS-49 |
| Lịch crawl bật muộn | Tháng 12 không có lịch sử giá để demo | Bật từ Sprint 2 và coi đây là story chặn | BDS-12 |

## 9. Cách import vào Jira

File `docs/jira-import.csv` đã ở định dạng Jira CSV import, mã hóa UTF-8 có BOM.

1. Jira → *Settings* → *System* → *External System Import* → *CSV*.
2. Map cột: `Issue Type`, `Summary`, `Description`, `Epic Name` cho dòng Epic, `Epic Link` cho Story (trỏ bằng tên epic), `Labels`, `Components`, `Story Points`, `Priority`.
3. Cột `Sprint` chỉ import được khi project đã tạo sẵn sprint cùng tên; nếu chưa thì bỏ qua cột này rồi kéo story vào sprint trên backlog.
4. Cột `Issue Key` chỉ để tham chiếu trong tài liệu này, **không map** khi import để Jira tự sinh key.
5. Sau khi import, thêm link `blocks` / `is blocked by` theo mục *Phụ thuộc* ghi trong description của từng story.
6. Gán người thực hiện theo label `owner-prediction` / `owner-rag`; các story `owner-both` cần chọn một người làm assignee chính để tránh việc không ai nhận.
