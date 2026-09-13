# Đề cương thực hiện Đồ án 2

## 1. Thông tin chung

- **Tên đề tài đề xuất:** Nền tảng Chatbot Tư vấn Bất động sản AI-First trên Web Thực nghiệm.
- **Thời gian thực hiện:** 31/08/2026 – 25/12/2026.
- **Phạm vi địa lý:** Thành phố Hồ Chí Minh.
- **Nguồn dữ liệu tin đăng:** `batdongsan.com.vn`.
- **Định hướng:** Không phát triển tính năng đấu thầu. Đồ án tập trung vào dữ liệu không gian, dự đoán giá với spatial feature, Hybrid Search RAG và chatbot multi-agent.

## 2. Bối cảnh và vấn đề cần giải quyết

Đồ án 1 đã có crawler, API FastAPI, pipeline Random Forest, geocoding và chatbot dự đoán giá cơ bản. Tuy nhiên, dữ liệu tin đăng bất động sản thay đổi thường xuyên; một tin có thể đổi giá hoặc hết hạn sau một thời gian. Vì vậy dữ liệu cũ không phù hợp để dùng trực tiếp làm kho tư vấn/RAG hiện hành.

Đồ án 2 xây dựng lại pipeline dữ liệu sống từ `batdongsan.com.vn`. Hệ thống lưu lịch sử từng lần quan sát tin đăng, chỉ tư vấn các tin còn hiệu lực, đồng thời khai thác vị trí bất động sản và tiện ích xung quanh để:

1. Dự đoán giá rao bán chính xác hơn.
2. Tìm và đề xuất nhà theo điều kiện định lượng chính xác, ví dụ ngân sách hoặc khoảng cách tới bệnh viện.
3. Tạo giao diện chat tự nhiên kết hợp bản đồ trực quan.

> **Lưu ý về nhãn dự đoán:** Model dự đoán **giá rao bán** từ tin đăng, không khẳng định đó là giá giao dịch thực tế.

## 3. Mục tiêu

### 3.1. Mục tiêu tổng quát

Xây dựng nền tảng web có chatbot AI hỗ trợ người dùng tìm kiếm và tham khảo giá bất động sản tại TP.HCM, dựa trên dữ liệu tin đăng được cập nhật liên tục và truy vấn không gian chính xác.

### 3.2. Mục tiêu cụ thể

1. Xây dựng pipeline crawl định kỳ, theo dõi tin mới, tin thay đổi và tin hết hạn.
2. Chuẩn hóa địa chỉ, quản lý tọa độ và hỗ trợ chuyển đổi địa chỉ cũ sang địa chỉ mới khi cần.
3. Xây dựng kho POI gồm chợ, bệnh viện và trường học tại TP.HCM.
4. Huấn luyện lại Random Forest với các đặc trưng không gian trong bán kính 1 km và 3 km.
5. Thực hiện A/B Testing có kiểm soát giữa Model A (baseline từ Đồ án 1) và Model B (bổ sung đúng 6 spatial feature đếm POI trong bán kính 1 km/3 km) bằng MAE, RMSE, R².
6. Xây dựng Hybrid Search: SQL/PostGIS lọc điều kiện cứng, vector search và reranking xử lý ý nghĩa ngữ nghĩa.
7. Xây dựng chatbot multi-agent với hai mode tường minh: `prediction` để dự đoán giá rao bán và `recommendation` để gợi ý Top 5 bất động sản phù hợp trên bản đồ.

## 4. Phạm vi thực hiện

### Trong phạm vi

- Bất động sản tại TP.HCM.
- Tin đăng từ `batdongsan.com.vn` với các trường sẵn có như ID/URL, tiêu đề, mô tả, giá, diện tích, loại BĐS, số phòng, số tầng, pháp lý, địa chỉ, tọa độ nếu có, ngày đăng, trạng thái, ảnh và tiện ích.
- POI thuộc ba nhóm: chợ, bệnh viện và trường học.
- Dự đoán giá rao bán bằng Random Forest.
- Chatbot tiếng Việt có hai mode nghiệp vụ: `prediction` (dự đoán giá) và `recommendation` (gợi ý bất động sản). Hỏi thêm hoặc so sánh kết quả chỉ là thao tác hỗ trợ trong mode `recommendation`, không phải mode độc lập.

### Ngoài phạm vi

