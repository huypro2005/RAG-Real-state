# Crawl dữ liệu bất động sản

Pipeline thu thập link và dữ liệu bài đăng từ Batdongsan.com.vn.

README này giả định terminal đang được mở tại chính thư mục chứa các file:

```text
1_GetLinkNhaDat.py
2_LocDataLink.py
browser_runtime.py
crawl_data.py
listing_extractor.py
requirements.txt
```

## 1. Yêu cầu hệ thống

- Python 3.10 trở lên.
- Google Chrome đã được cài đặt.
- Kết nối Internet để truy cập website và tải ChromeDriver lần đầu.

Không cần tải ChromeDriver thủ công. `webdriver-manager` sẽ tìm/tải executable phù hợp; sau đó `undetected-chromedriver` patch và sử dụng executable đó.

Kiểm tra Python:

```powershell
python --version
```

Nếu lệnh `python` không tồn tại trên Windows, thử:

```powershell
py --version
```

## 2. Tạo môi trường ảo

Tại thư mục hiện tại, chạy:

```powershell
python -m venv venv
```

Nếu máy sử dụng lệnh `py`:

```powershell
py -m venv venv
```

Kích hoạt môi trường ảo trong PowerShell:

```powershell
.\venv\Scripts\Activate.ps1
```

Nếu PowerShell chặn script kích hoạt, chỉ mở quyền cho phiên terminal hiện tại rồi chạy lại:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\venv\Scripts\Activate.ps1
```

Khi kích hoạt thành công, đầu dòng lệnh thường xuất hiện `(venv)`.

## 3. Cài thư viện

Nâng cấp `pip` và cài dependencies:

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Các thư viện chính:

- `selenium`: cung cấp API WebDriver và các explicit wait.
- `undetected-chromedriver`: khởi chạy Chromium với ChromeDriver đã patch để giảm dấu hiệu automation.
- `webdriver-manager`: tự động tìm và tải ChromeDriver.
- `setuptools`: cung cấp lớp tương thích `distutils` mà `undetected-chromedriver` cần trên Python mới.
- `beautifulsoup4`: đọc link bài đăng từ HTML trang danh sách.

## 4. Bước 1 — Crawl link bài đăng

File thực thi:

```text
1_GetLinkNhaDat.py
```

Chạy mặc định từ trang 1 đến trang 25:

```powershell
python .\1_GetLinkNhaDat.py
```

Chọn trang bắt đầu và trang kết thúc:

```powershell
python .\1_GetLinkNhaDat.py `
  --start-page 100 `
  --end-page 200
```

Ví dụ cấu hình đầy đủ:

```powershell
python .\1_GetLinkNhaDat.py `
  --start-page 100 `
  --end-page 200 `
  --workers 6 `
  --retries 3 `
  --timeout 20 `
  --launch-delay 0.3
```

`--start-page` và `--end-page` đều được tính. Ví dụ `100` đến `200` sẽ crawl cả trang 100 và trang 200.

| Tham số | Mặc định | Ý nghĩa |
|---|---:|---|
| `--start-page` | `1` | Trang đầu tiên cần crawl |
| `--end-page` | `25` | Trang cuối cùng cần crawl |
| `--output` | `linkNhaDat.txt` | File lưu link |
| `--workers` | `6` | Số Chrome chạy đồng thời tối đa |
| `--retries` | `3` | Số lần thử lại cho mỗi trang |
| `--timeout` | `20` | Timeout tải trang, tính bằng giây |
| `--launch-delay` | `0.3` | Khoảng cách tối thiểu giữa hai lần mở Chrome, tính bằng giây |

Kết quả được append vào `linkNhaDat.txt`. Link đã tồn tại trong file sẽ không được ghi lại.

Để tiếp tục sau lần chạy trước, chọn trang bắt đầu mới:

```powershell
python .\1_GetLinkNhaDat.py --start-page 201 --end-page 400
```

## 5. Bước 2 — Extract dữ liệu từ link

File thực thi:

```text
2_LocDataLink.py
```

Extract toàn bộ link từ đầu:

```powershell
python .\2_LocDataLink.py
```

Extract bắt đầu từ link thứ 501:

```powershell
python .\2_LocDataLink.py --start-index 501
```

`--start-index` đếm từ `1` và được áp dụng sau khi chương trình bỏ dòng rỗng và link trùng trong `linkNhaDat.txt`.

Chạy thử 20 link, bắt đầu từ link thứ 501:

```powershell
python .\2_LocDataLink.py `
  --start-index 501 `
  --limit 20
