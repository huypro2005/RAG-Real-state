-- Bảng tin đăng và RAG trong database housing. Chạy lại an toàn: không DROP, không xóa dữ liệu.
-- Cần sẵn schema amenities (POI) do tools/import_pois.py tạo.

CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS vector;

CREATE SCHEMA IF NOT EXISTS listing;
CREATE SCHEMA IF NOT EXISTS rag;

-- Tin đã qua ListingCleaner. Đơn vị giữ như crawler: price (triệu VND), price_per_m2 (triệu/m²).
CREATE TABLE IF NOT EXISTS listing.listings (
    listing_id          text PRIMARY KEY,
    listing_url         text NOT NULL,
    title               text NOT NULL,
    description         text,
    transaction_type    text NOT NULL,
    property_type       text,
    price               double precision NOT NULL CHECK (price > 0),
    price_per_m2        double precision,
    area                double precision NOT NULL CHECK (area > 0),
    frontage            double precision,
    bedrooms            integer,
    bathrooms           integer,
    road_width          double precision,
    floors              integer,
    legal               text,
    legal_group         text,
    interior            text,
    province_old        text,
    district_old        text,
    old_ward            text,
    old_address         text,
    old_address_detail  text,
    new_ward            text,
    new_city            text,
    new_address         text,
    latitude            double precision,
    longitude           double precision,
    posted_at           date,
    expired_at          date,
    quality_flags       text[] NOT NULL DEFAULT '{}',
    raw_record          jsonb NOT NULL,
    source_file         text NOT NULL,
    first_loaded_at     timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),
    geom geography(Point, 4326) GENERATED ALWAYS AS (
        CASE WHEN latitude IS NOT NULL AND longitude IS NOT NULL
             THEN ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)::geography END
    ) STORED,
    CHECK ((latitude IS NULL) = (longitude IS NULL))
);
CREATE INDEX IF NOT EXISTS listings_geom_gist ON listing.listings USING gist (geom);
CREATE INDEX IF NOT EXISTS listings_filter_idx
    ON listing.listings (property_type, district_old, price);
CREATE INDEX IF NOT EXISTS listings_expired_at_idx ON listing.listings (expired_at);

-- 6 biến đếm POI cho Model B và thông tin POI gần nhất cho document RAG.
CREATE TABLE IF NOT EXISTS listing.listing_spatial_features (
    listing_id              text PRIMARY KEY REFERENCES listing.listings ON DELETE CASCADE,
    school_count_1km        integer NOT NULL,
    hospital_count_1km      integer NOT NULL,
    market_count_1km        integer NOT NULL,
    school_count_3km        integer NOT NULL,
    hospital_count_3km      integer NOT NULL,
    market_count_3km        integer NOT NULL,
    nearest_school_name     text,
    nearest_school_m        double precision,
    nearest_hospital_name   text,
    nearest_hospital_m      double precision,
    nearest_market_name     text,
    nearest_market_m        double precision,
    computed_at             timestamptz NOT NULL DEFAULT now()
);

-- Tính lại đặc trưng không gian cho mọi tin có tọa độ; xóa dòng của tin đã mất tọa độ.
-- Trả về số tin được tính.
CREATE OR REPLACE FUNCTION listing.refresh_spatial_features() RETURNS integer
LANGUAGE plpgsql AS $$
DECLARE
    refreshed integer;
