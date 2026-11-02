"""Dashboard mô hình giá: proxy tới Prediction Server (frontend không giữ khóa API)."""

from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import ValidationError

from app.core.config import get_settings
from app.schemas.dashboard import DashboardRun, ModelDetail
from app.services.dashboard import (
    DashboardClient,
    DashboardNotFoundError,
    DashboardUnavailableError,
)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@lru_cache
def get_dashboard_client() -> DashboardClient:
    settings = get_settings()
    key = settings.prediction_server_api_key
    return DashboardClient(settings.prediction_server_url,
                           key.get_secret_value() if key else None)


ClientDep = Annotated[DashboardClient, Depends(get_dashboard_client)]


@router.get("/models", response_model=list[DashboardRun])
def list_models(client: ClientDep):
    return _proxied(client.runs)


@router.get("/models/{model_id}", response_model=ModelDetail)
def model_detail(model_id: str, client: ClientDep):
    """`model_id` là số phiên bản hoặc `active`."""
    if model_id != "active" and not model_id.isdigit():
        raise HTTPException(422, "model_id phải là số hoặc 'active'")
    return _proxied(lambda: client.detail(model_id))


def _proxied(call):
    """Đổi lỗi của client sang HTTP: 404 không có, 503 server mô hình không dùng được."""
    try:
        return call()
    except DashboardNotFoundError as error:
        raise HTTPException(404, str(error)) from error
    except DashboardUnavailableError as error:
        raise HTTPException(503, str(error)) from error
    except ValidationError as error:  # server trả dữ liệu sai schema: không chuyển tiếp bừa
        raise HTTPException(502, "Prediction Server trả dữ liệu sai định dạng") from error
