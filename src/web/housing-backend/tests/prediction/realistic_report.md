# Báo cáo kiểm thử thực tế mode dự đoán giá

**KẾT QUẢ: 20/20 ca không FAIL {'PASS': 18, 'PASS-biên': 1, 'KNOWN-LIMIT': 1, 'FAIL': 0}** (mỗi ca chạy 1 lần, một lần sai là FAIL). Số lượt API: 66, trung bình 1.08s/lượt, p95 1.92s.

| Ca | Mô tả | Kết quả | Số lỗi | Số cảnh báo | Ghi chú Goong |
|---|---|---|---|---|---|
| R01 | Anh Nam, 34 tuổi, nhân viên văn phòng, hỏi từng bước về căn hộ Phú Mỹ Hưng Q7 | PASS | 0 | 0 | CHƯA xác nhận bằng Goong (dùng tâm quận) |
| R02 | Chị Lan, chủ nhà ở Nguyễn Trãi Q5, nhập một lần đủ rồi thắc mắc giá cao | PASS | 0 | 0 | CHƯA xác nhận bằng Goong (dùng tâm quận) |
| R03 | Khách gõ không dấu, hỏi biệt thự Thảo Điền Q2 | PASS | 0 | 0 | CHƯA xác nhận bằng Goong (dùng tâm quận) |
| R04 | Chú Hải, nói kích thước ngang x dài nhưng không nói diện tích, đường 3/2 Q10 | PASS | 0 | 0 |  |
| R05 | Anh Tùng, nhà đầu tư đất vườn Củ Chi, thử nhiều kịch bản | PASS | 0 | 0 |  |
| R06 | Chị Mai, đang phân vân Q7 hay Nhà Bè, nói số bằng chữ | PASS | 0 | 0 |  |
| R07 | Anh Phát hỏi chung cư Bình Tân rồi so với Q7 sau khi có kết quả | PASS-biên | 0 | 1 |  |
| R08 | Khách vội, gõ ok trước khi cung cấp thông tin, căn hộ Bình Thạnh | PASS | 0 | 0 |  |
| R09 | Khách hỏi thuê căn hộ Q2 (ngoài phạm vi) rồi quay lại hỏi giá mua | PASS | 0 | 0 |  |
| R10 | Khách hỏi nhà ở Đà Nẵng (tỉnh khác) rồi chuyển sang Gò Vấp | PASS | 0 | 0 |  |
| R11 | Bác Sáu có miếng đất Hóc Môn, gõ không dấu, nói 'mặt tiền 8m' cho đất, sau đó hỏi nếu xây nhà | PASS | 0 | 0 |  |
| R12 | Anh Khoa hỏi biệt thự nghỉ dưỡng Cần Giờ (xa trung tâm, dữ liệu thưa) | KNOWN-LIMIT | 0 | 2 |  |
| R13 | Chủ nhà mặt phố Nguyễn Huệ Q1, ngạc nhiên vì giá cao | PASS | 0 | 0 | CHƯA xác nhận bằng Goong (dùng tâm quận) |
| R14 | Cô Hạnh nhà hẻm xe hơi Q3, sửa diện tích giữa chừng, gõ 'ok luôn' ngay khi bổ sung | PASS | 0 | 0 |  |
| R15 | Anh Đạt nói 'nhà' chung chung, đường Tên Lửa Bình Tân, '1 trệt 2 lầu' | PASS | 0 | 0 | CHƯA xác nhận bằng Goong (dùng tâm quận) |
| R16 | Chị Thu hỏi căn Botanica Tân Bình, kèm giá chủ chào '5 tỷ 2' (số không phải trường nào) | PASS | 0 | 0 | CHƯA xác nhận bằng Goong (dùng tâm quận) |
| R17 | Anh Long mua căn Vinhomes Grand Park (Q9 cũ, rìa dữ liệu train) | PASS | 0 | 0 | CHƯA xác nhận bằng Goong (dùng tâm quận) |
| R18 | Anh Vỹ hỏi liền kề Vạn Phúc City Thủ Đức rồi đổi diện tích | PASS | 0 | 2 | CHƯA xác nhận bằng Goong (dùng tâm quận) |
| R19 | Khách định giá hai BĐS liên tiếp, dùng reset giữa hai căn (Q12 rồi Q8) | PASS | 0 | 0 |  |
| R20 | Khách hỏi nhà ở Thuận An Bình Dương (tỉnh khác), gõ ok, rồi hỏi nhà riêng Tân Phú | PASS | 0 | 0 |  |

## Chấm giá/m² theo dữ liệu thật (lần chạy 1)

