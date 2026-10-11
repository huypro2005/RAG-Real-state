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


def make_predictor(medians: dict | None = None) -> PricePredictor:
    return PricePredictor(SpyPipeline(), medians or {"9": 100.0, "18": 60.0})


def ext(**fields) -> Extraction:
    """Extraction viết gọn: ext(property_type="nhà riêng", district_name="Quận 1", area_m2=80)."""
    return Extraction(**fields)
