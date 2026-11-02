"""baseline: extension, bảng (sinh từ model), function nearby(), refresh_spatial_features(),
refresh_listing_address_ids()

Revision ID: 0001
Revises:
Create Date: 2026-10-09

Dựng DB mới (trống): `alembic upgrade head`. Dữ liệu nạp lại bằng scripts/seed_address.py
và scripts/migrate_legacy_data.py. Thay đổi sau này viết thành migration mới (0002...).
"""

import sqlalchemy as sa
from alembic import op
from geoalchemy2 import Geography
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

EXTENSIONS = ("postgis", "vector", "pg_trgm", "unaccent")

# Cùng kiểu và biểu thức với GEOGRAPHY_POINT / GEOM_SQL trong app/db/models/poi.py
GEOGRAPHY_POINT = Geography(geometry_type="POINT", srid=4326, spatial_index=False)
GEOM_SQL = (
    "CASE WHEN longitude IS NOT NULL AND latitude IS NOT NULL "
    "THEN st_setsrid(st_makepoint(longitude, latitude), 4326)::geography "
    "ELSE NULL::geography END"
)

NEARBY_SQL = """
-- POI trong bán kính radius_m (mét) quanh một điểm, gần nhất trước.
--   SELECT * FROM nearby(106.70, 10.77, 1000);               -- mọi loại
--   SELECT * FROM nearby(106.70, 10.77, 1000, 'truong_hoc');  -- chỉ trường học
CREATE OR REPLACE FUNCTION nearby(
    query_longitude double precision,
    query_latitude  double precision,
    radius_m        double precision DEFAULT 1000,
    filter_type     text DEFAULT NULL
)
RETURNS TABLE(poi_id integer, poi_type text, name text, distance_m double precision)
LANGUAGE plpgsql STABLE
AS $$
DECLARE origin geography;
BEGIN
    IF query_longitude IS NULL OR query_latitude IS NULL OR radius_m IS NULL
       OR NOT query_longitude BETWEEN -180 AND 180
       OR NOT query_latitude BETWEEN -90 AND 90
       OR radius_m < 0 OR radius_m >= 'Infinity'::double precision THEN
        RAISE EXCEPTION 'Invalid longitude, latitude or radius (meters)';
    END IF;
    origin := ST_SetSRID(ST_MakePoint(query_longitude, query_latitude), 4326)::geography;
    RETURN QUERY
    SELECT p.id, p.poi_type, p.name, ST_Distance(p.geom, origin)
      FROM pois p
     WHERE ST_DWithin(p.geom, origin, radius_m)
       AND (filter_type IS NULL OR p.poi_type = filter_type)
     ORDER BY ST_Distance(p.geom, origin), p.id;
END;
$$;
"""