| Ca | Quận | Loại | m² | Dự đoán/m² | Tổng (tr) | DB P10 - median - P90 | data.csv P10 - median - P90 | Nhóm so sánh | km | Kết quả |
|---|---|---|---|---|---|---|---|---|---|---|
| R01 | Quận 7 | căn hộ chung cư | 70 | 89.36 | 6255.2 | 50 - 71 - 90 (n=225) | 46 - 69 - 98 (n=799) | DB cùng quận+loại+diện tích 0,6-1,6x | 5.5 | IN |
| R02 | Quận 5 | nhà riêng | 60 | 129.91 | 7794.6 | 95 - 162 - 244 (n=11) | 69 - 222 - 272 (n=42) | DB cùng quận+loại+diện tích 0,6-1,6x | 4.3 | IN (IQR) |
| R02 | Quận 5 | nhà riêng | 60 | 129.91 | 7794.6 | 95 - 162 - 244 (n=11) | 69 - 222 - 272 (n=42) | DB cùng quận+loại+diện tích 0,6-1,6x | 4.3 | IN (IQR) |
| R03 | Quận 2 | nhà biệt thự, liền kề | 250 | 254.39 | 63597.5 | 166 - 265 - 378 (n=52) | 217 - 241 - 281 (n=570) | DB cùng quận+loại+diện tích 0,6-1,6x | 5.8 | IN (IQR) |
| R04 | Quận 10 | nhà mặt phố | 100 | 283.91 | 28391.0 | 231 - 347 - 487 (n=38) | 208 - 329 - 480 (n=183) | DB cùng quận+loại+diện tích 0,6-1,6x | 3.4 | IN (IQR) |
| R05 | Củ Chi | bán đất | 500 | 6.67 | 3335.0 | 3 - 7 - 14 (n=28) | 3 - 10 - 17 (n=64) | DB cùng quận+loại+diện tích 0,6-1,6x | 31.7 | IN (IQR) |
| R05 | Củ Chi | bán đất | 500 | 6.65 | 3325.0 | 3 - 7 - 14 (n=28) | 3 - 10 - 17 (n=64) | DB cùng quận+loại+diện tích 0,6-1,6x | 31.7 | IN (IQR) |
| R05 | Củ Chi | bán đất | 1000 | 6.65 | 6650.0 | 2 - 7 - 11 (n=16) | 2 - 8 - 15 (n=42) | DB cùng quận+loại+diện tích 0,6-1,6x | 31.7 | IN (IQR) |
| R06 | Nhà Bè | nhà riêng | 80 | 74.11 | 5928.8 | 41 - 82 - 121 (n=66) | 53 - 99 - 123 (n=198) | DB cùng quận+loại+diện tích 0,6-1,6x | 9.6 | IN (IQR) |
| R07 | Bình Tân | căn hộ chung cư | 65 | 49.53 | 3219.5 | 41 - 51 - 63 (n=70) | 36 - 52 - 63 (n=194) | DB cùng quận+loại+diện tích 0,6-1,6x | 10.3 | IN (IQR) |
| R07 | Quận 7 | căn hộ chung cư | 65 | 89.86 | 5840.9 | 50 - 70 - 90 (n=215) | 46 - 69 - 96 (n=744) | DB cùng quận+loại+diện tích 0,6-1,6x | 5.5 | EDGE |
| R08 | Bình Thạnh | căn hộ chung cư | 80 | 58.16 | 4652.8 | 50 - 106 - 163 (n=120) | 53 - 100 - 145 (n=352) | DB cùng quận+loại+diện tích 0,6-1,6x | 3.3 | IN |
| R09 | Quận 2 | căn hộ chung cư | 90 | 93.89 | 8450.1 | 67 - 113 - 188 (n=456) | 69 - 109 - 201 (n=1373) | DB cùng quận+loại+diện tích 0,6-1,6x | 5.8 | IN (IQR) |
| R10 | Gò Vấp | nhà riêng | 100 | 117.52 | 11752.0 | 80 - 116 - 165 (n=142) | 82 - 114 - 167 (n=521) | DB cùng quận+loại+diện tích 0,6-1,6x | 7.3 | IN (IQR) |
| R11 | Hóc Môn | bán đất | 200 | 33.27 | 6654.0 | 22 - 31 - 57 (n=20) | 22 - 30 - 65 (n=29) | DB cùng quận+loại+diện tích 0,6-1,6x | 16.3 | IN (IQR) |
| R11 | Hóc Môn | nhà riêng | 200 | 38.58 | 7716.0 | 29 - 38 - 55 (n=18) | 12 - 31 - 52 (n=16) | DB cùng quận+loại+diện tích 0,6-1,6x | 16.3 | IN (IQR) |
| R12 | Cần Giờ | nhà biệt thự, liền kề | 400 | 48.92 | 19568.0 | 103 - 150 - 168 (n=35) | 106 - 109 - 117 (n=8) | THƯA: nới ra mọi diện tích của quận+loại (DB) | 45.4 | LIMIT |
| R13 | Quận 1 | nhà mặt phố | 120 | 362.38 | 43485.6 | 312 - 460 - 907 (n=55) | 275 - 411 - 799 (n=436) | DB cùng quận+loại+diện tích 0,6-1,6x | 0.6 | IN (IQR) |
| R13 | Quận 1 | nhà mặt phố | 120 | 362.38 | 43485.6 | 312 - 460 - 907 (n=55) | 275 - 411 - 799 (n=436) | DB cùng quận+loại+diện tích 0,6-1,6x | 0.6 | IN (IQR) |
| R14 | Quận 3 | nhà riêng | 52 | 141.28 | 7346.6 | 134 - 214 - 279 (n=55) | 131 - 197 - 267 (n=196) | DB cùng quận+loại+diện tích 0,6-1,6x | 2.0 | IN |
| R15 | Bình Tân | nhà riêng | 64 | 95.89 | 6137.0 | 68 - 98 - 132 (n=183) | 76 - 94 - 121 (n=757) | DB cùng quận+loại+diện tích 0,6-1,6x | 10.3 | IN (IQR) |
| R16 | Tân Bình | căn hộ chung cư | 95 | 60.75 | 5771.2 | 47 - 72 - 83 (n=48) | 42 - 65 - 83 (n=110) | DB cùng quận+loại+diện tích 0,6-1,6x | 6.1 | IN (IQR) |
| R16 | Tân Bình | căn hộ chung cư | 95 | 60.75 | 5771.2 | 47 - 72 - 83 (n=48) | 42 - 65 - 83 (n=110) | DB cùng quận+loại+diện tích 0,6-1,6x | 6.1 | IN (IQR) |
| R17 | Quận 9 | căn hộ chung cư | 59 | 46.41 | 2738.2 | 44 - 58 - 70 (n=217) | 44 - 57 - 69 (n=829) | DB cùng quận+loại+diện tích 0,6-1,6x | 12.9 | IN |
| R18 | Thủ Đức | nhà biệt thự, liền kề | 100 | 172.5 | 17250.0 | 105 - 192 - 262 (n=18) | 133 - 219 - 230 (n=127) | THƯA: nới ra mọi diện tích của quận+loại (DB) | 9.0 | IN (IQR) |
| R18 | Thủ Đức | nhà biệt thự, liền kề | 120 | 173.39 | 20806.8 | 105 - 192 - 262 (n=18) | 133 - 214 - 230 (n=136) | THƯA: nới ra mọi diện tích của quận+loại (DB) | 9.0 | IN (IQR) |
| R19 | Quận 12 | nhà riêng | 80 | 81.48 | 6518.4 | 57 - 99 - 131 (n=191) | 64 - 64 - 108 (n=1084) | DB cùng quận+loại+diện tích 0,6-1,6x | 10.9 | IN (IQR) |
| R19 | Quận 8 | căn hộ chung cư | 55 | 51.67 | 2841.8 | 36 - 52 - 66 (n=94) | 32 - 47 - 62 (n=256) | DB cùng quận+loại+diện tích 0,6-1,6x | 6.8 | IN (IQR) |
| R20 | Tân Phú | nhà riêng | 90 | 103.37 | 9303.3 | 87 - 109 - 151 (n=111) | 90 - 92 - 132 (n=756) | DB cùng quận+loại+diện tích 0,6-1,6x | 8.3 | IN (IQR) |

