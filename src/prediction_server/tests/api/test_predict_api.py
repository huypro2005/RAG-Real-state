"""P2, P3, P4, P15: API không cần DB (registry/runs giả)."""
import pytest

from src.prediction_server.tests.conftest import CASE


def test_health_needs_no_key_and_reports_missing_model(make_client):
    body = make_client(predictor=None).get("/api/v1/health").json()
    assert body["db_schema_missing"] is False and body["model"] == "no_active_model"


def test_health_reports_missing_table(make_client):
    response = make_client(schema_ready=False).get("/api/v1/health")
    assert response.status_code == 200 and response.json()["db_schema_missing"] is True


@pytest.mark.parametrize("bad_headers", [{}, {"X-API-Key": "sai"}])
def test_routes_reject_missing_or_wrong_key(make_client, predictor, bad_headers):
    client = make_client(predictor)
    for method, path in (("post", "/predict"), ("post", "/ingest"), ("post", "/retrain"),
                         ("get", "/models"), ("get", "/jobs/x"), ("post", "/models/1/activate")):
        response = client.request(method, f"/api/v1{path}", headers=bad_headers)
        assert response.status_code == 401, path


def test_predict_returns_estimate_with_model_run(make_client, predictor, headers):
    body = make_client(predictor).post("/api/v1/predict", json=CASE, headers=headers).json()
    assert body["model_run_id"] == 7 and body["range_source"] == "tree_percentiles"
    assert body["price_per_m2_low"] <= body["price_per_m2"] <= body["price_per_m2_high"]
    assert body["total_price"] == pytest.approx(body["price_per_m2"] * 80, rel=1e-3)


def test_predict_503_without_model(make_client, headers):
    response = make_client(None).post("/api/v1/predict", json=CASE, headers=headers)
    assert response.status_code == 503


@pytest.mark.parametrize("change", [
    {"district_code": 24}, {"property_code": 1}, {"area": 0}, {"area": -3},
    {"latitude": 21.03, "longitude": 105.85}, {"property_code": True},
])
def test_predict_422_on_invalid_input(make_client, predictor, headers, change):
    response = make_client(predictor).post(
        "/api/v1/predict", json={**CASE, **change}, headers=headers)
    assert response.status_code == 422


def test_batch_equals_single_calls(make_client, predictor, headers):
    client = make_client(predictor)
    cases = [CASE, {**CASE, "district_code": 4, "property_code": 7, "latitude": 10.9},
             {**CASE, "property_code": 0, "bedrooms": 2}]
    singles = [client.post("/api/v1/predict", json=c, headers=headers).json() for c in cases]
    batch = client.post("/api/v1/predict", json={"items": cases}, headers=headers).json()
    assert batch["items"] == singles
