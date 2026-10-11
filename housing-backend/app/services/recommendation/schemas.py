"""Hợp đồng dữ liệu hội thoại gợi ý (spec mục 2); đơn vị như bảng listings: triệu VND, m², mét."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

PoiType = Literal["truong_hoc", "benh_vien", "cho"]
POI_NAMES = {"truong_hoc": "trường học", "benh_vien": "bệnh viện", "cho": "chợ"}

# Nhóm loại BĐS mà TurnInterpreter được phép trả; code map sang giá trị thật của
# listings.property_type bằng PROPERTY_TYPES (LLM không tự viết giá trị DB).
PropertyKind = Literal[
    "can_ho", "nha_rieng", "nha_mat_pho", "biet_thu_lien_ke", "shophouse",
    "dat", "dat_nen_du_an", "kho_xuong",
]
PROPERTY_TYPES: dict[str, list[str]] = {
    "can_ho": ["Căn hộ chung cư"],
    "nha_rieng": ["Nhà riêng"],
    "nha_mat_pho": ["Nhà mặt phố"],
    "biet_thu_lien_ke": ["Nhà biệt thự, liền kề"],
    "shophouse": ["Shophouse, nhà phố thương mại"],
    "dat": ["Bán đất"],
    "dat_nen_du_an": ["Đất nền dự án"],
    "kho_xuong": ["Kho, nhà xưởng"],
}

# Trường được phép bỏ. near_pois.<loại> chỉ bỏ điều kiện POI của loại đó.
ClearableField = Literal[
    "price_min", "price_max", "property_types", "district_ids", "new_ward_ids",
    "area_min", "area_max", "bedrooms_min", "near_pois",
    "near_pois.truong_hoc", "near_pois.benh_vien", "near_pois.cho", "soft_query",
]

Intent = Literal[
    "search", "refine", "relax", "answer_clarification",
    "ask_detail", "compare", "reset", "out_of_scope",
]
TurnStatus = Literal["ok", "need_clarification", "out_of_scope", "no_results", "answered"]


class PoiConstraint(BaseModel):
    poi_type: PoiType
    max_distance_m: int  # "dưới 2 km" -> 2000


class PoiRequest(BaseModel):
    """POI trong câu người dùng; không nói khoảng cách thì null, code dùng mặc định 2 km."""

    poi_type: PoiType
    max_distance_m: int | None


class SearchConstraints(BaseModel):
    """Điều kiện cứng + sở thích mềm, cộng dồn qua các lượt."""

    price_min: float | None = None
    price_max: float | None = None
    # price_min do "tầm X" sinh ra, đổi giá thì bỏ (spec 9 #16). Cờ nội bộ của state: không
    # ra API/ngữ cảnh LLM.
    price_min_derived: bool = Field(default=False, exclude=True)
    property_types: list[str] = []  # giá trị nguyên văn của listings.property_type
    district_ids: list[int] = []    # districts_old.id
    new_ward_ids: list[int] = []    # wards_new.id
    area_min: float | None = None
    area_max: float | None = None
    bedrooms_min: int | None = None
    near_pois: list[PoiConstraint] = []
    soft_query: str | None = None   # chỉ dùng để sắp xếp bằng vector, không lọc


class ConstraintDelta(BaseModel):
    """Thay đổi điều kiện trong một câu (khu vực là TÊN); price_max đứng trước price_min để LLM
    điền "3 tỷ"/"tầm 3 tỷ" vào đúng price_max."""

    price_max: float | None = None
    price_min: float | None = None
    price_approx: bool = False  # "tầm/khoảng X": price_max = X gốc, code tính khoảng giá
    cheaper: bool = False  # "rẻ hơn chút": code giảm giá theo CHEAPER_FACTOR
    property_kinds: list[PropertyKind] = []
    district_names: list[str] = []
    new_ward_names: list[str] = []
    area_min: float | None = None
    area_max: float | None = None
    bedrooms_min: int | None = None
    near_pois: list[PoiRequest] = []
    soft_query: str | None = None


class TurnPlan(BaseModel):
    """Đầu ra của TurnInterpreter; set_fields đặt CUỐI vì đứng trước thì gpt-4o-mini hay sinh
    khoảng trắng vô hạn (đo 7/8 lần)."""

    intent: Intent
    clear_fields: list[ClearableField] = []
    set_fields: ConstraintDelta


class ListingHit(BaseModel):
    listing_id: str
    title: str
    price: float
    area: float
    property_type: str | None
    bedrooms: int | None
    district_old: str | None
    old_address: str | None
    new_address: str | None
    listing_url: str
    posted_at: date | None
    expired_at: date | None
    poi_distances: dict[str, float]  # poi_type -> mét tới POI gần nhất loại đó
    score: float | None              # 1 - cosine distance; None khi sắp theo ngày đăng
    similar_ids: list[str] = []      # tin đăng lại gần như y hệt đã gộp vào tin này
    latitude: float | None = None
    longitude: float | None = None
    coords_reliable: bool = True     # False: thiếu tọa độ hoặc cờ coords_outside_hcm
    position: int = 0                # 1..5, khớp "căn thứ N" và số trên bản đồ
    days_left: int | None = None     # expired_at - as_of (âm: tin đã hết hạn)


class RelaxOption(BaseModel):
    field: Literal["near_pois", "price_max", "property_types", "location"]
    description: str     # "bỏ điều kiện gần bệnh viện", "tăng ngân sách lên 3,6 tỷ"
    result_count: int    # số tin người dùng sẽ thấy (đã gộp tin đăng lại) nếu chỉ nới điều này
    message: str         # câu gửi lại nguyên văn làm tin nhắn tiếp theo để áp phương án này


class ChatTurnResult(BaseModel):
    conversation_id: str
    status: TurnStatus
    constraints: SearchConstraints  # trạng thái SAU lượt này
    listings: list[ListingHit] = []
    referenced_ids: list[str] = []
    relax_options: list[RelaxOption] = []
    degraded: bool = False          # embed/rerank lỗi, đã dùng phương án dự phòng
    answer: str
    summary: str = ""               # answer bỏ khối từng tin (UI vẽ tin bằng thẻ)


class ChatRequest(BaseModel):
    mode: Literal["recommendation"]  # client chọn mode, backend không đoán (đề cương 5.10)
    conversation_id: str | None = Field(default=None, max_length=100)
    # Không giới hạn 1.000 ở đây: câu dài hơn được cắt và báo lại (spec mục 2), không trả 422.
    message: str = Field(min_length=1, max_length=20_000)
    as_of: date | None = None


class ConversationState(BaseModel):
    conversation_id: str
    constraints: SearchConstraints = SearchConstraints()
    last_results: list[str] = []          # tối đa 5 listing_id theo thứ tự đã trả
    pending_question: str | None = None   # câu hỏi bổ sung đang chờ người dùng trả lời
    pending_value: float | None = None    # giá tối đa đang chờ xác nhận ("ừ" thì áp, spec 9 #29d)
    last_status: TurnStatus | None = None  # ok/no_results của lượt tìm gần nhất
    history: list[dict[str, str]] = []    # 6 lượt gần nhất: {"role", "content"}


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