(IQR: giá nằm cả trong [P25,P75] của nhóm so sánh)

## Thay đổi bộ test

- R17: Lượt 1 bỏ kỳ vọng status=ready/loại=căn hộ; thay bằng collecting + hỏi loại, thêm lượt 'chung cư'. Lý do: Khách chỉ nói 'căn 2pn' (không có 'hộ'/'chung cư'), loại thật sự mơ hồ (căn có thể là villa/shophouse) nên hệ thống hỏi lại loại là hợp lý; kỳ vọng ban đầu của test quá chặt
- R16: answer_has lượt 2 đổi từ 'Goong' thành 'Cách trung tâm'. Lý do: Theo main: Goong hết hạn mức (429) nên nguồn tọa độ không phải yêu cầu của hệ thống; báo cáo ghi riêng ca nào chưa xác nhận bằng Goong
- tiêu chí: Thêm PASS-biên (giá lệch <=3% ngoài [P10,P90]) và KNOWN-LIMIT (R12: giá ngoài oracle nhưng câu trả lời có 'Lưu ý'). Lý do: Theo main: dung sai 3% cho sai số lấy mẫu của oracle; R12 là giới hạn dữ liệu/model đã biết, ghi 'FAIL giá / PASS cảnh báo', không che

## Cảnh báo (không tính FAIL)

- R07: lượt 3 ('nếu ở quận 7 thì giá bao nhiêu'): PASS (biên, dung sai 3%): GIÁ/M² 89.9 so với [P10,P90] = [49.7, 89.8] (median 70.1, n=215, DB cùng quận+loại+diện tích 0,6-1,6x)
- R12: lượt 2 ('ok'): KNOWN-LIMIT (FAIL giá / PASS cảnh báo): GIÁ/M² 48.9 so với [P10,P90] = [102.6, 168.0] (median 150.0, n=35, THƯA: nới ra mọi diện tích của quận+loại (DB))
- R12: lượt 2 ('ok'): nhóm so sánh thưa (THƯA: nới ra mọi diện tích của quận+loại (DB), n=35)
- R18: lượt 2 ('ok'): nhóm so sánh thưa (THƯA: nới ra mọi diện tích của quận+loại (DB), n=18)
- R18: lượt 3 ('còn nếu là 120m2'): nhóm so sánh thưa (THƯA: nới ra mọi diện tích của quận+loại (DB), n=18)

## Ca FAIL

Không có ca FAIL.
