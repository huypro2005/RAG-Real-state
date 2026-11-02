"""ModelRegistry (đường dẫn artifact) và JobRunner (ingest xong nhưng retrain lỗi)."""
import time
from types import SimpleNamespace

import joblib
import pytest

from src.prediction_server.services.jobs.runner import JobRunner
from src.prediction_server.services.jobs.store import JobStore
from src.prediction_server.services.registry.registry import (
    ModelFileMissingError,
    ModelRegistry,
)


class RunsWithPath:
    def __init__(self, path):
        self.path, self.active_id = path, None

    def succeeded(self, run_id):
        return {"id": run_id, "artifact_path": str(self.path)}

    def set_active(self, run_id):
        self.active_id = run_id


def test_activate_loads_artifact_inside_models_dir(tmp_path, trained):
    path = tmp_path / "price_run_7.joblib"
    joblib.dump(trained, path)
    runs = RunsWithPath(path)
    registry = ModelRegistry(runs, "postgresql://unused", tmp_path)
    assert registry.activate(7).run_id == 7 and runs.active_id == 7
    assert registry.current().run_id == 7  # đã nạp nóng, không cần hỏi DB


def test_activate_refuses_artifact_outside_models_dir(tmp_path, trained):
    models_dir = tmp_path / "models"
    models_dir.mkdir()
    outside = tmp_path / "evil.joblib"
    joblib.dump(trained, outside)
    registry = ModelRegistry(RunsWithPath(outside), "postgresql://unused", models_dir)
    with pytest.raises(ModelFileMissingError):
        registry.activate(1)


class FailingRetrain:
    def run(self, trigger, force=False):
        return {"status": "failed", "run_id": 1, "error": "ValueError('boom')"}


class FakeIngest:
    def run(self, records, malformed):
        return {"clean": {"clean": 1}, "load": {"inserted": 1}}


def test_ingest_job_is_partial_when_following_retrain_fails():
    store = JobStore(workers=1)
    runner = JobRunner(
        SimpleNamespace(), None, None, FailingRetrain(), FakeIngest(), store, charts=None)
    job_id = runner.submit_ingest([{}])
    for _ in range(50):
        job = store.get(job_id)
        if job["status"] not in ("queued", "running"):
            break
        time.sleep(0.1)
    store.shutdown()
    assert job["status"] == "partial" and "retrain" in job["error"]
    assert job["steps"]["load"]["inserted"] == 1
