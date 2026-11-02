"""RemotePricePredictor: gọi Prediction Server (src/prediction_server) để dự đoán giá.

Cùng giao diện với PricePredictor (predict, metrics, medians) để chatbot không phải đổi gì.
Server lỗi, quá hạn hoặc chưa có model (503) thì rơi về mô hình cục bộ kèm cảnh báo.
"""

import logging
from dataclasses import asdict

import httpx

from app.services.prediction.predictor import PriceEstimate, PriceInput, PricePredictor

logger = logging.getLogger(__name__)

FALLBACK_WARNING = "Máy chủ dự đoán không phản hồi, kết quả lấy từ mô hình cục bộ."
AUTH_WARNING = "Máy chủ dự đoán từ chối khóa API, kết quả lấy từ model cục bộ."


class RemotePricePredictor:
    """`local` là dự phòng (có thể None nếu máy này chưa train model cục bộ)."""

    def __init__(
        self, url: str, api_key: str | None, timeout: float, local: PricePredictor | None = None
    ):
        self.local = local
        self.client = httpx.Client(
            base_url=url.rstrip("/"), timeout=timeout,
            headers={"X-API-Key": api_key} if api_key else {},
        )

    @property
    def metrics(self) -> dict | None:
        return self.local.metrics if self.local else None

    @property
    def medians(self) -> dict[str, float]:
        return self.local.medians if self.local else {}

    def predict(self, fields: PriceInput | dict) -> PriceEstimate:
        """Raises:
            ValueError: server báo đầu vào sai (422), giống PricePredictor.
            RuntimeError: server không dùng được và không có mô hình cục bộ.
        """
        data = PriceInput(**fields) if isinstance(fields, dict) else fields
        try:
            response = self.client.post("/api/v1/predict", json=asdict(data))
        except httpx.HTTPError as error:
            return self._fallback(data, repr(error))
        if response.status_code == httpx.codes.UNPROCESSABLE_ENTITY:
            raise ValueError(response.json().get("detail"))
        if response.status_code in (httpx.codes.UNAUTHORIZED, httpx.codes.FORBIDDEN):
            logger.error("Prediction Server từ chối khóa API (HTTP %s)", response.status_code)
            return self._fallback(data, f"sai khóa API, HTTP {response.status_code}", AUTH_WARNING)
        if response.is_error:
            return self._fallback(data, f"HTTP {response.status_code}")
        return PriceEstimate(**response.json())  # trường thừa (model_run_id...) bị bỏ qua

    def _fallback(
        self, data: PriceInput, reason: str, warning: str = FALLBACK_WARNING
    ) -> PriceEstimate:
        logger.warning("Prediction Server không dùng được (%s)", reason)
        if self.local is None:
            raise RuntimeError(f"Server dự đoán lỗi ({reason}) và không có model cục bộ")
        estimate = self.local.predict(data)
        estimate.warnings = [*estimate.warnings, warning]
        return estimate
