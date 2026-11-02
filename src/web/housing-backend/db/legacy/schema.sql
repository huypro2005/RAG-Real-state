-- =====================================================================
-- housing database — mọi bảng nằm trong schema mặc định (public)
-- nên tên bảng không cần tiền tố schema.
--
-- Tạo từ cấu trúc DB thật (dump pg_dump 18.6), bỏ 5 schema riêng
-- (admin, amenities, listing, ml, rag). Tên bảng, cột, constraint, index
-- giữ nguyên như DB cũ để code import/pipeline không phải đổi tên.
--
-- Dùng cho DB MỚI:  psql -d housing -v ON_ERROR_STOP=1 -f db/schema.sql
-- DB ĐANG CÓ dữ liệu ở 5 schema cũ -> dùng db/move_to_public.sql
-- =====================================================================

CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS unaccent;


-- ---------------------------------------------------------------------
-- 1. ĐƠN VỊ HÀNH CHÍNH (trước đây: admin.*)
-- ---------------------------------------------------------------------

-- Tỉnh / quận / phường của cả bộ cũ (legacy_2025) và bộ mới (from_2025).
-- Bộ mới không còn cấp quận. Chỉ cấp tỉnh mới không có parent.
CREATE TABLE unit (
    id          bigint GENERATED ALWAYS AS IDENTITY,
    version     text   NOT NULL,
    level       text   NOT NULL,
    code        text   NOT NULL,
    name        text   NOT NULL,
    parent_id   bigint,
    source_file text   NOT NULL,
    raw_record  jsonb  NOT NULL,
    CONSTRAINT unit_pkey PRIMARY KEY (id),
    CONSTRAINT unit_version_level_code_key UNIQUE (version, level, code),
    CONSTRAINT unit_parent_id_fkey FOREIGN KEY (parent_id) REFERENCES unit(id),
    CONSTRAINT unit_version_check CHECK (version = ANY (ARRAY['legacy_2025', 'from_2025'])),
    CONSTRAINT unit_level_check   CHECK (level = ANY (ARRAY['province', 'district', 'ward'])),
    CONSTRAINT unit_check  CHECK (NOT (version = 'from_2025' AND level = 'district')),
    CONSTRAINT unit_check1 CHECK ((level = 'province') = (parent_id IS NULL))
);
CREATE INDEX unit_parent_idx ON unit USING btree (parent_id);

-- Phường cũ -> phường mới (sáp nhập: nhiều - nhiều)
CREATE TABLE ward_transition (
    old_ward_id bigint NOT NULL,
    new_ward_id bigint NOT NULL,
    source_file text   NOT NULL,
    raw_record  jsonb  NOT NULL,
    CONSTRAINT ward_transition_pkey PRIMARY KEY (old_ward_id, new_ward_id),
    CONSTRAINT ward_transition_old_ward_id_fkey FOREIGN KEY (old_ward_id) REFERENCES unit(id),
    CONSTRAINT ward_transition_new_ward_id_fkey FOREIGN KEY (new_ward_id) REFERENCES unit(id)
);


-- ---------------------------------------------------------------------
-- 2. NHÃN QUẬN CHO MODEL DỰ ĐOÁN GIÁ (trước đây: ml.*)
-- ---------------------------------------------------------------------

CREATE TABLE district_label (
    model_version text     NOT NULL,
    label         smallint NOT NULL,
    district_name text     NOT NULL,
    CONSTRAINT district_label_pkey PRIMARY KEY (model_version, label),
    CONSTRAINT district_label_model_version_district_name_key UNIQUE (model_version, district_name),
    CONSTRAINT district_label_label_check CHECK (label >= 0 AND label <= 23)
);

CREATE TABLE district_link (
    admin_district_id bigint   NOT NULL,
    model_version     text     NOT NULL,
    label             smallint NOT NULL,
    evidence          text     NOT NULL,
    CONSTRAINT district_link_pkey PRIMARY KEY (admin_district_id, model_version),
    CONSTRAINT district_link_admin_district_id_fkey
        FOREIGN KEY (admin_district_id) REFERENCES unit(id),
    CONSTRAINT district_link_model_version_label_fkey
        FOREIGN KEY (model_version, label) REFERENCES district_label(model_version, label)
);


-- ---------------------------------------------------------------------
-- 3. TIỆN ÍCH / POI (trước đây: amenities.*)
--    3 bảng có chung 18 cột đầu + geom; khác nhau ở vài cột lấy từ raw_record.
-- ---------------------------------------------------------------------

