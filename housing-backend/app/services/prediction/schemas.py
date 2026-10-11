"""Mô hình dữ liệu của hội thoại dự đoán giá: kết quả trích xuất, state, phản hồi."""

from typing import Literal

from pydantic import BaseModel, Field

from app.services.prediction.geocoder import Location
from app.services.prediction.predictor import PriceEstimate

PropertyName = Literal[
    "căn hộ chung cư", "nhà riêng", "nhà biệt thự, liền kề", "nhà mặt phố", "bán đất"
]
TurnStatus = Literal["collecting", "ready", "predicted", "out_of_scope"]


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
    asked_optional: bool = False       # đã hỏi trường tuỳ chọn một lần, không hỏi lặp
    asking: str | None = None          # trường vừa hỏi, giúp LLM hiểu câu trả lời cộc lốc ("80")
    location: Location | None = None   # tọa độ đã geocode cho (address_text, district_code)
    located_for: tuple[str | None, int | None] | None = None
    prediction: PriceEstimate | None = None


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
