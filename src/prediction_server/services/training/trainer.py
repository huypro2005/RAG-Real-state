"""PriceModelTrainer: dựng bảng huấn luyện từ listings, so nhiều ứng viên và chọn mô hình tốt nhất.

Tái dùng, không chép:
  - build_training_csv.TrainingCsvBuilder: đọc listings và mã hóa loại nhà/quận/pháp lý;
  - SchoolCounter của backend: đếm trường 1 km/3 km (cùng cách tính lúc dự đoán);
  - scripts/train_price_model.py của backend: lọc ngoại lai, median giá theo quận;
  - TrainingTableCleaner của backend: làm sạch bảng huấn luyện (chung với script train).

Không rò rỉ: mọi thống kê (median điền thiếu, median giá quận) chỉ tính trên train; test chỉ
dùng để đo. Chọn mô hình theo CV 5-fold trên train, test để kiểm chứng và báo cáo.
"""
import gc
import time
import zlib
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from app.services.prediction.predictor import FEATURES, PricePredictor
from app.services.prediction.schools import SCHOOL_COLUMNS, SchoolCounter
from app.services.prediction.training_table import TrainingTableCleaner
from scripts.train_price_model import PriceModelTrainer as BackendTrainer
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import (
    ExtraTreesRegressor,
    HistGradientBoostingRegressor,
    RandomForestRegressor,
)
from sklearn.impute import SimpleImputer
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import KFold, cross_val_score
from sklearn.pipeline import Pipeline

from src.notebook.predictionEDA.db_to_training.build_training_csv import TrainingCsvBuilder
from src.prediction_server.core.settings import ServerSettings
from src.prediction_server.services.training.charts import ChartBuilder

BASE_FEATURES = [name for name in FEATURES if name not in SCHOOL_COLUMNS]  # 9 cột
FEATURE_SETS = {"": BASE_FEATURES, "+school": FEATURES}                    # 9 và 11 cột
# Thứ tự ưu tiên khi hòa: mô hình đơn giản/nhỏ và có khoảng tham khảo theo cây đứng trước
SIMPLICITY_ORDER = ["extra_trees", "random_forest", "hist_gb", "lightgbm", "xgboost"]
FILL_COLUMNS = ["số tầng", "phòng ngủ", "mặt tiền"]
CODE_COLUMNS = ["loại nhà đất", "địa chỉ"]
SEED = 42
TEST_MOD = 5  # 1/5 số tin vào test
SPLIT_RULE = "crc32(listing_id) % 5 == 0"


@dataclass
class TrainingOutcome:
    """Kết quả một lần huấn luyện; `bundle` là thứ ghi vào file .joblib (chưa có run_id)."""

    bundle: dict
    candidates: list[dict]
    metrics: dict
    train_rows: int
    test_rows: int
    baseline: dict | None = None  # mô hình đang hoạt động đo lại trên test mới
    charts: dict | None = None    # dữ liệu dashboard (cột price_model_runs.charts)


