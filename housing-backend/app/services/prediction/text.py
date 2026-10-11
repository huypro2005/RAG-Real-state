"""MessageRules: quy tắc tất định trên chuỗi tin nhắn (lệnh, quận, loại nhà, tỉnh khác, số).

Code dùng chúng để kiểm chứng điều LLM trích xuất có thật sự nằm trong tin nhắn hay không.
"""

import re
import unicodedata
from typing import Literal

from app.services.prediction.constants import DISTRICT_NAMES

CONFIRM_WORDS = {
    "ok", "okay", "oke", "o k", "xong", "xong roi", "du", "du roi", "da du", "da du roi",
    "du thong tin", "tien hanh", "du doan di", "du doan luon", "bat dau du doan", "xac nhan",
    "chot", "chot luon", "dong y", "dung roi", "dung vay", "duoc", "duoc roi", "uh", "u", "um",
    "vang", "da", "du doan", "du doan gia", "du doan giup",
}
RESET_WORDS = {"reset", "lam lai", "bat dau lai", "lam moi", "xoa het"}
# LLM hay gán wants_reset cho câu đổi quận ("sang quận 12 đi"): chỉ nhận khi có cụm báo làm lại
RESET_HINTS = ("reset", "lam lai", "bat dau lai", "bat dau moi", "xoa het", "tu dau", "lam moi",
               "can khac", "nha khac", "dat khac")
PROPERTY_KEYWORDS = {
    "căn hộ chung cư": ("chung cu", "can ho", "apartment", "condo", "flat"),
    "nhà riêng": ("nha rieng", "nha trong hem", "nha hem", "house"),
    "nhà biệt thự, liền kề": ("biet thu", "lien ke", "villa", "townhouse"),
    # "mặt tiền 10m" là thuộc tính frontage, không phải loại nhà: chỉ nhận "nhà mặt tiền"
    "nhà mặt phố": ("mat pho", "nha mat tien", "nha pho", "street front"),
    "bán đất": ("dat", "land", "plot"),
}
# Địa danh ngoài TP.HCM hay gặp: chặn bằng code vì LLM có thể gán nhầm sang một quận.
# Không có "hue" trần vì trùng "Nguyễn Huệ", "Hồ Văn Huê".
OTHER_PROVINCES = (
    "ha noi", "da nang", "hai phong", "can tho", "binh duong", "dong nai", "vung tau",
    "ba ria", "long an", "bien hoa", "di an", "thuan an", "thu dau mot", "tan uyen",
    "ben cat", "nha trang", "da lat", "tp hue", "thanh pho hue", "thua thien hue",
    "quang ninh", "tay ninh",
)
# Tỉnh chỉ làm mốc tham chiếu, không phải địa chỉ tài sản: "giáp Long An", "xa lộ Hà Nội"
NOT_A_TARGET = (r"\b(?:giap|gan|canh|sat|ke ben|ben canh|duong|xa lo|quoc lo|ql|pho|hem|ngo)\s+"
                rf"(?:{'|'.join(OTHER_PROVINCES)})\b")
# Thuê/cho thuê, đấu giá, thuế: ngoài phạm vi định giá nhà đất để bán
OUT_OF_DOMAIN = ("thue", "dau gia")
# Cụm xác nhận dự đoán: code kiểm lại wants_confirm của LLM (không có cụm này thì bỏ qua)
CONFIRM_HINTS = ("ok", "oke", "okay", "chot", "du doan di", "du doan luon", "tien hanh", "xong",
                 "du roi", "duoc roi", "dong y", "xac nhan", "dung roi", "du doan giup",
                 "du doan gia")
