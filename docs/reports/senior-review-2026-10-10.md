# Báo cáo đánh giá của senior dev — 10/10/2026

Đối tượng đọc: chủ đồ án (người quyết định việc tiếp theo). Phạm vi: toàn bộ phần đã làm — database địa chỉ, pipeline dữ liệu,
chat gợi ý (recommendation), chat dự đoán giá (prediction), giao diện demo. Mọi con số dưới đây do main tự chạy lại hôm nay
(`pytest` 481 xanh/103 bỏ qua do cần OpenAI, ruff sạch, `src/tests` 20 xanh, frontend 8 test + build xanh) hoặc lấy từ báo cáo
của tester/reviewer độc lập; số nào chưa kiểm lại thì nói rõ.

## 1. Kết luận ngắn

Phần **kỹ thuật lõi chắc**: database sạch, pipeline chạy lặp được, hai chế độ chat chạy thật qua API, có bộ test nhiều lớp.
Phần **chưa sẵn sàng đem demo/nộp**: dữ liệu tin đăng đã quá hạn gần hết, database thật (`housing`) chưa được chuyển sang
thiết kế mới, toàn bộ công việc chưa được commit, và mô hình dự đoán giá chỉ ở mức đồ án 1 (R² ≈ 0,57).
Nếu chỉ làm 3 việc tiếp theo: (1) commit + ignore đúng, (2) crawl lại dữ liệu, (3) áp DB thật.

## 2. Những phần tốt (giữ nguyên)

| Phần | Vì sao tốt | Bằng chứng |
|---|---|---|
| Thiết kế database | Mọi bảng ở `public`, khoá chính là ID batdongsan, không lưu `raw_record`/hash; mapping phường cũ→mới dùng mã chính thức; hàm SQL tách rõ việc | reviewer PASS toàn bộ tiêu chí; pipeline nạp 2 lần không đổi dòng nào (7.603 / 7.603 không đổi) |
| Nguyên tắc "code quyết định, LLM chỉ trích xuất" | Quy tắc reset, tham chiếu "căn thứ N", giá xấp xỉ, từ chối thuê/tỉnh khác, xác nhận "ok" nằm trong code → kiểm thử được, không bịa | các lỗi LLM tự quyết (reset nhầm, từ chối nhầm) đều bị bắt rồi chuyển về code |
| Hybrid search | Lọc cứng SQL + PostGIS + pgvector + lexical, gom tin đăng lại, có chế độ dự phòng khi Kaggle tắt | 50 kịch bản/174 lượt: điều kiện cứng 129/129, trích điều kiện 542/542 (kết quả vòng chấm trước) |
| Quy trình hai agent + main duyệt cuối | Mỗi lỗi nặng đều được tìm ra bằng thử thật, không tin báo cáo; có tiêu chí mã hoá ([S1]…, [P1]…) | prediction qua 5 vòng; reviewer tìm ra lỗi do chính refactor gây ra (mất state khi khởi động nguội) |
| Bộ test nhiều lớp | unit, kịch bản hội thoại, 20 ca thực tế có chuẩn giá lấy từ dữ liệu thật, test chạy song song | 481 test, 20 ca thực tế: 18 PASS + 1 PASS-biên + 1 giới hạn đã biết |
| Tài liệu điều hành | `STATUS.md` là điểm vào duy nhất; spec có tiêu chí nghiệm thu | tiếp tục được sau mỗi lần nén ngữ cảnh |

## 3. Phần chưa tốt, xếp theo mức độ

### Nghiêm trọng (chặn demo/nộp)

1. **Chưa có commit nào cho toàn bộ công việc mới.** `git log` vẫn dừng ở commit cũ; hàng chục thư mục là `??` (untracked). Máy hỏng là mất hết. `.gitignore` gốc còn bị comment gần như toàn bộ (venv, `__pycache__`…), nên `git add .` sẽ kéo cả rác (`.codex_tmp/`, `housing-backend.zip`, `a.py`, `__pycache__`). → Làm sạch rồi commit từng cụm.
2. **Dữ liệu tin đăng đã hết hạn.** Ngày 22/09 chỉ 186/7.603 tin còn hiệu lực; hôm nay (10/10) còn ít hơn nữa. Hậu quả đã thấy khi đóng vai khách: "căn hộ Bình Thạnh tầm 3 tỷ" trả `no_results`. Các bài test dùng `as_of = 22/09/2026` nên **che mất vấn đề này**. Pipeline cũng đang tắt bộ lọc tin hết hạn. → Crawler định kỳ (GĐ3) là việc khẩn nhất để chatbot gợi ý có ý nghĩa.
3. **Database thật `housing` chưa chuyển sang thiết kế mới.** Mọi thứ chỉ kiểm trên `housing_dev`; `housing` vẫn là 5 schema cũ. Cấu hình mặc định (`config.py`) còn trỏ vào `housing` thật và chứa mật khẩu Postgres dạng chữ. Cách áp dụng đã có sẵn ở `STATUS.md` mục 2.1b (bạn tự chạy hoặc cấp quyền).
4. **Khoá bí mật.** Khoá OpenAI và khoá Goong từng được dán vào hội thoại → nên xoay (rotate) khoá. Khoá Goong của bạn hiện chỉ gọi được API địa chỉ; bản đồ nền Goong trả 403 (cần "maptiles key" riêng).

