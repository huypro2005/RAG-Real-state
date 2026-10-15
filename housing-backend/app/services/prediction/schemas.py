"""Mô hình dữ liệu của hội thoại dự đoán giá: kết quả trích xuất, state, phản hồi."""

from typing import Literal

from pydantic import BaseModel, Field

from app.services.prediction.constants import DISTRICT_NAMES, OPTIONAL_FIELDS, OPTIONALS_BY_TYPE
from app.services.prediction.geocoder import Location
from app.services.prediction.predictor import PriceEstimate

PropertyName = Literal[
    "căn hộ chung cư", "nhà riêng", "nhà biệt thự, liền kề", "nhà mặt phố", "bán đất"
]
TurnStatus = Literal["collecting", "ready", "predicted", "out_of_scope"]
# what_if: giả định chưa áp dụng; other_mode: muốn tìm tin đăng (thuộc chế độ Gợi ý)
Intent = Literal["provide_info", "confirm", "question", "what_if", "chitchat", "other_mode",
                 "reset", "off_topic"]
QuestionTopic = Literal["why_price", "range", "model", "compare_district", "accuracy_tips", "other"]


class Extraction(BaseModel):
    """Những gì LLM đọc được từ MỘT tin nhắn; trường không nhắc tới phải là null/false."""

    # none: đúng việc; off_topic: không liên quan định giá nhà đất; other_province: ngoài TP.HCM
    refusal: Literal["none", "off_topic", "other_province"] = "none"
    property_type: PropertyName | None = None
    district_name: str | None = None   # quận/huyện như người dùng viết ("Q7", "Thủ Đức")
    address_text: str | None = None    # tên đường/khu/dự án cụ thể, không phải "cách trung tâm"
    area_m2: float | None = None
    floors: int | None = None
    bedrooms: int | None = None
    frontage_m: float | None = None
    wants_confirm: bool = False        # "ok", "chốt", "dự đoán đi"
    wants_reset: bool = False          # muốn bắt đầu BĐS mới
    # Giữ refusal/wants_* như cũ; code coi intent "off_topic"/"confirm"/"reset" là tương đương
    intent: Intent = "provide_info"
    question_topic: QuestionTopic | None = None   # chỉ khi intent = "question"
    compare_districts: list[str] = []  # quận được so sánh khi question_topic = "compare_district"


class PredictionState(BaseModel):
    """Trạng thái một hội thoại: các trường đã biết, tọa độ đã geocode, kết quả gần nhất."""

    conversation_id: str
    property_code: int | None = None
    district_code: int | None = None
    address_text: str | None = None
    area: float | None = None
    frontage: float | None = None
    bedrooms: int | None = None
    floors: int | None = None
    skipped: list[str] = []            # trường tuỳ chọn (và "address") đã hỏi một lần hoặc bỏ qua
    pending_values: dict[str, float | int] = {}  # số bất thường chờ người dùng xác nhận
    pending_check: str | None = None   # câu hỏi xác nhận tương ứng
    asking: str | None = None          # trường vừa hỏi, giúp LLM hiểu câu trả lời cộc lốc ("80")
    location: Location | None = None   # tọa độ đã geocode cho (address_text, district_code)
    located_for: tuple[str | None, int | None] | None = None
    prediction: PriceEstimate | None = None


    def district_only(self) -> bool:
        """Mới biết tên quận, chưa có tên đường/dự án cụ thể."""
        code = self.district_code
        return code is not None and self.address_text == DISTRICT_NAMES[code]

    def missing_optionals(self) -> list[str]:
        """Trường tuỳ chọn mà model dùng cho loại nhà này và chưa có, theo thứ tự nên hỏi."""
        used = OPTIONALS_BY_TYPE.get(self.property_code, OPTIONAL_FIELDS)
        return [key for key in used if getattr(self, key) is None]


class PredictionTurn(BaseModel):
    """Phản hồi của một lượt chat mode prediction (khớp spec mục 3.3)."""

    conversation_id: str
    mode: Literal["prediction"] = "prediction"
    status: TurnStatus
    answer: str
    summary: str = ""                  # trường đã biết, một dòng
    fields: dict[str, str | float | int | None] = Field(default_factory=dict)
    missing: list[str] = []            # trường bắt buộc còn thiếu
    prediction: PriceEstimate | None = None
    suggestions: list[str] = []        # ≤ 4 câu trả lời nhanh do code chọn (giao diện hiện chip)
