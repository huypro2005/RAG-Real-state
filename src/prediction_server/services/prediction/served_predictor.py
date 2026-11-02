"""ServedPredictor: PricePredictor của backend + khoảng tham khảo cho mô hình không cây."""
import copy

import numpy as np
from app.services.prediction.predictor import (
    TREE_PERCENTILES,
    PriceEstimate,
    PriceInput,
    PricePredictor,
)
from sklearn.ensemble import ExtraTreesRegressor, RandomForestRegressor

TREE_RANGE = "tree_percentiles"     # phân vị p10-p90 dự đoán của từng cây
ERROR_RANGE = "test_error_q90"      # giá × exp(±sai số log phân vị 90 trên tập test)


class _PrefetchedSchools:
    """Trả số trường đã đếm sẵn cho từng điểm của một lô (cùng giao diện SchoolCounter.count)."""

    def __init__(self, counts: dict[tuple[float, float], np.ndarray]):
        self.counts = counts

    def count(self, latitudes, longitudes) -> np.ndarray:
        return np.array([self.counts[(latitudes[0], longitudes[0])]])


class PredictionResult(PriceEstimate):
    """PriceEstimate của backend, thêm model đã dùng và nguồn của khoảng tham khảo."""

    model_run_id: int
    range_source: str


class ServedPredictor(PricePredictor):
    """Một mô hình đã train (gói trong file .joblib) sẵn sàng phục vụ /predict.

    Pipeline gồm bước chọn cột nên nhận dòng đặc trưng đủ 11 cột của backend dù mô hình chỉ
    dùng 9 cột (bộ `base`). Model là rừng cây thì khoảng tham khảo lấy theo từng cây như backend;
    các model còn lại dùng sai số log trên tập test (`residual_q90`) vì không có "từng cây".
    """

    def __init__(self, bundle: dict, school_counter=None):
        super().__init__(bundle["pipeline"], bundle["medians"], bundle["metrics"], school_counter)
        self.run_id: int = bundle["run_id"]
        self.candidate: str = bundle["candidate"]
        self.residual_q90: float = bundle["residual_q90"]
        self.split_rule: str | None = bundle.get("split_rule")  # None: chia kiểu cũ
        self.tree_based = isinstance(
            self.pipeline[-1], (ExtraTreesRegressor, RandomForestRegressor))
        self.range_source = TREE_RANGE if self.tree_based else ERROR_RANGE

    def predict_many(self, inputs: list[PriceInput]) -> list[PredictionResult]:
        """Mỗi tin vẫn dự đoán độc lập qua predict() nên kết quả y hệt gọi từng tin; chỉ khác là
        số trường của cả lô được đếm bằng một truy vấn thay vì một truy vấn mỗi tin."""
        if len(inputs) > 1 and self.school_counter is not None:
            points = [(item.latitude, item.longitude) for item in inputs]
            try:
                counts = self.school_counter.count(*zip(*points, strict=True))
            except Exception:  # noqa: BLE001 - DB lỗi: từng tin tự xử lý và gắn cảnh báo
                return [self.predict_one(item) for item in inputs]
            batch = copy.copy(self)  # bản sao nông, chỉ đổi bộ đếm trường: an toàn khi đa luồng
            batch.school_counter = _PrefetchedSchools(dict(zip(points, counts, strict=True)))
            return [batch.predict_one(item) for item in inputs]
        return [self.predict_one(item) for item in inputs]

    def predict_one(self, data: PriceInput) -> PredictionResult:
        estimate = self.predict(data)
        return PredictionResult(**estimate.model_dump(), model_run_id=self.run_id,
                                range_source=self.range_source)

    def _tree_range(self, row) -> tuple[float, float]:
        if self.tree_based:
            matrix = self.pipeline[:-1].transform(row)
            prices = np.exp([tree.predict(matrix)[0] for tree in self.pipeline[-1].estimators_])
            low, high = np.percentile(prices, TREE_PERCENTILES)
        else:
            price = float(np.exp(self.pipeline.predict(row))[0])
            low, high = price * np.exp(-self.residual_q90), price * np.exp(self.residual_q90)
        return round(float(low), 2), round(float(high), 2)