CREATE TABLE poi_schools (
    poi_id          text   NOT NULL,
    poi_type        text   NOT NULL,
    poi_subtype     text,
    name            text   NOT NULL,
    address_old     text,
    address_new     text,
    old_province_id bigint,
    old_district_id bigint,
    old_ward_id     bigint,
    new_province_id bigint,
    new_ward_id     bigint,
    latitude        double precision,
    longitude       double precision,
    mapping_status  jsonb  NOT NULL,
    source_file     text   NOT NULL,
    source_sha256   text   NOT NULL,
    raw_record      jsonb  NOT NULL,
    imported_at     timestamp with time zone DEFAULT now() NOT NULL,
    -- cột tự tính từ raw_record
    campus_name            text    GENERATED ALWAYS AS (NULLIF(raw_record ->> 'campus_name', '')) STORED,
    school_level_codes     text    GENERATED ALWAYS AS (NULLIF(raw_record ->> 'school_level_codes', '')) STORED,
    ownership              text    GENERATED ALWAYS AS (NULLIF(raw_record ->> 'ownership', '')) STORED,
    student_count          integer GENERATED ALWAYS AS ((NULLIF(raw_record ->> 'student_count', ''))::integer) STORED,
    old_address_confidence text    GENERATED ALWAYS AS (NULLIF(raw_record ->> 'old_address_confidence', '')) STORED,
    geom geography(Point, 4326) GENERATED ALWAYS AS (
        CASE WHEN longitude IS NOT NULL AND latitude IS NOT NULL
             THEN st_setsrid(st_makepoint(longitude, latitude), 4326)::geography
             ELSE NULL::geography
        END) STORED,
    CONSTRAINT poi_schools_pkey PRIMARY KEY (poi_id),
    CONSTRAINT poi_schools_poi_type_check  CHECK (poi_type = 'truong_hoc'),
    CONSTRAINT poi_schools_check           CHECK ((latitude IS NULL) = (longitude IS NULL)),
    CONSTRAINT poi_schools_latitude_check  CHECK (latitude >= -90 AND latitude <= 90),
    CONSTRAINT poi_schools_longitude_check CHECK (longitude >= -180 AND longitude <= 180),
    CONSTRAINT poi_schools_old_province_id_fkey FOREIGN KEY (old_province_id) REFERENCES unit(id),
    CONSTRAINT poi_schools_old_district_id_fkey FOREIGN KEY (old_district_id) REFERENCES unit(id),
    CONSTRAINT poi_schools_old_ward_id_fkey     FOREIGN KEY (old_ward_id)     REFERENCES unit(id),
    CONSTRAINT poi_schools_new_province_id_fkey FOREIGN KEY (new_province_id) REFERENCES unit(id),
    CONSTRAINT poi_schools_new_ward_id_fkey     FOREIGN KEY (new_ward_id)     REFERENCES unit(id)
);
CREATE INDEX poi_schools_geom_gist        ON poi_schools USING gist (geom);
CREATE INDEX poi_schools_old_district_idx ON poi_schools USING btree (old_district_id);
CREATE INDEX poi_schools_new_ward_idx     ON poi_schools USING btree (new_ward_id);

CREATE TABLE poi_hospitals (
    poi_id          text   NOT NULL,
    poi_type        text   NOT NULL,
    poi_subtype     text,
    name            text   NOT NULL,
    address_old     text,
    address_new     text,
    old_province_id bigint,
    old_district_id bigint,
    old_ward_id     bigint,
    new_province_id bigint,
    new_ward_id     bigint,
    latitude        double precision,
    longitude       double precision,
    mapping_status  jsonb  NOT NULL,
    source_file     text   NOT NULL,
    source_sha256   text   NOT NULL,
    raw_record      jsonb  NOT NULL,
    imported_at     timestamp with time zone DEFAULT now() NOT NULL,
    ownership text GENERATED ALWAYS AS (NULLIF(raw_record ->> 'ownership', '')) STORED,
    geom geography(Point, 4326) GENERATED ALWAYS AS (
        CASE WHEN longitude IS NOT NULL AND latitude IS NOT NULL
             THEN st_setsrid(st_makepoint(longitude, latitude), 4326)::geography
             ELSE NULL::geography
        END) STORED,
    CONSTRAINT poi_hospitals_pkey PRIMARY KEY (poi_id),
    CONSTRAINT poi_hospitals_poi_type_check  CHECK (poi_type = 'benh_vien'),
    CONSTRAINT poi_hospitals_check           CHECK ((latitude IS NULL) = (longitude IS NULL)),
    CONSTRAINT poi_hospitals_latitude_check  CHECK (latitude >= -90 AND latitude <= 90),
    CONSTRAINT poi_hospitals_longitude_check CHECK (longitude >= -180 AND longitude <= 180),
    CONSTRAINT poi_hospitals_old_province_id_fkey FOREIGN KEY (old_province_id) REFERENCES unit(id),
    CONSTRAINT poi_hospitals_old_district_id_fkey FOREIGN KEY (old_district_id) REFERENCES unit(id),
    CONSTRAINT poi_hospitals_old_ward_id_fkey     FOREIGN KEY (old_ward_id)     REFERENCES unit(id),
    CONSTRAINT poi_hospitals_new_province_id_fkey FOREIGN KEY (new_province_id) REFERENCES unit(id),
    CONSTRAINT poi_hospitals_new_ward_id_fkey     FOREIGN KEY (new_ward_id)     REFERENCES unit(id)
);
CREATE INDEX poi_hospitals_geom_gist        ON poi_hospitals USING gist (geom);
CREATE INDEX poi_hospitals_old_district_idx ON poi_hospitals USING btree (old_district_id);
CREATE INDEX poi_hospitals_new_ward_idx     ON poi_hospitals USING btree (new_ward_id);

