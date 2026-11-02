"""Đối tượng giả cho unit test mode prediction (không gọi OpenAI, Goong, DB)."""

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline

from app.services.prediction.geocoder import Location
from app.services.prediction.predictor import FEATURES, PricePredictor
from app.services.prediction.schemas import Extraction


class FakeExtractor:
    """Trả lần lượt các Extraction dựng sẵn; ghi lại (message, pending, known) đã nhận."""

    def __init__(self, extractions: list[Extraction] | None = None):
        self.extractions = list(extractions or [])
        self.calls: list[tuple[str, str | None, dict]] = []

    async def extract(self, message, pending, known) -> Extraction:
        self.calls.append((message, pending, known))
        return self.extractions.pop(0)


class FakeGeocoder:
    """Trả tọa độ cố định (hoặc None); đếm số lần gọi để kiểm tra cache theo địa chỉ."""

    def __init__(self, location: Location | None = None):
        self.location = location or Location(latitude=10.78, longitude=106.70, source="goong")
        self.calls: list[tuple[str, int]] = []

    async def locate(self, address, district_code, hint=None):
        self.calls.append((address, district_code))
        return self.location


class SpyPipeline:
    """Bọc Pipeline sklearn nhỏ (luôn dự đoán 50 triệu/m²): lưu hàng đặc trưng nhận được."""

    def __init__(self):
        rng = np.random.default_rng(0)
        train = pd.DataFrame(rng.uniform(1, 100, (40, len(FEATURES))), columns=FEATURES)
        self.pipeline = Pipeline([
            ("imputer", SimpleImputer(strategy="median")),
            ("model", RandomForestRegressor(n_estimators=5, random_state=0)),
        ]).fit(train, np.full(40, np.log(50.0)))
        self.named_steps = self.pipeline.named_steps
        self.rows = []

    def predict(self, row):
        self.rows.append(row)
        return self.pipeline.predict(row)


class VaryingPipeline(SpyPipeline):
    """Giá/m² = 50 + 10 × phòng ngủ + 5 × số tầng: để thấy khác biệt "trước → sau" của what-if."""

    def predict(self, row):
        super().predict(row)
        extra = row["phòng ngủ"].fillna(0) * 10 + row["số tầng"].fillna(0) * 5
        return np.log(50 + extra.to_numpy())


METRICS = {"r2": 0.57, "r2_log": 0.8, "mae": 33.9, "test_rows": 2478, "train_rows": 9066}


def make_predictor(medians: dict | None = None, pipeline=None) -> PricePredictor:
    return PricePredictor(pipeline or SpyPipeline(), medians or {"9": 100.0, "18": 60.0}, METRICS)


def ext(**fields) -> Extraction:
    """Extraction viết gọn: ext(property_type="nhà riêng", district_name="Quận 1", area_m2=80)."""
    return Extraction(**fields)
