# Hướng dẫn: viết pipeline làm sạch dữ liệu như dự án thực tế

Tài liệu giải thích vì sao [src/pipeline/listing_cleaner.py](../src/pipeline/listing_cleaner.py) được viết lại
thành một class, các dự án thực tế thường tổ chức code làm sạch dữ liệu thế nào, và cách đọc,
sửa, mở rộng class `ListingCleaner`.

## 1. Bản cũ sai ở đâu?

Bản đầu tiên có khoảng 15 hàm nhỏ cấp module: `clean_text`, `clean_label`, `parse_date`,
`number`, `legal_group`, `fix_area_thousands`, `reject_reason`, `clean_record`... Mỗi hàm chỉ vài
dòng, và `clean_record` gọi lần lượt từng hàm cho **từng tin một**.

Vấn đề:

- **Phải nhảy qua lại nhiều hàm mới hiểu một bước.** Muốn biết một tin bị loại vì sao, phải đọc
  `clean_record` → `number` → `fix_area_thousands` → `reject_reason`.
- **Hàm "nông".** Nhiều hàm chỉ bọc một hai dòng, dùng đúng một lần. Chúng thêm tên gọi nhưng
  không giấu được độ phức tạp nào.
- **Xử lý từng dòng bằng vòng lặp Python**, trong khi dữ liệu là một bảng. Với dữ liệu bảng,
  pandas xử lý cả cột một lượt: ngắn hơn và nhanh hơn.

## 2. Dự án thực tế làm thế nào?

### 2.1 "Hàm càng nhỏ càng tốt" không phải chân lý

Sách *Clean Code* (Robert Martin) khuyên chia nhỏ hàm cho tới khi mỗi hàm "chỉ làm một việc".
John Ousterhout (*A Philosophy of Software Design*) phản biện: chia quá nhỏ tạo ra các hàm
**nông**, tức giao diện gần phức tạp bằng phần ruột. Khi đó các hàm bị **dính chùm**: muốn hiểu
hàm này phải đọc cả hàm kia. Ông khuyên viết **module sâu**: giao diện đơn giản, bên trong làm
được nhiều việc. Hai tác giả đã tranh luận công khai về chính chủ đề này, và cả hai đều thừa nhận
có thể chia nhỏ quá mức.

Quy tắc thực dụng rút ra:

| Nên tách thành hàm/phương thức riêng khi | Không nên tách khi |
|---|---|
| Đoạn code là **một bước nghiệp vụ** có tên rõ ràng (chuẩn hóa, gắn cờ, loại tin) | Chỉ 1–3 dòng và dùng đúng một lần |
| Được gọi ở **nhiều nơi** | Người đọc vẫn phải mở ra xem mới hiểu nơi gọi |
| Cần **test riêng** | Tên hàm dài gần bằng code bên trong |

Khi không tách, dùng **comment một dòng** để đặt tên cho đoạn code. Hiệu quả tương đương mà
người đọc không phải nhảy đi đâu.

### 2.2 Dữ liệu bảng: xử lý theo cột, không theo dòng

Code làm sạch trong các dự án dữ liệu thường dùng pandas theo kiểu **vector hóa**: một câu lệnh
áp dụng cho cả cột.

```python
# Theo dòng (bản cũ): viết hàm, gọi cho từng tin
def number(value): ...
for raw in records: record['price'] = number(raw['price'])

# Theo cột (bản mới): một lệnh cho cả bảng
numbers = listings[NUMBER_COLUMNS].apply(pd.to_numeric, errors='coerce')
listings[NUMBER_COLUMNS] = numbers.where(numbers > 0)
```

### 2.3 Quy tắc khai báo dưới dạng dữ liệu

Thay vì một chuỗi `if ... return` dài, ta viết các quy tắc thành **bảng tên → điều kiện**. Người
đọc nhìn là thấy toàn bộ luật. Thêm hay bớt luật chỉ là thêm hay bớt một dòng.

```python
rules = {
    'missing_price': price.isna(),
    'area_too_small': area < self.MIN_AREA,
    ...
}
np.select(list(rules.values()), list(rules), default='')   # luật đầu tiên khớp thắng
```

Ngưỡng (`MIN_AREA`, `FIELD_MAX`, khung tọa độ...) là **thuộc tính của class** ở đầu file, không
rải rác trong code.

### 2.4 Tách đọc/ghi file khỏi logic

