"""PricePredictor: dự đoán giá bằng mô hình ExtraTrees (train bằng scripts/train_price_model.py).
Mục tiêu của mô hình là log(giá/m²) nên kết quả phải exp()."""

import json
import logging
import math
from dataclasses import dataclass
from numbers import Integral
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from pydantic import BaseModel

from app.services.prediction.constants import (
    APARTMENT,
    CENTER,
    DISTRICT_NAMES,
    HCM_LAT,
    HCM_LON,
    LAND,
    PROPERTY_TYPES,
)
from app.services.prediction.schools import SCHOOL_COLUMNS, SchoolCounter
from app.services.prediction.text import MessageRules

logger = logging.getLogger(__name__)

BACKEND_DIR = Path(__file__).resolve().parents[3]
MODEL_PATH = BACKEND_DIR / "models/price_rf.joblib"
METRICS_PATH = BACKEND_DIR / "models/price_rf.metrics.json"

# Thứ tự cột phải đúng thứ tự lúc train
FEATURES = [
    "loại nhà đất", "địa chỉ", "diện tích", "mặt tiền", "phòng ngủ",
    "tọa độ x", "tọa độ y", "số tầng", "cách trung tâm", *SCHOOL_COLUMNS,
]
EARTH_RADIUS_KM = 6371
TREE_PERCENTILES = (10, 90)  # biên độ tham khảo: phân vị các cây (mỗi cây một dự đoán)
WIDE_RANGE_RATIO = 3         # cao/thấp vượt mức này thì cảnh báo các cây bất đồng
SPARSE_WARNING = "Dữ liệu huấn luyện ở khu vực/loại này rất ít, giá có thể lệch nhiều."
WIDE_WARNING = "Các cây trong mô hình bất đồng nhiều (khoảng tham khảo rất rộng), giá có thể lệch."
SCHOOL_WARNING = "Chưa tra được số trường học quanh vị trí này nên mô hình dùng giá trị trung vị."


@dataclass
class PriceInput:
    """Đầu vào của predict(). Trường tuỳ chọn để None: SimpleImputer điền median.

    Raises:
        ValueError: mã loại/quận lạ hoặc kiểu bool, thiếu hay sai diện tích, toạ độ thiếu,
            NaN hoặc ngoài TP.HCM.
    """

    property_code: int
    district_code: int
    area: float | None = None
    latitude: float | None = None
    longitude: float | None = None
    frontage: float | None = None
    bedrooms: int | None = None
    floors: int | None = None

    def __post_init__(self):
        for name in ("property_code", "district_code"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, Integral):
                raise ValueError(f"{name} phải là số nguyên, nhận {value!r}")  # noqa: TRY004
        if self.property_code not in PROPERTY_TYPES.values():
            raise ValueError(f"Mã loại nhà đất không hỗ trợ: {self.property_code}")
        if not 0 <= self.district_code < len(DISTRICT_NAMES):
            raise ValueError(f"Mã quận/huyện không hợp lệ: {self.district_code}")
        if self.area is None or not (math.isfinite(self.area) and self.area > 0):
            raise ValueError(f"Thiếu hoặc sai diện tích: {self.area!r}")
        lat, lon = self.latitude, self.longitude
        if lat is None or lon is None or not (
            HCM_LAT[0] <= lat <= HCM_LAT[1] and HCM_LON[0] <= lon <= HCM_LON[1]
        ):  # NaN làm phép so sánh sai nên cũng bị chặn ở đây
            raise ValueError(f"Toạ độ thiếu hoặc ngoài TP.HCM: ({lat!r}, {lon!r})")


class PriceEstimate(BaseModel):
    price_per_m2: float                    # triệu VND / m²
    total_price: float                     # triệu VND
    price_per_m2_low: float                # phân vị thấp của các cây
    price_per_m2_high: float               # phân vị cao của các cây
    schools_1km: int | None = None         # số trường trong 1 km (None: không tra được)
    schools_3km: int | None = None
    distance_to_center_km: float
    district_median_per_m2: float | None   # median giá/m² tập train của quận
    median_by_type: bool = False           # True: median riêng cho loại nhà này (đủ mẫu)
    warnings: list[str] = []               # dữ liệu train thưa / ngoại suy / các cây bất đồng