BEGIN
    DELETE FROM listing.listing_spatial_features f
     USING listing.listings l
     WHERE l.listing_id = f.listing_id AND l.geom IS NULL;

    INSERT INTO listing.listing_spatial_features AS f (
        listing_id,
        school_count_1km, hospital_count_1km, market_count_1km,
        school_count_3km, hospital_count_3km, market_count_3km,
        nearest_school_name, nearest_school_m,
        nearest_hospital_name, nearest_hospital_m,
        nearest_market_name, nearest_market_m,
        computed_at)
    SELECT l.listing_id,
           sc.count_1km, hc.count_1km, mc.count_1km,
           sc.count_3km, hc.count_3km, mc.count_3km,
           sn.name, sn.distance_m,
           hn.name, hn.distance_m,
           mn.name, mn.distance_m,
           now()
      FROM listing.listings l
      -- Đếm POI trong 3 km, trong đó bao nhiêu POI trong 1 km.
      CROSS JOIN LATERAL (
            SELECT count(*) FILTER (WHERE ST_DWithin(p.geom, l.geom, 1000)) AS count_1km,
                   count(*) AS count_3km
              FROM amenities.poi_schools p WHERE ST_DWithin(p.geom, l.geom, 3000)) sc
      CROSS JOIN LATERAL (
            SELECT count(*) FILTER (WHERE ST_DWithin(p.geom, l.geom, 1000)) AS count_1km,
                   count(*) AS count_3km
              FROM amenities.poi_hospitals p WHERE ST_DWithin(p.geom, l.geom, 3000)) hc
      CROSS JOIN LATERAL (
            SELECT count(*) FILTER (WHERE ST_DWithin(p.geom, l.geom, 1000)) AS count_1km,
                   count(*) AS count_3km
              FROM amenities.poi_markets p WHERE ST_DWithin(p.geom, l.geom, 3000)) mc
      -- POI gần nhất (không giới hạn bán kính), dùng GiST index qua toán tử <->.
      LEFT JOIN LATERAL (
            SELECT p.name, ST_Distance(p.geom, l.geom) AS distance_m
              FROM amenities.poi_schools p WHERE p.geom IS NOT NULL
             ORDER BY p.geom <-> l.geom LIMIT 1) sn ON true
      LEFT JOIN LATERAL (
            SELECT p.name, ST_Distance(p.geom, l.geom) AS distance_m
              FROM amenities.poi_hospitals p WHERE p.geom IS NOT NULL
             ORDER BY p.geom <-> l.geom LIMIT 1) hn ON true
      LEFT JOIN LATERAL (
            SELECT p.name, ST_Distance(p.geom, l.geom) AS distance_m
              FROM amenities.poi_markets p WHERE p.geom IS NOT NULL
             ORDER BY p.geom <-> l.geom LIMIT 1) mn ON true
     WHERE l.geom IS NOT NULL
    ON CONFLICT (listing_id) DO UPDATE SET
        school_count_1km = EXCLUDED.school_count_1km,
        hospital_count_1km = EXCLUDED.hospital_count_1km,
        market_count_1km = EXCLUDED.market_count_1km,
        school_count_3km = EXCLUDED.school_count_3km,
        hospital_count_3km = EXCLUDED.hospital_count_3km,
        market_count_3km = EXCLUDED.market_count_3km,
        nearest_school_name = EXCLUDED.nearest_school_name,
        nearest_school_m = EXCLUDED.nearest_school_m,
        nearest_hospital_name = EXCLUDED.nearest_hospital_name,
        nearest_hospital_m = EXCLUDED.nearest_hospital_m,
        nearest_market_name = EXCLUDED.nearest_market_name,
        nearest_market_m = EXCLUDED.nearest_market_m,
        computed_at = EXCLUDED.computed_at;
    GET DIAGNOSTICS refreshed = ROW_COUNT;
    RETURN refreshed;
END;
$$;

-- Corpus RAG: embedding_text là phần nhúng vector (ngữ nghĩa), rag_document là đoạn đưa cho LLM.
-- content_hash = sha256(model_name + embedding_text): chỉ embed lại khi nội dung hoặc model đổi.
-- Chưa tạo HNSW index: ~8 nghìn vector quét tuần tự chỉ vài ms, và HNSW kết hợp WHERE chặt có
-- thể trả thiếu kết quả. Khi dữ liệu lớn hơn nhiều mới thêm:
--   CREATE INDEX ON rag.listing_embeddings USING hnsw (embedding vector_cosine_ops);
CREATE TABLE IF NOT EXISTS rag.listing_embeddings (
    listing_id      text PRIMARY KEY REFERENCES listing.listings ON DELETE CASCADE,
    model_name      text NOT NULL,
    content_hash    text NOT NULL,
    embedding_text  text NOT NULL,
    rag_document    text NOT NULL,
    embedding       vector(1024) NOT NULL,
    embedded_at     timestamptz NOT NULL DEFAULT now()
);