`run()` lo đọc và ghi file; `clean()` chỉ nhận list dict và trả về DataFrame. Nhờ vậy test gọi
thẳng `clean()` với dữ liệu giả, không cần file tạm. Đây là cách phổ biến để code dữ liệu dễ test.

### 2.5 Bước tiếp theo trong thực tế: kiểm tra schema

Các dự án lớn hơn thường thêm một lớp **validation schema** (ví dụ thư viện `pandera`) để khai báo
kiểu và miền giá trị của từng cột, rồi cho pipeline dừng sớm khi dữ liệu sai. Dự án hiện chưa cần.
Có thể cân nhắc khi crawler chạy định kỳ và cấu trúc dữ liệu có nguy cơ thay đổi.

## 3. Cấu trúc class `ListingCleaner`

```text
ListingCleaner
├── Hằng số cấu hình      OLD_HCM_DISTRICTS, HCM_LATITUDE/LONGITUDE, MIN_AREA,
│                         PRICE_PER_M2_RANGE, FIELD_MAX, LEGAL_GROUPS, *_COLUMNS
│
├── run(input, output)    Đọc JSON Lines → clean() → ghi 3 file + trả về báo cáo
└── clean(records)        Điều phối 4 bước, trả về (tin sạch, tin bị loại)
      ├── _normalize          Bước 1: text sạch khoảng trắng, số dương, ngày ISO, legal_group
      ├── _fix_and_flag       Bước 2: sửa diện tích kiểm chứng được, đặt None giá trị sai, gắn cờ
      ├── (bỏ trùng)          Bước 3: vài dòng ngay trong clean(), giữ tin đăng mới nhất
      └── _reject_reasons     Bước 4: bảng luật loại tin
```

Chỉ có **2 phương thức công khai** (`run`, `clean`) và **3 phương thức nội bộ**, mỗi phương
thức là một bước nghiệp vụ. Đọc `clean()` từ trên xuống là thấy cả luồng xử lý.

## 4. Cách sử dụng

Chạy tại thư mục gốc dự án:

```powershell
python -m src.pipeline.listing_cleaner               # chỉ làm sạch: đọc CrawlData/data.json, ghi data/listings/
python -m src.pipeline.listing_cleaner --input khac.json --output-dir data/listings_test
python -m src.pipeline                               # làm sạch + nạp PostgreSQL + embedding (mục 6)
python -m unittest discover -s src/tests -t .
```

Dùng trong code khác:

```python
from src.pipeline.listing_cleaner import ListingCleaner

clean, rejected = ListingCleaner().clean(records)    # records: list[dict] đọc từ crawler
```

## 5. Sửa và mở rộng

| Muốn… | Sửa ở đâu |
|---|---|
| Đổi ngưỡng (diện tích tối thiểu, số tầng tối đa...) | Hằng số đầu class |
| Thêm luật loại tin | Thêm một dòng vào `rules` trong `_reject_reasons` (thứ tự = độ ưu tiên) |
| Thêm cờ chất lượng | Thêm một dòng vào `flags` trong `_fix_and_flag`; cần xóa giá trị thì thêm `.mask(...)` |
| Thêm nhóm pháp lý | Thêm một cặp vào `LEGAL_GROUPS` (xét theo thứ tự) |
| Thêm cột đầu ra | Thêm vào `OUTPUT_COLUMNS` |
| **Bật lọc tin hết hạn** | Trong `_reject_reasons`, bỏ comment dòng `'expired': ...` và đặt `as_of` là ngày chạy dạng `'yyyy-mm-dd'`. Nhớ sửa test `test_expired_listing_is_kept` |

Nguyên tắc khi sửa: **không suy đoán dữ liệu**. Giá trị sai thì đặt `None` và gắn cờ, hoặc loại
tin, chứ không tự điền. Bản gốc luôn nằm trong `raw_record` để đối chiếu.

## 6. Pipeline đầy đủ: đưa tin vào database cho RAG

```text
CrawlData/data.json
   │  ListingCleaner     src/pipeline/listing_cleaner.py   làm sạch, bỏ trùng, loại tin lỗi
   ▼
listing.listings         ListingLoader  (listing_loader.py) upsert theo listing_id
listing.listing_spatial_features        6 biến đếm POI 1 km/3 km + POI gần nhất (hàm SQL)
   │  ListingEmbedder    listing_embedder.py               dựng document, gọi API embedding
   │        ▲ HTTPS
   │        └── Kaggle GPU: src/kaggle/embedding_server.ipynb (BAAI/bge-m3 + Cloudflare Tunnel)
   ▼
rag.listing_embeddings   embedding_text, rag_document, vector(1024)
```

