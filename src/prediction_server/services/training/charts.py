"""ChartBuilder: dữ liệu biểu đồ dashboard (cột price_model_runs.charts) của một phiên bản mô hình.

Scatter và độ quan trọng đặc trưng chỉ tính trên tập test cố định (không dùng để fit); phân bố giá
và median theo quận × loại nhà tính trên cả bảng huấn luyện sau lọc. Mỗi phiên bản ≤ 150 KB.
"""
import json

import numpy as np
import pandas as pd
from app.services.prediction.constants import CENTER, DISTRICT_NAMES, HCM_LAT, HCM_LON
from app.services.prediction.predictor import FEATURES
from sklearn.inspection import permutation_importance
from sklearn.metrics import r2_score

from src.notebook.predictionEDA.db_to_training.build_training_csv import PROPERTY_CODES

# Mã loại nhà -> tên đầy đủ (gồm cả mã 9 "Kho, nhà xưởng" mà PROPERTY_PHRASES của chat không có)
TYPE_LABELS = {code: name for name, code in PROPERTY_CODES.items()}
SCHEMA_VERSION = 1
N_BINS = 35                # 30-40 bin; trục giá cắt ở p99
MAX_POINTS = 800           # điểm scatter, lấy mẫu seed cố định
MIN_GROUP = 5              # nhóm quận × loại nhà ít hơn thì median không đáng tin
PERMUTATION_REPEATS = 5
MAX_GEO_POINTS = 1200     # điểm bản đồ tọa độ × giá
MIN_GEO_PER_TYPE = 50      # mỗi loại nhà giữ tối thiểu chừng này điểm để loại hiếm không mất
MAX_BYTES = 200 * 1024
SEED = 42


