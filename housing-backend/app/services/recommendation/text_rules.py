r"""Quy tắc tất định trên câu người dùng (docs/tasks/hybrid-search.md mục 9 #14-#29).

Regex hậu tố `_FOLDED` chạy trên `fold(message)` (bỏ dấu, chữ thường, khoảng trắng đơn, nên viết
`\s` thay dấu cách); `_RAW` chạy trên bản có dấu để phân biệt từ bỏ dấu bị trùng ("chợ"/"chỗ").
"""

import re
import unicodedata
from collections.abc import Sequence
from typing import NamedTuple

from app.services.recommendation.schemas import (
    POI_NAMES,
    PROPERTY_TYPES,
    ConstraintDelta,
    PlaceRequest,
    SearchConstraints,
    TurnPlan,
)

PRICE_APPROX_LOW = 0.20   # "tầm X" = từ X x (1 - 20%) ...
PRICE_APPROX_HIGH = 0.05  # ... đến X x (1 + 5%) (spec 9 #15)
LISTING_ID_MIN_DIGITS = 7   # mã tin 7-9 chữ số; ngắn hơn là số thứ tự ("căn 3")
MAX_CONFIRM_WORDS = 6       # quá dài thì không còn là câu chỉ để xác nhận/hủy

NUMBER_WORDS = {
    "mot": 1, "nhat": 1, "hai": 2, "ba": 3, "bon": 4, "tu": 4, "nam": 5, "sau": 6, "bay": 7,
    "tam": 8, "chin": 9, "muoi": 10,
}
_WORD = "|".join(NUMBER_WORDS)
_INT = rf"\d+|{_WORD}"
_DECIMAL = rf"\d+(?:[.,]\d+)?|{_WORD}"
# "củ"/"tỏi" bỏ dấu trùng "cũ"/"tôi", nên chỉ tính khi đi sau một số.
_MONEY_UNIT = r"(?:ty|ti|trieu|tr|toi|cu)(?![a-z])"  # "2ty5": sau đơn vị có thể là chữ số
_REF_NOUN = r"(?:can|tin|cai|lo)"
# Một vị trí: "thứ hai", "số 3", "2", "đầu tiên", "cuối". Số viết bằng chữ chỉ nhận sau
# "thứ/số" vì "tầm" bỏ dấu trùng "tám".
_POSITION = rf"(?:(?:thu|so)\s(?:{_INT})|\d+|dau\stien|dau|cuoi\scung|cuoi)(?![a-z0-9])"

LISTING_ID_PATTERN = re.compile(r"\b\d{7,9}\b")  # mã tin 7-9 chữ số, dùng cho cả bản fold/có dấu
# "tìm lại từ đầu", "bỏ hết điều kiện"; "xóa điều kiện bệnh viện" chỉ bỏ một điều kiện
RESET_PATTERN_FOLDED = re.compile(r"""
    \b(?: tim\slai\stu\sdau | lam\slai\stu\sdau | bat\sdau\slai
        | bo\shet\s(?:cac\s)?dieu\skien | bo\shet(?=\s,|\stim|\sroi|$)
        | xoa\s(?:het\s)?(?:cac\s)?dieu\skien
          (?!\s(?:benh|truong|cho|gia|dien|phong|khu|quan|loai))
    )\b""", re.VERBOSE)
# "toàn thành phố", "quận nào cũng được", "đâu cũng được"
ANY_AREA_PATTERN_FOLDED = re.compile(r"""
    \b(?: toan\s(?:thanh\spho|tp|tphcm|sai\sgon)
        | (?:quan|khu\svuc|khu)\snao\scung\sduoc | dau\scung\sduoc )\b""", re.VERBOSE)
