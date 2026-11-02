"""Request/response của POST /predict (kết quả là PredictionResult của served_predictor)."""
from pydantic import BaseModel, Field, StrictInt

from src.prediction_server.services.prediction.served_predictor import PredictionResult

MAX_BATCH = 100


class PredictItem(BaseModel):
    """Cùng trường với PriceInput của backend; biên hợp lệ do PriceInput kiểm (lỗi -> 422)."""

    property_code: StrictInt
    district_code: StrictInt
    area: float
    latitude: float
    longitude: float
    frontage: float | None = None
    bedrooms: StrictInt | None = None
    floors: StrictInt | None = None


class PredictBatch(BaseModel):
    items: list[PredictItem] = Field(min_length=1, max_length=MAX_BATCH)


class PredictBatchResult(BaseModel):
    items: list[PredictionResult]