REFRESH_SPATIAL_FEATURES_SQL = """
-- Tính lại listing_spatial_features cho mọi tin có tọa độ. Trả về số tin đã tính.
--   SELECT refresh_spatial_features();
CREATE OR REPLACE FUNCTION refresh_spatial_features()
RETURNS integer
LANGUAGE plpgsql
AS $$
DECLARE refreshed integer;
BEGIN
    -- Tin đã mất tọa độ thì xóa đặc trưng cũ
    DELETE FROM listing_spatial_features f
     USING listings l
     WHERE l.listing_id = f.listing_id AND l.geom IS NULL;

    INSERT INTO listing_spatial_features AS f (
        listing_id,
        school_count_1km, hospital_count_1km, market_count_1km,
        school_count_3km, hospital_count_3km, market_count_3km,
        nearest_school_name, nearest_school_m,
        nearest_hospital_name, nearest_hospital_m,
        nearest_market_name, nearest_market_m,
        computed_at)
    SELECT l.listing_id,
           c.school_1km, c.hospital_1km, c.market_1km,
           c.school_3km, c.hospital_3km, c.market_3km,
           sn.name, sn.distance_m,
           hn.name, hn.distance_m,
           mn.name, mn.distance_m,
           now()
      FROM listings l
      -- Đếm POI từng loại trong 3 km, trong đó bao nhiêu trong 1 km.
      CROSS JOIN LATERAL (
            SELECT count(*) FILTER (WHERE p.poi_type = 'truong_hoc') AS school_3km,
                   count(*) FILTER (WHERE p.poi_type = 'benh_vien')  AS hospital_3km,
                   count(*) FILTER (WHERE p.poi_type = 'cho')        AS market_3km,
                   count(*) FILTER (WHERE p.poi_type = 'truong_hoc'
                                    AND ST_DWithin(p.geom, l.geom, 1000)) AS school_1km,
                   count(*) FILTER (WHERE p.poi_type = 'benh_vien'
                                    AND ST_DWithin(p.geom, l.geom, 1000)) AS hospital_1km,
                   count(*) FILTER (WHERE p.poi_type = 'cho'
                                    AND ST_DWithin(p.geom, l.geom, 1000)) AS market_1km
              FROM pois p
             WHERE ST_DWithin(p.geom, l.geom, 3000)) c
      -- POI gần nhất từng loại (không giới hạn bán kính), dùng GiST index qua toán tử <->;
      -- p.id phá hòa khi hai POI cách bằng nhau để kết quả tất định.
      LEFT JOIN LATERAL (
            SELECT p.name, ST_Distance(p.geom, l.geom) AS distance_m
              FROM pois p WHERE p.poi_type = 'truong_hoc' AND p.geom IS NOT NULL
             ORDER BY p.geom <-> l.geom, p.id LIMIT 1) sn ON true
      LEFT JOIN LATERAL (
            SELECT p.name, ST_Distance(p.geom, l.geom) AS distance_m
              FROM pois p WHERE p.poi_type = 'benh_vien' AND p.geom IS NOT NULL
             ORDER BY p.geom <-> l.geom, p.id LIMIT 1) hn ON true
      LEFT JOIN LATERAL (
            SELECT p.name, ST_Distance(p.geom, l.geom) AS distance_m
              FROM pois p WHERE p.poi_type = 'cho' AND p.geom IS NOT NULL
             ORDER BY p.geom <-> l.geom, p.id LIMIT 1) mn ON true
     WHERE l.geom IS NOT NULL
    ON CONFLICT (listing_id) DO UPDATE SET
        school_count_1km      = EXCLUDED.school_count_1km,
        hospital_count_1km    = EXCLUDED.hospital_count_1km,
        market_count_1km      = EXCLUDED.market_count_1km,
        school_count_3km      = EXCLUDED.school_count_3km,
        hospital_count_3km    = EXCLUDED.hospital_count_3km,
        market_count_3km      = EXCLUDED.market_count_3km,
        nearest_school_name   = EXCLUDED.nearest_school_name,
        nearest_school_m      = EXCLUDED.nearest_school_m,
        nearest_hospital_name = EXCLUDED.nearest_hospital_name,
        nearest_hospital_m    = EXCLUDED.nearest_hospital_m,
        nearest_market_name   = EXCLUDED.nearest_market_name,
        nearest_market_m      = EXCLUDED.nearest_market_m,
        computed_at           = EXCLUDED.computed_at;
    GET DIAGNOSTICS refreshed = ROW_COUNT;
    RETURN refreshed;
END;
$$;
"""

