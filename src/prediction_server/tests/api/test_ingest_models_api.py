"""POST /ingest (trần dung lượng/bản ghi) và GET /models (không lộ đường dẫn tuyệt đối)."""
import json

from fastapi.testclient import TestClient

from src.prediction_server.core.settings import ServerSettings
from src.prediction_server.main import create_app
from src.prediction_server.tests.conftest import API_KEY, FakeRuns


class FakeRunner:
    def __init__(self):
        self.calls = []

    def submit_ingest(self, records, malformed=0):
        self.calls.append((len(records), malformed))
        return "job1"


def build(max_bytes: int = 20 * 1024 * 1024) -> tuple[TestClient, FakeRunner]:
    settings = ServerSettings(prediction_server_api_key=API_KEY, max_ingest_bytes=max_bytes,
                              scheduler_enabled=False)
    app = create_app(settings)
    container = app.state.container
    container.runner, container.runs = FakeRunner(), FakeRuns()
    return TestClient(app), container.runner


def test_json_and_multipart_are_accepted_within_limits(headers):
    client, runner = build()
    assert client.post("/api/v1/ingest", json={"records": [{"a": 1}] * 3},
                       headers=headers).status_code == 202
    files = {"file": ("x.jsonl", b'{"a": 1}\nnot json\n{"a": 2}\n')}
    assert client.post("/api/v1/ingest", files=files, headers=headers).status_code == 202
    assert runner.calls == [(3, 0), (2, 1)]


def test_too_many_records_is_413_on_both_paths(headers):
    client, _ = build()
    assert client.post("/api/v1/ingest", json={"records": [{}] * 5001},
                       headers=headers).status_code == 413
    lines = b"\n".join(json.dumps({"a": i}).encode() for i in range(5001))
    assert client.post("/api/v1/ingest", files={"file": ("x", lines)},
                       headers=headers).status_code == 413


def test_oversized_body_is_413_on_both_paths(headers):
    client, runner = build(max_bytes=1000)
    big = {"records": [{"text": "x" * 2000}]}
    assert client.post("/api/v1/ingest", json=big, headers=headers).status_code == 413
    assert client.post("/api/v1/ingest", files={"file": ("x", b"y" * 5000)},
                       headers=headers).status_code == 413
    assert runner.calls == []


def test_chunked_body_without_content_length_is_still_capped(headers):
    client, runner = build(max_bytes=1000)

    def chunks():
        for _ in range(10):
            yield b'{"records": [' + b" " * 300

    response = client.post("/api/v1/ingest", content=chunks(),
                           headers={**headers, "content-type": "application/json"})
    assert response.status_code == 413 and runner.calls == []


def test_malformed_structure_is_422(headers):
    client, _ = build()
    assert client.post("/api/v1/ingest", json={"foo": 1}, headers=headers).status_code == 422
    assert client.post("/api/v1/ingest", content=b"{", headers={
        **headers, "content-type": "application/json"}).status_code == 422


def test_models_list_hides_absolute_artifact_path(headers):
    client, _ = build()
    runs = client.get("/api/v1/models", headers=headers).json()
    assert runs[0]["artifact_path"] == "price_run_1.joblib"


class ChartsRunner:
    def submit_charts_rebuild(self, run_id):
        return f"rebuild-{run_id}"


def test_charts_endpoints(headers):
    client, _ = build()
    client.app.state.container.runner = ChartsRunner()
    assert client.get("/api/v1/models/1/charts", headers=headers).json() == {"schema_version": 1}
    assert client.get("/api/v1/models/active/charts", headers=headers).status_code == 200
    assert client.get("/api/v1/models/2/charts", headers=headers).status_code == 404
    rebuild = client.post("/api/v1/models/1/charts/rebuild", headers=headers)
    assert rebuild.status_code == 202 and rebuild.json() == {"job_id": "rebuild-1"}
    assert client.post("/api/v1/models/9/charts/rebuild", headers=headers).status_code == 404
    assert client.get("/api/v1/models/1/charts").status_code == 401
