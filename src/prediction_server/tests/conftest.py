"""Fixture chung: model giả train trên dữ liệu tổng hợp để test không cần DB hay file .joblib."""
import numpy as np
import pandas as pd
import pytest
from app.services.prediction.predictor import FEATURES
from fastapi.testclient import TestClient

from src.prediction_server.core.settings import ServerSettings
from src.prediction_server.main import create_app
from src.prediction_server.services.prediction.served_predictor import ServedPredictor
from src.prediction_server.services.training.trainer import PriceModelTrainer

API_KEY = "test-key"
CASE = {"property_code": 2, "district_code": 18, "area": 80,
        "latitude": 10.73, "longitude": 106.72}


def make_table(rows: int = 400, seed: int = 0, first_id: int = 0) -> pd.DataFrame:
    """Bảng huấn luyện tổng hợp có đủ cột như PriceModelTrainer.load_table() trả về."""
    rng = np.random.default_rng(seed)
    table = pd.DataFrame({
        "listing_id": [f"id{first_id + i}" for i in range(rows)],
        "loại nhà đất": rng.choice([0, 2, 3, 4, 7], rows),
        "địa chỉ": rng.integers(0, 24, rows),
        "diện tích": rng.uniform(20, 300, rows),
        "mặt tiền": rng.uniform(3, 10, rows),
        "phòng ngủ": rng.integers(1, 6, rows).astype(float),
        "tọa độ x": rng.uniform(10.65, 10.9, rows),
        "tọa độ y": rng.uniform(106.55, 106.8, rows),
        "số tầng": rng.integers(1, 6, rows).astype(float),
    })
    offset = np.hypot(table["tọa độ x"] - 10.7769, table["tọa độ y"] - 106.7009)
    table["cách trung tâm"] = offset * 111
    table["trường học 1 km"] = rng.integers(0, 20, rows).astype(float)
    table["trường học 3 km"] = rng.integers(10, 200, rows).astype(float)
    price = 150 - 6 * table["cách trung tâm"] + rng.normal(0, 5, rows)
    table["giá/m2"] = price.clip(lower=20)
    table.loc[::7, "mặt tiền"] = np.nan  # ô thiếu để imputer có việc làm
    return table


def feature_frame(table: pd.DataFrame) -> pd.DataFrame:
    return table[FEATURES].head(20)


@pytest.fixture(scope="session")
def settings() -> ServerSettings:
    return ServerSettings(
        prediction_server_api_key=API_KEY, candidates="extra_trees", cv_folds=2,
        min_train_rows=50, n_jobs=1, scheduler_enabled=False)


@pytest.fixture(scope="session")
def trained(settings):
    """Bundle (đã gắn run_id) từ trainer thật trên dữ liệu tổng hợp."""
    outcome = PriceModelTrainer(settings).train_table(make_table())
    return {**outcome.bundle, "run_id": 7}


@pytest.fixture
def predictor(trained) -> ServedPredictor:
    return ServedPredictor(trained, school_counter=None)  # None: số trường để thiếu


class FakeRuns:
    """Thay RunRepository: không đụng DB."""

    def __init__(self, schema_ready: bool = True):
        self._schema_ready = schema_ready

    def schema_ready(self) -> bool:
        return self._schema_ready

    def active(self):
        return None

    def running_count(self) -> int:
        return 0

    def charts(self, run_id):
        return {"schema_version": 1} if run_id in (None, 1) else None

    def succeeded(self, run_id):
        return {"id": run_id} if run_id == 1 else None

    def history(self, limit: int) -> list[dict]:
        return [{"id": 1, "artifact_path": "D:/secret/models/price_run_1.joblib"}]


class FakeRegistry:
    def __init__(self, predictor):
        self.predictor = predictor

    def current(self):
        return self.predictor


@pytest.fixture
def make_client(settings):
    """Dựng app thật (không chạy lifespan) rồi thay registry/runs bằng bản giả."""
    def build(predictor=None, schema_ready=True) -> TestClient:
        app = create_app(settings)
        container = app.state.container
        container.registry = FakeRegistry(predictor)
        container.runs = FakeRuns(schema_ready)
        return TestClient(app)
    return build


@pytest.fixture
def headers():
    return {"X-API-Key": API_KEY}