CREATE TABLE poi_markets (
    poi_id          text   NOT NULL,
    poi_type        text   NOT NULL,
    poi_subtype     text,
    name            text   NOT NULL,
    address_old     text,
    address_new     text,
    old_province_id bigint,
    old_district_id bigint,
    old_ward_id     bigint,
    new_province_id bigint,
    new_ward_id     bigint,
    latitude        double precision,
    longitude       double precision,
    mapping_status  jsonb  NOT NULL,
    source_file     text   NOT NULL,
    source_sha256   text   NOT NULL,
    raw_record      jsonb  NOT NULL,
    imported_at     timestamp with time zone DEFAULT now() NOT NULL,
    manual_review_required boolean GENERATED ALWAYS AS ((NULLIF(raw_record ->> 'manual_review_required', ''))::boolean) STORED,
    geom geography(Point, 4326) GENERATED ALWAYS AS (
        CASE WHEN longitude IS NOT NULL AND latitude IS NOT NULL
             THEN st_setsrid(st_makepoint(longitude, latitude), 4326)::geography
             ELSE NULL::geography
        END) STORED,
    CONSTRAINT poi_markets_pkey PRIMARY KEY (poi_id),
    CONSTRAINT poi_markets_poi_type_check  CHECK (poi_type = 'cho'),
    CONSTRAINT poi_markets_check           CHECK ((latitude IS NULL) = (longitude IS NULL)),
    CONSTRAINT poi_markets_latitude_check  CHECK (latitude >= -90 AND latitude <= 90),
    CONSTRAINT poi_markets_longitude_check CHECK (longitude >= -180 AND longitude <= 180),
    CONSTRAINT poi_markets_old_province_id_fkey FOREIGN KEY (old_province_id) REFERENCES unit(id),
    CONSTRAINT poi_markets_old_district_id_fkey FOREIGN KEY (old_district_id) REFERENCES unit(id),
    CONSTRAINT poi_markets_old_ward_id_fkey     FOREIGN KEY (old_ward_id)     REFERENCES unit(id),
    CONSTRAINT poi_markets_new_province_id_fkey FOREIGN KEY (new_province_id) REFERENCES unit(id),
    CONSTRAINT poi_markets_new_ward_id_fkey     FOREIGN KEY (new_ward_id)     REFERENCES unit(id)
);
CREATE INDEX poi_markets_geom_gist        ON poi_markets USING gist (geom);
CREATE INDEX poi_markets_old_district_idx ON poi_markets USING btree (old_district_id);
CREATE INDEX poi_markets_new_ward_idx     ON poi_markets USING btree (new_ward_id);


-- ---------------------------------------------------------------------
-- 4. TIN ĐĂNG (trước đây: listing.*)
-- ---------------------------------------------------------------------

CREATE TABLE listings (
    listing_id         text NOT NULL,
    listing_url        text NOT NULL,
    title              text NOT NULL,
    description        text,
    transaction_type   text NOT NULL,
    property_type      text,
    price              double precision NOT NULL,
    price_per_m2       double precision,
    area               double precision NOT NULL,
    frontage           double precision,
    bedrooms           integer,
    bathrooms          integer,
    road_width         double precision,
    floors             integer,
    legal              text,
    legal_group        text,
    interior           text,
    province_old       text,
    district_old       text,
    old_ward           text,
    old_address        text,
    old_address_detail text,
    new_ward           text,
    new_city           text,
    new_address        text,
    latitude           double precision,
    longitude          double precision,
    posted_at          date,
    expired_at         date,
    quality_flags      text[] DEFAULT '{}'::text[] NOT NULL,
    raw_record         jsonb NOT NULL,
    source_file        text  NOT NULL,
    first_loaded_at    timestamp with time zone DEFAULT now() NOT NULL,
    updated_at         timestamp with time zone DEFAULT now() NOT NULL,
    geom geography(Point, 4326) GENERATED ALWAYS AS (
        CASE WHEN latitude IS NOT NULL AND longitude IS NOT NULL
             THEN st_setsrid(st_makepoint(longitude, latitude), 4326)::geography
             ELSE NULL::geography
        END) STORED,
    CONSTRAINT listings_pkey PRIMARY KEY (listing_id),
    CONSTRAINT listings_price_check CHECK (price > 0),
    CONSTRAINT listings_area_check  CHECK (area > 0),
    CONSTRAINT listings_check       CHECK ((latitude IS NULL) = (longitude IS NULL))
);
CREATE INDEX listings_geom_gist      ON listings USING gist (geom);
CREATE INDEX listings_filter_idx     ON listings USING btree (property_type, district_old, price);
CREATE INDEX listings_expired_at_idx ON listings USING btree (expired_at);

