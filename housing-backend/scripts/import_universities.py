"""Thêm trường đại học/cao đẳng (OSM, CrawUltilities/poi_master.csv) vào bảng pois.

Chạy từ thư mục housing-backend, sau `alembic upgrade head` (docs/tasks/named-places.md 2.1):

    DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/housing_dev \
        python scripts/import_universities.py

Idempotent: trường đã có (cùng tên chuẩn hoá, cách < 200 m) thì bỏ qua, nên chạy lại không thêm
dòng; dòng ĐH/CĐ trong pois không còn hợp lệ theo luật hiện tại thì tự xoá. Không lưu id
OSM/URL/nguồn (AGENTS.md mục 5). "gần trường học" chung chung không dùng các dòng này (lọc theo
poi_subtype ở search.py và refresh_spatial_features()).
"""

import csv
import math
import os
import re
import sys
import unicodedata
from pathlib import Path

import psycopg


class UniversityImporter:
    """Đọc CSV → lọc đại học/cao đẳng trong TP.HCM cũ → bỏ trùng → thêm vào pois."""

    CSV_PATH = Path(__file__).resolve().parents[2] / "CrawUltilities/poi_master.csv"
    HCM_LAT, HCM_LON = (10.37, 11.17), (106.35, 107.03)  # = constants.HCM_LAT/HCM_LON
    NAME_PATTERN = re.compile(r"^(?:truong )?(?:dai hoc|dh|cao dang|cd|hoc vien)\b")
    OTHER_PROVINCES = ("long an", "binh duong", "dong nai", "tay ninh", "vung tau", "ba ria",
                       "di an", "thuan an", "bien hoa", "thu dau mot")
    # Ranh giới bắc xấp xỉ giữa Thủ Đức (cũ) và Dĩ An/Thuận An (Bình Dương): ĐH Quốc tế, ĐH Công
    # nghệ Thông tin ở ~10,870-10,878 còn trong TP.HCM; phía bắc vĩ độ này là Bình Dương. Chọn vĩ
    # độ đơn giản vì không có polygon ranh giới; tin đăng chỉ phủ TP.HCM nên không dùng để suy ranh.
    # HẠN CHẾ ĐÃ BIẾT: ranh thật không nằm ngang, vài điểm sát ranh có thể sai (đã gặp ĐH Bách
    # khoa cơ sở 2 ở Đông Hòa, Dĩ An dưới vĩ độ này). Vì vậy điểm cách ≤ BORDER_TWIN_M một điểm đã
    # bị loại (vì vĩ độ hoặc tên tỉnh) VÀ trùng ≥ 2 từ tên cũng bị loại: cùng cơ sở, OSM hay có
    # hai bản. Chỉ xét khoảng cách là không đủ: địa chỉ OSM của ĐH Quốc tế (thuộc Thủ Đức) cũng ghi
    # "Dĩ An, Bình Dương", cách ĐH Quốc tế thật chưa tới 300 m.
    NORTH_LAT = 10.885
    BORDER_TWIN_M = 300
    GENERIC_WORDS = frozenset([  # từ chung của tên trường, không dùng để so tên
        "truong", "dai", "hoc", "cao", "dang", "vien", "co", "so", "thanh", "pho", "ho", "chi",
        "minh", "tp", "hcm", "phan", "hieu"])
    # Nhãn OSM sai / không phải trường: "VGU" gắn nhầm cho điểm ở 307A Nguyễn Trọng Tuyển (Phú
    # Nhuận), toà nhà đang xây của ĐH Quốc tế.
    NOT_A_SCHOOL = ("vgu", "toa nha")
    SAME_PLACE_M = 200
    # Tin đăng phủ TP.HCM cũ: điểm cách mọi tin > 3 km (vd. ĐH Tân Tạo ở Long An) bị loại
    NEAR_LISTING_SQL = """
        SELECT EXISTS (SELECT 1 FROM listings
                        WHERE ST_DWithin(geom, ST_MakePoint(%s, %s)::geography, 3000)
                          AND NOT ('coords_outside_hcm' = ANY(quality_flags)))
    """

    def __init__(self, database_url: str):
        # Cùng biến DATABASE_URL với app (driver asyncpg) -> bỏ phần +driver cho psycopg
        self.conninfo = re.sub(r"^postgresql\+\w+://", "postgresql://", database_url)

    def run(self) -> None:
        with psycopg.connect(self.conninfo) as connection:
            rows = self.transform(self.load(), connection)
            added, removed = self.save(rows, connection)
        print(f"Đại học/cao đẳng hợp lệ: {len(rows)}, thêm mới: {added}, xoá dòng sai: {removed}")

    def load(self) -> list[dict]:
        """Dòng school là university, hoặc tên bắt đầu bằng Trường Đại học/Cao đẳng/Học viện."""
        with self.CSV_PATH.open(encoding="utf-8") as file:
            return [row for row in csv.DictReader(file) if row["category"] == "school" and (
                row["subtype"] == "university" or self.NAME_PATTERN.match(self.plain(row["name"])))]

    def transform(self, rows: list[dict], connection) -> list[dict]:
        """Có toạ độ trong TP.HCM cũ, không nhắc tỉnh khác, gần tin đăng; bỏ trùng trong file."""
        kept: list[dict] = []
        outside = [row for row in rows if row["latitude"] and self.is_outside(row)]
        for row in rows:
            if not (row["latitude"] and row["longitude"]):
                continue
            lat, lon = float(row["latitude"]), float(row["longitude"])
            text = self.plain(f"{row['name']} {row['address_raw']}")
            if "trung cap" in text or any(word in text for word in self.NOT_A_SCHOOL):
                continue  # trung cấp: OSM gắn nhầm subtype; nhãn sai / không phải trường
            if row in outside or any(self.same_place(
                    row, other, by_name=False) for other in outside):
                continue
            if not connection.execute(self.NEAR_LISTING_SQL, (lon, lat)).fetchone()[0]:
                continue
            item = {"name": row["name"].strip(), "address_old": row["address_raw"] or None,
                    "latitude": lat, "longitude": lon,
                    "poi_subtype": "Cao đẳng" if re.search(r"\b(?:cao dang|cd)\b",
                                                           self.plain(row["name"])) else "Đại học"}
            if not any(self.same_place(item, other) for other in kept):
                kept.append(item)
        return kept

    def is_outside(self, row: dict) -> bool:
        """Ngoài TP.HCM cũ: ngoài khung toạ độ, phía bắc ranh Thủ Đức–Dĩ An, hoặc nhắc tỉnh khác."""
        lat, lon = float(row["latitude"]), float(row["longitude"])
        text = self.plain(f"{row['name']} {row['address_raw']}")
        return not (self.HCM_LAT[0] <= lat <= self.NORTH_LAT
                    and self.HCM_LON[0] <= lon <= self.HCM_LON[1]) or any(
                    province in text for province in self.OTHER_PROVINCES)

    def save(self, rows: list[dict], connection) -> int:
        """Chỉ thêm trường chưa có trong pois (so tên chuẩn hoá + khoảng cách)."""
        existing = [dict(zip(("id", "name", "latitude", "longitude"), row, strict=True))
                    for row in connection.execute(
                        "SELECT id, name, latitude, longitude FROM pois WHERE poi_subtype IN"
                        " ('Đại học', 'Cao đẳng')")]
        stale = [old for old in existing  # không còn hợp lệ (vd. luật lọc siết chặt hơn)
                 if not any(self.same_place(old, row) for row in rows)]
        connection.execute("DELETE FROM pois WHERE poi_subtype IN ('Đại học', 'Cao đẳng')"
                           " AND id = ANY(%s)", ([old["id"] for old in stale],))
        new = [row for row in rows if not any(self.same_place(row, old) for old in existing)]
        with connection.cursor() as cursor:
            cursor.executemany(
                "INSERT INTO pois (poi_type, poi_subtype, name, address_old, latitude, longitude)"
                " VALUES ('truong_hoc', %(poi_subtype)s, %(name)s, %(address_old)s,"
                " %(latitude)s, %(longitude)s)", new)
        return len(new), len(stale)

    @classmethod
    def same_place(cls, a: dict, b: dict, by_name: bool = True) -> bool:
        """by_name: cùng tên chuẩn hoá và cách nhau < SAME_PLACE_M; không thì cách nhau <
        BORDER_TWIN_M và trùng ≥ 2 từ tên (bỏ từ chung "trường", "đại học"...)."""
        words = [set(cls.plain(x["name"]).split()) - cls.GENERIC_WORDS for x in (a, b)]
        if by_name and cls.plain(a["name"]) != cls.plain(b["name"]):
            return False
        if not by_name and len(words[0] & words[1]) < 2:
            return False
        lat_a, lon_a, lat_b, lon_b = (float(v) for v in (a["latitude"], a["longitude"],
                                                          b["latitude"], b["longitude"]))
        dy = math.radians(lat_a - lat_b)
        dx = math.radians(lon_a - lon_b) * math.cos(math.radians(lat_a))
        return 6_371_000 * math.hypot(dx, dy) < (cls.SAME_PLACE_M if by_name else cls.BORDER_TWIN_M)

    @staticmethod
    def plain(text: str) -> str:
        """Chữ thường, bỏ dấu (kể cả đ), chỉ giữ chữ/số."""
        text = unicodedata.normalize("NFD", (text or "").lower().replace("đ", "d"))
        text = "".join(c for c in text if unicodedata.category(c) != "Mn")
        return " ".join(re.sub(r"[^a-z0-9]+", " ", text).split())


if __name__ == "__main__":
    url = os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("Thiếu DATABASE_URL")
    UniversityImporter(url).run()
