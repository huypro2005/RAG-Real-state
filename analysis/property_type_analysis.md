# Phân tích theo loại bất động sản

Selector/layout chính giống nhau; khác biệt nằm ở tập specs do người đăng cung cấp và tính phù hợp theo loại.

| Property type | Files | area | frontage | bedrooms | bathrooms | road_width | legal | interior | floors |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Căn hộ chung cư | 5 | 5/5 | 0/5 | 5/5 | 5/5 | 0/5 | 5/5 | 4/5 | 2/5 |
| Nhà biệt thự, liền kề | 3 | 3/3 | 1/3 | 1/3 | 1/3 | 2/3 | 2/3 | 1/3 | 1/3 |
| Nhà mặt phố | 3 | 3/3 | 2/3 | 3/3 | 3/3 | 2/3 | 3/3 | 1/3 | 3/3 |
| Nhà riêng | 6 | 6/6 | 3/6 | 6/6 | 6/6 | 5/6 | 6/6 | 4/6 | 6/6 |

## Nhận xét

- Căn hộ trong mẫu tập trung bedrooms, bathrooms, legal, interior; không có frontage/road width/floors structured.
- Nhà riêng và nhà mặt phố thường có floors; frontage/road width vẫn không bắt buộc.
- Biệt thự/liền kề biến thiên mạnh: bài dự án có thể chỉ có giá/diện tích, bài căn cụ thể có bedrooms/bathrooms/floors.
- Tập mẫu không có đất, đất nền dự án hoặc shophouse độc lập, nên không kết luận structure cho các nhóm đó.
- Việc thiếu field không phải lỗi nếu field không phù hợp hoặc người đăng không khai báo.
