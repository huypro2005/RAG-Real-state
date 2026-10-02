-- Non-destructive schema. Run via tools/import_pois.py, in one transaction.
CREATE SCHEMA IF NOT EXISTS admin;
CREATE SCHEMA IF NOT EXISTS amenities;
CREATE SCHEMA IF NOT EXISTS ml;

CREATE TABLE IF NOT EXISTS admin.unit (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    version text NOT NULL CHECK (version IN ('legacy_2025', 'from_2025')),
    level text NOT NULL CHECK (level IN ('province', 'district', 'ward')),
    code text NOT NULL,
    name text NOT NULL,
    parent_id bigint REFERENCES admin.unit(id),
    source_file text NOT NULL,
    raw_record jsonb NOT NULL,
    UNIQUE (version, level, code),
    CHECK (NOT (version = 'from_2025' AND level = 'district')),
    CHECK ((level = 'province') = (parent_id IS NULL))
);
CREATE INDEX IF NOT EXISTS unit_parent_idx ON admin.unit(parent_id);

-- Candidate relations from the source, NOT a deterministic address converter.
CREATE TABLE IF NOT EXISTS admin.ward_transition (
    old_ward_id bigint NOT NULL REFERENCES admin.unit(id),
    new_ward_id bigint NOT NULL REFERENCES admin.unit(id),
    source_file text NOT NULL,
    raw_record jsonb NOT NULL,
    PRIMARY KEY (old_ward_id, new_ward_id)
);

-- User-defined model labels; these are NOT official administrative codes.
CREATE TABLE IF NOT EXISTS ml.district_label (
    model_version text NOT NULL,
    label smallint NOT NULL CHECK (label BETWEEN 0 AND 23),
    district_name text NOT NULL,
    PRIMARY KEY (model_version, label),
    UNIQUE (model_version, district_name)
);
CREATE TABLE IF NOT EXISTS ml.district_link (
    admin_district_id bigint NOT NULL REFERENCES admin.unit(id),
    model_version text NOT NULL,
    label smallint NOT NULL,
    evidence text NOT NULL,
    PRIMARY KEY (admin_district_id, model_version),
    FOREIGN KEY (model_version, label) REFERENCES ml.district_label(model_version, label)
);

CREATE TABLE IF NOT EXISTS amenities.poi_schools (
    poi_id text PRIMARY KEY,
    poi_type text NOT NULL CHECK (poi_type = 'truong_hoc'),
    poi_subtype text,
    name text NOT NULL,
    address_old text,
    address_new text,
    old_province_id bigint REFERENCES admin.unit(id),
    old_district_id bigint REFERENCES admin.unit(id),
    old_ward_id bigint REFERENCES admin.unit(id),
    new_province_id bigint REFERENCES admin.unit(id),
    new_ward_id bigint REFERENCES admin.unit(id),
    latitude double precision CHECK (latitude BETWEEN -90 AND 90),
    longitude double precision CHECK (longitude BETWEEN -180 AND 180),
    mapping_status jsonb NOT NULL,
    source_file text NOT NULL,
    source_sha256 text NOT NULL,
    raw_record jsonb NOT NULL,
    imported_at timestamptz NOT NULL DEFAULT now(),
    CHECK ((latitude IS NULL) = (longitude IS NULL)),
    campus_name text GENERATED ALWAYS AS (NULLIF(raw_record->>'campus_name', '')) STORED,
    school_level_codes text GENERATED ALWAYS AS (NULLIF(raw_record->>'school_level_codes', '')) STORED,
    ownership text GENERATED ALWAYS AS (NULLIF(raw_record->>'ownership', '')) STORED,
    student_count integer GENERATED ALWAYS AS (NULLIF(raw_record->>'student_count', '')::integer) STORED,
    old_address_confidence text GENERATED ALWAYS AS (NULLIF(raw_record->>'old_address_confidence', '')) STORED
);
CREATE INDEX IF NOT EXISTS poi_schools_old_district_idx ON amenities.poi_schools(old_district_id);
CREATE INDEX IF NOT EXISTS poi_schools_new_ward_idx ON amenities.poi_schools(new_ward_id);

