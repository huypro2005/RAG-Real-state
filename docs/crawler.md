# Hướng dẫn vận hành crawler

## Cài đặt

Tại thư mục root của project:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Crawler cần Google Chrome. ChromeDriver được chọn theo major version của Chrome và được chia sẻ trong cache của `undetected-chromedriver` để dùng được với nhiều worker.

## Thu thập URL

```powershell
python .\CrawlData\1_GetLinkNhaDat.py `
  --start-page 1 `
  --end-page 25 `
  --workers 6 `
  --retries 3 `
  --launch-delay 0.3
```

Kết quả được append vào `CrawlData/linkNhaDat.txt`; link trùng được loại trong lúc đọc input.

## Trích xuất tin chi tiết

```powershell
python .\CrawlData\2_LocDataLink.py `
  --start-index 1 `
  --workers 6 `
  --retries 3 `
  --launch-delay 0.3
```

- Record hợp lệ được append theo JSON Lines vào `CrawlData/data.json`.
- Record bị bỏ hoặc lỗi được append vào `CrawlData/data_errors.json`.
- Cả ba file crawl này đều bị Git ignore.

## Điều kiện lưu và retry

Record chỉ bị bỏ ngay khi `price` hoặc `area` sau trích xuất là `null`. `legal` có thể là `null`, sổ hoặc hợp đồng mua bán.

Một exception khi tạo browser, tải trang hoặc trích xuất sẽ được thử lại tối đa theo `--retries` (mặc định 3 lần). Giữa hai lần có khoảng chờ 2 giây và profile Chrome của lần trước được đóng.

`driver.get()` dùng page-load timeout mặc định của Selenium. Sau khi trang mở, crawler chờ phần thông tin bất động sản xuất hiện; nếu selector không bao giờ xuất hiện, worker sẽ chờ đến khi người dùng dừng chương trình.

## Dừng an toàn

Nhấn `Ctrl+C`. Runtime sẽ ngăn mở browser mới, cố đóng các browser hiện có và dọn profile tạm. Các dòng dữ liệu đã append trước đó được giữ lại.

## Lưu ý chất lượng

Một lần crawl có thể gặp trang tải chậm, tin đã gỡ hoặc phản hồi thiếu dữ liệu. Khi cần kiểm tra parser, hãy giữ raw HTML/snapshot ngoài Git và đối chiếu với các báo cáo trong `analysis/`.