OWN_HOME_PATTERN_FOLDED = re.compile(r"\b(?:dinh\sgia|nha\s(?:cua\s)?toi|ban\sduoc\sbao\snhieu)\b")
# Bí danh địa điểm → tên (không dấu) có trong pois; khoá so với cả cụm sau khi bỏ từ đệm
ALIASES = {
    "uit": "cong nghe thong tin", "cntt": "cong nghe thong tin", "bk": "dai hoc bach khoa",
    "bach khoa": "dai hoc bach khoa", "hcmut": "dai hoc bach khoa",
    "khtn": "khoa hoc tu nhien", "hcmus": "khoa hoc tu nhien", "kinh te": "kinh te thanh pho",
    "ueh": "kinh te thanh pho", "xhnv": "khoa hoc xa hoi", "ussh": "khoa hoc xa hoi",
    "tdtu": "ton duc thang", "spkt": "cong nghe ky thuat thanh pho",  # SPKT nay đổi tên (OSM)
    "su pham ky thuat": "cong nghe ky thuat thanh pho",
}
# Viết tắt KHÔNG tra bằng pois mà để Goong: "đhqg" gần nhất trong pois là Bách khoa (Q10), trong
# khi ĐHQG-HCM ở Thủ Đức. Giá trị là tên đầy đủ gửi Goong và dùng để kiểm kết quả.
GOONG_ONLY = {"dhqg": "dai hoc quoc gia thanh pho ho chi minh"}
# "gần <từ chỉ loại> <tên riêng>": nhóm poi là từ chỉ loại, nhóm rest là phần còn lại của câu
POI_ALT = "dai hoc|dh|cao dang|hoc vien|thpt|thcs|truong|benh vien|bv|cho"
PLACE_PATTERN_FOLDED = re.compile(
    rf"\b(?:gan|canh|sat|quanh|toi|den|cach)\s+(?:(?P<poi>{POI_ALT})\s+)?(?P<rest>[a-z0-9 ]+)")
REMOVE_PLACE_PATTERN_FOLDED = re.compile(r"\b(?:bo|xoa|khong can)\s+(?:dieu\skien\s+)?gan\b")
POI_KINDS = {"truong": "truong_hoc", "thpt": "truong_hoc", "thcs": "truong_hoc",
             "dai hoc": "truong_hoc", "dh": "truong_hoc", "cao dang": "truong_hoc",
             "hoc vien": "truong_hoc", "benh vien": "benh_vien", "bv": "benh_vien", "cho": "cho"}
KEEP_POI_WORD = {"dai hoc", "dh", "cao dang", "hoc vien", "thpt", "thcs"}  # nằm trong tên riêng
# Hết tên riêng: từ nối, quận, giá, số lượng
NAME_STOP = {"o", "tai", "quan", "huyen", "phuong", "q", "duoi", "tren", "khoang", "tam", "gia",
             "co", "voi", "de", "va", "ma", "can", "thi", "khong", "nhe", "nua", "hon", "gan",
             "ban", "den", "ra", "len", "xuong", "thoi"}
# "tu", "nha" cũng là tên ("bệnh viện Từ Dũ", "chợ Nhà Bè"): chỉ là từ nối khi đứng sau tên
LATE_STOP = {"tu", "nha", "cho"}  # "cho": "gần trường học cho con"
NAME_UNITS = {"ty", "tr", "trieu", "pn", "phong", "m2", "km", "m", "met", "tang", "lau"}
# Phần đầu chỉ là mô tả loại ("trường học", "bệnh viện lớn"): không phải tên riêng. "đa khoa"
# chỉ là mô tả khi đứng cuối; "bệnh viện đa khoa Sài Gòn" là tên. "từ" không có ("bệnh viện Từ Dũ").
GENERIC_NAME = re.compile(r"^(?:(?:hoc|lon|nho|tot|cong|tu nhan|quoc te|dan lap|chat luong|mam non|"
                          r"tieu hoc|ban tru)\b\s*|(?:da khoa|chuyen khoa)\s*$)")
# Câu có số + đơn vị khoảng cách: "8 km", "tầm 12 km", "500m", "3 cây số" (không phải "60 m vuông")
DISTANCE_PATTERN_FOLDED = re.compile(
    r"\b(\d+(?:[.,]\d+)?)\s*(km|met|cay\sso|m(?!\s*(?:2|vuong)))\b")
