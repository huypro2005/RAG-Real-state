"""TrainingTableCleaner: bước làm sạch bảng huấn luyện giá, MỘT nguồn cho cả script train của
backend (CSV đồ án 1) lẫn Prediction Server (bảng dựng từ listings)."""

import pandas as pd

from app.services.prediction.constants import HCM_LAT, HCM_LON
from app.services.prediction.predictor import PricePredictor
from app.services.prediction.schools import SCHOOL_COLUMNS, SchoolCounter

# Loại bị bỏ như retrain.py: 1 chung cư mini, 5 shophouse, 6 đất nền dự án
DROPPED_TYPES = (1, 5, 6)


class TrainingTableCleaner:
    """Nhận bảng có toạ độ ĐỘ THỰC (cột "tọa độ x" = vĩ độ, "tọa độ y" = kinh độ)."""

    def __init__(self, school_counter: SchoolCounter):
        self.school_counter = school_counter

    def clean(self, raw: pd.DataFrame) -> pd.DataFrame:
        """Bản đã làm sạch của `raw` (không sửa DataFrame đầu vào).

        Cột `listing_id` (nếu có) chỉ là định danh, không tính vào việc phát hiện dòng trùng.
        """
        df = raw.copy()
        df["cách trung tâm"] = PricePredictor.distance_to_center(df["tọa độ x"], df["tọa độ y"])
        features = [column for column in df.columns if column != "listing_id"]
        df = df.drop(columns=["giá"]).drop_duplicates(  # cột giá tuyệt đối gây rò rỉ nhãn
            subset=[column for column in features if column != "giá"])
        df = df[~df["loại nhà đất"].isin(DROPPED_TYPES)]
        in_city = df["tọa độ y"].between(*HCM_LON) & df["tọa độ x"].between(*HCM_LAT)
        df = df[in_city].copy()
        # Đếm trường chỉ dùng toạ độ (không dùng nhãn) nên làm trước khi chia train/test
        df[list(SCHOOL_COLUMNS)] = self.school_counter.count(df["tọa độ x"], df["tọa độ y"])
        # pháp lý chỉ để lọc: bỏ tin pháp lý = 2 và tin thiếu pháp lý, rồi bỏ cột
        df = df[(df["pháp lý"] != 2) & df["pháp lý"].notna()]
        return df.drop(columns=["pháp lý"]).reset_index(drop=True)
