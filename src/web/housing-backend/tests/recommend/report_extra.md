# Báo cáo recommendation — 2026-10-10

KẾT LUẬN: PASS (4 lượt, [S7] chấm tay bên dưới)

| Tiêu chí | Ngưỡng | Kết quả | Đạt? |
|---|---|---|---|
| [S1] Không tin nào vi phạm điều kiện cứng cộng dồn | 100% | 3/3 | có |
| [S2] status đúng kỳ vọng | 100% | 4/4 | có |
| [S3] Trường expect_constraints đúng | 95% | 12/12 | có |
| [S4] Lượt ok có >= min_results tin | 100% | 3/3 | có |
| [S5] answer không chứa ID/URL ngoài dữ liệu lượt đó | 100% | 4/4 | có |
| [S6] Chỉ tin còn hạn tại as_of | 100% | 3/3 | có |
| [S8] referenced_ids đúng tin được hỏi | 100% | 0/0 | có |
| [S9] Không rò state sau reset / giữa hội thoại | 100% | 1/1 | có |
| [S14] relax_options khớp oracle | 100% | 0/0 | có |
| [S15] Không 2 tin cùng nhóm đăng lại trong Top 5 | 100% | 3/3 | có |
| [X1] Câu trả lời đủ ý (expect_answer_all / expect_answer_not) | 100% | 1/1 | có |
| [S13] p95 thời gian/lượt | <= 8 s | 3.29 s | có |

Chi phí ước tính: ~0.004 USD (2 lần gọi gpt-4o-mini/lượt, 2000+300 token/lần).

## CASE FAIL

| ID | Nhóm | Lượt | Câu hỏi | Kỳ vọng | Thực tế | Lỗi |
|---|---|---|---|---|---|---|

## [S7] Top 5 sở thích mềm (chấm tay: số tin phù hợp/5 + lý do)

## Giá trong answer cần xem tay ([S5])

- X01 lượt 2: 4,5 tỷ

## Thay đổi bộ test

(chưa có)