# Câu có nhắc loại BĐS: khớp "căn hộ", "nhà", "loại nào cũng được"; không khớp "bệnh viện".
PROPERTY_WORDS_PATTERN_FOLDED = re.compile(
    r"\b(?:loai|can\sho|chung\scu|nha|dat|biet\sthu|lien\ske|shophouse|kho|xuong)\b"
)
# "loại nào cũng được", "không nhất thiết căn hộ": bỏ điều kiện loại (spec 9 #32b)
ANY_KIND_PATTERN_FOLDED = re.compile(r"\bloai\s(?:nao|gi)\scung\sduoc\b|\bkhong\snhat\sthiet\b")
# Từ khóa loại BĐS theo thứ tự ưu tiên (cụ thể trước chung sau); "đất" xử lý riêng ở _RAW.
KIND_KEYWORDS_FOLDED = (
    (re.compile(r"\bdat\snen\b"), "dat_nen_du_an"),
    (re.compile(r"\b(?:biet\sthu|lien\ske)\b"), "biet_thu_lien_ke"),
    (re.compile(r"\b(?:shophouse|nha\spho\sthuong\smai)\b"), "shophouse"),
    (re.compile(r"\bnha\smat\s(?:pho|tien)\b"), "nha_mat_pho"),
    (re.compile(r"\b(?:can\sho|chung\scu)\b"), "can_ho"),
    (re.compile(r"\bnha\s(?:rieng|pho(?!\sthuong)|hem|trong\shem)\b"), "nha_rieng"),
    (re.compile(r"\b(?:nha\skho|nha\sxuong|kho\sxuong|kho\sbai)\b"), "kho_xuong"),
)
LAND_PATTERN_RAW = re.compile(r"\b(?:đất|dat)\b")  # "đất"/"dat" nhưng không phải "đạt"/"đặt"
# Phần câu đứng TRƯỚC từ khóa: "không cần căn hộ", "bỏ nhà phố" -> từ khóa bị phủ định
NEGATED_PATTERN_FOLDED = re.compile(r"(?:khong\s(?:can|lay|muon|phai)|bo|tru)\s$")
CHEAPER_PATTERN_FOLDED = re.compile(r"\b(?:re|giam|bot|thap\shon)\b")  # "rẻ hơn", "giảm bớt"
# Số + đơn vị tiền: "3 tỷ", "một tỷ rưỡi", "900tr"; không khớp "2 phòng ngủ", "70m2".
MONEY_PATTERN_FOLDED = re.compile(rf"\b(?:{_DECIMAL}|chuc|tram|vai)\s?{_MONEY_UNIT}")
# price_min chỉ nhận khi có "trên/từ/ít nhất/tối thiểu <số> <tiền|đến>" (spec 9 #24):
# "trên 6 tỷ", "từ 4 đến 6 tỷ", "tối thiểu phải 8 tỷ"; không khớp "trên 100m2".
MIN_PRICE_PATTERN_FOLDED = re.compile(rf"""
    \b(?:tren|tu|it\snhat|toi\sthieu|hon)\s(?:phai\s|la\s)?(?:{_DECIMAL})\s?
    (?:{_MONEY_UNIT}|(?:den|toi)\b)""", re.VERBOSE)
# "tầm/khoảng/xấp xỉ/gần 3 tỷ"; "cỡ"/"độ" chỉ nhận có dấu (bỏ dấu trùng "có"/"đó").
APPROX_PATTERN_FOLDED = re.compile(rf"""
    \b(?:tam|khoang|xap\sxi|gan)\s(?:la\s|muc\s)?(?:{_DECIMAL})\s?{_MONEY_UNIT}""",
                                   re.VERBOSE)
APPROX_PATTERN_RAW = re.compile(rf"\b(?:cỡ|độ)\s(?:{_DECIMAL})\s?(?:tỷ|triệu|tr|ty|trieu)(?![a-z])")
EXACT_PRICE_PATTERN_FOLDED = re.compile(r"\bdo\slai\b")  # "6 tỷ đổ lại" = giá tối đa
# Số tiền đầu tiên trong câu: "3 tỷ", "2 tỷ rưỡi", "3 tỷ 8", "900tr"; làm gốc của "tầm X"
FIRST_MONEY_PATTERN_FOLDED = re.compile(
    r"(\d+(?:[.,]\d+)?)\s?(ty|ti|toi|trieu|tr|cu)(?![a-z])"
    r"(?:\s?(ruoi|\d{1,3})\b(?!\s?(?:m|pn|phong|tang|lau|tr|ty)))?")
# Câu ngắn chỉ để xác nhận / hủy giá trị đang chờ (spec 9 #29d)
YES_PATTERN_FOLDED = re.compile(r"\b(?:u|um|uh|dung|ok|oke|vang|chuan|dong\sy)\b")
NO_PATTERN_FOLDED = re.compile(r"\b(?:khong|thoi|giu\snguyen|huy)\b")
# "lệch 10%", "sai số 5": tỷ lệ người dùng tự nói cho khoảng "tầm X"
RATIO_PATTERN_FOLDED = re.compile(r"\b(?:lech|sai\sso|chenh\slech)\s(\d+(?:[.,]\d+)?)\b")
# "nâng/tăng ngân sách" và "giảm/hạ ngân sách"; "tang" bỏ dấu trùng "tầng" nên chỉ nhận có dấu.
RAISE_PATTERN_RAW = re.compile(r"\b(?:nâng|tăng)\b|\bnang\s(?:ngan|len|gia)")
LOWER_PATTERN_RAW = re.compile(
    r"\b(?:giảm|hạ)\s(?:ngân sách|xuống|giá)|\b(?:giam|ha)\s(?:ngan|xuong|gia)"
)
# Số + "PN/phòng ngủ/phòng" (trừ phòng tắm/vệ sinh/khách); "2 lầu", "tầng 12" không khớp.
BEDROOMS_PATTERN_FOLDED = re.compile(rf"""
    \b({_INT})\s?(?:pn|phong\sngu|phong(?!\s(?:tam|ve\ssinh|khach|wc)))(?![a-z])""",
                                     re.VERBOSE)
