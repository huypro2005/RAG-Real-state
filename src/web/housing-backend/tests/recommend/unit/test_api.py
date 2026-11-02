"""API chatbot (FastAPI TestClient, TurnInterpreter giả, DB housing_dev): mode, CORS, map, reset."""

import os

import pytest
from fakes import AS_OF, FakeEmbeddingClient, FakeInterpreter, plan
from fastapi.testclient import TestClient

from app.api.deps import get_recommendation_service
from app.main import app
from app.services.recommendation.schemas import SearchConstraints
from app.services.recommendation.service import RecommendationService

ORIGIN = "http://localhost:5173"
CHAT = "/api/v1/recommend/chat"
PREFLIGHT = {
    "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "content-type",
}


@pytest.fixture
def service():
    """Service dùng interpreter giả; dependency được thay trong suốt test."""
    if not os.environ.get("DATABASE_URL"):
        pytest.skip("chưa đặt DATABASE_URL (vd. ...@localhost:5432/housing_dev)")
    fake = RecommendationService(
        interpreter=FakeInterpreter([]), embedding_client=FakeEmbeddingClient(),
        rerank_enabled=False,
    )
    app.dependency_overrides[get_recommendation_service] = lambda: fake
    yield fake
    app.dependency_overrides.clear()


@pytest.fixture
def client(service):
    with TestClient(app) as test_client:  # một event loop cho cả lifespan và engine
        yield test_client


def chat(client, message, conversation_id=None, **extra):
    body = {"mode": "recommendation", "message": message, "as_of": AS_OF.isoformat(), **extra}
    if conversation_id:
        body["conversation_id"] = conversation_id
    return client.post(CHAT, json=body)


def test_mode_is_required_and_must_be_recommendation(client):
    assert client.post(CHAT, json={"message": "xin chào"}).status_code == 422
    assert chat(client, "xin chào", mode="prediction").status_code == 422


def test_cors_preflight_allows_the_frontend_origins_only(client):
    for origin in (ORIGIN, "http://127.0.0.1:5173"):
        allowed = client.options(CHAT, headers={"Origin": origin, **PREFLIGHT})
        assert allowed.status_code == 200
        assert allowed.headers["access-control-allow-origin"] == origin
    other = client.options(CHAT, headers={"Origin": "http://evil.example", **PREFLIGHT})
    assert "access-control-allow-origin" not in other.headers


def test_three_turn_conversation_returns_new_fields_and_reset_clears_state(client, service):
    service.interpreter.plans = [
        plan(price_max=5000, district_names=["Quận 7"]),
        plan("ask_detail"),
        plan("search"),
    ]
    first = chat(client, "Nhà Quận 7 dưới 5 tỷ").json()
    conversation_id, hits = first["conversation_id"], first["listings"]
    assert [h["position"] for h in hits] == list(range(1, len(hits) + 1))
    for hit in hits:
        assert isinstance(hit["coords_reliable"], bool) and "latitude" in hit
        assert hit["days_left"] is not None and hit["days_left"] >= 0
    assert "[Tin " in first["answer"] and "[Tin " not in first["summary"]
    assert first["summary"].startswith("Mình tìm được")

    second = chat(client, "Căn 1 diện tích bao nhiêu?", conversation_id).json()
    assert second["status"] == "answered" and second["summary"] == second["answer"]
    assert second["referenced_ids"] == [hits[0]["listing_id"]]

    reset = client.post("/api/v1/recommend/reset", json={"conversation_id": conversation_id})
    assert reset.json() == {"conversation_id": conversation_id}
    state = service.store.get(conversation_id)
    assert state.constraints == SearchConstraints() and state.last_results == []
    third = chat(client, "chủ nhà có thương lượng không?", conversation_id).json()
    assert third["answer"] == "Mình chưa gợi ý tin nào để hỏi chi tiết."


def test_no_results_relax_options_carry_a_sendable_message(client, service):
    service.interpreter.plans = [
        plan(price_max=1000, district_names=["Quận 1"], property_kinds=["nha_mat_pho"])]
    body = chat(client, "Nhà mặt phố Quận 1 dưới 1 tỷ").json()
    assert body["status"] == "no_results" and body["relax_options"]
    assert all(o["message"] for o in body["relax_options"])


def test_map_returns_geojson_with_numbered_listings_pois_and_missing_ids(client, service):
    service.interpreter.plans = [plan(price_max=5000, district_names=["Quận 7"])]
    hits = chat(client, "Nhà Quận 7 dưới 5 tỷ").json()["listings"]
    ids = [h["listing_id"] for h in hits] + ["00000000"]
    body = client.get("/api/v1/recommend/map", params={"ids": ",".join(ids)}).json()
    assert body["type"] == "FeatureCollection"
    no_coords = [h["listing_id"] for h in hits if h["latitude"] is None]
    assert body["missing_ids"] == no_coords + ["00000000"]
    listings = [f for f in body["features"] if f["properties"]["kind"] == "listing"]
    pois = [f for f in body["features"] if f["properties"]["kind"] == "poi"]
    with_coords = [h for h in hits if h["latitude"] is not None]
    assert [f["properties"]["position"] for f in listings] == [h["position"] for h in with_coords]
    assert all(f["geometry"]["type"] == "Point" for f in body["features"])
    assert pois and len(pois) <= 40
    distances = [f["properties"]["distance_m"] for f in pois]
    assert distances == sorted(distances) and max(distances) <= 2000
    assert {f["properties"]["near_listing_id"] for f in pois} <= {h["listing_id"] for h in hits}


def test_map_validates_query(client):
    path = "/api/v1/recommend/map"
    assert client.get(path).status_code == 422
    assert client.get(path, params={"ids": "1", "poi_types": "san_bay"}).status_code == 422
    assert client.get(path, params={"ids": ",".join(map(str, range(11)))}).status_code == 422
    empty = client.get(path, params={"ids": "00000000", "poi_types": "truong_hoc"})
    assert empty.json() == {"type": "FeatureCollection", "features": [],
                            "missing_ids": ["00000000"]}