- Đấu thầu, thanh toán, ký hợp đồng và giao dịch bất động sản.
- Khẳng định giá giao dịch chính thức hoặc tư vấn pháp lý/tài chính chuyên nghiệp.
- Thu thập dữ liệu bằng cách vượt qua cơ chế bảo vệ hay vi phạm điều khoản của nguồn dữ liệu.

## 5. Kiến trúc kỹ thuật đề xuất

```text
batdongsan.com.vn
       │
       ▼
Crawler định kỳ ──► Raw snapshots ──► Chuẩn hóa / Deduplicate / Theo dõi hết hạn
                                                │
                      ┌─────────────────────────┼──────────────────────┐
                      ▼                         ▼                      ▼
             PostgreSQL + PostGIS        ML feature dataset       RAG corpus + pgvector
              listings / POI / geo       Random Forest A/B         embeddings tin đăng
                      │                         │                      │
                      └─────────────► API tools ◄──────────────────────┘
                                               │
                                               ▼
                                    Multi-agent chatbot + Map View
```

### 5.1. Database

Sử dụng **PostgreSQL + PostGIS + pgvector** trong một hệ quản trị:

- PostgreSQL lưu tin đăng, lịch crawl, lịch sử giá, model version và log tìm kiếm.
- PostGIS lưu/tìm theo tọa độ, ví dụ `cách bệnh viện dưới 2 km`.
- pgvector lưu embedding tiêu đề và mô tả để thực hiện semantic search.

Việc dùng chung một database giúp kết hợp điều kiện giá, trạng thái tin, tọa độ và vector search trong cùng một luồng truy vấn.

### 5.2. Các bảng dữ liệu chính

| Nhóm | Bảng/đối tượng | Nội dung chính |
|---|---|---|
| Crawl | `crawl_runs` | Thời gian chạy, số tin mới, lỗi, trạng thái job |
| Dữ liệu thô | `raw_listing_snapshots` | Payload/HTML hoặc dữ liệu trích xuất nguyên bản theo từng lần crawl |
| Tin chuẩn hóa | `listings` | ID nguồn, URL, thuộc tính BĐS, giá, mô tả, trạng thái hiện tại |
| Lịch sử | `listing_history` | Giá và trạng thái theo từng thời điểm |
| Vị trí | `property_locations` | Địa chỉ thô, địa chỉ chuẩn hóa, tọa độ, độ tin cậy geocode |
| Tiện ích | `pois` | Chợ, bệnh viện, trường học, địa chỉ và tọa độ |
| Spatial feature | `listing_spatial_features` | Số POI trong 1 km/3 km, khoảng cách POI gần nhất |
| RAG | `listing_embeddings` | Nội dung nhúng và vector embedding |
| ML | `model_runs`, `model_metrics`, `model_activation` | Version dữ liệu/model và các chỉ số đánh giá |
| Theo dõi | `search_logs`, `chat_sessions`, `user_feedback` | Kiểm thử và đánh giá chatbot |

## 6. Danh sách công việc chi tiết

### 6.1. Khảo sát nguồn và hợp đồng dữ liệu

- Xác nhận selector/API hợp lệ để lấy từng trường dữ liệu từ `batdongsan.com.vn`.
- Lập data dictionary: tên trường, kiểu dữ liệu, đơn vị, quy tắc thiếu dữ liệu và ví dụ.
- Xác định cơ chế nhận diện tin mới, tin thay đổi giá, tin không còn truy cập được và tin hết hạn.
- Kiểm tra điều khoản sử dụng, giới hạn tần suất và xây dựng crawler có rate limit, retry, logging.

### 6.2. Crawler liên tục và quản lý vòng đời tin đăng

- Crawl trang danh sách để phát hiện URL/ID tin mới.
- Crawl trang chi tiết để lấy đầy đủ thông tin.
- Lưu raw snapshot, không ghi đè thông tin cũ.
- Deduplicate theo ID nguồn và URL chuẩn hóa; bổ sung kiểm tra gần trùng khi cần.
- Lưu `first_seen_at`, `last_seen_at`, `posted_at`, `expired_at` nếu nguồn cung cấp.
- Khi nguồn không có ngày hết hạn, đánh dấu inactive sau các lần kiểm tra không còn thấy tin; không xóa lịch sử.
- Lập lịch chạy crawler và tạo báo cáo mỗi lượt: tin mới, tin cập nhật, tin hết hạn, lỗi.

