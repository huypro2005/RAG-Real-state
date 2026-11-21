"""Định giá bằng form (không qua chat): danh mục lựa chọn, tìm tọa độ địa chỉ, dự đoán giá.

Dự đoán đi qua cùng predictor với chatbot: RemotePricePredictor gọi Prediction Server, server lỗi
thì dùng mô hình cục bộ và thêm cảnh báo vào `warnings`.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from app.api.deps import PredictionChatDep
from app.services.prediction.chat import PredictionChat
from app.services.prediction.constants import (
    BOUNDS,
    CENTER,
    DISTRICT_NAMES,
    HCM_LAT,
    HCM_LON,
    OPTIONAL_FIELDS,
    OPTIONALS_BY_TYPE,
    PROPERTY_PHRASES,
    PROPERTY_TYPES,
)
from app.services.prediction.geocoder import Location
from app.services.prediction.predictor import PriceEstimate, PriceInput

router = APIRouter(prefix="/price", tags=["price"])

NOT_READY = "Mô hình định giá chưa sẵn sàng"
NO_LOCATION = "Không xác định được vị trí. Hãy chọn điểm trên bản đồ hoặc nhập tọa độ."
_AREA, _FLOORS, _BEDROOMS, _FRONTAGE = (
    BOUNDS[key] for key in ("area", "floors", "bedrooms", "frontage"))


class PriceFormRequest(BaseModel):
    """Một căn cần định giá. Trường tùy chọn để trống (null) nghĩa là không biết."""

    property_code: int
    district_code: int = Field(ge=0, lt=len(DISTRICT_NAMES))
    area: float = Field(ge=_AREA[0], le=_AREA[1])
    address: str | None = Field(default=None, max_length=300)
    latitude: float | None = Field(default=None, ge=HCM_LAT[0], le=HCM_LAT[1])
    longitude: float | None = Field(default=None, ge=HCM_LON[0], le=HCM_LON[1])
    frontage: float | None = Field(default=None, ge=_FRONTAGE[0], le=_FRONTAGE[1])
    bedrooms: int | None = Field(default=None, ge=_BEDROOMS[0], le=_BEDROOMS[1])
    floors: int | None = Field(default=None, ge=_FLOORS[0], le=_FLOORS[1])


class GeocodeRequest(BaseModel):
    district_code: int = Field(ge=0, lt=len(DISTRICT_NAMES))
    address: str | None = Field(default=None, max_length=300)
    property_code: int | None = None


class PriceFormResult(BaseModel):
    estimate: PriceEstimate
    location: Location          # tọa độ thực sự đưa vào mô hình
    used_fields: list[str]      # trường tùy chọn mô hình dùng cho loại nhà này


def _require(prediction: PredictionChat | None) -> PredictionChat:
    if prediction is None:
        raise HTTPException(503, NOT_READY)
    return prediction


@router.get("/options")
def options():
    """Danh mục cho form: loại nhà, quận/huyện, biên hợp lệ và trường dùng theo loại nhà."""
    return {
        "property_types": [{"code": code, "name": name} for name, code in PROPERTY_TYPES.items()],
        "districts": [{"code": code, "name": name} for code, name in enumerate(DISTRICT_NAMES)],
        "bounds": {key: {"min": low, "max": high, "label": label, "unit": unit}
                   for key, (low, high, label, unit) in BOUNDS.items()},
        "fields_by_type": {str(code): list(OPTIONALS_BY_TYPE.get(code, OPTIONAL_FIELDS))
                           for code in PROPERTY_TYPES.values()},
        "center": {"lat": CENTER[0], "lon": CENTER[1]},
        "hcm_bounds": {"lat": HCM_LAT, "lon": HCM_LON},
    }


@router.post("/geocode", response_model=Location)
async def geocode(request: GeocodeRequest, prediction: PredictionChatDep):
    """Tọa độ của địa chỉ trong quận đã chọn (Goong); không ra điểm trong quận thì tâm quận."""
    location = await _locate(_require(prediction), request.address, request.district_code,
                             request.property_code)
    if location is None:
        raise HTTPException(404, NO_LOCATION)
    return location


@router.post("/predict", response_model=PriceFormResult)
async def predict(request: PriceFormRequest, prediction: PredictionChatDep):
    """Dự đoán giá/m² và tổng giá. Có tọa độ thì dùng thẳng, không thì tìm từ địa chỉ + quận."""
    chat = _require(prediction)
    if request.property_code not in PROPERTY_TYPES.values():
        raise HTTPException(422, f"Loại nhà đất không hỗ trợ: {request.property_code}")
    if request.latitude is not None and request.longitude is not None:
        location = Location(latitude=request.latitude, longitude=request.longitude, source="user")
    else:
        location = await _locate(chat, request.address, request.district_code,
                                 request.property_code)
        if location is None:
            raise HTTPException(422, NO_LOCATION)
    data = PriceInput(
        property_code=request.property_code, district_code=request.district_code,
        area=request.area, latitude=location.latitude, longitude=location.longitude,
        frontage=request.frontage, bedrooms=request.bedrooms, floors=request.floors,
    )
    try:  # predictor đồng bộ (httpx/sklearn): chạy trong threadpool để không chặn event loop
        estimate = await run_in_threadpool(chat.predictor.predict, data)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    except RuntimeError as error:  # server dự đoán lỗi và không có model cục bộ
        raise HTTPException(503, NOT_READY) from error
    used = list(OPTIONALS_BY_TYPE.get(request.property_code, OPTIONAL_FIELDS))
    return PriceFormResult(estimate=estimate, location=location, used_fields=used)


async def _locate(chat: PredictionChat, address: str | None, district_code: int,
                  property_code: int | None) -> Location | None:
    text = (address or "").strip() or DISTRICT_NAMES[district_code]
    hint = PROPERTY_PHRASES.get(property_code) if property_code is not None else None
    return await chat.geocoder.locate(text, district_code, hint)
