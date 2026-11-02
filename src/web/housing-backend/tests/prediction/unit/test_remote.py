"""RemotePricePredictor: gọi Prediction Server, lỗi thì rơi về model cục bộ (httpx giả)."""

import httpx
import pytest
from prediction_fakes import make_predictor

from app.services.prediction.predictor import PriceInput
from app.services.prediction.remote import AUTH_WARNING, FALLBACK_WARNING, RemotePricePredictor

INPUT = PriceInput(property_code=2, district_code=18, area=80, latitude=10.73, longitude=106.72)
SERVER_ANSWER = {
    "price_per_m2": 100.0, "total_price": 8000.0, "price_per_m2_low": 80.0,
    "price_per_m2_high": 130.0, "distance_to_center_km": 5.6, "district_median_per_m2": None,
    "model_run_id": 3, "range_source": "tree_percentiles",
}


def remote(handler, local=None) -> RemotePricePredictor:
    predictor = RemotePricePredictor("http://server", "key", 1.0, local=local)
    predictor.client = httpx.Client(
        base_url="http://server", transport=httpx.MockTransport(handler),
        headers={"X-API-Key": "key"})
    return predictor


def test_uses_server_answer_and_sends_key():
    seen = {}

    def handler(request):
        seen["key"] = request.headers["X-API-Key"]
        return httpx.Response(200, json=SERVER_ANSWER)

    estimate = remote(handler).predict(INPUT)
    assert estimate.price_per_m2 == 100.0 and seen["key"] == "key"
    assert not estimate.warnings


@pytest.mark.parametrize("failure", [
    lambda request: httpx.Response(503, json={"detail": "chưa có model"}),
    lambda request: (_ for _ in ()).throw(httpx.ConnectError("server tắt")),
    lambda request: (_ for _ in ()).throw(httpx.ReadTimeout("quá hạn")),
])
def test_falls_back_to_local_model_with_warning(failure):
    estimate = remote(failure, local=make_predictor()).predict(INPUT)
    assert FALLBACK_WARNING in estimate.warnings and estimate.price_per_m2 > 0


def test_invalid_input_from_server_raises_value_error():
    with pytest.raises(ValueError, match="diện tích"):
        remote(lambda request: httpx.Response(422, json={"detail": "sai diện tích"})).predict(INPUT)


def test_no_local_model_and_server_down_raises_runtime_error():
    with pytest.raises(RuntimeError):
        remote(lambda request: httpx.Response(500)).predict(INPUT)


@pytest.mark.parametrize("status", [401, 403])
def test_wrong_api_key_is_reported_differently_from_downtime(status, caplog):
    estimate = remote(lambda request: httpx.Response(status), local=make_predictor()).predict(INPUT)
    assert AUTH_WARNING in estimate.warnings and FALLBACK_WARNING not in estimate.warnings
    assert "từ chối khóa API" in caplog.text