REFRESH_LISTING_ADDRESS_IDS_SQL = """
-- Điền old_district_id / old_ward_id / new_ward_id của listings từ cột chữ, chỉ khi khớp
-- chính xác ĐÚNG 1 dòng (HAVING count(*) = 1), còn lại NULL. So sánh sau normalize(NFC)
-- vì cùng chữ có thể lưu dạng tổ hợp hoặc dựng sẵn. Tên đầy đủ phường = prefix + ' ' + name
-- (prefix rỗng thì chỉ name). Trả về số tin có FK thay đổi.
--   SELECT refresh_listing_address_ids();
CREATE OR REPLACE FUNCTION refresh_listing_address_ids()
RETURNS integer
LANGUAGE plpgsql
AS $$
DECLARE updated integer;
BEGIN
    UPDATE listings l
       SET old_district_id = m.old_district_id,
           old_ward_id     = m.old_ward_id,
           new_ward_id     = m.new_ward_id
      FROM (SELECT x.listing_id, od.id AS old_district_id, ow.id AS old_ward_id,
                   nw.id AS new_ward_id
              FROM listings x
              LEFT JOIN LATERAL (
                    SELECT min(d.id) AS id FROM districts_old d
                     WHERE d.province_code = 'SG'
                       AND normalize(d.name, NFC) = normalize(x.district_old, NFC)
                    HAVING count(*) = 1) od ON true
              LEFT JOIN LATERAL (
                    SELECT min(w.id) AS id FROM wards_old w
                     WHERE w.district_id = od.id
                       AND normalize(concat_ws(' ', nullif(w.prefix, ''), w.name), NFC)
                           = normalize(x.old_ward, NFC)
                    HAVING count(*) = 1) ow ON true
              LEFT JOIN LATERAL (
                    SELECT min(w.id) AS id FROM wards_new w
                     WHERE w.province_code = 'SG'
                       AND normalize(concat_ws(' ', nullif(w.prefix, ''), w.name), NFC)
                           = normalize(x.new_ward, NFC)
                    HAVING count(*) = 1) nw ON true) m
     WHERE l.listing_id = m.listing_id
       AND (l.old_district_id, l.old_ward_id, l.new_ward_id)
           IS DISTINCT FROM (m.old_district_id, m.old_ward_id, m.new_ward_id);
    GET DIAGNOSTICS updated = ROW_COUNT;
    RETURN updated;
END;
$$;
"""


