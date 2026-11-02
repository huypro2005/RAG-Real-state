"""POST /retrain: ép retrain ngay (nền)."""
from fastapi import APIRouter, Depends

from src.prediction_server.api.deps import ContainerDep, require_api_key
from src.prediction_server.schemas.jobs import JobAccepted

router = APIRouter(prefix="/api/v1", tags=["retrain"], dependencies=[Depends(require_api_key)])


@router.post("/retrain", status_code=202, response_model=JobAccepted)
def retrain(container: ContainerDep):
    """Nếu đang có retrain khác chạy (khóa tư vấn), job này báo `skipped`."""
    return {"job_id": container.runner.submit_retrain("manual")}