Mỗi bước là một class, cùng tinh thần với `ListingCleaner`. `src/pipeline/__main__.py` chỉ nối
các bước lại với nhau. Schema nằm ở [src/pipeline/schema.sql](../src/pipeline/schema.sql).

**Model không chạy trên máy cá nhân.** Notebook Kaggle nạp `BAAI/bge-m3` lên GPU và mở API qua
Cloudflare Tunnel. Máy cá nhân chỉ gửi text và nhận vector về.

**Cài đặt một lần** (cần PostGIS và pgvector trong database, xem [setup-postgis-pgvector.md](setup-postgis-pgvector.md)):

```powershell
python -m pip install -r src/requirements.txt
```

**Chạy:**

1. Mở [src/kaggle/embedding_server.ipynb](../src/kaggle/embedding_server.ipynb) trên Kaggle
   (*File → Import Notebook*), bật GPU và Internet, rồi *Run All*. Hướng dẫn chi tiết nằm ở ô đầu notebook.
2. Chép hai dòng notebook in ra vào file `.env` ở máy cá nhân (file đã được gitignore), cùng mật khẩu database:

   ```text
   PGPASSWORD=...
   EMBEDDING_API_URL=https://xxxx.trycloudflare.com
   EMBEDDING_API_KEY=...
   ```

3. Chạy pipeline, rồi *Stop session* trên Kaggle khi xong:

   ```powershell
   python -m src.pipeline                 # làm sạch + nạp DB + tính POI + embed qua API Kaggle
   python -m src.pipeline --skip-embed    # không cần Kaggle: chỉ làm sạch + nạp DB + tính POI
   ```

URL tunnel đổi mỗi lần chạy lại notebook, nên phải cập nhật `EMBEDDING_API_URL`. Nếu tunnel đứt
giữa chừng, client tự thử lại 3 lần. Các lô đã embed được commit ngay, nên chạy lại pipeline sẽ
tiếp tục từ chỗ dừng.

Những điểm cần biết:

- **Chạy lại an toàn.** Tin đã có được cập nhật, không nhân bản. Tin không còn trong file mới
  vẫn giữ trong database (không xóa lịch sử).
- **Embedding tăng dần.** Chỉ embed lại tin có `content_hash` thay đổi (tiêu đề, mô tả, loại,
  khu vực hoặc model). Giá hay POI đổi thì chỉ cập nhật `rag_document`, không tốn GPU.
- **Hai loại text cho mỗi tin.** `embedding_text` chỉ gồm phần ngữ nghĩa (loại, khu vực, tiêu đề,
  mô tả, đã bỏ số điện thoại). `rag_document` đầy đủ giá, diện tích, pháp lý, địa chỉ cũ/mới,
  tiện ích, ngày đăng và link, dùng để đưa cho LLM. Giá và diện tích **không** đưa vào vector,
  vì SQL lọc chính xác hơn.
- **Tin hết hạn vẫn được nạp.** Cột `expired_at` có sẵn và có index. Khi làm phần tìm kiếm, lọc
  `expired_at >= current_date` để chỉ gợi ý tin còn hiệu lực.

## Nguồn tham khảo

- [John Ousterhout & Robert Martin – tranh luận APOSD vs Clean Code](https://github.com/johnousterhout/aposd-vs-clean-code)
- [Deep vs shallow modules – Sandor Dargo](https://www.sandordargo.com/blog/2023/01/25/deep-vs-shallow-modules)
- [Modules Should Be Deep – Software Engineering: A Modern Approach](https://softengbook.org/articles/deep-modules)
- [Review "A Philosophy of Software Design" – Henrik Warne](https://henrikwarne.com/2021/07/12/book-review-a-philosophy-of-software-design/)
- [Automated data cleaning pipelines with pandas – KDnuggets](https://www.kdnuggets.com/creating-automated-data-cleaning-pipelines-using-python-and-pandas)
- [Clean and validate your data using Pandera – KDnuggets](https://www.kdnuggets.com/clean-and-validate-your-data-using-pandera)