CREATE TABLE IF NOT EXISTS amenities.poi_hospitals (
    poi_id text PRIMARY KEY,
    poi_type text NOT NULL CHECK (poi_type = 'benh_vien'),
    poi_subtype text,
    name text NOT NULL,
    address_old text,
    address_new text,
    old_province_id bigint REFERENCES admin.unit(id),
    old_district_id bigint REFERENCES admin.unit(id),
    old_ward_id bigint REFERENCES admin.unit(id),
    new_province_id bigint REFERENCES admin.unit(id),
    new_ward_id bigint REFERENCES admin.unit(id),
    latitude double precision CHECK (latitude BETWEEN -90 AND 90),
    longitude double precision CHECK (longitude BETWEEN -180 AND 180),
    mapping_status jsonb NOT NULL,
    source_file text NOT NULL,
    source_sha256 text NOT NULL,
    raw_record jsonb NOT NULL,
    imported_at timestamptz NOT NULL DEFAULT now(),
    CHECK ((latitude IS NULL) = (longitude IS NULL)),
    ownership text GENERATED ALWAYS AS (NULLIF(raw_record->>'ownership', '')) STORED
);
CREATE INDEX IF NOT EXISTS poi_hospitals_old_district_idx ON amenities.poi_hospitals(old_district_id);
CREATE INDEX IF NOT EXISTS poi_hospitals_new_ward_idx ON amenities.poi_hospitals(new_ward_id);

CREATE TABLE IF NOT EXISTS amenities.poi_markets (
    poi_id text PRIMARY KEY,
    poi_type text NOT NULL CHECK (poi_type = 'cho'),
    poi_subtype text,
    name text NOT NULL,
    address_old text,
    address_new text,
    old_province_id bigint REFERENCES admin.unit(id),
    old_district_id bigint REFERENCES admin.unit(id),
    old_ward_id bigint REFERENCES admin.unit(id),
    new_province_id bigint REFERENCES admin.unit(id),
    new_ward_id bigint REFERENCES admin.unit(id),
    latitude double precision CHECK (latitude BETWEEN -90 AND 90),
    longitude double precision CHECK (longitude BETWEEN -180 AND 180),
    mapping_status jsonb NOT NULL,
    source_file text NOT NULL,
    source_sha256 text NOT NULL,
    raw_record jsonb NOT NULL,
    imported_at timestamptz NOT NULL DEFAULT now(),
    CHECK ((latitude IS NULL) = (longitude IS NULL)),
    manual_review_required boolean GENERATED ALWAYS AS (NULLIF(raw_record->>'manual_review_required', '')::boolean) STORED
);
CREATE INDEX IF NOT EXISTS poi_markets_old_district_idx ON amenities.poi_markets(old_district_id);
CREATE INDEX IF NOT EXISTS poi_markets_new_ward_idx ON amenities.poi_markets(new_ward_id);

-- COMMON_VIEW_START
CREATE OR REPLACE VIEW amenities.housing_poi AS
SELECT poi_id, poi_type, poi_subtype, name, address_old, address_new, old_province_id, old_district_id, old_ward_id, new_province_id, new_ward_id, latitude, longitude, mapping_status, source_file, source_sha256, raw_record, imported_at FROM amenities.poi_schools
UNION ALL
SELECT poi_id, poi_type, poi_subtype, name, address_old, address_new, old_province_id, old_district_id, old_ward_id, new_province_id, new_ward_id, latitude, longitude, mapping_status, source_file, source_sha256, raw_record, imported_at FROM amenities.poi_hospitals
UNION ALL
SELECT poi_id, poi_type, poi_subtype, name, address_old, address_new, old_province_id, old_district_id, old_ward_id, new_province_id, new_ward_id, latitude, longitude, mapping_status, source_file, source_sha256, raw_record, imported_at FROM amenities.poi_markets;

CREATE OR REPLACE VIEW ml.poi_district_features AS
SELECT p.poi_id, p.poi_type, p.name, p.old_district_id,
       l.label AS district_label,
       CASE WHEN l.label IS NOT NULL THEN 'matched_district_name'
            WHEN u.name = 'Thành phố Thủ Đức' THEN 'ambiguous_pre_2021_district'
            ELSE 'unresolved' END AS label_status,
       p.mapping_status,
       p.raw_record->>'old_address_confidence' AS old_address_confidence,
       p.raw_record->>'geocode_confidence' AS geocode_confidence,
       p.raw_record->>'manual_review_required' AS manual_review_required
FROM amenities.housing_poi p
LEFT JOIN admin.unit u ON u.id = p.old_district_id
LEFT JOIN ml.district_link l ON l.admin_district_id = p.old_district_id
    AND l.model_version = 'hcm_24_user_v1';