### Cao

5. **Chất lượng mô hình dự đoán giá còn thấp.**
   - R² = 0,5695 trên giá/m² (0,80 trên log). Khoảng 1/5 dự đoán lệch hơn 30%; mô hình "co" biên độ (ví dụ mặt phố Quận 1 từng ra 254 triệu/m² trong khi tin thật có median 460).
   - Cần Giờ/Q9 đông ít dữ liệu: biệt thự Cần Giờ 400 m² ra 48,9 trong khi tin thật 103–168; hệ thống chỉ cảnh báo, không sửa được số.
   - Khoảng "tham khảo" (phân vị 10–90 của các cây) chỉ phủ 71,8% dù mang nhãn 80% → đã đổi nhãn cho trung thực, nhưng chưa phải khoảng tin cậy thật.
   - Thiếu đặc trưng của đồ án 2 (số bệnh viện/trường/chợ trong 1 km, 3 km — đang là `TODO`).
   - Đã mở khung lọc toạ độ train (thêm 2.705 dòng Q9/Thủ Đức/Cần Giờ); đây là điểm khác duy nhất so với đồ án 1, đã ghi trong README.
6. **Hai chế độ chat dùng hai nguồn dữ liệu khác nhau.** Gợi ý dùng 7.603 tin trong DB đồ án 2; dự đoán dùng `data.csv` 24 nghìn dòng của đồ án 1 (thời điểm, độ phủ khác). Câu "giá/m² trung vị quận" trong dự đoán lấy từ dữ liệu train, không phải dữ liệu đang có trong DB → hai chế độ có thể nói hai con số khác nhau cho cùng quận.
7. **Geocoding phụ thuộc Goong và hạn mức ngày.** Hạn mức 1.000 lượt/ngày đã bị test dùng hết; khi lỗi, hệ thống rơi về tâm quận (đúng thiết kế, có ghi chú trong câu trả lời) nhưng độ chính xác giảm. 8 ca thực tế có địa chỉ cụ thể **chưa được xác nhận bằng Goong thật**; một nhánh mới (thử thêm tiền tố "chung cư …") mới chỉ có unit test. Nên chạy lại bộ 20 ca khi hạn mức hồi phục. Hướng bền hơn: dùng toạ độ có sẵn trong bảng `listings` cho dự án/chung cư đã biết.
8. **Phụ thuộc dịch vụ ngoài mong manh.** Embedding chạy trên Kaggle qua đường hầm Cloudflare, URL/khoá đổi mỗi lần bật notebook. Có chế độ dự phòng (không embedding) nên chat vẫn chạy, nhưng chất lượng thứ tự gợi ý thấp hơn. OpenAI từng timeout 1 lần trong lúc chạy thật; chưa có chính sách thử lại/hạ cấp rõ ràng.

### Trung bình

