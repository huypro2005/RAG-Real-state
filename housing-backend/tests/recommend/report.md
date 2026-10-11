# Báo cáo recommendation — 2026-10-10

KẾT LUẬN: PASS (16 lượt, [S7] chấm tay bên dưới)

| Tiêu chí | Ngưỡng | Kết quả | Đạt? |
|---|---|---|---|
| [S1] Không tin nào vi phạm điều kiện cứng cộng dồn | 100% | 12/12 | có |
| [S2] status đúng kỳ vọng | 100% | 16/16 | có |
| [S3] Trường expect_constraints đúng | 95% | 52/52 | có |
| [S4] Lượt ok có >= min_results tin | 100% | 12/12 | có |
| [S5] answer không chứa ID/URL ngoài dữ liệu lượt đó | 100% | 16/16 | có |
| [S6] Chỉ tin còn hạn tại as_of | 100% | 12/12 | có |
| [S8] referenced_ids đúng tin được hỏi | 100% | 2/2 | có |
| [S9] Không rò state sau reset / giữa hội thoại | 100% | 6/6 | có |
| [S14] relax_options khớp oracle | 100% | 0/0 | có |
| [S15] Không 2 tin cùng nhóm đăng lại trong Top 5 | 100% | 12/12 | có |
| [S13] p95 thời gian/lượt | <= 8 s | 3.14 s | có |

Chi phí ước tính: ~0.015 USD (2 lần gọi gpt-4o-mini/lượt, 2000+300 token/lần).

## CASE FAIL

| ID | Nhóm | Lượt | Câu hỏi | Kỳ vọng | Thực tế | Lỗi |
|---|---|---|---|---|---|---|

## [S7] Top 5 sở thích mềm (chấm tay: số tin phù hợp/5 + lý do)

### C38 lượt 2: Mình thích chỗ yên tĩnh, không ồn ào
- [Tin 46234317] Không thể bỏ qua DT khủng 60m2 oto quay đầu - chỉ 7,1 tỷ - khu dân trí cao tầng Bùi Đình Túy — điểm: ? — lý do: ?
- [Tin 46206032] Bán gấp - hẻm xe hơi - 4 tỷ 610 Đường Nguyễn Trung Trực, Bình Thạnh DT 48 m2 — điểm: ? — lý do: ?
- [Tin 45950918] Thông ra Phan Chu Trinh, nhà 4 tầng x 48,6m2 - Xe hơi đậu cửa - Bán gấp — điểm: ? — lý do: ?
- [Tin 46048063] Gấp bán 8 tỷ giảm về 7,19 tỷ - Bán nhanh nhà 2 tầng 50m2 - lô góc hẻm xe hơi 6m Lê Văn Duyệt — điểm: ? — lý do: ?
- [Tin 46152162] Giảm sâu 500tr nhà H3G 40m2 ngang 3.5m Võ Duy Ninh, P22, Bình Thạnh - sổ chính chủ - chỉ 2.98 tỷ TL — điểm: ? — lý do: ?

### C38 lượt 3: Thêm là hẻm xe hơi vào tận nhà
- [Tin 46234317] Không thể bỏ qua DT khủng 60m2 oto quay đầu - chỉ 7,1 tỷ - khu dân trí cao tầng Bùi Đình Túy — điểm: ? — lý do: ?
- [Tin 46205999] Bán gấp hẻm xe hơi - 3 tỷ 290 Đ. Phan Văn Hân, Bình Thạnh - DT 32 m2 — điểm: ? — lý do: ?
- [Tin 45926598] Cần bán gấp nhà hẻm xe hơi Chu Văn An. Mới xây 3 tầng full nội thất cao cấp. Có phòng ngủ tầng trệt — điểm: ? — lý do: ?
- [Tin 46206032] Bán gấp - hẻm xe hơi - 4 tỷ 610 Đường Nguyễn Trung Trực, Bình Thạnh DT 48 m2 — điểm: ? — lý do: ?
- [Tin 46048063] Gấp bán 8 tỷ giảm về 7,19 tỷ - Bán nhanh nhà 2 tầng 50m2 - lô góc hẻm xe hơi 6m Lê Văn Duyệt — điểm: ? — lý do: ?

## Giá trong answer cần xem tay ([S5])

- C01 lượt 5: 30 triệu, 1,56 triệu

## Thay đổi bộ test

(chưa có)