```

Ví dụ cấu hình đầy đủ:

```powershell
python .\2_LocDataLink.py `
  --start-index 501 `
  --workers 6 `
  --retries 3 `
  --timeout 20 `
  --launch-delay 0.3
```

| Tham số | Mặc định | Ý nghĩa |
|---|---:|---|
| `--start-index` | `1` | Vị trí link đầu tiên cần xử lý, đếm từ 1 |
| `--limit` | Không giới hạn | Số link tối đa cần xử lý |
| `--input` | `linkNhaDat.txt` | File link đầu vào |
| `--output` | `data.json` | File dữ liệu đầu ra |
| `--workers` | `6` | Số Chrome chạy đồng thời tối đa |
| `--retries` | `3` | Số lần thử lại cho mỗi link |
| `--timeout` | `20` | Timeout tải bài đăng, tính bằng giây |
| `--launch-delay` | `0.3` | Khoảng cách tối thiểu giữa hai lần mở Chrome, tính bằng giây |

Kết quả:

- Bản ghi hợp lệ được append ngay vào `data.json`.
- Link lỗi hoặc bị bộ lọc loại được append vào `data_errors.json`.
- Mỗi dòng chứa một JSON object độc lập theo định dạng JSON Lines.
- Dữ liệu đã lưu vẫn được giữ nếu chương trình dừng giữa chừng.

Lưu ý: `data.json` dùng chế độ append. Chạy lại cùng một phạm vi link có thể tạo bản ghi trùng.

## 6. Chạy toàn bộ pipeline

`crawl_data.py` chạy bước lấy link trước, sau đó chạy bước extract.

Ví dụ crawl trang 100–200 rồi extract từ link thứ 501:

```powershell
python .\crawl_data.py `
  --start-page 100 `
  --end-page 200 `
  --start-index 501 `
  --workers 6 `
  --launch-delay 0.3
```

Chỉ chạy bước lấy link:

```powershell
python .\crawl_data.py `
  --start-page 100 `
  --end-page 200 `
  --skip-details
```

Chỉ chạy bước extract:

```powershell
python .\crawl_data.py `
  --start-index 501 `
  --skip-links
```

## 7. Dừng khẩn cấp

Nhấn:

```text
Ctrl+C
```

Chương trình sẽ:

- Ngăn mở thêm Chrome mới.
- Hủy các task chưa chạy.
- Đóng các Chrome profile đang hoạt động.
- Giữ nguyên link và dữ liệu đã append trước thời điểm dừng.

Khi khởi động, chương trình in PID, ví dụ:

```text
Crawler PID: 12345
```

Nếu `Ctrl+C` không dừng được chương trình, mở một cửa sổ PowerShell khác và kết thúc đúng cây tiến trình crawler bằng PID đã hiển thị:

```powershell
taskkill /PID 12345 /T /F
```

Trong đó:

- Thay `12345` bằng PID thực tế của lần chạy.
- `/T` kết thúc cả crawler và các tiến trình Chrome/ChromeDriver con.
- `/F` buộc tiến trình dừng ngay.

Không nên dùng `taskkill /IM python.exe /F` vì lệnh đó có thể tắt tất cả chương trình Python khác đang chạy trên máy. Khi buộc dừng bằng `taskkill`, bản ghi đã flush xuống file vẫn được giữ, nhưng tác vụ đang xử lý có thể chưa kịp lưu.

## 8. Xem tất cả tham số

```powershell
python .\1_GetLinkNhaDat.py --help
python .\2_LocDataLink.py --help
python .\crawl_data.py --help
```

## 9. Chạy lại ở lần sau

Mỗi khi mở terminal mới tại thư mục này, chỉ cần kích hoạt lại môi trường rồi chạy crawler:

```powershell
.\venv\Scripts\Activate.ps1
python .\1_GetLinkNhaDat.py --start-page 1 --end-page 25
```

Khi làm xong, có thể thoát môi trường ảo:

```powershell
deactivate
```