# "căn 1, 2 và 4", "căn thứ 2 với căn thứ 3", "lô 2 với lô 4"
REF_PATTERN_FOLDED = re.compile(rf"""
    \b{_REF_NOUN}\s({_POSITION}
        (?:\s(?:,|va|voi|hoac)\s(?:{_REF_NOUN}\s)?{_POSITION})*)""", re.VERBOSE)
POSITION_PATTERN_FOLDED = re.compile(_POSITION)
FIRST_N_PATTERN_FOLDED = re.compile(rf"\b({_INT})\s{_REF_NOUN}\sdau\b")  # "3 căn đầu"
# "phường Bình Trưng", "xã Nhà Bè": nhóm 2 lấy mọi chữ sau đó (cắt theo tên đã biết).
WARD_PATTERN_FOLDED = re.compile(r"\b(phuong|xa)\s((?:[a-z]+\s?)+)")
# Tiền tố bỏ khi so tên khu vực: "Quận 7" -> "7", "Phường Bình Trưng" -> "binh trung"
AREA_PREFIX_PATTERN_FOLDED = re.compile(r"^(?:quan|huyen|thanh\spho|tp|phuong|xa)\s")
# POI chỉ hợp lệ khi câu nhắc đúng từ, để phân biệt "chợ" với "cho con" (spec 9 #18).
POI_MENTIONS_RAW = {
    "truong_hoc": re.compile(r"\b(?:trường|truong|trg)\b"),
    "benh_vien": re.compile(r"\b(?:bệnh viện|benh vien|bv)\b"),
    "cho": re.compile(r"\bchợ\b|\b(?:gần|gan|cách|cach)\s+cho\b"),
}
# Nơi không thuộc 3 loại POI: không bao giờ là điều kiện cứng, chuyển vào sở thích mềm. Cụm
# viết đúng cách tin đăng gọi nơi đó (không kèm "gần") để xếp hạng theo từ khóa khớp được.
SOFT_PLACES_FOLDED = (
    (re.compile(r"\b(?:trung\stam\sthuong\smai|tttm)\b"), "trung tâm thương mại, tttm"),
    (re.compile(r"\bcong\svien\b"), "công viên"),
    (re.compile(r"\bsieu\sthi\b"), "siêu thị"),
    (re.compile(r"\bmetro\b"), "metro"),
)


def fold(text: str) -> str:
    """'Phường Thủ Đức, Q.7' -> 'phuong thu duc , q 7'; giữ dấu , . giữa hai chữ số."""
    text = unicodedata.normalize("NFD", text.lower().replace("đ", "d"))
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = re.sub(r"(?<!\d)[.,]|[.,](?!\d)", lambda m: " , " if m.group() == "," else " ", text)
    return " ".join(re.sub(r"[^a-z0-9,.]+", " ", text).split())


def phrases(soft_query: str | None) -> list[str]:
    """'yên tĩnh, view sông' -> ['yên tĩnh', 'view sông'] (sở thích mềm ngăn cách bằng dấu phẩy)."""
    return [part.strip() for part in (soft_query or "").split(",") if part.strip()]


def area_key(name: str) -> str:
    """Tên khu vực bỏ dấu, bỏ tiền tố: 'Quận 7' -> '7', 'Phường Bình Trưng' -> 'binh trung'."""
    return AREA_PREFIX_PATTERN_FOLDED.sub("", fold(name))


def _said(key: str, text: str) -> bool:
    """Tên khu vực (đã area_key) có trong câu; số chỉ tính khi đi sau q/quận ("Q7")."""
    pattern = rf"\b(?:q|quan)\s?{key}\b" if key.isdigit() else rf"\b{re.escape(key)}\b"
    return bool(re.search(pattern, text))


class Correction(NamedTuple):
    """Kết quả MessageRules.correct: plan đã sửa + những gì code đã bác/đọc lại từ câu."""

    plan: TurnPlan
    ignored: list[str]        # điều kiện LLM đề xuất nhưng câu không nói rõ, nên chưa áp dụng
    typed_price: float | None  # số tiền khách gõ (triệu), để báo lỗi bằng đúng số đó