class PriceModelTrainer:
    """load_table -> split -> trim -> fit_candidates -> pick -> refit; `train()` chạy cả chuỗi."""

    def __init__(self, settings: ServerSettings):
        self.settings = settings
        self.school_counter = SchoolCounter(settings.dsn)
        self.backend = BackendTrainer()  # chỉ dùng phương thức không trạng thái (trim/median)

    def train(self, active: PricePredictor | None = None) -> TrainingOutcome:
        """Đọc listings trong DB và huấn luyện; `active` là model cũ để đo lại trên test mới."""
        return self.train_table(self.load_table(), active)

    def train_table(self, table: pd.DataFrame, active: PricePredictor | None = None):
        """Phần không cần DB: nhận bảng đã dựng (cũng là chỗ để test kiểm tra rò rỉ)."""
        train, test = self.split(table)
        train = self.trim(train)
        if len(train) < self.settings.min_train_rows:
            raise ValueError(
                f"Chỉ có {len(train)} dòng train, cần >= {self.settings.min_train_rows}")
        results = self.fit_candidates(train, test)
        winner = self.pick(results)
        features = FEATURE_SETS[winner["features"]]
        pipeline = self.build_pipeline(winner["model"], features)
        pipeline.fit(train[FEATURES], np.log(train["giá/m2"]))  # refit duy nhất được giữ lại
        metrics = {**winner["test"], "cv_r2_mean": winner["cv_r2_mean"],
                   "cv_r2_std": winner["cv_r2_std"], "test_rows": len(test),
                   "train_rows": len(train)}
        bundle = {
            "pipeline": pipeline, "candidate": winner["name"], "metrics": metrics,
            "features": features, "medians": self.backend.price_medians(train),
            "residual_q90": self.residual_quantile(pipeline, test), "split_rule": SPLIT_RULE,
        }
        # Model cũ chỉ so được công bằng nếu nó train với cùng luật chia (không thấy test mới);
        # model train bằng cách chia ngẫu nhiên cũ không có split_rule nên baseline = None
        fair = active is not None and getattr(active, "split_rule", None) == SPLIT_RULE
        baseline = self.measure(active.pipeline, test) if fair else None
        charts = ChartBuilder().build(table, test, pipeline, features, metrics,
                                      bundle["residual_q90"], results)
        gc.collect()
        return TrainingOutcome(bundle, results, metrics, len(train), len(test), baseline, charts)

    def load_table(self) -> pd.DataFrame:
        """Bảng huấn luyện từ listings: cùng mã hóa với build_training_csv.py + đếm trường."""
        builder = TrainingCsvBuilder(self.settings.dsn, Path(), scale_coordinates=False)
        table, _ = builder.convert(builder.read_listings(), keep_listing_id=True)
        ids = table.pop("listing_id")
        table = table.astype(float).assign(listing_id=ids)
        table = TrainingTableCleaner(self.school_counter).clean(table)
        # Khóa median giá ("18|2") phải là số nguyên, không phải "18.0|2.0"
        table[CODE_COLUMNS] = table[CODE_COLUMNS].astype(int)
        return table

    @staticmethod
    def split(table: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
        """Chia train/test CỐ ĐỊNH theo định danh tin: test <=> crc32(listing_id) % 5 == 0.

        Một tin luôn ở cùng phía qua mọi lần retrain dù bảng thêm/bớt dòng, nên model cũ chưa
        từng thấy test mới và so sánh với nó là công bằng. Đánh đổi: không phân tầng theo
        khoảng cách trung tâm như retrain.py; với vài nghìn tin thì băm vẫn chia khá đều.
        """
        in_test = table["listing_id"].map(lambda i: zlib.crc32(str(i).encode()) % TEST_MOD == 0)
        return table[~in_test].copy(), table[in_test].copy()

    def trim(self, train: pd.DataFrame) -> pd.DataFrame:
        """Điền median (tính trên train) rồi bỏ ngoại lai; chỉ áp cho train, không đụng test."""
        filled = train.fillna(train[FILL_COLUMNS].median())
        return self.backend.trim_outliers(filled)

    def build_pipeline(self, model: str, features: list[str]) -> Pipeline:
        """Chọn cột -> điền median (fit trên train) -> mô hình. Test không bao giờ đi vào fit."""
        return Pipeline([
            ("select", ColumnTransformer([("keep", "passthrough", features)])),
            ("imputer", SimpleImputer(strategy="median")),
            ("model", self.build_estimator(model)),
        ])

    def build_estimator(self, model: str):
        jobs = self.settings.jobs
        if model == "extra_trees":
            return ExtraTreesRegressor(n_estimators=200, n_jobs=jobs, random_state=SEED)
        if model == "random_forest":
            return RandomForestRegressor(n_estimators=200, n_jobs=jobs, random_state=SEED)
        if model == "hist_gb":
            return HistGradientBoostingRegressor(max_iter=300, learning_rate=0.08,
                                                 random_state=SEED)
        if model == "xgboost":
            from xgboost import XGBRegressor
            return XGBRegressor(n_estimators=400, learning_rate=0.05, max_depth=6, subsample=0.8,
                                colsample_bytree=0.8, n_jobs=jobs, random_state=SEED)
        if model == "lightgbm":
            from lightgbm import LGBMRegressor
            return LGBMRegressor(n_estimators=400, learning_rate=0.05, num_leaves=31,
                                 n_jobs=jobs, random_state=SEED, verbose=-1)
        raise ValueError(f"Ứng viên không hỗ trợ: {model}")

    def available_models(self) -> list[str]:
        """Ứng viên cấu hình được mà thư viện đã cài (xgboost/lightgbm là tùy chọn)."""
        models = []
        for name in self.settings.candidate_names:
            try:
                self.build_estimator(name)
            except ImportError:
                continue
            models.append(name)
        return models

    def fit_candidates(self, train: pd.DataFrame, test: pd.DataFrame) -> list[dict]:
        """CV 5-fold trên train + đo trên test cho mỗi (mô hình, bộ đặc trưng).

        Mô hình đã fit bị bỏ ngay sau khi đo để RAM không phình; chỉ người thắng được fit lại.
        """
        target = np.log(train["giá/m2"])
        folds = KFold(self.settings.cv_folds, shuffle=True, random_state=SEED)
        results = []
        for model in self.available_models():
            for suffix, features in FEATURE_SETS.items():
                started = time.perf_counter()
                pipeline = self.build_pipeline(model, features)
                scores = cross_val_score(pipeline, train[FEATURES], target, cv=folds,
                                         scoring="r2")
                pipeline.fit(train[FEATURES], target)
                results.append({
                    "name": model + suffix, "model": model, "features": suffix,
                    "n_features": len(features),
                    "cv_r2_mean": round(float(scores.mean()), 5),
                    "cv_r2_std": round(float(scores.std()), 5),
                    "test": self.measure(pipeline, test),
                    "seconds": round(time.perf_counter() - started, 1),
                })
                del pipeline
                gc.collect()
        return results

    @staticmethod
    def pick(results: list[dict]) -> dict:
        """Cao nhất theo CV R² mean; ứng viên nào kém top chưa tới 1 độ lệch chuẩn CV thì coi là
        hòa và chọn cái đơn giản nhất (thứ tự SIMPLICITY_ORDER, rồi ít đặc trưng hơn)."""
        top = max(results, key=lambda r: r["cv_r2_mean"])
        tied = [r for r in results if r["cv_r2_mean"] >= top["cv_r2_mean"] - top["cv_r2_std"]]
        winner = min(tied, key=lambda r: (SIMPLICITY_ORDER.index(r["model"]), r["n_features"]))
        for result in results:
            result["selected"] = result is winner
        winner["tie_break"] = winner is not top
        return winner

    @staticmethod
    def measure(pipeline: Pipeline, test: pd.DataFrame) -> dict:
        """R² log, R² giá/m², MAE (triệu/m²), MAPE trên tập test."""
        actual = test["giá/m2"].to_numpy()
        predicted = np.exp(pipeline.predict(test[FEATURES]))
        return {
            "r2_log": round(float(r2_score(np.log(actual), np.log(predicted))), 5),
            "r2": round(float(r2_score(actual, predicted)), 5),
            "mae": round(float(mean_absolute_error(actual, predicted)), 4),
            "mape": round(float(np.mean(np.abs(actual - predicted) / actual)), 5),
        }

    @staticmethod
    def residual_quantile(pipeline: Pipeline, test: pd.DataFrame) -> float:
        """Phân vị 90 của |log dự đoán - log thật| trên test, nửa rộng khoảng cho model không cây"""
        error = np.abs(pipeline.predict(test[FEATURES]) - np.log(test["giá/m2"].to_numpy()))
        return round(float(np.quantile(error, 0.9)), 5)