-- Đặc trưng không gian của từng tin (1 tin : 0..1 dòng), do refresh_spatial_features() ghi
CREATE TABLE listing_spatial_features (
    listing_id            text    NOT NULL,
    school_count_1km      integer NOT NULL,
    hospital_count_1km    integer NOT NULL,
    market_count_1km      integer NOT NULL,
    school_count_3km      integer NOT NULL,
    hospital_count_3km    integer NOT NULL,
    market_count_3km      integer NOT NULL,
    nearest_school_name   text,
    nearest_school_m      double precision,
    nearest_hospital_name text,
    nearest_hospital_m    double precision,
    nearest_market_name   text,
    nearest_market_m      double precision,
    computed_at           timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT listing_spatial_features_pkey PRIMARY KEY (listing_id),
    CONSTRAINT listing_spatial_features_listing_id_fkey
        FOREIGN KEY (listing_id) REFERENCES listings(listing_id) ON DELETE CASCADE
);


-- ---------------------------------------------------------------------
-- 5. EMBEDDING CHO RAG (trước đây: rag.*)
-- ---------------------------------------------------------------------

CREATE TABLE listing_embeddings (
    listing_id     text NOT NULL,
    model_name     text NOT NULL,
    content_hash   text NOT NULL,
    embedding_text text NOT NULL,
    rag_document   text NOT NULL,
    embedding      vector(1024) NOT NULL,
    embedded_at    timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT listing_embeddings_pkey PRIMARY KEY (listing_id),
    CONSTRAINT listing_embeddings_listing_id_fkey
        FOREIGN KEY (listing_id) REFERENCES listings(listing_id) ON DELETE CASCADE
);


-- ---------------------------------------------------------------------
-- 6. VIEW
-- ---------------------------------------------------------------------

-- Gộp 3 bảng POI thành một
CREATE VIEW housing_poi AS
    SELECT poi_id, poi_type, poi_subtype, name, address_old, address_new,
           old_province_id, old_district_id, old_ward_id, new_province_id, new_ward_id,
           latitude, longitude, mapping_status, source_file, source_sha256, raw_record,
           imported_at, geom
      FROM poi_schools
    UNION ALL
    SELECT poi_id, poi_type, poi_subtype, name, address_old, address_new,
           old_province_id, old_district_id, old_ward_id, new_province_id, new_ward_id,
           latitude, longitude, mapping_status, source_file, source_sha256, raw_record,
           imported_at, geom
      FROM poi_hospitals
    UNION ALL
    SELECT poi_id, poi_type, poi_subtype, name, address_old, address_new,
           old_province_id, old_district_id, old_ward_id, new_province_id, new_ward_id,
           latitude, longitude, mapping_status, source_file, source_sha256, raw_record,
           imported_at, geom
      FROM poi_markets;

-- Mỗi POI kèm nhãn quận của model 'hcm_24_user_v1'
CREATE VIEW poi_district_features AS
    SELECT p.poi_id,
           p.poi_type,
           p.name,
           p.old_district_id,
           l.label AS district_label,
           CASE
               WHEN l.label IS NOT NULL THEN 'matched_district_name'
               WHEN u.name = 'Thành phố Thủ Đức' THEN 'ambiguous_pre_2021_district'
               ELSE 'unresolved'
           END AS label_status,
           p.mapping_status,
           p.raw_record ->> 'old_address_confidence' AS old_address_confidence,
           p.raw_record ->> 'geocode_confidence'     AS geocode_confidence,
           p.raw_record ->> 'manual_review_required' AS manual_review_required
      FROM housing_poi p
      LEFT JOIN unit u          ON u.id = p.old_district_id
      LEFT JOIN district_link l ON l.admin_district_id = p.old_district_id
                                      AND l.model_version = 'hcm_24_user_v1';


-- ---------------------------------------------------------------------
-- 7. FUNCTION
-- ---------------------------------------------------------------------

-- Viết riêng trong functions.sql để move_to_public.sql dùng lại.
-- \ir = include đường dẫn tương đối theo file này (lệnh của psql).
\ir functions.sql
