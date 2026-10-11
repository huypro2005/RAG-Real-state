"""Nạp 7 bảng địa chỉ + ward_mappings từ address_data/ (JSON batdongsan + ward_mappings.sql).

Chạy từ thư mục housing-backend/housing-backend, sau `alembic upgrade head`:

    DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/housing_dev \
        python scripts/seed_address.py

Upsert theo khóa chính nên chạy lại nhiều lần kết quả không đổi.
Không import `app` để chạy được bằng `python scripts/...` mà không cần cài package.
"""

import json
import os
import re
import sys
import unicodedata
from pathlib import Path
from typing import ClassVar

import psycopg


class AddressSeeder:
    """Đọc JSON, nối mapping phường cũ -> mới sang ID batdongsan, upsert vào DB."""

    DATA_DIR = Path(__file__).resolve().parents[3] / "address_data"
    HCM_OLD_PROVINCE = "Thành phố Hồ Chí Minh"  # giá trị old_province_name trong ward_mappings.sql
    # Bảng -> (cột khóa chính, các cột khác), theo thứ tự cha trước con để FK hợp lệ
    TABLES: ClassVar[dict[str, tuple[list[str], list[str]]]] = {
        "provinces_old": (["code"], ["name", "alias"]),
        "provinces_new": (["code"], ["name", "alias"]),
        "districts_old": (["id"], ["province_code", "name", "prefix", "alias"]),
        "wards_old": (["id"], ["district_id", "name", "prefix", "alias"]),
        "streets_old": (["id", "district_id"], ["name", "prefix", "alias"]),
        "wards_new": (["id"], ["province_code", "name", "prefix", "alias"]),
        "streets_new": (["id", "ward_id"], ["name", "prefix", "alias"]),
        "ward_mappings": (["old_ward_id"], ["new_ward_id"]),
    }
    # Bảng -> (file JSON, cột ID cha nếu file gom theo ID cha, {cột: field JSON})
    SOURCES: ClassVar[dict[str, tuple[str, str | None, dict[str, str]]]] = {
        "provinces_old": ("old_cities.json", None,
                          {"code": "cityCode", "name": "cityName", "alias": "cityAlias"}),
        "provinces_new": ("new_cities.json", None,
                          {"code": "cityCode", "name": "cityName", "alias": "cityAlias"}),
        "districts_old": ("sg_old.json", None,
                          {"id": "districtId", "province_code": "cityCode",
                           "name": "districtName", "prefix": "districtPrefix",
                           "alias": "districtAlias"}),
        "wards_old": ("sg_old_wards.json", "district_id",
                      {"id": "wardId", "name": "wardName", "prefix": "wardPrefix",
                       "alias": "wardAlias"}),
        "streets_old": ("sg_old_streets.json", "district_id",
                        {"id": "streetId", "name": "streetName", "prefix": "streetPrefix",
                         "alias": "streetAlias"}),
        "wards_new": ("sg_new_wards.json", None,
                      {"id": "wardId", "province_code": "cityCode", "name": "wardName",
                       "prefix": "wardPrefix", "alias": "wardAlias"}),
        "streets_new": ("sg_new_streets.json", "ward_id",
                        {"id": "streetId", "name": "streetName", "prefix": "streetPrefix",
                         "alias": "streetAlias"}),
    }
    INSERT_PATTERN = re.compile(r"^INSERT INTO `ward_mappings` \((.+?)\) VALUES \((.+)\);$")
    VALUE_PATTERN = re.compile(r"'((?:[^'\\]|\\.)*)'|(NULL)|(-?\d+)")

    def __init__(self, database_url: str):
        # Cùng biến DATABASE_URL với app (driver asyncpg) -> bỏ phần +driver cho psycopg
        self.conninfo = re.sub(r"^postgresql\+\w+://", "postgresql://", database_url)

    def run(self) -> None:
        rows = self.load_json()
        rows["ward_mappings"], unmatched = self.match_ward_mappings(rows)
        (self.DATA_DIR / "ward_mappings_unmatched.json").write_text(
            json.dumps(unmatched, ensure_ascii=False, indent=4), encoding="utf-8"
        )
        print(f"ward_mappings: khớp {len(rows['ward_mappings'])}, không khớp {len(unmatched)}")
        self.save(rows)

    def read(self, file_name: str):
        return json.loads((self.DATA_DIR / file_name).read_text(encoding="utf-8"))

    def load_json(self) -> dict[str, list[dict]]:
        """Map 1-1 field JSON -> cột. File theo ID cha lấy ID cha từ khóa ngoài của file."""
        rows = {}
        for table, (file_name, parent_column, fields) in self.SOURCES.items():
            data = self.read(file_name)
            if parent_column:  # {"<id cha>": [bản ghi, ...]}
                records = [({parent_column: int(parent_id)}, item)
                           for parent_id, group in data.items() for item in group]
            else:
                records = [({}, item) for item in data]
            rows[table] = [{**parent, **{column: item[field] for column, field in fields.items()}}
                           for parent, item in records]
        return rows

    def match_ward_mappings(self, rows: dict[str, list[dict]]) -> tuple[list[dict], list[dict]]:
        """Nối từng dòng TP.HCM của ward_mappings.sql sang ID batdongsan bằng tên đầy đủ.

        Chỉ bỏ dấu cách thừa + không phân biệt hoa/thường + chuẩn hóa Unicode NFC; không bỏ
        dấu, không fuzzy. NFC vì file .sql lưu một số tên dạng tổ hợp (NFD), batdongsan dạng
        dựng sẵn: cùng chữ, khác byte (tương đương chuẩn Unicode).
        Tên đầy đủ batdongsan = prefix + ' ' + name (prefix rỗng thì chỉ name, vd. 'Quận 1').

        'Thành phố Thủ Đức' trong file mapping khớp chính xác quận 71 'Thành phố Thủ Đức' của
        batdongsan (34 phường). Không tìm thêm trong Quận 2, Quận 9 như spec dự kiến: quận 71
        lặp lại 22 phường của Quận 2 (9) và Quận 9 (13) với ID khác, tìm cả 3 quận sẽ ra 2 kết
        quả cho 22 phường đó.
        """
        key = self.name_key
        district_ids, old_wards, new_wards = {}, {}, {}
        for d in rows["districts_old"]:
            district_ids.setdefault(key(d["prefix"], d["name"]), []).append(d["id"])
        for w in rows["wards_old"]:
            ward_key = (w["district_id"], key(w["prefix"], w["name"]))
            old_wards.setdefault(ward_key, []).append(w["id"])
        for w in rows["wards_new"]:
            new_wards.setdefault(key(w["prefix"], w["name"]), []).append(w["id"])

        matched, unmatched = [], []
        for record in self.read_ward_mappings_sql():
            if record["old_province_name"] != self.HCM_OLD_PROVINCE:
                continue
            districts = district_ids.get(key("", record["old_district_name"]), [])
            old_ids = []
            if len(districts) == 1:
                old_ids = old_wards.get((districts[0], key("", record["old_ward_name"])), [])
            new_ids = new_wards.get(key("", record["new_ward_name"]), [])
            if reason := self.mismatch_reason(districts, old_ids, new_ids):
                unmatched.append({**record, "reason": reason})
            else:
                matched.append({"old_ward_id": old_ids[0], "new_ward_id": new_ids[0]})
        return matched, unmatched

    @staticmethod
    def name_key(prefix: str, name: str) -> str:
        """Khóa so khớp tên: gộp khoảng trắng, NFC, chữ thường."""
        return unicodedata.normalize("NFC", " ".join(f"{prefix} {name}".split())).lower()

    @staticmethod
    def mismatch_reason(districts: list, old_ids: list, new_ids: list) -> str | None:
        """Lý do không nối được (mỗi cấp phải khớp đúng 1 ID batdongsan); None nếu khớp cả ba."""
        if len(districts) != 1:
            return f"quận cũ khớp {len(districts)} quận batdongsan"
        if len(old_ids) != 1:
            return f"phường cũ khớp {len(old_ids)} phường batdongsan"
        if len(new_ids) != 1:
            return f"phường mới khớp {len(new_ids)} phường batdongsan"
        return None

    def read_ward_mappings_sql(self) -> list[dict]:
        """Đọc từng dòng INSERT của dump MySQL (không cần MySQL, không sửa file gốc)."""
        records = []
        with open(self.DATA_DIR / "ward_mappings.sql", encoding="utf-8") as sql_file:
            for line in sql_file:
                match = self.INSERT_PATTERN.match(line.strip())
                if not match:
                    continue
                columns = [c.strip(" `") for c in match.group(1).split(",")]
                # Mỗi giá trị là chuỗi '...' (bỏ ký tự thoát \), NULL hoặc số
                values = []
                for text, null, number in self.VALUE_PATTERN.findall(match.group(2)):
                    if null:
                        values.append(None)
                    elif number:
                        values.append(int(number))
                    else:
                        values.append(re.sub(r"\\(.)", r"\1", text))
                records.append(dict(zip(columns, values, strict=True)))
        return records

    def save(self, rows: dict[str, list[dict]]) -> None:
        """Upsert từng bảng trong một transaction rồi in số dòng DB so với số bản ghi nguồn."""
        with psycopg.connect(self.conninfo) as conn, conn.cursor() as cur:
            for table, (pk, others) in self.TABLES.items():
                columns = pk + others
                cur.executemany(
                    f"INSERT INTO {table} ({', '.join(columns)}) "
                    f"VALUES ({', '.join(f'%({c})s' for c in columns)}) "
                    f"ON CONFLICT ({', '.join(pk)}) DO UPDATE SET "
                    + ", ".join(f"{c} = EXCLUDED.{c}" for c in others),
                    rows[table],
                )
            conn.commit()
            for table in self.TABLES:
                count = cur.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
                print(f"{table:15} DB {count:6}   nguồn {len(rows[table]):6}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # console Windows mặc định cp1252
    AddressSeeder(os.environ["DATABASE_URL"]).run()