### 6.3. Chuẩn hóa dữ liệu và địa chỉ

- Làm sạch giá, diện tích, giá/m², phòng ngủ, số tầng, loại BĐS và pháp lý.
- Phát hiện và loại các bản ghi sai đơn vị, thiếu dữ liệu quan trọng, trùng lặp hoặc outlier bất thường.
- Luôn lưu `raw_address`; không chuyển địa chỉ sang mã số ngay khi crawl.
- Tạo `normalized_address` dùng cho tìm kiếm, geocoding và hiển thị.
- Nếu tin có tọa độ chính xác, sử dụng trực tiếp; nếu không có, geocode từ địa chỉ chuẩn hóa.
- Xây dựng bảng mapping địa chỉ hành chính cũ–mới. Khi người dùng nhập địa chỉ cũ, hệ thống chuyển đổi sang tên hiện hành rồi mới geocode/truy vấn.
- Lưu `geocode_confidence`; tọa độ không đáng tin cậy không được dùng cho feature không gian chính xác.

### 6.4. Xây dựng kho POI

- Thu thập chợ, bệnh viện và trường học tại TP.HCM.
- Lưu tên, loại POI, địa chỉ, tọa độ, nguồn và thời gian cập nhật.
- Deduplicate POI theo tên gần đúng và vị trí.
- Nếu dữ liệu tiện ích từ trang tin chỉ là “gần một BĐS”, tổng hợp và chuẩn hóa về bảng POI riêng để dùng nhất quán cho toàn bộ BĐS.
- Tạo spatial index PostGIS cho bảng POI.

### 6.5. Tạo spatial features

- Với mỗi BĐS có tọa độ hợp lệ, tính:
  - Số chợ trong bán kính 1 km và 3 km.
  - Số bệnh viện trong bán kính 1 km và 3 km.
  - Số trường học trong bán kính 1 km và 3 km.
- Có thể bổ sung khoảng cách tới POI gần nhất như thí nghiệm phụ.
- Lưu kết quả vào bảng feature và cập nhật lại khi tọa độ BĐS/POI thay đổi.

### 6.6. Pipeline dự đoán giá

- Tạo dataset ML riêng từ dữ liệu đã sạch và đạt yêu cầu chất lượng.
- EDA: phân phối giá, diện tích, giá/m², thiếu dữ liệu, outlier, loại BĐS và khu vực.
- Biến mục tiêu của cả hai model là `price` (giá rao bán).
- Dataset Đồ án 1 có các trường: loại nhà đất, địa chỉ, giá, diện tích, giá/m², mặt tiền, phòng ngủ, tọa độ x, tọa độ y, số tầng và khoảng cách tới trung tâm Quận 1. Khi xây model, chuẩn hóa `tọa độ x/y` thành `longitude/latitude`.
- Không dùng `price` làm feature vì đây là biến mục tiêu. Không dùng `price_per_m2` làm feature đầu vào vì giá/m² được tính trực tiếp từ giá và diện tích, có thể gây target leakage; trường này vẫn được giữ để EDA, kiểm tra chất lượng và hiển thị.
- Xây dựng **Model A (baseline)** với các feature từ Đồ án 1 có thể sử dụng tại thời điểm dự đoán: loại nhà đất, đặc trưng vị trí từ địa chỉ, diện tích, mặt tiền, phòng ngủ, longitude, latitude, số tầng và khoảng cách tới trung tâm Quận 1.
- Xây dựng **Model B (spatial)** bằng toàn bộ feature của Model A cộng đúng 6 biến:
  - `school_count_1km`
  - `hospital_count_1km`
  - `market_count_1km`
  - `school_count_3km`
  - `hospital_count_3km`
  - `market_count_3km`
- Chia dữ liệu train/test theo thời gian để mô phỏng dự đoán dữ liệu tương lai.
- Tuning Random Forest trên train set; so sánh hai model trên cùng tập train/test, cùng cách tiền xử lý, cùng quy trình tuning và cùng thời điểm đánh giá. Khác biệt có chủ đích duy nhất giữa hai model là 6 spatial feature của Model B.
- Báo cáo MAE, RMSE, R²; phân tích thêm theo quận/huyện, loại BĐS và phân khúc giá.
- Chỉ kích hoạt Model B nếu đạt tiêu chí cải thiện đã công bố trước, ví dụ MAE hoặc RMSE cải thiện tối thiểu 2%.
- Nếu Model B không đạt tiêu chí, tiếp tục sử dụng Model A làm model active và báo cáo trung thực rằng nhóm spatial feature thử nghiệm chưa cải thiện đủ lớn.
- Version hóa dataset, feature schema, tham số, model file và kết quả thí nghiệm.