# Từ/cụm không phải tên riêng trong địa chỉ: loại nhà, từ đệm, tên quận, tên thành phố
FILLER_PHRASES = {
    "nha", "hem xe hoi", "xe hoi", "hem", "ngo", "trong", "gan", "o", "tai", "khu", "duong", "pho",
    "cua toi", "ho chi minh", "tphcm", "hcm", "sai gon", "tp", "quan", "huyen",
}
MAX_PHRASE_WORDS = 4
AREA_UNIT = r"(?:m2|m²|m vuong|met vuong|sqm)"
SPOKEN_DIGITS = {"mot": 1, "hai": 2, "ba": 3, "bon": 4, "nam": 5, "sau": 6, "bay": 7, "tam": 8,
                 "chin": 9, "lam": 5}
SPOKEN = "|".join([*SPOKEN_DIGITS, "tram", "muoi", "linh", "le"])
MAX_WORD_NUMBER = 10
# "quận 7", "q.7", "district 7", "dist 7" và dạng chữ "quận bảy" (trừ "quận Ba Đình" của Hà Nội)
DISTRICT_PREFIX = r"\b(?:quan|q|district|dist)\.?\s*"
SPELLED_DISTRICT = rf"{DISTRICT_PREFIX}((?:{SPOKEN})(?:\s+(?:{SPOKEN}))*)\b(?!\s+dinh)"


def plain(text: str) -> str:
    """Chữ thường, bỏ dấu (kể cả đ), gộp khoảng trắng; trả chuỗi `text` đã chuẩn hoá."""
    text = unicodedata.normalize("NFD", text.lower().replace("đ", "d"))
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", text).strip()


PLAIN_DISTRICTS = [plain(name) for name in DISTRICT_NAMES]
GENERIC_PHRASES = FILLER_PHRASES | set(PLAIN_DISTRICTS) | {
    word for words in PROPERTY_KEYWORDS.values() for word in words
}


def _number(digits: str) -> float:
    """"2.000" là hai nghìn (dấu chấm ngăn nhóm), "1,5" và "1.5" là một rưỡi."""
    thousands = re.fullmatch(r"\d{1,3}(?:\.\d{3})+", digits)
    return float(digits.replace(".", "") if thousands else digits.replace(",", "."))


def _spoken_number(words: list[str]) -> float | None:
    """"tám mươi" → 80, "một trăm hai mươi" → 120; không đọc được thì None."""
    total = current = 0
    for word in words:
        if word in SPOKEN_DIGITS:
            current = SPOKEN_DIGITS[word]
        elif word in ("tram", "muoi"):
            total, current = total + max(current, 1) * (100 if word == "tram" else 10), 0
        elif word not in ("linh", "le"):
            return None
    return total + current or None


def _contains(text: str, words) -> bool:
    return any(re.search(rf"\b{word}\b", text) for word in words)


