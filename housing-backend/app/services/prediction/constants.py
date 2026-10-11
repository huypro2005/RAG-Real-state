"""Hằng số dùng chung của mode dự đoán giá: model, geocoder, text và script train."""

CENTER = (10.7769, 106.7009)  # Nhà thờ Đức Bà
# Khung địa giới TP.HCM cũ: MỘT nguồn cho cả lọc dữ liệu train lẫn chấp nhận điểm Goong/toạ độ.
# Đây là điểm DUY NHẤT khác retrain.py của đồ án 1 (gốc: lat 10,38-11,10, lon 106,1-106,8 làm mất
# ~2.700 dòng thuộc Quận 9 đông, Thủ Đức và Cần Giờ; đã kiểm tra nhãn quận của chúng đều hợp lệ).
HCM_LAT, HCM_LON = (10.37, 11.17), (106.35, 107.03)

# Mã loại nhà đất của đồ án 1 (các loại 1, 5, 6 đã bị loại khỏi dữ liệu train)
PROPERTY_TYPES = {
    "căn hộ chung cư": 0, "nhà riêng": 2, "nhà biệt thự, liền kề": 3,
    "nhà mặt phố": 4, "bán đất": 7,
}
PROPERTY_PHRASES = {  # cách gọi trong câu trả lời
    0: "căn hộ chung cư", 2: "nhà riêng", 3: "nhà biệt thự/liền kề", 4: "nhà mặt phố", 7: "lô đất",
}
APARTMENT, LAND = 0, 7
# Trường tuỳ chọn mà model dùng theo loại: chung cư chỉ phòng ngủ, đất chỉ mặt tiền
OPTIONAL_FIELDS = ("bedrooms", "frontage", "floors")
OPTIONALS_BY_TYPE = {APARTMENT: ("bedrooms",), LAND: ("frontage",)}

# Mã quận/huyện 0-23 theo bảng trong retrain.py; tên khớp cột listings.district_old
DISTRICT_NAMES = [
    "Bình Chánh", "Bình Tân", "Bình Thạnh", "Cần Giờ", "Củ Chi", "Gò Vấp", "Hóc Môn",
    "Nhà Bè", "Phú Nhuận", "Quận 1", "Quận 10", "Quận 11", "Quận 12", "Quận 2", "Quận 3",
    "Quận 4", "Quận 5", "Quận 6", "Quận 7", "Quận 8", "Quận 9", "Thủ Đức", "Tân Bình",
    "Tân Phú",
]