### 6.7. Chuẩn bị dữ liệu RAG và embedding

- Chỉ đưa tin còn hiệu lực vào kết quả đề xuất mặc định.
- Tạo document RAG gồm tiêu đề, mô tả, giá, diện tích, loại BĐS, vị trí, thông tin POI, ngày cập nhật và URL nguồn.
- Sinh embedding cho nội dung ngữ nghĩa: tiêu đề và mô tả đã làm sạch.
- Khi có tin mới hoặc mô tả thay đổi: chuẩn hóa → geocode → tính spatial feature → embedding → cập nhật pgvector.
- Khi tin hết hạn: giữ lịch sử nhưng loại tin khỏi tập retrieve mặc định.

### 6.8. Hybrid Search và RAG

Với truy vấn: *“Tôi có 3 tỷ, tìm căn hộ ở Thủ Đức cách bệnh viện dưới 2 km”*, hệ thống thực hiện:

1. Trích xuất điều kiện thành JSON có schema kiểm tra được.
2. SQL lọc cứng: giá, loại BĐS, diện tích, khu vực, trạng thái active.
3. PostGIS lọc cứng: khoảng cách tới bệnh viện/chợ/trường.
4. Vector search tìm mức phù hợp ngữ nghĩa trên tập ứng viên còn lại.
5. Reranking và trả về Top 5.
6. LLM trả lời dựa trên dữ liệu Top 5, nêu giá, vị trí, khoảng cách, thời gian cập nhật và link tin gốc; không được tự bịa thông tin.

### 6.9. API/tool nền

- `chat(mode, message, conversation_id)`: nhận mode tường minh từ client, quản lý state và điều phối đúng workflow; backend không yêu cầu LLM tự đoán mode.
- `search_listings(filters)`: SQL/PostGIS/semantic retrieval và Top 5.
- `predict_price(property_features)`: dự đoán giá bằng model đang active.
- `normalize_address(address)`: chuẩn hóa địa chỉ cũ/mới và geocode.
- `get_nearby_pois(location, radius)`: truy vấn tiện ích xung quanh.
- `get_map_results(listing_ids)`: trả marker BĐS và POI cho bản đồ.

Mỗi tool cần schema đầu vào/đầu ra rõ ràng và unit test độc lập trước khi tích hợp với LLM.

### 6.10. Chatbot multi-agent

Chatbot chỉ có hai mode nghiệp vụ. Người dùng chọn mode trên giao diện và client gửi giá trị `prediction` hoặc `recommendation` cho backend. Mode là đầu vào được kiểm tra bằng schema, không phải kết quả do LLM tự suy đoán. Khi đổi mode, hệ thống reset hoặc tách state của phiên để tránh dùng nhầm dữ liệu giữa hai workflow.

#### Mode `prediction`

1. Thu thập các thuộc tính bất động sản người dùng có thể cung cấp như loại nhà đất, diện tích, địa chỉ, mặt tiền, phòng ngủ và số tầng.
2. Kiểm tra schema và hỏi bổ sung các field bắt buộc còn thiếu.
3. Chuẩn hóa địa chỉ, geocode để lấy longitude/latitude và tính khoảng cách tới trung tâm Quận 1.
4. Nếu Model B đang active, backend tự tính 6 biến đếm trường học, bệnh viện và chợ trong bán kính 1 km/3 km; người dùng không phải tự nhập các biến này.
5. Gọi `predict_price(property_features)` với feature schema đúng version của model active.
6. Trả giá rao bán dự đoán kèm cảnh báo đây là giá tham khảo, không phải giá giao dịch thực tế; thông báo rõ nếu dữ liệu vị trí có độ tin cậy thấp.

#### Mode `recommendation`