class MessageRules:
    """Quy tắc tất định trên tin nhắn của lượt này; code có quyền bác đề xuất của LLM."""

    def __init__(self, message: str):
        self.raw = unicodedata.normalize("NFC", message).lower()
        self.text = fold(message)

    def correct(
        self, plan: TurnPlan, current: SearchConstraints, current_areas: list[str],
        ward_names: list[str], district_names: Sequence[str] = (),
    ) -> Correction:
        """TurnPlan đã sửa kèm ghi chú; hai danh mục tên dùng để tìm khu vực trong câu."""
        plan = plan.model_copy(deep=True)
        if RESET_PATTERN_FOLDED.search(self.text):  # C45: LLM hay coi đó là search + chép lại
            plan.intent = "reset"
        delta = plan.set_fields
        reset = plan.intent == "reset"
        ignored: list[str] = []
        typed_price = self._correct_price(delta, current, ignored)
        # "giảm xuống 3 tỷ" là giá tối đa mới (spec 9 #16), không phải "rẻ hơn 10%"
        delta.cheaper = (delta.cheaper and bool(CHEAPER_PATTERN_FOLDED.search(self.text))
                         and delta.price_max is None and delta.price_min is None)
        self._correct_bedrooms(delta)
        self._correct_places(delta, current, ignored)
        self._correct_pois(delta, current, ignored)
        self._correct_property_kinds(plan, delta, reset)
        self._correct_areas(delta, [] if reset else current_areas, ward_names, district_names)
        self._correct_clear_fields(plan, delta)
        own_home = plan.intent == "other_mode" and OWN_HOME_PATTERN_FOLDED.search(self.text)
        if plan.intent in ("chitchat", "other_mode") and not own_home and (
                self._adds_conditions(plan, current, current_areas)):
            plan.intent = "refine" if current != SearchConstraints() else "search"
        if (plan.intent in ("search", "refine") and "?" in self.raw and not plan.clear_fields
                and delta.model_copy(update={"soft_query": None}) == ConstraintDelta()):
            plan.intent = "ask_detail"  # câu hỏi không có điều kiện mới thì không có gì để tìm lại
        if reset:  # sở thích cũ mà LLM chép lại không được rò sang (spec 9 #1)
            old = {fold(part) for part in phrases(current.soft_query)}
            delta.soft_query = ", ".join(
                part for part in phrases(delta.soft_query) if fold(part) not in old
            ) or None
        return Correction(plan, ignored, typed_price)

    @staticmethod
    def _adds_conditions(plan: TurnPlan, current: SearchConstraints, areas: list[str]) -> bool:
        """Plan có điều kiện tìm MỚI; LLM chép lại điều kiện đang có (câu "hi") thì không tính."""
        delta = plan.set_fields.model_copy(update={"soft_query": None})
        kinds = {t for kind in delta.property_kinds for t in PROPERTY_TYPES[kind]}
        names = {area_key(name) for name in [*delta.district_names, *delta.new_ward_names]}
        if kinds <= set(current.property_types):
            delta.property_kinds = []
        if names <= {area_key(name) for name in areas}:
            delta.district_names, delta.new_ward_names = [], []
        same = [f for f in ("price_min", "price_max", "area_min", "area_max", "bedrooms_min")
                if getattr(delta, f) == getattr(current, f)]
        delta = delta.model_copy(update=dict.fromkeys(same))
        return bool(plan.clear_fields) or delta != ConstraintDelta()

    def references(self, last_results: list[str]) -> tuple[list[str], list[str]]:
        """(listing_id hợp lệ, tham chiếu không có); không tham chiếu nào thì xét mọi tin (#25)."""
        positions = list(dict.fromkeys(self._positions(len(last_results))))
        listing_ids = list(dict.fromkeys(LISTING_ID_PATTERN.findall(self.text)))
        if not positions and not listing_ids:
            return list(last_results), []
        ids = [last_results[p - 1] for p in positions if 1 <= p <= len(last_results)]
        ids += [i for i in listing_ids if i in last_results]
        missing = [f"căn thứ {p}" for p in positions if not 1 <= p <= len(last_results)]
        missing += [f"tin {i}" for i in listing_ids if i not in last_results]
        return list(dict.fromkeys(ids)), missing

    def names_listing(self, available: int) -> bool:
        """Câu có nói căn nào ("căn 2") hoặc mã tin."""
        return bool(self._positions(available) or LISTING_ID_PATTERN.search(self.text))

    def confirmation(self) -> str | None:
        """"yes"/"no" khi câu ngắn chỉ để xác nhận/hủy (không kèm số tiền); ngược lại None."""
        if len(self.text.split()) > MAX_CONFIRM_WORDS or MONEY_PATTERN_FOLDED.search(self.text):
            return None
        if NO_PATTERN_FOLDED.search(self.text):
            return "no"
        return "yes" if YES_PATTERN_FOLDED.search(self.text) else None

    def reverses_budget(self, new_max: float | None, current_max: float | None) -> bool:
        """"Nâng ngân sách" mà mức mới thấp hơn hiện tại (hoặc "giảm" mà cao hơn): mâu thuẫn."""
        if new_max is None or current_max is None:
            return False
        return (bool(RAISE_PATTERN_RAW.search(self.raw)) and new_max < current_max) or (
            bool(LOWER_PATTERN_RAW.search(self.raw)) and new_max > current_max
        )

    def _positions(self, available: int) -> list[int]:
        """Vị trí 1..N người dùng nói ("căn thứ hai", "3 căn đầu", "căn cuối")."""
        positions: list[int] = []
        for match in FIRST_N_PATTERN_FOLDED.finditer(self.text):
            word = match.group(1)
            positions += range(1, (NUMBER_WORDS.get(word) or int(word)) + 1)
        for match in REF_PATTERN_FOLDED.finditer(self.text):
            for token in POSITION_PATTERN_FOLDED.findall(match.group(1)):
                token = token.removeprefix("thu ").removeprefix("so ")
                if token.startswith("cuoi"):
                    positions.append(available)
                elif token.startswith("dau"):
                    positions.append(1)
                elif len(token) < LISTING_ID_MIN_DIGITS:
                    positions.append(NUMBER_WORDS.get(token) or int(token))
        return positions

    def _correct_price(
        self, delta: ConstraintDelta, current: SearchConstraints, ignored: list[str]
    ) -> float | None:
        """Giá chỉ nhận khi câu có tiền, price_min khi có "trên/từ" (#24); trả số tiền khách gõ."""
        if not MONEY_PATTERN_FOLDED.search(self.text):  # giá chép lại từ ngữ cảnh
            if delta.price_max not in (None, current.price_max):
                ignored.append("ngân sách")
            delta.price_min = delta.price_max = None
        if not MIN_PRICE_PATTERN_FOLDED.search(self.text):  # "trên 100m2" không phải giá
            delta.price_min = None
        approx = not EXACT_PRICE_PATTERN_FOLDED.search(self.text) and bool(
            APPROX_PATTERN_FOLDED.search(self.text) or APPROX_PATTERN_RAW.search(self.raw)
        )
        low, high, base = PRICE_APPROX_LOW, PRICE_APPROX_HIGH, delta.price_max
        if money := FIRST_MONEY_PATTERN_FOLDED.search(self.text):  # không tin giá LLM đã nhân
            number = float(money.group(1).replace(",", "."))
            if tail := money.group(3):  # "rưỡi" = nửa đơn vị; "3 tỷ 8" = 3,8
                number += 0.5 if tail == "ruoi" else int(tail) / 10 ** len(tail)
            base = number * (1000 if money.group(2) in ("ty", "ti", "toi") else 1)
            if approx and delta.price_min is None:
                delta.price_max = base
        delta.price_approx = delta.price_max is not None and delta.price_min is None and approx
        if delta.price_approx:  # "tầm X" -> khoảng giá do code tính (spec 9 #15)
            if ratio := RATIO_PATTERN_FOLDED.search(self.text):  # người dùng tự nói tỷ lệ
                low = high = float(ratio.group(1).replace(",", ".")) / 100
            delta.price_min = round(base * (1 - low), 2)
            delta.price_max = round(base * (1 + high), 2)
        return base if money else None

    def _correct_bedrooms(self, delta: ConstraintDelta) -> None:
        """Số phòng ngủ phải có trong câu ("2PN"), không thì lấy số trong câu hoặc bỏ."""
        if delta.bedrooms_min is None:
            return
        found = [NUMBER_WORDS.get(w) or int(w) for w in BEDROOMS_PATTERN_FOLDED.findall(self.text)]
        if delta.bedrooms_min not in found:
            delta.bedrooms_min = found[0] if found else None

    def _correct_places(
        self, delta: ConstraintDelta, current: SearchConstraints, ignored: list[str]
    ) -> None:
        """Địa điểm có tên: bỏ tên kèm chỉ thị (N9); LLM không đặt thì dựng từ câu ("gần bv chợ
        rẫy", "gần UIT"); loại (kind) theo từ loại đứng ngay trước tên trong câu; bán kính chỉ nhận
        khi câu có số + km/m (LLM hay điền mặc định 2 km) và đổi được bán kính địa điểm đang có."""
        places = [p for p in delta.near_places if not re.search(r"[;!?\n]", p.name)]
        dropping = REMOVE_PLACE_PATTERN_FOLDED.search(self.text)  # "bỏ điều kiện gần X"
        distance = DISTANCE_PATTERN_FOLDED.search(self.text)
        meters = distance and float(distance[1].replace(",", ".")) * (
            1000 if distance[2] in ("km", "cay so") else 1)
        radius = int(meters) if distance else None  # "cách chợ Tân Bình 800m"
        for match in [] if places or dropping else PLACE_PATTERN_FOLDED.finditer(self.text):
            words, tokens = match["rest"].split(), []
            for i, token in enumerate(words):
                stop = token in NAME_STOP or re.fullmatch(r"q?\d+[a-z]+", token) or len(tokens) >= 6
                stop = stop or (tokens and token in LATE_STOP)
                if stop or (token.isdigit() and words[i + 1:i + 2] and words[i + 1] in NAME_UNITS):
                    break
                tokens.append(token)
            poi, name = match["poi"], " ".join(tokens)
            if poi not in KEEP_POI_WORD:  # "trường học", "bệnh viện lớn": mô tả loại, không có tên
                name = GENERIC_NAME.sub("", name)
            if poi and name:
                name = f"{poi} {name}" if poi in KEEP_POI_WORD else name
                places.append(PlaceRequest(name=name, kind=POI_KINDS[poi], max_distance_m=radius))
            elif not poi and (" ".join(tokens) in ALIASES or " ".join(tokens) in GOONG_ONLY):
                places.append(PlaceRequest(name=" ".join(tokens), kind=None, max_distance_m=radius))
        skip = {"truong", "dai", "hoc", "benh", "vien", "bv", "dh"}
        for i, place in enumerate(places):  # "chợ rẫy" khi đang có "Bệnh viện Chợ Rẫy": một nơi
            words = set(fold(place.name).split()) - skip
            same = [c for c in current.near_places
                    if words and words <= set(fold(c.name).split())]
            if same:
                places[i] = place.model_copy(update={
                    "name": same[0].name, "max_distance_m": place.max_distance_m or radius})
        if not places and distance and current.near_places and not re.search(
                rf"\b(?:{POI_ALT})\b", self.text):  # "gần hơn nữa, 1 km thôi": đổi bán kính
            targets = current.near_places if len(current.near_places) == 1 else [
                c for c in current.near_places if self._mentions(c.name)]
            if len(targets) == 1:
                places = [PlaceRequest(name=targets[0].name, kind=None, max_distance_m=int(meters))]
            else:
                ignored.append("bán kính (quanh địa điểm nào?)")
        delta.near_places = [self._place_kind(p).model_copy(update={
            # một địa điểm + một số km trong câu: tin số trong câu, LLM hay cộng dồn ("nới ra 3 km")
            "max_distance_m": radius if distance and len(places) == 1 else (
                p.max_distance_m if distance else None)}) for p in places]

    def _place_kind(self, place: PlaceRequest) -> PlaceRequest:
        """Từ loại ngay trước tên ("bệnh viện Hùng Vương") hoặc đầu tên thắng kind "khac"/None."""
        name = re.escape(fold(place.name))
        before = re.search(rf"\b(?:({POI_ALT})\s+)?{name}\b", self.text)
        leading = re.match(rf"({POI_ALT})\b", fold(place.name))
        word = (before and before.group(1)) or (leading and leading.group(1))
        if place.kind in (None, "khac") and word:
            return place.model_copy(update={"kind": POI_KINDS[word]})
        return place

    def _mentions(self, name: str) -> bool:
        """Câu nhắc tên địa điểm đang có (một từ riêng của tên, hoặc bí danh của nó)."""
        words = set(fold(name).split()) - {"truong", "dai", "hoc", "benh", "vien", "cao", "dang"}
        said = set(self.text.split())
        return any(len(w) > 2 and w in said for w in words) or any(
            key in said and set(value.split()) <= words for key, value in ALIASES.items())

    def _correct_pois(
        self, delta: ConstraintDelta, current: SearchConstraints, ignored: list[str]
    ) -> None:
        """POI chỉ khi câu nhắc trường/bệnh viện/chợ; TTTM, công viên... thành sở thích mềm."""
        known = {poi.poi_type for poi in current.near_pois}
        mentioned = [r for r in delta.near_pois if POI_MENTIONS_RAW[r.poi_type].search(self.raw)
                     and r.poi_type not in {p.kind for p in delta.near_places}]  # tên riêng thắng
        explained = delta.near_places or any(p.search(self.text) for p, _ in SOFT_PLACES_FOLDED)
        if "gan" in self.text.split() and not explained:  # "gần <nơi lạ>": báo, không bỏ im
            ignored += [f"gần {POI_NAMES[r.poi_type]}" for r in delta.near_pois
                        if r not in mentioned and r.poi_type not in known]
        delta.near_pois = mentioned
        for pattern, phrase in SOFT_PLACES_FOLDED:
            if pattern.search(self.text):  # thay cách LLM viết ("gần TTTM") bằng cụm chuẩn
                kept = [p for p in phrases(delta.soft_query) if not pattern.search(fold(p))]
                delta.soft_query = ", ".join([*kept, phrase])

    def _correct_property_kinds(
        self, plan: TurnPlan, delta: ConstraintDelta, reset: bool
    ) -> None:
        """Loại BĐS suy từ từ khóa trong câu (spec 9 #23, #32); bảng map của code thắng LLM."""
        if ANY_KIND_PATTERN_FOLDED.search(self.text):  # "loại nào cũng được": bỏ, không suy lại
            delta.property_kinds = []
            plan.clear_fields = list(dict.fromkeys([*plan.clear_fields, "property_types"]))
            return
        kinds = []
        for pattern, kind in KIND_KEYWORDS_FOLDED:
            match = pattern.search(self.text)
            if match and not NEGATED_PATTERN_FOLDED.search(self.text[:match.start()]):
                kinds.append(kind)
        if "dat_nen_du_an" not in kinds and LAND_PATTERN_RAW.search(self.raw):
            kinds.append("dat")
        if kinds or reset:  # sau reset chỉ tính câu nói (loại nêu trong câu thắng "bỏ hết", B6)
            delta.property_kinds = kinds

    def _correct_areas(
        self, delta: ConstraintDelta, current_areas: list[str], ward_names: list[str],
        district_names: Sequence[str],
    ) -> None:
        """"Phường/xã <tên>" là phường mới, tên còn lại là quận cũ; tên LLM chỉ giữ khi có nhắc."""
        wards, rest = self._wards_in_message(ward_names)
        is_ward = {name: fold(name).startswith(("phuong ", "xa ")) for name in current_areas}
        echo_wards = {area_key(n) for n, ward in is_ward.items() if ward}
        echo_districts = {area_key(n) for n, ward in is_ward.items() if not ward}

        districts = [
            name for name in delta.district_names
            if area_key(name) in echo_districts or _said(area_key(name), rest)
        ]
        if not (delta.district_names or delta.new_ward_names):  # LLM bỏ sót khu vực (C35#5)
            districts = [name for name in district_names if _said(area_key(name), rest)]
        for name in delta.new_ward_names:
            key = area_key(name)
            if re.search(rf"\b(?:phuong|xa)\s{re.escape(key)}\b", self.text):
                wards.setdefault(key, name)
            elif _said(key, rest):  # tên trần, không có "phường/xã" đứng trước: quận cũ
                districts.append(name)
            elif key in echo_wards:
                wards.setdefault(key, name)
        delta.district_names = list({area_key(name): name for name in districts}.values())
        delta.new_ward_names = list(wards.values())

    def _wards_in_message(self, ward_names: list[str]) -> tuple[dict[str, str], str]:
        """Phường/xã mới có chữ "phường/xã" đứng trước; trả thêm phần câu sau khi bỏ các cụm đó."""
        known = {area_key(name): name for name in ward_names}
        found: dict[str, str] = {}
        rest = self.text
        for match in WARD_PATTERN_FOLDED.finditer(self.text):
            tail = match.group(2).strip()
            key = max((k for k in known if tail == k or tail.startswith(k + " ")),
                      key=len, default=None)
            if key:
                found[key] = known[key]
                rest = rest.replace(f"{match.group(1)} {key}", " ")
        return found, rest

    def _correct_clear_fields(self, plan: TurnPlan, delta: ConstraintDelta) -> None:
        """Bỏ khu vực khi câu nói "toàn thành phố"; không bỏ loại BĐS nếu câu không nhắc loại."""
        if ANY_AREA_PATTERN_FOLDED.search(self.text):  # C42#2
            delta.district_names, delta.new_ward_names = [], []
            plan.clear_fields = list(
                dict.fromkeys([*plan.clear_fields, "district_ids", "new_ward_ids"])
            )
        if not PROPERTY_WORDS_PATTERN_FOLDED.search(self.text):
            plan.clear_fields = [f for f in plan.clear_fields if f != "property_types"]
