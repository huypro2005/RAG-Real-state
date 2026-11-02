"""DashboardClient: lấy lịch sử và charts của mô hình giá từ Prediction Server (giữ khóa API)."""

import httpx
from pydantic import TypeAdapter

from app.schemas.dashboard import Charts, DashboardRun, ModelDetail

DASHBOARD_TIMEOUT_S = 10.0  # charts ~100 KB, rộng hơn timeout 3 giây của /predict
MAX_RUNS = 100


class DashboardUnavailableError(Exception):
    """Server mô hình tắt, chưa cấu hình, từ chối khóa hoặc trả dữ liệu sai dạng (-> HTTP 503)."""


class DashboardNotFoundError(Exception):
    """Không có phiên bản/charts được hỏi (-> HTTP 404)."""


class DashboardClient:
    def __init__(self, url: str, api_key: str | None, client: httpx.Client | None = None):
        self.configured = bool(url)
        self.client = client or httpx.Client(
            base_url=url.rstrip("/"), timeout=DASHBOARD_TIMEOUT_S,
            headers={"X-API-Key": api_key} if api_key else {})

    def runs(self) -> list[DashboardRun]:
        body = self._get("/api/v1/models", {"limit": MAX_RUNS})
        return TypeAdapter(list[DashboardRun]).validate_python(body)

    def detail(self, model_id: str) -> ModelDetail:
        """`model_id` là số hoặc "active" (phiên bản đang chạy)."""
        runs = self.runs()
        run = next((r for r in runs if (r.is_active if model_id == "active"
                                         else str(r.id) == model_id)), None)
        if run is None:
            raise DashboardNotFoundError("Không có phiên bản mô hình này")
        charts = self._get(f"/api/v1/models/{run.id}/charts")
        return ModelDetail(model=run, charts=Charts.model_validate(charts))

    def _get(self, path: str, params: dict | None = None):
        if not self.configured:
            raise DashboardUnavailableError(
                "Chưa cấu hình PREDICTION_SERVER_URL nên chưa có dashboard mô hình")
        try:
            response = self.client.get(path, params=params)
        except httpx.HTTPError as error:
            raise DashboardUnavailableError(
                "Prediction Server không phản hồi, thử lại sau") from error
        if response.status_code == httpx.codes.NOT_FOUND:
            raise DashboardNotFoundError(response.json().get("detail", "Không tìm thấy"))
        if response.status_code in (httpx.codes.UNAUTHORIZED, httpx.codes.FORBIDDEN):
            raise DashboardUnavailableError(
                "Prediction Server từ chối khóa API (xem PREDICTION_SERVER_API_KEY)")
        if response.is_error:
            raise DashboardUnavailableError(f"Prediction Server lỗi (HTTP {response.status_code})")
        return response.json()
