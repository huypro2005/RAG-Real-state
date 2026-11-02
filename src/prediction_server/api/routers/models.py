"""GET /models, GET /models/{id|active}/charts, POST /models/{id}/charts/rebuild, rollback."""
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from src.prediction_server.api.deps import ContainerDep, require_api_key
from src.prediction_server.schemas.jobs import JobAccepted
from src.prediction_server.schemas.models import ActivateResult
from src.prediction_server.services.registry.registry import (
    ModelFileMissingError,
    ModelNotFoundError,
)

router = APIRouter(prefix="/api/v1", tags=["models"], dependencies=[Depends(require_api_key)])


@router.get("/models")
def list_models(container: ContainerDep, limit: int = 50) -> list[dict]:
    """Lịch sử retrain, mới nhất trước; có `has_charts`, không nhúng `charts`."""
    runs = container.runs.history(limit)
    for run in runs:  # chỉ tên file, không lộ đường dẫn tuyệt đối của máy chủ
        run["artifact_path"] = Path(run["artifact_path"]).name if run["artifact_path"] else None
    return runs


# `active` phải khai báo trước `{run_id}`, nếu không "active" bị đọc thành số nguyên (422)
@router.get("/models/active/charts")
def active_charts(container: ContainerDep) -> dict:
    return _charts_or_404(container.runs.charts(None))


@router.get("/models/{run_id}/charts")
def run_charts(run_id: int, container: ContainerDep) -> dict:
    return _charts_or_404(container.runs.charts(run_id))


@router.post("/models/{run_id}/charts/rebuild", status_code=202, response_model=JobAccepted)
def rebuild_charts(run_id: int, container: ContainerDep):
    """Dựng lại charts của phiên bản từ artifact + dữ liệu hiện tại (nền)."""
    if container.runs.succeeded(run_id) is None:
        raise HTTPException(404, f"Không có run {run_id} đã train xong")
    return {"job_id": container.runner.submit_charts_rebuild(run_id)}


@router.post("/models/{run_id}/activate", response_model=ActivateResult)
def activate_model(run_id: int, container: ContainerDep):
    """Đặt run cũ làm model hoạt động; /predict dùng ngay ở request kế tiếp."""
    try:
        predictor = container.registry.activate(run_id)
    except ModelNotFoundError as error:
        raise HTTPException(404, str(error)) from error
    except ModelFileMissingError as error:
        raise HTTPException(409, str(error)) from error
    return {"active_run_id": run_id, "candidate": predictor.candidate}


def _charts_or_404(charts: dict | None) -> dict:
    if charts is None:
        raise HTTPException(404, "Phiên bản này chưa có charts (dùng POST .../charts/rebuild)")
    return charts
