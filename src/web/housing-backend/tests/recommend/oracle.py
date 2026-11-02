"""SQL oracle độc lập cho bộ kịch bản recommendation.

Không import bất kỳ thứ gì từ ``app``: mọi điều kiện cứng được viết lại bằng SQL thuần để
đối chiếu với hệ thống (``[S1]``, ``[S4]``, ``[S6]``, ``[S14]``, ``[S15]``).

Điều kiện kỳ vọng dùng tên (``district_names``, ``new_ward_names``) như trong
``scenarios.json``; oracle tự tra ID trong ``districts_old``/``wards_new``.
"""

from __future__ import annotations

import os
from datetime import date

import psycopg

DEFAULT_DSN = "postgresql://postgres:123456789@localhost:5432/housing_dev"
DEDUP_RADIUS_M = 30
RELAX_PRICE_FACTOR = 1.2


def oracle_dsn() -> str:
    """URL DB cho oracle: ``ORACLE_DATABASE_URL`` > ``DATABASE_URL`` > housing_dev."""
    url = os.environ.get("ORACLE_DATABASE_URL") or os.environ.get("DATABASE_URL") or DEFAULT_DSN
    return url.replace("postgresql+asyncpg://", "postgresql://").replace(
        "postgresql+psycopg://", "postgresql://"
    )


