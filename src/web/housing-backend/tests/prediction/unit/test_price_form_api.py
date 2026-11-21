"""/api/v1/price/* (form định giá): options, geocode, predict với predictor/geocoder giả."""

import pytest
from fastapi.testclient import TestClient
from prediction_fakes import FakeExtractor, FakeGeocoder, make_predictor

from app.api.deps import get_prediction_chat
from app.main import app
from app.services.prediction.chat import PredictionChat
from app.services.prediction.geocoder import Location

BASE = "/api/v1/price"
HOUSE = {"property_code": 2, "district_code": 22, "area": 60}


@pytest.fixture
def chat():
    geocoder = FakeGeocoder(Location(latitude=10.80, longitude=106.65, source="goong"))
    instance = PredictionChat(FakeExtractor(), make_predictor(), geocoder)
    app.dependency_overrides[get_prediction_chat] = lambda: instance
    yield instance
    app.dependency_overrides.clear()


@pytest.fixture
def client(chat):
    with TestClient(app) as test_client:
        yield test_client


def test_options_lists_supported_types_and_all_districts(client):
    body = client.get(f"{BASE}/options").json()
    assert {item["code"] for item in body["property_types"]} == {0, 2, 3, 4, 7}
    assert len(body["districts"]) == 24
    assert body["fields_by_type"]["0"] == ["bedrooms"]          # chung cư chỉ dùng phòng ngủ
    assert body["bounds"]["area"]["min"] == 10


def test_predict_with_user_coordinates_skips_geocoder(client, chat):
    response = client.post(f"{BASE}/predict", json={**HOUSE, "latitude": 10.79, "longitude": 106.82,
                                                     "bedrooms": 3, "floors": 2})
    assert response.status_code == 200
    body = response.json()
    assert body["location"] == {"latitude": 10.79, "longitude": 106.82, "source": "user"}
    assert body["estimate"]["price_per_m2"] == pytest.approx(50, rel=0.01)
    assert body["estimate"]["total_price"] == pytest.approx(3000, rel=0.01)
    assert chat.geocoder.calls == []


def test_predict_without_coordinates_geocodes_address(client, chat):
    response = client.post(f"{BASE}/predict", json={**HOUSE, "address": "Cộng Hòa"})
    assert response.status_code == 200
    assert response.json()["location"]["source"] == "goong"
    assert chat.geocoder.calls == [("Cộng Hòa", 22)]


def test_predict_without_address_uses_district_name(client, chat):
    client.post(f"{BASE}/predict", json=HOUSE)
    assert chat.geocoder.calls == [("Tân Bình", 22)]


@pytest.mark.parametrize("change", [
    {"area": 5},                                   # dưới biên diện tích
    {"floors": 0},                                 # 0 tầng: phải để trống, không gửi 0
    {"latitude": 21.03, "longitude": 105.85},      # Hà Nội
    {"district_code": 24},
    {"property_code": 9},                          # kho xưởng: mô hình không hỗ trợ
])
def test_predict_rejects_invalid_input(client, change):
    assert client.post(f"{BASE}/predict", json={**HOUSE, **change}).status_code == 422


def test_predict_without_location_returns_422(client, chat):
    chat.geocoder.location = None
    response = client.post(f"{BASE}/predict", json=HOUSE)
    assert response.status_code == 422
    assert "bản đồ" in response.json()["detail"]


def test_geocode_returns_location(client):
    body = {"district_code": 20, "address": "Eastmark City"}
    response = client.post(f"{BASE}/geocode", json=body)
    assert response.status_code == 200
    assert response.json()["source"] == "goong"


def test_model_not_ready_returns_503():
    app.dependency_overrides[get_prediction_chat] = lambda: None
    try:
        with TestClient(app) as test_client:
            assert test_client.post(f"{BASE}/predict", json=HOUSE).status_code == 503
    finally:
        app.dependency_overrides.clear()
