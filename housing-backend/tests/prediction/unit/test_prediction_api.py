"""POST /api/v1/chat và /reset (TestClient, extractor/geocoder giả): mode, 422, CORS, reset."""

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from prediction_fakes import FakeExtractor, FakeGeocoder, ext, make_predictor

from app.api.deps import get_prediction_chat, get_recommendation_service
from app.main import app
from app.services.prediction.chat import PredictionChat
from app.services.recommendation.schemas import ChatTurnResult, SearchConstraints
from app.services.recommendation.service import ConversationStore

CHAT, RESET = "/api/v1/chat", "/api/v1/reset"
ORIGIN = "http://localhost:5173"


@pytest.fixture
def prediction():
    chat = PredictionChat(FakeExtractor(), make_predictor(), FakeGeocoder())
    app.dependency_overrides[get_prediction_chat] = lambda: chat
    yield chat
    app.dependency_overrides.clear()


@pytest.fixture
def recommendation():
    """Service giả: không cần DB/OpenAI, đủ để kiểm tra điều phối mode và reset."""
    async def fake_chat(conversation_id, message, as_of):
        return ChatTurnResult(
            conversation_id=conversation_id or "r1", status="ok",
            constraints=SearchConstraints(), answer=f"gợi ý cho: {message}")

    service = SimpleNamespace(chat=fake_chat, store=ConversationStore())
    app.dependency_overrides[get_recommendation_service] = lambda: service
    yield service
    app.dependency_overrides.pop(get_recommendation_service, None)


@pytest.fixture
def client(prediction, recommendation):
    with TestClient(app) as test_client:
        yield test_client


def post(client, message, mode="prediction", **extra):
    return client.post(CHAT, json={"mode": mode, "message": message, **extra})


def test_four_turn_prediction_conversation_returns_documented_shape(client, prediction):
    prediction.extractor.extractions = [
        ext(property_type="nhà riêng"), ext(district_name="Quận 1", area_m2=80)]
    first = post(client, "nhà riêng").json()
    assert set(first) == {"conversation_id", "mode", "status", "answer", "summary", "fields",
                          "missing", "prediction"}
    assert first["mode"] == "prediction" and first["status"] == "collecting"
    assert first["prediction"] is None and first["missing"] == ["district", "area"]
    cid = first["conversation_id"]
    assert post(client, "q1 80m2", conversation_id=cid).json()["status"] == "ready"
    done = post(client, "ok", conversation_id=cid).json()
    assert done["status"] == "predicted" and done["conversation_id"] == cid
    assert set(done["prediction"]) == {
        "price_per_m2", "total_price", "price_per_m2_low", "price_per_m2_high",
        "distance_to_center_km", "district_median_per_m2", "median_by_type", "warnings"}
    assert done["prediction"]["total_price"] == pytest.approx(
        done["prediction"]["price_per_m2"] * 80)
    assert post(client, "reset", conversation_id=cid).json()["missing"] == [
        "property_type", "district", "area"]


def test_recommendation_mode_is_dispatched_with_mode_in_response(client):
    body = post(client, "nhà Quận 7 dưới 5 tỷ", mode="recommendation").json()
    assert body["mode"] == "recommendation" and body["answer"] == "gợi ý cho: nhà Quận 7 dưới 5 tỷ"
    assert body["conversation_id"] == "r1" and "constraints" in body


@pytest.mark.parametrize("body", [
    {"message": "xin chào"},
    {"mode": "valuation", "message": "xin chào"},
    {"mode": "prediction"},
    {"mode": "prediction", "message": ""},
])
def test_invalid_mode_or_body_is_422(client, body):
    assert client.post(CHAT, json=body).status_code == 422


def test_cors_preflight_for_chat_and_reset_allows_only_frontend_origins(client):
    headers = {"Access-Control-Request-Method": "POST",
               "Access-Control-Request-Headers": "content-type"}
    for path in (CHAT, RESET):
        ok = client.options(path, headers={"Origin": ORIGIN, **headers})
        assert ok.status_code == 200 and ok.headers["access-control-allow-origin"] == ORIGIN
        other = client.options(path, headers={"Origin": "http://evil.example", **headers})
        assert "access-control-allow-origin" not in other.headers


def test_reset_clears_both_modes(client, prediction, recommendation):
    prediction.extractor.extractions = [ext(property_type="nhà riêng")]
    cid = post(client, "nhà riêng", conversation_id="same").json()["conversation_id"]
    state = recommendation.store.get(cid)
    state.last_results = ["1"]
    recommendation.store.save(state)
    assert client.post(RESET, json={"conversation_id": cid}).json() == {"conversation_id": cid}
    assert recommendation.store.get(cid).last_results == []
    prediction.extractor.extractions = [ext()]
    assert post(client, "xin chào", conversation_id=cid).json()["fields"]["property_type"] is None


def test_prediction_mode_without_trained_model_is_503_but_recommendation_still_works(
    client, prediction
):
    app.dependency_overrides[get_prediction_chat] = lambda: None
    assert post(client, "nhà riêng").status_code == 503
    assert post(client, "nhà Quận 7", mode="recommendation").status_code == 200