class ChartBuilder:
    """build() ghép đủ các khối theo schema trong docs/tasks/model-dashboard.md mục 1."""

    def build(self, table: pd.DataFrame, test: pd.DataFrame, pipeline, features: list[str],
              metrics: dict, residual_q90: float, candidates: list[dict]) -> dict:
        charts = {
            "schema_version": SCHEMA_VERSION,
            "price_distribution": self.price_distribution(table),
            "scatter": self.scatter(test, pipeline, metrics, residual_q90),
            "feature_importance": self.feature_importance(test, pipeline, features),
            "district_type_median": self.district_type_median(table),
            "geo_scatter": self.geo_scatter(table),
            "candidates": self.candidate_rows(candidates),
        }
        while len(json.dumps(charts, ensure_ascii=False)) > MAX_BYTES:  # chỉ xảy ra khi bất thường
            for block in (charts["scatter"], charts["geo_scatter"]):
                block["points"] = block["points"][: int(len(block["points"]) * 0.8)]
        return charts

    @staticmethod
    def price_distribution(table: pd.DataFrame) -> dict:
        prices = table["giá/m2"].to_numpy()
        p99 = float(np.percentile(prices, 99))
        counts, edges = np.histogram(prices[prices <= p99], bins=N_BINS, range=(0, p99))
        by_type = {}
        for code, group in table.groupby("loại nhà đất"):
            values = group["giá/m2"]
            by_type[str(int(code))] = {
                "label": TYPE_LABELS[int(code)], "n": len(values),
                "median": round(float(values.median()), 2),
                "p10": round(float(values.quantile(0.1)), 2),
                "p90": round(float(values.quantile(0.9)), 2)}
        return {
            "unit": "triệu/m²",
            "bins": [{"x0": round(float(edges[i]), 2), "x1": round(float(edges[i + 1]), 2),
                      "count": int(counts[i])} for i in range(N_BINS)],
            "clipped_above": int((prices > p99).sum()),
            "stats": {"n": len(prices), "mean": round(float(prices.mean()), 2),
                      "median": round(float(np.median(prices)), 2),
                      "p10": round(float(np.percentile(prices, 10)), 2),
                      "p90": round(float(np.percentile(prices, 90)), 2)},
            "by_type": by_type,
        }

    @staticmethod
    def scatter(test: pd.DataFrame, pipeline, metrics: dict, residual_q90: float) -> dict:
        actual = test["giá/m2"].to_numpy()
        predicted = np.exp(pipeline.predict(test[FEATURES]))
        rng = np.random.default_rng(SEED)
        picked = np.sort(rng.choice(len(test), min(MAX_POINTS, len(test)), replace=False))
        points = [{"actual": round(float(actual[i]), 1), "predicted": round(float(predicted[i]), 1),
                   "type": int(test["loại nhà đất"].iloc[i]),
                   "district": int(test["địa chỉ"].iloc[i])}
                  for i in picked]
        return {
            "points": points, "n_test": len(test),
            "r2_log": round(float(r2_score(np.log(actual), np.log(predicted))), 5),
            "mae": round(float(np.mean(np.abs(actual - predicted))), 4),
            "mape": round(float(np.mean(np.abs(actual - predicted) / actual)), 5),
            "residual_q90_log": residual_q90,
        }

    @staticmethod
    def feature_importance(test: pd.DataFrame, pipeline, features: list[str]) -> dict:
        """Permutation importance trên test: R² log giảm bao nhiêu khi xáo một cột."""
        result = permutation_importance(
            pipeline, test[features], np.log(test["giá/m2"]), scoring="r2",
            n_repeats=PERMUTATION_REPEATS, random_state=SEED, n_jobs=1)
        order = np.argsort(-result.importances_mean)
        return {"method": "permutation_r2_log",
                "items": [{"feature": features[i],
                           "importance": round(float(result.importances_mean[i]), 5),
                           "std": round(float(result.importances_std[i]), 5)} for i in order]}

    @staticmethod
    def geo_scatter(table: pd.DataFrame) -> dict:
        """Tin trên bản đồ (x = kinh độ, y = vĩ độ, màu = giá/m², cỡ = diện tích).

        Lấy mẫu từ cả bảng huấn luyện, phân tầng theo loại nhà, seed cố định (tất định).
        """
        located = table[table["tọa độ x"].between(*HCM_LAT) & table["tọa độ y"].between(*HCM_LON)]
        located = located.reset_index(drop=True)
        rng = np.random.default_rng(SEED)
        sizes = located["loại nhà đất"].value_counts()
        base = sizes.clip(upper=MIN_GEO_PER_TYPE)
        spare = max(MAX_GEO_POINTS - int(base.sum()), 0)
        extra = (sizes - base) * spare / max(int((sizes - base).sum()), 1)
        quota = (base + extra.astype(int)).clip(upper=sizes)
        picked = np.sort(np.concatenate([
            rng.choice(np.flatnonzero(located["loại nhà đất"] == kind), int(count), replace=False)
            for kind, count in quota.items()]))
        sample = located.iloc[picked]
        return {
            "points": [
                {"lat": round(float(r["tọa độ x"]), 4), "lon": round(float(r["tọa độ y"]), 4),
                 "price_per_m2": round(float(r["giá/m2"]), 1),
                 "area": round(float(r["diện tích"]), 1), "type": int(r["loại nhà đất"])}
                for _, r in sample.iterrows()],
            "n_total": len(located),
            "bounds": {
                "lat": [round(float(np.percentile(sample["tọa độ x"], p)), 4) for p in (1, 99)],
                "lon": [round(float(np.percentile(sample["tọa độ y"], p)), 4) for p in (1, 99)]},
            "price_clip": {"p5": round(float(np.percentile(located["giá/m2"], 5)), 1),
                           "p95": round(float(np.percentile(located["giá/m2"], 95)), 1)},
            "center": {"name": "Nhà thờ Đức Bà", "lat": CENTER[0], "lon": CENTER[1]},
        }

    @staticmethod
    def district_type_median(table: pd.DataFrame) -> list[dict]:
        groups = table.groupby(["địa chỉ", "loại nhà đất"])["giá/m2"].agg(["median", "count"])
        return [{"district": int(district), "district_name": DISTRICT_NAMES[int(district)],
                 "property_type": int(kind), "label": TYPE_LABELS[int(kind)],
                 "median": round(float(row["median"]), 2), "n": int(row["count"])}
                for (district, kind), row in groups.iterrows() if row["count"] >= MIN_GROUP]

    @staticmethod
    def candidate_rows(candidates: list[dict]) -> list[dict]:
        """Chỉ các dòng ứng viên (bỏ dòng quyết định thăng hạng ở cuối)."""
        return [{"name": c["name"], "cv_r2": c["cv_r2_mean"], "cv_std": c["cv_r2_std"],
                 "test_r2_log": c["test"]["r2_log"], "mae": c["test"]["mae"],
                 "chosen": bool(c.get("selected"))} for c in candidates if "name" in c]
