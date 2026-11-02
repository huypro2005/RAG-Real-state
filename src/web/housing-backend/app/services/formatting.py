"""Định dạng số trong câu trả lời, dùng chung cho chatbot gợi ý và so giá tin rao.

Đơn vị như bảng listings: giá triệu VND, diện tích m², khoảng cách mét; dấu phẩy thập phân.
"""


def format_number(value: float) -> str:
    """53.0 -> '53', 46.6 -> '46,6' (số trong câu trả lời, dấu phẩy thập phân)."""
    return f"{value:g}".replace(".", ",")


def format_distance(meters: float) -> str:
    """350 -> '350 m', 2000 -> '2 km', 1250 -> '1,2 km'."""
    if meters < 1000:
        return f"{meters:.0f} m"
    return f"{meters / 1000:.1f}".rstrip("0").rstrip(".").replace(".", ",") + " km"


def format_price(million_vnd: float) -> str:
    """2800 -> '2,8 tỷ', 2065 -> '2,065 tỷ', 900 -> '900 triệu' (giá trong câu trả lời)."""
    if million_vnd >= 1000:
        value, unit = million_vnd / 1000, "tỷ"
    else:
        value, unit = million_vnd, "triệu"
    text = f"{value:.3f}".rstrip("0").rstrip(".").replace(".", ",")
    return f"{text} {unit}"


def round_distance(meters: float) -> float:
    """Khoảng cách như người đọc thấy ('1,2 km' -> 1200): hiệu hai khoảng cách tính từ số này."""
    return round(meters) if meters < 1000 else round(meters / 1000, 1) * 1000


def round_price(million_vnd: float) -> float:
    """Giá như người đọc thấy (đến 1 triệu khi >= 1 tỷ, 0,001 triệu khi nhỏ hơn)."""
    return round(million_vnd) if million_vnd >= 1000 else round(million_vnd, 3)