def upgrade() -> None:
    for extension in EXTENSIONS:
        op.execute(f"CREATE EXTENSION IF NOT EXISTS {extension}")

    # ------------------------------------------------------------ địa chỉ
    for table in ("provinces_old", "provinces_new"):
        op.create_table(
            table,
            sa.Column("code", sa.Text(), nullable=False),
            sa.Column("name", sa.Text(), nullable=False),
            sa.Column("alias", sa.Text(), nullable=False),
            sa.PrimaryKeyConstraint("code", name=f"{table}_pkey"),
        )
    # Bốn bảng con cùng dạng: id (ID batdongsan) + khóa cha + name/prefix/alias.
    # Bảng đường có PK (id, khóa cha) vì cùng streetId lặp lại ở nhiều quận/phường.
    for table, parent_column, parent, composite_pk in (
        ("districts_old", "province_code", "provinces_old.code", False),
        ("wards_old", "district_id", "districts_old.id", False),
        ("streets_old", "district_id", "districts_old.id", True),
        ("wards_new", "province_code", "provinces_new.code", False),
        ("streets_new", "ward_id", "wards_new.id", True),
    ):
        parent_type = sa.Text() if parent_column == "province_code" else sa.Integer()
        pk_columns = ("id", parent_column) if composite_pk else ("id",)
        op.create_table(
            table,
            sa.Column("id", sa.Integer(), autoincrement=False, nullable=False),
            sa.Column(parent_column, parent_type, nullable=False),
            sa.Column("name", sa.Text(), nullable=False),
            sa.Column("prefix", sa.Text(), nullable=False),
            sa.Column("alias", sa.Text(), nullable=False),
            sa.ForeignKeyConstraint(
                [parent_column], [parent], name=f"{table}_{parent_column}_fkey"
            ),
            sa.PrimaryKeyConstraint(*pk_columns, name=f"{table}_pkey"),
        )
        op.create_index(f"{table}_{parent_column}_idx", table, [parent_column])

    op.create_table(
        "ward_mappings",
        sa.Column("old_ward_id", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("new_ward_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["old_ward_id"], ["wards_old.id"], name="ward_mappings_old_ward_id_fkey"
        ),
        sa.ForeignKeyConstraint(
            ["new_ward_id"], ["wards_new.id"], name="ward_mappings_new_ward_id_fkey"
        ),
        sa.PrimaryKeyConstraint("old_ward_id", name="ward_mappings_pkey"),
    )
    op.create_index("ward_mappings_new_ward_id_idx", "ward_mappings", ["new_ward_id"])

    op.create_table(
        "district_label",
        sa.Column("model_version", sa.Text(), nullable=False),
        sa.Column("label", sa.SmallInteger(), nullable=False),
        sa.Column("district_id", sa.Integer(), nullable=False),
        sa.CheckConstraint("label >= 0", name="district_label_label_check"),
        sa.ForeignKeyConstraint(
            ["district_id"], ["districts_old.id"], name="district_label_district_id_fkey"
        ),
        sa.PrimaryKeyConstraint("model_version", "label", name="district_label_pkey"),
        sa.UniqueConstraint(
            "model_version", "district_id", name="district_label_model_version_district_id_key"
        ),
    )

    # ------------------------------------------------------------ POI
    op.create_table(
        "pois",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("poi_type", sa.Text(), nullable=False),
        sa.Column("poi_subtype", sa.Text(), nullable=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("address_old", sa.Text(), nullable=True),
        sa.Column("address_new", sa.Text(), nullable=True),
        sa.Column("latitude", sa.Double(), nullable=True),
        sa.Column("longitude", sa.Double(), nullable=True),
        sa.Column("ownership", sa.Text(), nullable=True),
        sa.Column("school_level_codes", sa.Text(), nullable=True),
        sa.Column(
            "geom",
            GEOGRAPHY_POINT,
            sa.Computed(GEOM_SQL, persisted=True),
            nullable=True,
        ),
        sa.CheckConstraint(
            "poi_type IN ('truong_hoc', 'benh_vien', 'cho')", name="pois_poi_type_check"
        ),
        sa.CheckConstraint("(latitude IS NULL) = (longitude IS NULL)", name="pois_check"),
        sa.CheckConstraint("latitude >= -90 AND latitude <= 90", name="pois_latitude_check"),
        sa.CheckConstraint(
            "longitude >= -180 AND longitude <= 180", name="pois_longitude_check"
        ),
        sa.PrimaryKeyConstraint("id", name="pois_pkey"),
    )
    op.create_index("pois_geom_gist", "pois", ["geom"], postgresql_using="gist")
    op.create_index("pois_poi_type_idx", "pois", ["poi_type"])

    # ------------------------------------------------------------ tin đăng
    op.create_table(
        "listings",
        sa.Column("listing_id", sa.Text(), nullable=False),
        sa.Column("listing_url", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("transaction_type", sa.Text(), nullable=False),
        sa.Column("property_type", sa.Text(), nullable=True),
        sa.Column("price", sa.Double(), nullable=False),
        sa.Column("price_per_m2", sa.Double(), nullable=True),
        sa.Column("area", sa.Double(), nullable=False),
        sa.Column("frontage", sa.Double(), nullable=True),
        sa.Column("bedrooms", sa.Integer(), nullable=True),
        sa.Column("bathrooms", sa.Integer(), nullable=True),
        sa.Column("road_width", sa.Double(), nullable=True),
        sa.Column("floors", sa.Integer(), nullable=True),
        sa.Column("legal", sa.Text(), nullable=True),
        sa.Column("legal_group", sa.Text(), nullable=True),
        sa.Column("interior", sa.Text(), nullable=True),
        sa.Column("province_old", sa.Text(), nullable=True),
        sa.Column("district_old", sa.Text(), nullable=True),
        sa.Column("old_ward", sa.Text(), nullable=True),
        sa.Column("old_address", sa.Text(), nullable=True),
        sa.Column("old_address_detail", sa.Text(), nullable=True),
        sa.Column("new_ward", sa.Text(), nullable=True),
        sa.Column("new_city", sa.Text(), nullable=True),
        sa.Column("new_address", sa.Text(), nullable=True),
        sa.Column("old_district_id", sa.Integer(), nullable=True),
        sa.Column("old_ward_id", sa.Integer(), nullable=True),
        sa.Column("new_ward_id", sa.Integer(), nullable=True),
        sa.Column("latitude", sa.Double(), nullable=True),
        sa.Column("longitude", sa.Double(), nullable=True),
        sa.Column("posted_at", sa.Date(), nullable=True),
        sa.Column("expired_at", sa.Date(), nullable=True),
        sa.Column(
            "quality_flags",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'::text[]"),
            nullable=False,
        ),
        sa.Column(
            "first_loaded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "geom",
            GEOGRAPHY_POINT,
            sa.Computed(GEOM_SQL, persisted=True),
            nullable=True,
        ),
        sa.CheckConstraint("price > 0", name="listings_price_check"),
        sa.CheckConstraint("area > 0", name="listings_area_check"),
        sa.CheckConstraint("(latitude IS NULL) = (longitude IS NULL)", name="listings_check"),
        sa.ForeignKeyConstraint(
            ["old_district_id"], ["districts_old.id"], name="listings_old_district_id_fkey"
        ),
        sa.ForeignKeyConstraint(
            ["old_ward_id"], ["wards_old.id"], name="listings_old_ward_id_fkey"
        ),
        sa.ForeignKeyConstraint(
            ["new_ward_id"], ["wards_new.id"], name="listings_new_ward_id_fkey"
        ),
        sa.PrimaryKeyConstraint("listing_id", name="listings_pkey"),
    )
    op.create_index("listings_geom_gist", "listings", ["geom"], postgresql_using="gist")
    op.create_index(
        "listings_filter_idx", "listings", ["property_type", "old_district_id", "price"]
    )
    op.create_index("listings_expired_at_idx", "listings", ["expired_at"])
    for column in ("old_district_id", "old_ward_id", "new_ward_id"):
        op.create_index(f"listings_{column}_idx", "listings", [column])

    op.create_table(
        "listing_spatial_features",
        sa.Column("listing_id", sa.Text(), nullable=False),
        sa.Column("school_count_1km", sa.Integer(), nullable=False),
        sa.Column("hospital_count_1km", sa.Integer(), nullable=False),
        sa.Column("market_count_1km", sa.Integer(), nullable=False),
        sa.Column("school_count_3km", sa.Integer(), nullable=False),
        sa.Column("hospital_count_3km", sa.Integer(), nullable=False),
        sa.Column("market_count_3km", sa.Integer(), nullable=False),
        sa.Column("nearest_school_name", sa.Text(), nullable=True),
        sa.Column("nearest_school_m", sa.Double(), nullable=True),
        sa.Column("nearest_hospital_name", sa.Text(), nullable=True),
        sa.Column("nearest_hospital_m", sa.Double(), nullable=True),
        sa.Column("nearest_market_name", sa.Text(), nullable=True),
        sa.Column("nearest_market_m", sa.Double(), nullable=True),
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["listing_id"],
            ["listings.listing_id"],
            name="listing_spatial_features_listing_id_fkey",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("listing_id", name="listing_spatial_features_pkey"),
    )

    op.create_table(
        "listing_embeddings",
        sa.Column("listing_id", sa.Text(), nullable=False),
        sa.Column("model_name", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.Text(), nullable=False),
        sa.Column("embedding_text", sa.Text(), nullable=False),
        sa.Column("rag_document", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(1024), nullable=False),
        sa.Column(
            "embedded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["listing_id"],
            ["listings.listing_id"],
            name="listing_embeddings_listing_id_fkey",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("listing_id", name="listing_embeddings_pkey"),
    )

    # ------------------------------------------------------------ function
    # exec_driver_sql: gửi nguyên văn cho Postgres, SQLAlchemy không phân tích dấu ':'
    op.get_bind().exec_driver_sql(NEARBY_SQL)
    op.get_bind().exec_driver_sql(REFRESH_SPATIAL_FEATURES_SQL)
    op.get_bind().exec_driver_sql(REFRESH_LISTING_ADDRESS_IDS_SQL)


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS refresh_listing_address_ids()")
    op.execute("DROP FUNCTION IF EXISTS refresh_spatial_features()")
    op.execute(
        "DROP FUNCTION IF EXISTS nearby(double precision, double precision, double precision, text)"
    )
    # Bảng con trước, bảng cha sau; extension giữ lại vì có thể DB khác đang dùng.
    for table in (
        "listing_embeddings",
        "listing_spatial_features",
        "listings",
        "pois",
        "district_label",
        "ward_mappings",
        "streets_new",
        "wards_new",
        "provinces_new",
        "streets_old",
        "wards_old",
        "districts_old",
        "provinces_old",
    ):
        op.drop_table(table)
