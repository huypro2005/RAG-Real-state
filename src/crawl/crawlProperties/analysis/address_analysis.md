# Phân tích địa chỉ cũ / mới

- Old address: 17/17.
- New address: 17/17.
- New ward/xã: 17/17; new district/huyện: 0/17.
- Cả 17 new address đều không đầy đủ: chỉ phường/xã mới và `Hồ Chí Minh mới`; không lặp lại đường/số nhà/dự án và không có quận/huyện mới.

## Biểu diễn và tính deterministic

Old address nằm ở `.re__address-line-1`; new address nằm ở `.re__address-line-2` và được đặt trong ngoặc. Vì có selector riêng và hậu tố `mới`, việc phân biệt hai chuỗi là deterministic trong snapshot. Tuy nhiên chỉ deterministic về chuỗi website cung cấp, không đủ để dựng full new address và tuyệt đối không được ghép/suy luận từ old address.

## Flags và IDs

- Tất cả mẫu có `isDisplayNewAddress: false` trong `getListingRecommendationParams`, dù line 2 vẫn visible.
- Tất cả location objects quan sát được có `isNewLocation: false` và chứa `cityCode`, `districtId`, `wardId`, đôi khi `streetId/projectId`; đây là bộ ID location cũ dùng cho truy vấn/recommendation.
- Không thấy một bộ `newDistrictId/newWardId/newStreetId` riêng hoặc object IDs mới.
- `recommendationLocation` lại dùng text địa chỉ mới. Do đó không dùng hai boolean trên để phủ định sự tồn tại của `.re__address-line-2`.

## Lưu trữ

- Visible HTML: cả old và new address.
- Script: old location IDs, flags, tọa độ, và recommendation text theo địa chỉ mới.
- Breadcrumb/canonical URL: taxonomy/slug theo địa giới cũ trong các mẫu; không phải nguồn new address.

## Chi tiết từng file

| File | Old address | New address | Complete? |
|---|---|---|---|
| 1.html | The Privé, Đường Song Hành, Phường An Phú, Quận 2, Hồ Chí Minh | Phường Bình Trưng, Hồ Chí Minh mới | Không |
| 2.html | Vinhomes Green Paradise , Xã Long Hòa, Huyện Cần Giờ, Hồ Chí Minh | Xã Cần Giờ, Hồ Chí Minh mới | Không |
| 3.html | Đường Hoàng Xuân Nhị, Phường Phú Trung, Quận Tân Phú, Hồ Chí Minh | Phường Tân Phú, Hồ Chí Minh mới | Không |
| 4.html | Eaton Park, Đường Mai Chí Thọ, Phường An Phú, Quận 2, Hồ Chí Minh | Phường Bình Trưng, Hồ Chí Minh mới | Không |
| 5.html | Gladia by The Water, Đường Võ Chí Công, Phường Bình Trưng Đông, Quận 2, Hồ Chí Minh | Phường Bình Trưng, Hồ Chí Minh mới | Không |
| 6.html | Đường Điện Biên Phủ, Phường 15, Quận Bình Thạnh, Hồ Chí Minh | Phường Gia Định, Hồ Chí Minh mới | Không |
| 7.html | Đường Tân Túc, Thị trấn Tân Túc, Huyện Bình Chánh, Hồ Chí Minh | Xã Tân Nhựt, Hồ Chí Minh mới | Không |
| 8.html | The Glen - Celadon City, Đường N1, Phường Sơn Kỳ, Quận Tân Phú, Hồ Chí Minh | Phường Tân Sơn Nhì, Hồ Chí Minh mới | Không |
| 9.html | Đường Phan Huy Ích, Phường 12, Quận Gò Vấp, Hồ Chí Minh | Phường An Hội Tây, Hồ Chí Minh mới | Không |
| 10.html | Đường Trần Mai Ninh, Phường 12, Quận Tân Bình, Hồ Chí Minh | Phường Bảy Hiền, Hồ Chí Minh mới | Không |
| 11.html | Đường Nguyễn Văn Linh, Phường Tân Thuận Tây, Quận 7, Hồ Chí Minh | Phường Tân Thuận, Hồ Chí Minh mới | Không |
| 12.html | Gladia Heights, Phường Bình Trưng Đông, Quận 2, Hồ Chí Minh | Phường Bình Trưng, Hồ Chí Minh mới | Không |
| 13.html | hẻm 86, Đường Phổ Quang, Phường 2, Quận Tân Bình, Hồ Chí Minh | Phường Tân Sơn Hòa, Hồ Chí Minh mới | Không |
| 14.html | Phường 2, Quận Tân Bình, Hồ Chí Minh | Phường Tân Sơn Hòa, Hồ Chí Minh mới | Không |
| 15.html | Feliz En Vista, Đường Phan Văn Đáng, Phường Thạnh Mỹ Lợi, Quận 2, Hồ Chí Minh | Phường Cát Lái, Hồ Chí Minh mới | Không |
| 16.html | 96/5/10A, Đường Đào Tông Nguyên, Xã Phú Xuân, Huyện Nhà Bè, Hồ Chí Minh | Xã Nhà Bè, Hồ Chí Minh mới | Không |
| 17.html | Khu phố 1, Số nhà 42, Đường Số 36, Phường Tân Quy, Quận 7, Hồ Chí Minh | Phường Tân Hưng, Hồ Chí Minh mới | Không |
