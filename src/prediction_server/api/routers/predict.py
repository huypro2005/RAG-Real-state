"""POST /predict: một tin hoặc `items` (tối đa 100)."""
from app.services.prediction.predictor import PriceInput
from fastapi import APIRouter, Depends, HTTPException

from src.prediction_server.api.deps import ContainerDep, require_api_key
from src.prediction_server.schemas.predict import PredictBatch, PredictBatchResult, PredictItem
from src.prediction_server.services.prediction.served_predictor import PredictionResult

router = APIRouter(prefix="/api/v1", tags=["predict"], dependencies=[Depends(require_api_key)])


@router.post("/predict", response_model=PredictionResult | PredictBatchResult)
def predict(body: PredictBatch | PredictItem, container: ContainerDep):
    predictor = container.registry.current()
    if predictor is None:
        raise HTTPException(503, "Chưa có model đang hoạt động (đang bootstrap?)")
    items = body.items if isinstance(body, PredictBatch) else [body]
    try:
        inputs = [PriceInput(**item.model_dump()) for item in items]
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    results = predictor.predict_many(inputs)
    return PredictBatchResult(items=results) if isinstance(body, PredictBatch) else results[0]