1. Thu thập nhu cầu mua như ngân sách, loại bất động sản, khu vực, khoảng diện tích, địa điểm/POI muốn ở gần và khoảng cách tối đa nếu có.
2. Trích xuất thông tin thành JSON có schema; phân biệt điều kiện cứng với sở thích mềm và hỏi bổ sung khi thiếu điều kiện cần thiết.
3. Gọi `search_listings(filters)`: SQL lọc giá, diện tích, loại BĐS, khu vực và trạng thái active; PostGIS lọc khoảng cách; vector search và reranking đánh giá mức phù hợp còn lại.
4. Trả tối đa 5 tin active phù hợp nhất. Mỗi kết quả nêu giá, diện tích, địa chỉ, khoảng cách liên quan, lý do phù hợp, thời gian cập nhật và URL nguồn.
5. Các thao tác hỏi thêm hoặc so sánh các tin đã trả về được xử lý trong cùng mode này.

| Thành phần | Nhiệm vụ |
|---|---|
| Mode Controller | Kiểm tra mode do client truyền vào, quản lý state và điều phối workflow `prediction` hoặc `recommendation` |
| Feature/Constraint Extractor | Theo mode, trích xuất feature dự đoán hoặc ngân sách, loại nhà, khu vực, diện tích, khoảng cách và tiện ích thành JSON |
| Geo Agent | Chuẩn hóa địa chỉ, xử lý địa chỉ cũ/mới và gọi truy vấn không gian |
| Search Agent | Trong mode `recommendation`, gọi Hybrid Search và lấy Top 5 |
| Price Agent | Trong mode `prediction`, geocode, tính feature nền/spatial và gọi Random Forest đang active |
| Response Agent | Tổng hợp câu trả lời có căn cứ từ tool output |
| Map Formatter | Trong mode `recommendation`, tạo dữ liệu marker/GeoJSON cho Top 5 và POI liên quan |

Agent chỉ được gọi các tool đã định nghĩa; không để LLM tự tạo SQL, tự đổi mode hoặc tự suy luận dữ kiện không có trong database.

### 6.11. Giao diện và kiểm thử

- Xây dựng khung chatbot có bộ chọn hai mode `prediction`/`recommendation`; hiển thị form hoặc gợi ý nhập liệu phù hợp với mode đang chọn.
- Hiển thị Top 5 bằng card: giá, diện tích, địa chỉ, khoảng cách POI, thời gian cập nhật, link gốc.
- Gắn Map View thu nhỏ cạnh chatbot, hiển thị BĐS và các POI liên quan.
- Hiển thị cảnh báo tin cũ/hết hạn và cảnh báo tọa độ thiếu tin cậy.
- Kiểm thử end-to-end: crawl → lưu DB → embedding → Hybrid Search hoặc prediction → chatbot → map.

## 7. Kế hoạch thời gian thực hiện

