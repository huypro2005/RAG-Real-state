# Kiến trúc hệ thống

## Mục tiêu

Hệ thống sử dụng cùng một nguồn tin đăng bất động sản cho hai nhu cầu khác nhau: dự đoán giá rao bán và gợi ý bằng RAG. Vì vậy dữ liệu thu thập không được tối ưu riêng cho một model hoặc một kiểu truy vấn.

```text
Batdongsan.com.vn
        │
        ▼
Crawler ──► Raw snapshots / crawl logs
        │
        ▼
Chuẩn hóa, deduplicate, theo dõi trạng thái tin
        │
        ├──► Dataset cho Price Prediction
        └──► Corpus và chỉ mục cho RAG Recommendation
```

## Các thành phần dự kiến

- **Crawler**: phát hiện URL, tải trang chi tiết, ghi dữ liệu trích xuất và lỗi theo từng link.
- **Raw snapshot store**: lưu payload/HTML hoặc dữ liệu raw theo lần quan sát để có thể kiểm tra lại parser.
- **Dữ liệu chuẩn hóa**: quản lý listing hiện tại, lịch sử giá, trạng thái active/inactive và tọa độ.
- **PostgreSQL + PostGIS**: lọc điều kiện cứng, lưu địa lý và truy vấn khoảng cách tới POI.
- **pgvector/RAG**: tìm kiếm ngữ nghĩa trên tiêu đề và mô tả, sau khi đã lọc theo điều kiện cứng.
- **Price Prediction**: huấn luyện trên tập đã đạt tiêu chí chất lượng; giá là target, không được dùng làm feature đầu vào.
- **Chatbot multi-agent**: có hai mode rõ ràng là `prediction` và `recommendation`.

## Nguyên tắc tách pipeline

- Giá và diện tích hợp lệ là bắt buộc cho tập train; với RAG, chúng dùng để lọc và xếp hạng khi có.
- Pháp lý là feature tùy giai đoạn cho prediction, nhưng là nội dung tư vấn quan trọng cho RAG.
- Tiêu đề và mô tả có thể tạo feature có kiểm soát cho model, đồng thời là nguồn ngữ nghĩa chính cho RAG.
- Tin hết hạn không dùng để gợi ý mặc định, nhưng vẫn cần giữ lịch sử để truy vết.

## Địa chỉ và vị trí

Crawler lưu địa chỉ cũ và địa chỉ mới như nguồn thể hiện. Không tự suy luận địa chỉ mới từ địa chỉ cũ. Tọa độ chỉ dùng cho feature không gian khi có độ tin cậy phù hợp.

Xem [quy ước dữ liệu](data-contract.md) để biết cách biểu diễn field thiếu và [hướng dẫn crawler](crawler.md) để biết cơ chế thu thập hiện tại.
