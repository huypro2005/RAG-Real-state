"""Backend proxy /api/v1/dashboard/models (httpx MockTransport, không cần Prediction Server)."""

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api.v1.dashboard import get_dashboard_client
from app.main import app
from app.services.dashboard import DashboardClient

RUN = {
    "id": 4, "created_at": "2026-10-31T19:00:00+07:00", "finished_at": "2026-10-31T19:01:00+07:00",
    "trigger": "manual", "status": "succeeded", "is_active": True, "best_candidate": "extra_trees",
    "train_rows": 4000, "test_rows": 1000, "has_charts": True, "artifact_path": "x.joblib",
    "metrics": {"r2_log": 0.8, "mae": 31.0, "mape": 0.22, "cv_r2_mean": 0.84},
}
CHARTS = {
    "schema_version": 1,
    "price_distribution": {
        "unit": "triệu/m²", "bins": [{"x0": 0, "x1": 10, "count": 5}], "clipped_above": 1,
        "stats": {"n": 6, "mean": 5, "median": 5, "p10": 1, "p90": 9},
        "by_type": {"0": {"label": "Căn hộ chung cư", "n": 6, "median": 5, "p10": 1, "p90": 9}}},
    "scatter": {"points": [{"actual": 50, "predicted": 55, "type": 0, "district": 2}],
                "n_test": 1000, "r2_log": 0.8, "mae": 31, "mape": 0.22, "residual_q90_log": 0.4},
    "feature_importance": {"method": "permutation_r2_log",
                           "items": [{"feature": "cách trung tâm", "importance": 0.4,
                                      "std": 0.01}]},
    "district_type_median": [{"district": 2, "district_name": "Bình Thạnh", "property_type": 0,
                              "label": "Căn hộ chung cư", "median": 70, "n": 9}],
    "geo_scatter": {
        "points": [{"lat": 10.7942, "lon": 106.7346, "price_per_m2": 231.4, "area": 105.0,
                    "type": 4}],
        "n_total": 5206, "bounds": {"lat": [10.7, 10.9], "lon": [106.6, 106.8]},
        "price_clip": {"p5": 40.0, "p95": 300.0},
        "center": {"name": "Nhà thờ Đức Bà", "lat": 10.7769, "lon": 106.7009}},
    "candidates": [{"name": "extra_trees", "cv_r2": 0.84, "cv_std": 0.01, "test_r2_log": 0.8,
                    "mae": 31, "chosen": True}],
}


def use(handler, url="http://server"):
    client = DashboardClient(url, "key", httpx.Client(
        base_url="http://server", transport=httpx.MockTransport(handler)))
    app.dependency_overrides[get_dashboard_client] = lambda: client
    return TestClient(app)


@pytest.fixture(autouse=True)
def _clean():
    yield
    app.dependency_overrides.clear()


def server(request):
    if request.url.path == "/api/v1/models":
        return httpx.Response(200, json=[RUN, {**RUN, "id": 3, "is_active": False}])
    if request.url.path == "/api/v1/models/4/charts":
        return httpx.Response(200, json=CHARTS)
    return httpx.Response(404, json={"detail": "Phiên bản này chưa có charts"})


def test_lists_runs_without_leaking_artifact_path():
    runs = use(server).get("/api/v1/dashboard/models").json()
    assert [r["id"] for r in runs] == [4, 3] and "artifact_path" not in runs[0]
    assert runs[0]["metrics"] == {"r2_log": 0.8, "mae": 31.0, "mape": 0.22}


@pytest.mark.parametrize("model_id", ["4", "active"])
def test_detail_by_id_and_active(model_id):
    body = use(server).get(f"/api/v1/dashboard/models/{model_id}").json()
    assert body["model"]["id"] == 4 and body["charts"]["scatter"]["n_test"] == 1000
    assert body["charts"]["approximate"] is False
    assert body["charts"]["geo_scatter"]["points"][0]["price_per_m2"] == 231.4  # không bị rơi


def test_unknown_or_chartless_model_is_404_and_bad_id_422():
    client = use(server)
    assert client.get("/api/v1/dashboard/models/99").status_code == 404
    assert client.get("/api/v1/dashboard/models/3").status_code == 404  # run 3 chưa có charts
    assert client.get("/api/v1/dashboard/models/abc").status_code == 422


def test_server_down_is_503_with_clear_message():
    def down(request):
        raise httpx.ConnectError("tắt")

    response = use(down).get("/api/v1/dashboard/models")
    assert response.status_code == 503 and "không phản hồi" in response.json()["detail"]


def test_not_configured_is_503():
    response = use(server, url="").get("/api/v1/dashboard/models")
    assert response.status_code == 503 and "PREDICTION_SERVER_URL" in response.json()["detail"]


def test_rejected_api_key_is_503_not_leaked_as_401():
    response = use(lambda request: httpx.Response(401)).get("/api/v1/dashboard/models")
    assert response.status_code == 503 and "khóa API" in response.json()["detail"]


def test_malformed_server_payload_is_502():
    response = use(lambda request: httpx.Response(200, json=[{"id": "x"}])).get(
        "/api/v1/dashboard/models")
    assert response.status_code == 502
