"""Chuyển dữ liệu thô trong database (bảng listings) thành CSV huấn luyện mô hình giá.

Cột đầu ra giống data/price_training.csv: loại nhà đất, địa chỉ, giá, diện tích, giá/m2,
mặt tiền, phòng ngủ, pháp lý, tọa độ x, tọa độ y, số tầng.

Chạy trong src/notebook/predictionEDA/ (dùng .venv gốc):

    python db_to_training/build_training_csv.py
    python db_to_training/build_training_csv.py --db-url postgresql://postgres:<mk>@localhost:5432/housing_dev \
        --output data/price_training_db.csv

Không ghi đè data/price_training.csv. Không đoán dữ liệu: ô thiếu giữ nguyên rỗng, tin có loại
nhà/quận không có mã bị bỏ và được đếm trong báo cáo.
"""

import argparse
import os
from pathlib import Path

import pandas as pd
import psycopg

DEFAULT_DB_URL = "postgresql://postgres:{password}@localhost:5432/housing_dev"
DEFAULT_OUTPUT = Path(__file__).resolve().parents[1] / "data/price_training_db.csv"

# Mã loại nhà đất của đồ án 1 (giống REAL_ESTATE_ trong notebook)
PROPERTY_CODES = {
    "Căn hộ chung cư": 0,
    "Chung cư mini, căn hộ dịch vụ": 1,
    "Nhà riêng": 2,
    "Nhà biệt thự, liền kề": 3,
    "Nhà mặt phố": 4,
    "Shophouse, nhà phố thương mại": 5,
    "Đất nền dự án": 6,
    "Bán đất": 7,
    "Kho, nhà xưởng": 9,
}
# Mã quận/huyện 0-23 (giống ADDRESS_ trong notebook), khớp listings.district_old
DISTRICT_CODES = {
    name: code for code, name in enumerate([
        "Bình Chánh", "Bình Tân", "Bình Thạnh", "Cần Giờ", "Củ Chi", "Gò Vấp", "Hóc Môn",
        "Nhà Bè", "Phú Nhuận", "Quận 1", "Quận 10", "Quận 11", "Quận 12", "Quận 2", "Quận 3",
        "Quận 4", "Quận 5", "Quận 6", "Quận 7", "Quận 8", "Quận 9", "Thủ Đức", "Tân Bình",
        "Tân Phú",
    ])
}
# Pháp lý: 1 = sổ đỏ/sổ hồng, 2 = hợp đồng mua bán; "đang chờ sổ", "khác", thiếu -> để trống
LEGAL_CODES = {"so_do_so_hong": 1, "hop_dong_mua_ban": 2}
COORDINATE_SCALE = 1_000_000_000  # file crawl cũ lưu tọa độ nhân 10⁹, notebook chia lại

COLUMNS = [
    "loại nhà đất", "địa chỉ", "giá", "diện tích", "giá/m2", "mặt tiền", "phòng ngủ",
    "pháp lý", "tọa độ x", "tọa độ y", "số tầng",
]


class TrainingCsvBuilder:
    """Đọc tin bán từ listings, đổi sang mã số của notebook và ghi CSV huấn luyện."""

    QUERY = """
        SELECT listing_id, property_type, district_old, price, area, price_per_m2, frontage,
               bedrooms, legal_group, latitude, longitude, floors
        FROM listings
        WHERE transaction_type = 'Bán'
        ORDER BY listing_id
    """

    def __init__(self, db_url: str, output: Path, scale_coordinates: bool = True):
        self.db_url = db_url
        self.output = output
        self.scale_coordinates = scale_coordinates

    def run(self) -> pd.DataFrame:
        raw = self.read_listings()
        training, report = self.convert(raw)
        self.output.parent.mkdir(parents=True, exist_ok=True)
        training.to_csv(self.output, index=False)
        print(f"Đã ghi {len(training)} dòng -> {self.output}")
        for reason, count in report.items():
            print(f"  {reason}: {count}")
        return training

    def read_listings(self) -> pd.DataFrame:
        with psycopg.connect(self.db_url) as conn, conn.cursor() as cur:
            cur.execute(self.QUERY)
            return pd.DataFrame(cur.fetchall(), columns=[c.name for c in cur.description])

    def convert(
        self, raw: pd.DataFrame, keep_listing_id: bool = False
    ) -> tuple[pd.DataFrame, dict[str, int]]:
        """Trả (bảng huấn luyện, số dòng bị bỏ theo lý do). Không sửa `raw`.

        `keep_listing_id`: giữ thêm cột listing_id (Prediction Server dùng để chia train/test cố
        định theo tin); CSV của CLI không bao giờ có cột này.
        """
        df = raw.copy()
        df["loại nhà đất"] = df["property_type"].map(PROPERTY_CODES)
        df["địa chỉ"] = df["district_old"].map(DISTRICT_CODES)
        df["pháp lý"] = df["legal_group"].map(LEGAL_CODES)
        df = df.rename(columns={
            "price": "giá", "area": "diện tích", "price_per_m2": "giá/m2", "frontage": "mặt tiền",
            "bedrooms": "phòng ngủ", "floors": "số tầng",
            "latitude": "tọa độ x", "longitude": "tọa độ y",
        })

        report = {"dòng đọc từ database": len(df)}
        has_label = df["loại nhà đất"].notna() & df["địa chỉ"].notna()
        report["bỏ vì loại nhà/quận không có mã"] = int((~has_label).sum())
        df = df[has_label]
        has_target = df["giá"].notna() & df["diện tích"].notna() & df["giá/m2"].notna()
        report["bỏ vì thiếu giá/diện tích/giá-m2"] = int((~has_target).sum())
        df = df[has_target]

        if self.scale_coordinates:
            df[["tọa độ x", "tọa độ y"]] = df[["tọa độ x", "tọa độ y"]] * COORDINATE_SCALE
        for column in ("loại nhà đất", "địa chỉ", "phòng ngủ", "pháp lý", "số tầng"):
            df[column] = df[column].astype("Int64")  # số nguyên, cho phép trống
        report["dòng ghi ra"] = len(df)
        return df[[*COLUMNS, "listing_id"] if keep_listing_id else COLUMNS], report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db-url", default=None, help="mặc định: housing_dev, mật khẩu PGPASSWORD")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--no-scale", action="store_true",
                        help="ghi tọa độ là độ thực (không nhân 10⁹ như file crawl cũ)")
    args = parser.parse_args()
    url = args.db_url or DEFAULT_DB_URL.format(password=os.environ.get("PGPASSWORD", ""))
    TrainingCsvBuilder(url, args.output, scale_coordinates=not args.no_scale).run()
