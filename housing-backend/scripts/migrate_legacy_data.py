"""Chuyển dữ liệu từ DB cũ (5 schema listing, rag, amenities, ml, admin) sang bảng public mới.

Chạy từ housing-backend/housing-backend, sau `alembic upgrade head` + `seed_address.py`:

    python scripts/migrate_legacy_data.py \
        --source-url postgresql://user:pass@localhost:5432/housing \
        --target-url postgresql://user:pass@localhost:5432/housing_dev

Nguồn chỉ đọc (default_transaction_read_only). Đích upsert trong một transaction nên chạy lại
nhiều lần kết quả không đổi. Hai URL có thể là cùng một DB.
"""

import argparse
import re
import sys

import psycopg

LISTING_COLUMNS = [
    "listing_id", "listing_url", "title", "description", "transaction_type", "property_type",
    "price", "price_per_m2", "area", "frontage", "bedrooms", "bathrooms", "road_width",
    "floors", "legal", "legal_group", "interior", "province_old", "district_old", "old_ward",
    "old_address", "old_address_detail", "new_ward", "new_city", "new_address", "latitude",
    "longitude", "posted_at", "expired_at", "quality_flags", "first_loaded_at", "updated_at",
]
SPATIAL_COLUMNS = [
    "listing_id", "school_count_1km", "hospital_count_1km", "market_count_1km",
    "school_count_3km", "hospital_count_3km", "market_count_3km", "nearest_school_name",
    "nearest_school_m", "nearest_hospital_name", "nearest_hospital_m", "nearest_market_name",
    "nearest_market_m", "computed_at",
]
EMBEDDING_COLUMNS = [
    "listing_id", "model_name", "content_hash", "embedding_text", "rag_document", "embedding",
    "embedded_at",
]
POI_COLUMNS = [
    "id", "poi_type", "poi_subtype", "name", "address_old", "address_new", "latitude",
    "longitude", "ownership", "school_level_codes",
]

# 3 bảng POI cũ gộp vào `pois`. Bảng cũ không có id số nên id được đánh theo thứ tự
# (poi_type, poi_id cũ): nguồn không đổi thì id không đổi, upsert chạy lại không nhân bản.
POI_SOURCE_SQL = """
    SELECT row_number() OVER (ORDER BY poi_type, poi_id)::integer, poi_type, poi_subtype, name,
           address_old, address_new, latitude, longitude, ownership, school_level_codes
      FROM (SELECT poi_id, poi_type, poi_subtype, name, address_old, address_new, latitude,
                   longitude, ownership, school_level_codes
              FROM amenities.poi_schools
            UNION ALL
            SELECT poi_id, poi_type, poi_subtype, name, address_old, address_new, latitude,
                   longitude, ownership, NULL
              FROM amenities.poi_hospitals
            UNION ALL
            SELECT poi_id, poi_type, poi_subtype, name, address_old, address_new, latitude,
                   longitude, NULL, NULL
              FROM amenities.poi_markets) p
"""


class LegacyDataMigrator:
    """Copy tin, đặc trưng không gian, embedding, POI, nhãn quận; rồi nối FK địa chỉ của tin."""

    def __init__(self, source_url: str, target_url: str):
        # Chấp nhận cả URL kiểu SQLAlchemy (postgresql+asyncpg://...) như DATABASE_URL của app
        self.source_url, self.target_url = (
            re.sub(r"^postgresql\+\w+://", "postgresql://", url)
            for url in (source_url, target_url)
        )

    def run(self) -> None:
        with (
            psycopg.connect(
                self.source_url, options="-c default_transaction_read_only=on"
            ) as src,
            psycopg.connect(self.target_url) as dst,
        ):
            self.copy(src, dst, "listings", LISTING_COLUMNS, ["listing_id"],
                      f"SELECT {', '.join(LISTING_COLUMNS)} FROM listing.listings")
            self.copy(src, dst, "listing_spatial_features", SPATIAL_COLUMNS, ["listing_id"],
                      f"SELECT {', '.join(SPATIAL_COLUMNS)} FROM listing.listing_spatial_features")
            # vector đọc ra dạng text, Postgres tự ép text -> vector khi ghi
            self.copy(src, dst, "listing_embeddings", EMBEDDING_COLUMNS, ["listing_id"],
                      "SELECT listing_id, model_name, content_hash, embedding_text, rag_document,"
                      " embedding::text, embedded_at FROM rag.listing_embeddings")
            self.copy(src, dst, "pois", POI_COLUMNS, ["id"], POI_SOURCE_SQL)
            # INSERT kèm id không đẩy sequence -> đặt lại để lần thêm POI sau không trùng id
            dst.execute(
                "SELECT setval('pois_id_seq', (SELECT coalesce(max(id), 0) + 1 FROM pois), false)"
            )
            self.copy_district_labels(src, dst)
            self.link_listings(dst)
            dst.commit()

    def copy(
        self, src, dst, table: str, columns: list[str], pk: list[str], select_sql: str
    ) -> None:
        """Đọc toàn bộ từ nguồn, upsert vào bảng đích theo khóa chính."""
        rows = src.execute(select_sql).fetchall()
        updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in columns if c not in pk)
        with dst.cursor() as cur:
            cur.executemany(
                f"INSERT INTO {table} ({', '.join(columns)}) "
                f"VALUES ({', '.join(['%s'] * len(columns))}) "
                f"ON CONFLICT ({', '.join(pk)}) DO UPDATE SET {updates}",
                rows,
            )
            count = cur.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
        print(f"{table:25} nguồn {len(rows):6}   đích {count:6}")

    def copy_district_labels(self, src, dst) -> None:
        """district_name cũ (viết thường) -> districts_old.id; phải khớp đủ, thiếu thì dừng."""
        district_ids = dict(dst.execute(
            "SELECT lower(name), id FROM districts_old WHERE province_code = 'SG'"
        ).fetchall())
        labels = src.execute(
            "SELECT model_version, label, district_name FROM ml.district_label"
        ).fetchall()
        missing = [name for _, _, name in labels if name not in district_ids]
        if missing:
            raise SystemExit(f"district_label: không khớp districts_old: {missing}")
        dst.cursor().executemany(
            "INSERT INTO district_label (model_version, label, district_id) VALUES (%s, %s, %s) "
            "ON CONFLICT (model_version, label) DO UPDATE SET district_id = EXCLUDED.district_id",
            [(version, label, district_ids[name]) for version, label, name in labels],
        )
        count = dst.execute("SELECT count(*) FROM district_label").fetchone()[0]
        print(f"{'district_label':25} nguồn {len(labels):6}   đích {count:6}")

    def link_listings(self, dst) -> None:
        """Điền FK địa chỉ của tin bằng function chung với ListingLoader (migration 0001)."""
        dst.execute("SELECT refresh_listing_address_ids()")
        total, *linked = dst.execute(
            "SELECT count(*), count(old_district_id), count(old_ward_id), count(new_ward_id)"
            " FROM listings"
        ).fetchone()
        columns = ("old_district_id", "old_ward_id", "new_ward_id")
        for column, count in zip(columns, linked, strict=True):
            print(f"listings.{column:16} khớp {count:5}   không khớp {total - count:5}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # console Windows mặc định cp1252
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source-url", required=True, help="DB cũ có 5 schema (chỉ đọc)")
    parser.add_argument("--target-url", required=True, help="DB đích đã upgrade + seed_address")
    args = parser.parse_args()
    LegacyDataMigrator(args.source_url, args.target_url).run()