class SqlOracle:
    """Đếm và kiểm tin theo điều kiện cứng cộng dồn, kết nối chỉ đọc."""

    def __init__(self, dsn: str | None = None) -> None:
        self._conn = psycopg.connect(
            dsn or oracle_dsn(),
            options="-c default_transaction_read_only=on",
            autocommit=True,
        )
        self.district_ids = self._name_map("districts_old")
        self.ward_ids = self._name_map("wards_new")

    def close(self) -> None:
        self._conn.close()

    def _name_map(self, table: str) -> dict[str, int]:
        rows = self._conn.execute(f"SELECT name, id FROM {table}").fetchall()
        return {name: id_ for name, id_ in rows}

    def ids_for(self, expected: dict, key: str) -> list[int]:
        """Đổi ``district_names``/``new_ward_names`` sang ID; tên sai ⇒ KeyError."""
        table = self.district_ids if key == "district_names" else self.ward_ids
        return sorted(table[name] for name in expected.get(key) or [])

    def _filter(self, expected: dict, as_of: date) -> tuple[str, list]:
        """WHERE cho bảng ``listings l`` từ điều kiện kỳ vọng (mọi giá trị qua placeholder)."""
        clauses = ["l.posted_at <= %s", "l.expired_at >= %s"]
        params: list = [as_of, as_of]
        scalar = [
            ("price_min", "l.price >= %s"),
            ("price_max", "l.price <= %s"),
            ("area_min", "l.area >= %s"),
            ("area_max", "l.area <= %s"),
            ("bedrooms_min", "l.bedrooms >= %s"),
        ]
        for key, sql in scalar:
            if expected.get(key) is not None:
                clauses.append(sql)
                params.append(expected[key])
        lists = [
            ("property_types", "l.property_type = ANY(%s)", expected.get("property_types")),
            ("district_names", "l.old_district_id = ANY(%s)",
             self.ids_for(expected, "district_names")),
            ("new_ward_names", "l.new_ward_id = ANY(%s)",
             self.ids_for(expected, "new_ward_names")),
        ]
        for _, sql, values in lists:
            if values:
                clauses.append(sql)
                params.append(list(values))
        for poi in expected.get("near_pois") or []:
            clauses.append(
                "EXISTS (SELECT 1 FROM pois p WHERE p.poi_type = %s"
                " AND ST_DWithin(p.geom, l.geom, %s))"
            )
            params += [poi["poi_type"], poi["max_distance_m"]]
        return " AND ".join(clauses), params

    def count(self, expected: dict, as_of: date, dedup: bool = True) -> int:
        """Số tin thỏa điều kiện; ``dedup`` đếm theo nhóm tin đăng lại (spec mục 3)."""
        where, params = self._filter(expected, as_of)
        if not dedup:
            sql = f"SELECT count(*) FROM listings l WHERE {where}"
            return self._conn.execute(sql, params).fetchone()[0]
        sql = f"""
            WITH f AS (SELECT l.* FROM listings l WHERE {where})
            SELECT count(*) FROM f
            WHERE NOT EXISTS (
                SELECT 1 FROM f g
                WHERE g.listing_id <> f.listing_id
                  AND g.property_type = f.property_type
                  AND g.price = f.price
                  AND g.area IS NOT DISTINCT FROM f.area
                  AND g.bedrooms IS NOT DISTINCT FROM f.bedrooms
                  AND ST_DWithin(g.geom, f.geom, %s)
                  AND (g.posted_at, g.listing_id) > (f.posted_at, f.listing_id))
        """
        return self._conn.execute(sql, params + [DEDUP_RADIUS_M]).fetchone()[0]

    def violations(self, listing_ids: list[str], expected: dict, as_of: date) -> dict:
        """Lý do vi phạm của từng tin: ``{"s6": [...], "s1": [...]}`` theo listing_id."""
        if not listing_ids:
            return {}
        where, params = self._filter(expected, as_of)
        sql = f"""
            SELECT l.listing_id, l.posted_at <= %s AND l.expired_at >= %s, ({where})
            FROM listings l WHERE l.listing_id = ANY(%s)
        """
        rows = self._conn.execute(sql, [as_of, as_of, *params, listing_ids]).fetchall()
        found = {row[0]: row for row in rows}
        result = {}
        for lid in listing_ids:
            row = found.get(lid)
            if row is None:
                result[lid] = {"s1": ["không có trong DB"], "s6": ["không có trong DB"]}
            elif not (row[1] and row[2]):
                result[lid] = {
                    "s6": [] if row[1] else ["ngoài khoảng posted_at/expired_at"],
                    "s1": [] if row[2] else self._explain(lid, expected, as_of),
                }
        return result

    def _explain(self, listing_id: str, expected: dict, as_of: date) -> list[str]:
        """Tách từng điều kiện để biết tin vi phạm điều kiện nào."""
        reasons = []
        for key in ("price_min", "price_max", "area_min", "area_max", "bedrooms_min",
                    "property_types", "district_names", "new_ward_names"):
            if expected.get(key) not in (None, []) and not self._matches(
                listing_id, {key: expected[key]}, as_of
            ):
                reasons.append(key)
        for poi in expected.get("near_pois") or []:
            if not self._matches(listing_id, {"near_pois": [poi]}, as_of):
                reasons.append(f"near_pois:{poi['poi_type']}<={poi['max_distance_m']}")
        return reasons or ["hết hạn/chưa đăng"]

    def _matches(self, listing_id: str, expected: dict, as_of: date) -> bool:
        where, params = self._filter(expected, as_of)
        sql = f"SELECT EXISTS (SELECT 1 FROM listings l WHERE l.listing_id = %s AND {where})"
        return self._conn.execute(sql, [listing_id, *params]).fetchone()[0]

    def relax_counts(self, expected: dict, as_of: date) -> dict[str, list[int]]:
        """Số tin (đã gộp tin đăng lại) cho từng phương án nới một điều kiện (spec mục 4, §9 #5).

        Khóa là đúng 4 giá trị ``RelaxOption.field``; ``near_pois`` có một số đếm cho mỗi POI
        bị bỏ, các khóa khác có đúng một số.
        """
        variants: dict[str, list[dict]] = {}
        pois = expected.get("near_pois") or []
        if pois:
            variants["near_pois"] = [
                {**expected, "near_pois": pois[:i] + pois[i + 1:]} for i in range(len(pois))
            ]
        if expected.get("price_max") is not None:
            variants["price_max"] = [
                {**expected, "price_max": expected["price_max"] * RELAX_PRICE_FACTOR}
            ]
        if expected.get("property_types"):
            variants["property_types"] = [{**expected, "property_types": []}]
        if expected.get("district_names") or expected.get("new_ward_names"):
            variants["location"] = [{**expected, "district_names": [], "new_ward_names": []}]
        return {
            field: [self.count(v, as_of) for v in options] for field, options in variants.items()
        }

    def duplicate_pairs(self, listing_ids: list[str]) -> list[tuple[str, str]]:
        """Cặp tin trong Top 5 thuộc cùng nhóm tin đăng lại (``[S15]``)."""
        sql = """
            SELECT a.listing_id, b.listing_id
            FROM listings a JOIN listings b
              ON a.listing_id < b.listing_id
             AND a.property_type = b.property_type AND a.price = b.price
             AND a.area IS NOT DISTINCT FROM b.area
             AND a.bedrooms IS NOT DISTINCT FROM b.bedrooms
             AND ST_DWithin(a.geom, b.geom, %s)
            WHERE a.listing_id = ANY(%s) AND b.listing_id = ANY(%s)
        """
        rows = self._conn.execute(sql, [DEDUP_RADIUS_M, listing_ids, listing_ids])
        return [tuple(row) for row in rows.fetchall()]

    def row_values(self, listing_ids: list[str]) -> dict[str, dict]:
        """Giá trị thật các cột tin + khoảng cách POI gần nhất (chấm superlative/chi tiết)."""
        sql = """
            SELECT l.listing_id, l.price, l.price_per_m2, l.area, l.bedrooms, l.bathrooms,
                   l.floors, l.frontage, l.road_width, l.legal, l.interior, l.posted_at,
                   l.expired_at, l.listing_url, f.nearest_school_m, f.nearest_hospital_m,
                   f.nearest_market_m
            FROM listings l LEFT JOIN listing_spatial_features f ON f.listing_pk = l.id
            WHERE l.listing_id = ANY(%s)
        """
        cur = self._conn.execute(sql, [listing_ids])
        names = [d.name for d in cur.description]
        return {row[0]: dict(zip(names, row, strict=True)) for row in cur.fetchall()}

    def listing_facts(self, listing_ids: list[str]) -> dict[str, dict]:
        """Giá, URL, tiêu đề + mô tả thật của các tin (dùng chấm grounding ``[S5]``)."""
        sql = ("SELECT listing_id, price, price_per_m2, listing_url,"
               " concat_ws(' ', title, description) FROM listings WHERE listing_id = ANY(%s)")
        rows = self._conn.execute(sql, [listing_ids]).fetchall()
        return {r[0]: {"price": r[1], "price_per_m2": r[2], "url": r[3], "text": r[4]}
                for r in rows}
