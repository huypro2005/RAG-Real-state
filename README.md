# Multi-Agent RAG and Prediction for Housing Prices

Nền tảng thử nghiệm hỗ trợ tìm kiếm, gợi ý và tham khảo giá bất động sản tại TP.HCM. Dự án dùng dữ liệu tin đăng để phục vụ hai pipeline độc lập:

- **Price Prediction**: dự đoán giá rao bán tham khảo.
- **RAG Recommendation**: tìm và gợi ý bất động sản theo điều kiện, ngữ nghĩa và vị trí.

> Giá dự đoán là giá rao bán từ tin đăng, không phải giá giao dịch thực tế và không phải tư vấn pháp lý hoặc tài chính.

## Mục lục tài liệu

- [Kiến trúc hệ thống](docs/architecture.md)
- [Quy ước dữ liệu và chất lượng](docs/data-contract.md)
- [Hướng dẫn vận hành crawler](docs/crawler.md)
- [Đề cương chi tiết](DoAn2.md)
- [Báo cáo reverse-engineering HTML](analysis/field_coverage.md)

## Cấu trúc dự án

```text
.
├── CrawlData/       # Thu thập link và dữ liệu chi tiết từ tin đăng
├── CrawUltilities/  # Tiện ích hỗ trợ dữ liệu/địa điểm
├── analysis/        # Báo cáo cấu trúc HTML và mẫu trích xuất
├── docs/            # Tài liệu kỹ thuật của dự án
├── src/             # Mã nguồn ứng dụng/pipeline dùng chung
├── tools/           # Script phục vụ phân tích
└── DoAn2.md         # Đề cương đồ án
```

## Khởi động nhanh

Yêu cầu: Python 3.10+, Google Chrome và kết nối Internet.

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Thu thập link tin đăng:

```powershell
python .\CrawlData\1_GetLinkNhaDat.py --start-page 1 --end-page 25
```

Trích xuất thông tin chi tiết:

```powershell
python .\CrawlData\2_LocDataLink.py --start-index 1 --workers 6 --retries 3
```

Chi tiết về đầu ra, retry và cách dừng an toàn có trong [tài liệu crawler](docs/crawler.md).

## Nguyên tắc dữ liệu hiện tại

- Lưu tin có pháp lý là sổ, hợp đồng mua bán hoặc chưa tìm thấy pháp lý (`null`).
- Chỉ loại một bản ghi khi không có giá số hoặc không có diện tích số.
- Dữ liệu crawl, log lỗi, link đầu vào, profile Chrome và secret được bỏ qua bởi Git.
- Không suy luận địa chỉ mới từ địa chỉ cũ; chỉ lưu khi nguồn thực sự cung cấp.

## Lưu ý nguồn dữ liệu

Chỉ crawl với tần suất phù hợp, tuân thủ điều khoản của nguồn dữ liệu và không cố vượt qua cơ chế bảo vệ của website. Dữ liệu tin đăng có thể thay đổi, hết hạn hoặc bị gỡ; các pipeline phía sau cần ghi nhận thời điểm quan sát.