| Giai đoạn | Thời gian | Công việc chính | Đầu ra cần bàn giao |
|---|---|---|---|
| **1 – Khảo sát và thiết kế dữ liệu** | 31/08 – 06/09 | Chốt phạm vi; reverse-engineer HTML mẫu; khảo sát field, selector, metadata và địa chỉ cũ/mới; lập data dictionary; thiết kế ERD; xác định schema đầu vào/đầu ra cho hai mode `prediction` và `recommendation` | Báo cáo phân tích HTML, SRS ngắn, ERD, data dictionary, schema hai mode và bộ câu hỏi kiểm thử |
| **2 – Xây dựng hạ tầng và crawler MVP** | 07/09 – 20/09 | Dựng PostgreSQL/PostGIS/pgvector và migration; xây crawler MVP bằng Selenium để lấy trang danh sách và trang chi tiết; lưu raw snapshot, crawl run và lỗi | Database chạy được, migration, crawler Selenium lấy được một luồng tin chi tiết và raw snapshot mẫu |
| **3 – Hoàn thiện pipeline thu thập dữ liệu** | 21/09 – 04/10 | Hoàn thiện crawler incremental; deduplicate theo ID/URL; theo dõi tin mới, tin thay đổi và tin inactive; bổ sung retry, rate limit và logging; tách bước thu thập raw khỏi chuẩn hóa | Crawler định kỳ, crawl logs, raw snapshots, dữ liệu listings chuẩn hóa và kiểm thử deduplicate/trạng thái tin |
| **4 – Chuẩn hóa vị trí và xây dựng kho POI** | 05/10 – 18/10 | Chuẩn hóa địa chỉ; xử lý địa chỉ hành chính cũ/mới; geocoding; lưu longitude/latitude và geocode confidence; thu thập, chuẩn hóa và deduplicate POI gồm trường học, bệnh viện và chợ | Bảng locations/POI, mapping địa chỉ cũ–mới, báo cáo chất lượng tọa độ và dữ liệu POI |
| **5 – Xây dựng đặc trưng không gian** | 19/10 – 01/11 | Tạo spatial index và truy vấn PostGIS; tính khoảng cách tới trung tâm Quận 1; tính 6 spatial features đếm trường học, bệnh viện và chợ trong bán kính 1 km/3 km; kiểm thử truy vấn vị trí | Bảng spatial features, script/job tính feature và bộ test truy vấn khoảng cách/đếm POI |
| **6 – Xây dựng và đánh giá mô hình dự đoán giá** | 02/11 – 15/11 | EDA và chuẩn bị dataset ML; xác nhận `price` là target, loại `price_per_m2` khỏi feature để tránh leakage; huấn luyện Model A baseline và Model B bổ sung đúng 6 spatial features; dùng cùng train/test split theo thời gian, tiền xử lý và tuning; đánh giá bằng MAE, RMSE, R² | Dataset và feature schema được version hóa, hai model Random Forest, báo cáo A/B Testing, feature importance và quyết định kích hoạt Model B nếu MAE hoặc RMSE cải thiện tối thiểu 2%; nếu không thì giữ Model A |
| **7 – Xây dựng RAG và Hybrid Search** | 16/11 – 29/11 | Xây RAG corpus và embedding pipeline bằng LangChain; xây Hybrid Search gồm SQL filtering, PostGIS, vector search và reranking; đảm bảo chỉ retrieve tin active | RAG corpus, embeddings trong pgvector, Search API và bộ truy vấn mẫu trả Top 5 đúng điều kiện |
| **8 – Tích hợp chatbot multi-agent và giao diện web** | 30/11 – 13/12 | Xây FastAPI và các API tools; tích hợp chatbot multi-agent sử dụng OpenAI `gpt-4o-mini`; triển khai Mode Controller và state riêng cho `prediction`/`recommendation`; xây giao diện React với bộ chọn mode và tích hợp hai workflow | API có schema và unit test, mode `prediction` gọi đúng model active, mode `recommendation` trả Top 5, giao diện React chạy được hai luồng |
| **9 – Tích hợp bản đồ, kiểm thử và hoàn thiện** | 14/12 – 25/12 | Tích hợp Map View bằng Leaflet và Goong; hiển thị marker/GeoJSON cho Top 5 và POI; kiểm thử end-to-end từ crawl đến ML/RAG, chatbot và bản đồ; đánh giá kết quả; hoàn thiện báo cáo, slide và video/demo | Bản demo hoàn chỉnh, test report, kết quả đánh giá model/search/chatbot, báo cáo, slide và video/demo |

## 8. Tiêu chí đánh giá kết quả

### 8.1. Dữ liệu và crawler

- Crawl lặp lại không tạo bản ghi trùng.
- Phân biệt được tin mới, tin cập nhật và tin inactive.
- Có báo cáo tỷ lệ lỗi crawl và tỷ lệ geocode thành công.
- Tin inactive không xuất hiện trong đề xuất mặc định.

### 8.2. Model dự đoán giá

- Báo cáo MAE, RMSE, R² cho cả Model A và Model B.
- Cùng train/test split theo thời gian, cùng cách xử lý dữ liệu, cùng quy trình tuning và cùng thời điểm đánh giá; Model B chỉ bổ sung 6 biến đếm POI.
- Xác nhận `price` là target và `price_per_m2` không được dùng làm feature để tránh target leakage.
- Giải thích feature importance và kết luận rõ model nào được kích hoạt.

### 8.3. Hybrid Search/RAG

- Điều kiện giá, khu vực, loại BĐS và khoảng cách được lọc chính xác bằng SQL/PostGIS.
- Top 5 chỉ gồm tin active.
- Câu trả lời có giá, thuộc tính, khoảng cách, thời gian cập nhật và link nguồn.
- Đánh giá Precision@5 hoặc tỷ lệ kết quả phù hợp trên bộ câu hỏi kiểm thử.

### 8.4. Chatbot và giao diện

