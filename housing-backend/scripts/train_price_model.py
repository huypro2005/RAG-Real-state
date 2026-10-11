"""Train lại mô hình dự đoán giá của đồ án 1 (không có file .pkl nên phải train lại).

Giữ nguyên phương pháp cũ (Data-Analysis-And-Predict-Housing-Price/src/web/app/retrain/retrain.py):
SimpleImputer(median) + RandomForestRegressor(200 cây), mục tiêu log(giá/m²), chia
StratifiedShuffleSplit theo khoảng cách tới trung tâm, lọc ngoại lai chỉ trên tập train.

Chạy trong housing-backend/housing-backend/:
    python scripts/train_price_model.py
Kết quả: models/price_rf.joblib và models/price_rf.metrics.json (thư mục models/ không commit).
"""

import json
import shutil
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import StratifiedShuffleSplit
from sklearn.pipeline import Pipeline

from app.services.prediction.constants import HCM_LAT, HCM_LON
from app.services.prediction.predictor import FEATURES, PricePredictor

BACKEND_DIR = Path(__file__).resolve().parents[1]
SOURCE_CSV = (
    BACKEND_DIR.parents[1]
    / "Data-Analysis-And-Predict-Housing-Price/src/web/app/data/data.csv"
)
TRAIN_CSV = BACKEND_DIR / "data/price_training.csv"
MODEL_PATH = BACKEND_DIR / "models/price_rf.joblib"
METRICS_PATH = BACKEND_DIR / "models/price_rf.metrics.json"

# Loại bị bỏ như retrain.py: 1 chung cư mini, 5 shophouse, 6 đất nền dự án
DROPPED_TYPES = (1, 5, 6)
# Ngoại lai chỉ lọc trên tập train (như retrain.py)
MAX_BEDROOMS_EXCLUSIVE, MAX_FRONTAGE, MAX_PRICE_PER_M2 = 11, 30, 500
AREA_RANGE = (15, 500)
MIN_GROUP_SAMPLES = 10  # nhóm quận/loại ít hơn thì median không ổn định


class PriceModelTrainer:
    """Nạp data.csv, làm sạch, train Pipeline, đánh giá và lưu model + median giá theo quận."""

    def run(self) -> dict:
        self.prepare_csv()
        train, test = self.split(self.clean(pd.read_csv(TRAIN_CSV)))
        train, test = self.fill_missing(train, test)
        train = self.trim_outliers(train)
        pipeline = self.fit(train)
        metrics = self.evaluate(pipeline, test)
        metrics["train_rows"] = len(train)
        metrics["medians"] = self.price_medians(train)
        self.save(pipeline, metrics)
        return metrics

    def prepare_csv(self) -> None:
        """Chép data.csv của đồ án 1 sang data/ (nếu chưa có) để đồ án 2 tự đủ dữ liệu."""
        if not TRAIN_CSV.exists():
            TRAIN_CSV.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(SOURCE_CSV, TRAIN_CSV)

    def clean(self, raw: pd.DataFrame) -> pd.DataFrame:
        """Bản đã làm sạch của `raw` (không sửa DataFrame đầu vào)."""
        df = raw.copy()
        # Tọa độ trong csv nhân 10⁹ → về độ thực
        df["tọa độ x"] = df["tọa độ x"] / 1e9
        df["tọa độ y"] = df["tọa độ y"] / 1e9
        df["cách trung tâm"] = PricePredictor.distance_to_center(df["tọa độ x"], df["tọa độ y"])
        df = df.drop(columns=["giá"]).drop_duplicates()  # cột giá tuyệt đối gây rò rỉ nhãn
        df = df[~df["loại nhà đất"].isin(DROPPED_TYPES)]
        in_city = df["tọa độ y"].between(*HCM_LON) & df["tọa độ x"].between(*HCM_LAT)
        df = df[in_city]
        # pháp lý chỉ để lọc: bỏ tin pháp lý = 2 và tin thiếu pháp lý, rồi bỏ cột
        df = df[(df["pháp lý"] != 2) & df["pháp lý"].notna()]
        return df.drop(columns=["pháp lý"])

    def split(self, df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
        """Chia 80/20 phân tầng theo khoảng cách trung tâm; lấy lần chia đầu như retrain.py."""
        strata = pd.cut(df["cách trung tâm"], bins=[0, 5, 10, 15, np.inf], labels=False)
        splitter = StratifiedShuffleSplit(n_splits=10, test_size=0.2, random_state=42)
        train_idx, test_idx = next(splitter.split(df, strata))
        return df.iloc[train_idx].copy(), df.iloc[test_idx].copy()

    def fill_missing(
        self, train: pd.DataFrame, test: pd.DataFrame
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        """Điền median độc lập cho train và test (như notebook); trả bản sao."""
        train, test = train.copy(), test.copy()
        for part in (train, test):
            for column in ("số tầng", "phòng ngủ", "mặt tiền"):
                part[column] = part[column].fillna(part[column].median())
        return train, test

    def trim_outliers(self, train: pd.DataFrame) -> pd.DataFrame:
        """Bỏ ngoại lai chỉ trên tập train; tập test giữ nguyên để đo trên dữ liệu thật."""
        keep = (
            (train["phòng ngủ"] < MAX_BEDROOMS_EXCLUSIVE) & (train["mặt tiền"] <= MAX_FRONTAGE)
            & (train["giá/m2"] <= MAX_PRICE_PER_M2) & train["diện tích"].between(*AREA_RANGE)
        )
        return train[keep]

    def fit(self, train: pd.DataFrame) -> Pipeline:
        pipeline = Pipeline([
            ("imputer", SimpleImputer(strategy="median")),
            ("model", RandomForestRegressor(n_estimators=200, random_state=42)),
        ])
        return pipeline.fit(train[FEATURES], np.log(train["giá/m2"]))

    def evaluate(self, pipeline: Pipeline, test: pd.DataFrame) -> dict:
        """RMSE/MAE/R² tính trên giá/m² thật (sau exp), không phải trên log."""
        actual = test["giá/m2"]
        predicted = np.exp(pipeline.predict(test[FEATURES]))
        return {
            "rmse": float(np.sqrt(mean_squared_error(actual, predicted))),
            "mae": float(mean_absolute_error(actual, predicted)),
            "r2": float(r2_score(actual, predicted)),
            "r2_log": float(r2_score(np.log(actual), np.log(predicted))),
            "test_rows": len(test),
        }

    def price_medians(self, train: pd.DataFrame) -> dict:
        """Median giá/m² theo quận ("9") và theo quận + loại ("9|2"), để so sánh khi giải thích."""
        by_district = train.groupby("địa chỉ")["giá/m2"].median()
        by_type = train.groupby(["địa chỉ", "loại nhà đất"])["giá/m2"].agg(["median", "count"])
        medians = {str(d): round(float(v), 2) for d, v in by_district.items()}
        for (district, kind), row in by_type.iterrows():
            if row["count"] >= MIN_GROUP_SAMPLES:
                medians[f"{district}|{kind}"] = round(float(row["median"]), 2)
        return medians

    def save(self, pipeline: Pipeline, metrics: dict) -> None:
        MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(pipeline, MODEL_PATH)
        METRICS_PATH.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), "utf-8")


if __name__ == "__main__":
    result = PriceModelTrainer().run()
    print({k: v for k, v in result.items() if k != "medians"})