9. **Trạng thái hội thoại nằm trong bộ nhớ một tiến trình.** Mất khi khởi động lại, không chạy được nhiều worker; kho hội thoại của recommendation **không giới hạn số lượng** (rò bộ nhớ), prediction có LRU 1.000. Chưa có xác thực hay giới hạn tần suất gọi API (mỗi lượt tốn tiền OpenAI).
10. **Một số mùi thiết kế** (agent clean code ghi nhận, chưa sửa): `ChatSupport` (`map.py`) ghép hai việc không liên quan; `ModeChatRequest` lặp `ChatRequest`; hai hàm chuẩn hoá tiếng Việt gần giống nhau (`plain` / `fold`); hai cách cắt tin nhắn dài khác nhau giữa hai chế độ; `PricePredictor.find_district` đặt sai tầng.
11. **Trần số dòng mang tính hình thức.** Recommendation nằm sát trần 1.898/1.900 (từng phải chuyển `EmbeddingClient` sang file khác để lách); prediction 1.043 dòng so với trần 600 ban đầu (đã chấp nhận vì thêm tính năng được yêu cầu). Trần số dòng không phải thước đo sạch; nên thay bằng giới hạn độ dài hàm và độ phức tạp.
12. **Báo cáo 50 kịch bản đã bị ghi đè.** `run_eval.py --ids …` ghi đè `tests/recommend/report.md` và `last_run*.json`; file hiện tại chỉ phản ánh 4 kịch bản vừa chạy. Cần chạy lại đủ 50 kịch bản để có báo cáo chốt (tốn tiền OpenAI, bạn cho phép thì mình chạy).
13. **103 test cần OpenAI bị bỏ qua mặc định**, không có CI. Test hồi quy thực sự cho hành vi chat nằm ở các script chạy tay (`run_live.py`, `run_realistic.py`, `run_eval.py`).
14. **Giao diện demo** chưa được mở bằng trình duyệt thật (chỉ kiểm bằng script + build + 8 test); mode dự đoán mới nối với backend thật ở mức API. Bản đồ dùng ô OSM của bên thứ ba, không bảo đảm uptime.

### Nhỏ

15. `AGENTS.md` còn ghi "Task hiện tại: làm lại database địa chỉ" ở trên cùng (đã lạc hậu; có dòng trỏ tới `STATUS.md`).
16. Pipeline: `--skip-embed` đã bỏ (đổi thành `--embed` opt-in) — script cũ gọi cờ cũ sẽ lỗi; `data1.json` có thêm 68 tin chưa nạp; chưa cảnh báo khi `--db-url` trỏ vào `housing` thật.
17. Còn vài lỗi nhỏ của prediction đã biết, chấp nhận được: "5x20"/"tám mươi mét vuông" có hỗ trợ nhưng chưa kiểm hết biến thể; tỉnh lạ (Phú Quốc, Phan Thiết) bị hỏi lại quận chứ không từ chối thẳng.

## 4. Đề xuất thứ tự việc tiếp theo

| # | Việc | Lý do | Ai làm |
|---|---|---|---|
| 1 | Sửa `.gitignore`, dọn rác, commit theo cụm (DB, pipeline, recommend, prediction, frontend, docs) | mất công việc nếu hỏng máy | main + bạn duyệt trước khi commit |
| 2 | Crawl lại dữ liệu + bật lọc tin còn hạn trong pipeline | chatbot gợi ý hiện gần như không có tin hợp lệ | agent code (crawler GĐ3) |
| 3 | Áp thiết kế mới lên DB `housing`, đổi mặc định cấu hình khỏi mật khẩu cứng | hiện chỉ có `housing_dev` | **bạn** chạy lệnh ở `STATUS.md` 2.1b hoặc cấp quyền |
| 4 | Xoay khoá OpenAI/Goong; xin maptiles key nếu cần bản đồ Goong | khoá đã lộ trong hội thoại | bạn |
| 5 | Chạy lại đủ 50 kịch bản + 20 ca thực tế (khi Goong hồi hạn mức) để có báo cáo chốt | báo cáo hiện bị ghi đè; 8 ca chưa xác nhận bằng Goong | tester |
| 6 | Thêm đặc trưng bán kính 1 km/3 km cho dự đoán; cân nhắc dùng dữ liệu DB đồ án 2 để train | khoảng cách chính với đồ án 2, cải thiện R² | agent code + tester |
| 7 | Dọn thiết kế (mục 10), giới hạn kho hội thoại, thêm rate-limit | độ bền | agent code |
| 8 | Mở giao diện bằng trình duyệt, chụp màn hình cho báo cáo | chưa kiểm bằng mắt | bạn/main |

## 5. Lời nhắn về cách trình bày với giảng viên

Điểm mạnh nên nhấn: (a) tách "hiểu câu" (LLM) khỏi "quyết định" (code) để chatbot không bịa; (b) bộ kiểm thử có chuẩn đối chiếu
từ dữ liệu thật; (c) quy trình lặp coder–reviewer có bằng chứng. Điểm cần nói thật: R² ≈ 0,57 là mức của đồ án 1, dữ liệu
tin đăng cần cập nhật, và khu vực ít dữ liệu (Cần Giờ, Q9 đông) kém tin cậy — hệ thống đã cảnh báo thay vì che.