- Client gửi đúng một trong hai mode `prediction` hoặc `recommendation`; backend không cần LLM đoán ý định ban đầu.
- Mode `prediction` thu thập đủ feature, tự tính feature không gian cần thiết và gọi đúng model active.
- Mode `recommendation` trích xuất đúng điều kiện, chỉ trả tối đa 5 tin active và cho phép hỏi thêm/so sánh trong cùng mode.
- Chuyển mode không làm rò rỉ state hoặc field giữa hai workflow.
- Có khả năng xử lý địa chỉ cũ/mới khi người dùng cung cấp.
- Map View hiển thị chính xác Top 5 và POI liên quan.

## 9. Rủi ro và hướng xử lý

| Rủi ro | Hướng xử lý |
|---|---|
| Website thay đổi giao diện hoặc giới hạn crawl | Tách parser, lưu raw snapshot, có retry/rate limit và giám sát lỗi |
| Tin không có ngày hết hạn | Dùng `last_seen_at` và quy tắc inactive qua nhiều lần kiểm tra |
| Địa chỉ/tọa độ không chính xác | Lưu confidence, không dùng dữ liệu chất lượng thấp cho spatial feature |
| POI trùng hoặc thiếu | Deduplicate, lưu nguồn/thời gian cập nhật, kiểm tra thủ công mẫu |
| Model không cải thiện | Báo cáo A/B trung thực và giữ Model A làm model active |
| LLM trả lời sai dữ kiện | Bắt buộc dùng tool output, giới hạn câu trả lời theo Top 5 đã retrieve |
| Phạm vi multi-agent quá lớn | Hoàn thiện từng tool độc lập trước, chỉ triển khai số agent cần thiết |

## 10. Kết quả cuối cùng dự kiến

1. Pipeline crawl liên tục cho dữ liệu tin đăng tại TP.HCM.
2. Database PostgreSQL/PostGIS/pgvector có dữ liệu tin đăng, lịch sử, POI, spatial features và embeddings.
3. Báo cáo EDA và A/B Testing Random Forest với MAE, RMSE, R².
4. API Hybrid Search trả Top 5 bất động sản theo giá, vị trí, khoảng cách và ngữ nghĩa.
5. Chatbot multi-agent hỗ trợ đề xuất nhà và dự đoán giá.
6. Giao diện web có chatbot, danh sách kết quả và Map View.
7. Báo cáo, slide, video/demo và bộ test end-to-end.

## 11. Hướng phát triển của đề tài

Sau khi hoàn thành các mục tiêu và đánh giá hệ thống trong phạm vi Đồ án 2, đề tài có thể tiếp tục phát triển theo các hướng sau:

1. **Mở rộng phạm vi dữ liệu:** mở rộng từ TP.HCM sang các tỉnh/thành khác; bổ sung thêm loại hình bất động sản và nguồn dữ liệu phù hợp sau khi đánh giá điều khoản sử dụng và chất lượng dữ liệu.
2. **Mở rộng dữ liệu không gian:** bổ sung các nhóm POI như giao thông công cộng, công viên, trung tâm thương mại và cơ sở hành chính; nghiên cứu thêm dữ liệu quy hoạch, ngập lụt, tiếng ồn hoặc chất lượng môi trường khi có nguồn dữ liệu tin cậy.
3. **Nâng cao mô hình dự đoán giá:** thử nghiệm Gradient Boosting, XGBoost, LightGBM hoặc mô hình học sâu khi quy mô dữ liệu đủ lớn; tiếp tục so sánh trên cùng tập kiểm thử theo thời gian và bổ sung khoảng dự đoán để thể hiện mức độ bất định.
4. **Cải thiện Spatial RAG và khả năng gợi ý:** thử nghiệm embedding và reranker khác nhau, mở rộng bộ câu hỏi đánh giá, bổ sung cơ chế giải thích lý do xếp hạng và học từ phản hồi người dùng sau khi có chính sách bảo vệ dữ liệu phù hợp.
5. **Tăng cường khả năng vận hành:** xây dựng cơ chế giám sát chất lượng dữ liệu, phát hiện selector thay đổi, tự động đánh giá model drift và lập lịch tái huấn luyện khi dữ liệu mới đạt ngưỡng yêu cầu.
6. **Mở rộng nền tảng người dùng:** tối ưu giao diện trên thiết bị di động, phát triển ứng dụng di động và bổ sung trực quan hóa bản đồ nâng cao như vùng tìm kiếm, lớp tiện ích và so sánh nhiều bất động sản.

Các nội dung trên là định hướng sau Đồ án 2, không được xem là chức năng bắt buộc trong phạm vi triển khai và đánh giá hiện tại.