class MessageRules:
    """Các phép kiểm tra tin nhắn; chỉ phương thức tĩnh, không giữ state."""

    @staticmethod
    def command(message: str) -> Literal["reset", "confirm"] | None:
        """Lệnh thuần ("reset", "ok", "chốt"...) để khỏi tốn một lượt LLM."""
        word = re.sub(r"[^\w\s]", "", plain(message))
        if word in RESET_WORDS:
            return "reset"
        return "confirm" if word in CONFIRM_WORDS else None

    @staticmethod
    def asks_reset(message: str) -> bool:
        """Tin nhắn có cụm báo làm lại từ đầu; dùng để bác wants_reset của LLM khi thiếu cụm này."""
        return _contains(plain(message), RESET_HINTS)

    @staticmethod
    def districts(message: str) -> list[int]:
        """Mã các quận/huyện được nhắc tới ("Q.7", "quan 07", "Thu Duc"), theo thứ tự xuất hiện."""
        text = re.sub(SPELLED_DISTRICT, lambda m: f"quan {_spoken_number(m[1].split())}",
                      plain(message))
        text = re.sub(rf"{DISTRICT_PREFIX}0*(\d{{1,2}})\b", r"quan \1", text)
        found = []
        for code, name in enumerate(PLAIN_DISTRICTS):
            match = re.search(rf"\b{name}\b", text)
            if match:
                found.append((match.start(), code))
        return [code for _, code in sorted(found)]

    @staticmethod
    def property_types(message: str) -> list[str]:
        """Các loại nhà đất có từ khoá trong tin nhắn."""
        text = plain(message)
        return [name for name, words in PROPERTY_KEYWORDS.items() if _contains(text, words)]

    @staticmethod
    def mentions_property(message: str, name: str | None = None) -> bool:
        """Tin nhắn có từ khoá của loại `name` (None: của loại nào cũng được)."""
        found = MessageRules.property_types(message)
        return name in found if name else bool(found)

    @staticmethod
    def other_province(message: str) -> bool:
        """Nhắc tỉnh khác mà không nêu quận/huyện TP.HCM nào; "giáp X", "đường X" không tính."""
        if MessageRules.districts(message):
            return False
        return _contains(re.sub(NOT_A_TARGET, " ", plain(message)), OTHER_PROVINCES)

    @staticmethod
    def out_of_domain(message: str) -> bool:
        """Thuê/cho thuê, đấu giá, thuế: từ chối bằng code, không phụ thuộc LLM.

        "nhà đang cho thuê, muốn bán" thì không: người dùng có ý bán/định giá.
        """
        lower = message.lower()
        accented = plain(message) != re.sub(r"\s+", " ", lower).strip()
        wants_to_sell = re.search(r"\bbán\b" if accented else r"\bban\b", lower)
        return _contains(plain(message), OUT_OF_DOMAIN) and not wants_to_sell

    @staticmethod
    def confirms(message: str) -> bool:
        """Tin nhắn có cụm xác nhận ("ok", "chốt", "dự đoán đi"...)."""
        return _contains(plain(message), CONFIRM_HINTS)

    @staticmethod
    def clean_address(address: str) -> str | None:
        """Bỏ loại nhà, tên quận và từ đệm khỏi địa chỉ LLM trích; không còn tên riêng thì None.

        "chung cư Bình Tân" → None (dùng tâm quận); "căn hộ Botanica Premier" → "Botanica Premier".
        """
        tokens = [token for token in re.split(r"[\s,;]+", address) if token]
        words = [re.sub(r"\W", "", plain(token)) for token in tokens]
        kept, i = [], 0
        while i < len(tokens):
            size = next((n for n in range(MAX_PHRASE_WORDS, 0, -1)
                         if " ".join(words[i:i + n]) in GENERIC_PHRASES), 0)
            if not size and not re.fullmatch(r"q\d{1,2}", words[i]):
                kept.append(tokens[i])
            i += size or 1
        return " ".join(kept) or None

    @staticmethod
    def area_from_text(message: str) -> tuple[float, bool] | None:
        """Diện tích trong tin ("300m2", "tám mươi mét vuông", "5x20") → (m², True nếu từ 5x20)."""
        text = plain(message).replace("×", "x")
        number = r"(?<![\w.\-])(\d+(?:[.,]\d+)*)"
        if match := re.search(rf"{number}\s*{AREA_UNIT}", text):
            return _number(match[1]), False
        if match := re.search(rf"{number}\s*x\s*(\d+(?:[.,]\d+)?)", text):
            return _number(match[1]) * _number(match[2]), True
        if match := re.search(rf"((?:(?:{SPOKEN})\s+)+){AREA_UNIT}", text):
            value = _spoken_number(match[1].split())
            return (value, False) if value else None
        return None

    @staticmethod
    def number_status(
        value: float, message: str, allow_bare: bool
    ) -> Literal["ok", "negative", "absent"]:
        """Số LLM trích có trong tin nhắn không. allow_bare: đang hỏi đúng trường này."""
        positive, negative = set(), set()
        for sign, digits in re.findall(r"(?<![\w.,])(-?)(\d+(?:[.,]\d+)?)", message):
            (negative if sign else positive).add(_number(digits))
        if value in positive:
            return "ok"
        if value in negative:
            return "negative"
        spelled = value <= MAX_WORD_NUMBER and _contains(plain(message), SPOKEN.split("|"))
        return "ok" if allow_bare or spelled else "absent"