class PricePredictor:
    """Nạp model một lần; predict() nhận các trường đã kiểm tra biên ở tầng hội thoại."""

    def __init__(
        self, pipeline, medians: dict[str, float], metrics: dict | None = None,
        school_counter: SchoolCounter | None = None,
    ):
        self.pipeline = pipeline
        self.medians = medians
        self.metrics = metrics  # nội dung metrics.json (R², số dòng test...)
        self.school_counter = school_counter  # None: không tra DB, số trường để thiếu

    @classmethod
    def load(
        cls, model_path: Path = MODEL_PATH, metrics_path: Path = METRICS_PATH,
        school_counter: SchoolCounter | None = None,
    ):
        """Nạp model và median đã train; `school_counter` tra số trường quanh vị trí lúc dự đoán.

        Raises:
            FileNotFoundError: chưa chạy scripts/train_price_model.py.
        """
        if not model_path.exists():
            raise FileNotFoundError(f"Chưa có {model_path}; chạy scripts/train_price_model.py")
        metrics = json.loads(metrics_path.read_text("utf-8"))
        return cls(joblib.load(model_path), metrics["medians"], metrics, school_counter)

    @staticmethod
    def distance_to_center(lat, lon):
        """Khoảng cách haversine (km) tới Nhà thờ Đức Bà; nhận số hoặc cột pandas."""
        lat1, lon1, lat2, lon2 = map(np.radians, (lat, lon, *CENTER))
        a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(
            (lon2 - lon1) / 2
        ) ** 2
        return EARTH_RADIUS_KM * 2 * np.arcsin(np.sqrt(a))

    @staticmethod
    def find_district(name: str) -> int | None:
        """Tên quận người dùng viết ("Q.7", "quan 07", "Thu Duc") → mã 0-23, không thì None."""
        codes = MessageRules.districts(name)
        return codes[0] if codes else None

    def predict(self, fields: PriceInput | dict) -> PriceEstimate:
        """Dự đoán giá/m² (làm tròn 2 chữ số), tổng giá = giá/m² × diện tích và biên độ.

        Raises:
            ValueError: đầu vào sai (xem PriceInput).
        """
        data = PriceInput(**fields) if isinstance(fields, dict) else fields
        kind, district = data.property_code, data.district_code
        distance = float(self.distance_to_center(data.latitude, data.longitude))
        schools, school_failed = self._count_schools(data)
        row = self._feature_row(data, distance, schools)
        price = round(float(np.exp(self.pipeline.predict(row))[0]), 2)
        low, high = self._tree_range(row)
        by_type = f"{district}|{kind}" in self.medians  # có khoá = đủ mẫu train cho quận + loại
        low, high = min(low, price), max(high, price)
        warnings = [] if by_type else [SPARSE_WARNING]
        if high / low > WIDE_RANGE_RATIO:
            warnings.append(WIDE_WARNING)
        if school_failed:
            warnings.append(SCHOOL_WARNING)
        known = not np.isnan(schools).any()
        return PriceEstimate(
            price_per_m2=price, total_price=round(price * data.area, 1),
            price_per_m2_low=low, price_per_m2_high=high, warnings=warnings,
            schools_1km=int(schools[0]) if known else None,
            schools_3km=int(schools[1]) if known else None,
            distance_to_center_km=round(distance, 1), median_by_type=by_type,
            district_median_per_m2=self.medians.get(
                f"{district}|{kind}", self.medians.get(str(district))
            ),
        )

    def _count_schools(self, data: PriceInput) -> tuple[np.ndarray, bool]:
        """(số trường 1 km và 3 km, True nếu có counter mà tra lỗi). Không tra được thì NaN để
        SimpleImputer điền median, không làm hỏng dự đoán."""
        if self.school_counter is None:
            return np.full(2, np.nan), False
        try:
            return self.school_counter.count([data.latitude], [data.longitude])[0], False
        except Exception:  # DB lỗi/chưa chạy: dự đoán vẫn phải trả được
            logger.exception("Không tra được số trường quanh vị trí")
            return np.full(2, np.nan), True

    @staticmethod
    def _feature_row(data: PriceInput, distance: float, schools: np.ndarray) -> pd.DataFrame:
        """Một dòng đặc trưng theo thứ tự FEATURES. Đặc điểm model không dùng cho loại nhà này
        thì coi như thiếu, kể cả khi người dùng lỡ nhập."""
        kind = data.property_code
        return pd.DataFrame([{
            "loại nhà đất": kind, "địa chỉ": data.district_code, "diện tích": data.area,
            "mặt tiền": np.nan if kind == APARTMENT else data.frontage,
            "phòng ngủ": np.nan if kind == LAND else data.bedrooms,
            "tọa độ x": data.latitude, "tọa độ y": data.longitude,
            "số tầng": np.nan if kind in (APARTMENT, LAND) else data.floors,
            "cách trung tâm": distance,
            SCHOOL_COLUMNS[0]: schools[0], SCHOOL_COLUMNS[1]: schools[1],
        }], columns=FEATURES).astype(float)

    def _tree_range(self, row: pd.DataFrame) -> tuple[float, float]:
        """Phân vị dự đoán của từng cây trong rừng: cho biết mức bất định của model."""
        imputed = self.pipeline.named_steps["imputer"].transform(row)
        trees = self.pipeline.named_steps["model"].estimators_
        prices = np.exp([tree.predict(imputed)[0] for tree in trees])
        low, high = np.percentile(prices, TREE_PERCENTILES)
        return round(float(low), 2), round(float(high), 2)
