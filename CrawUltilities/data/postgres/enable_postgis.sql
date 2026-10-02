-- Transactional; requires PostGIS binaries installed for this PostgreSQL server.
CREATE EXTENSION IF NOT EXISTS postgis;
ALTER TABLE amenities.poi_schools ADD COLUMN IF NOT EXISTS geom geography(Point,4326)
GENERATED ALWAYS AS (
    CASE WHEN longitude IS NOT NULL AND latitude IS NOT NULL
         THEN ST_SetSRID(ST_MakePoint(longitude, latitude),4326)::geography END
) STORED;
CREATE INDEX IF NOT EXISTS poi_schools_geom_gist ON amenities.poi_schools USING gist(geom);

ALTER TABLE amenities.poi_hospitals ADD COLUMN IF NOT EXISTS geom geography(Point,4326)
GENERATED ALWAYS AS (
    CASE WHEN longitude IS NOT NULL AND latitude IS NOT NULL
         THEN ST_SetSRID(ST_MakePoint(longitude, latitude),4326)::geography END
) STORED;
CREATE INDEX IF NOT EXISTS poi_hospitals_geom_gist ON amenities.poi_hospitals USING gist(geom);

ALTER TABLE amenities.poi_markets ADD COLUMN IF NOT EXISTS geom geography(Point,4326)
GENERATED ALWAYS AS (
    CASE WHEN longitude IS NOT NULL AND latitude IS NOT NULL
         THEN ST_SetSRID(ST_MakePoint(longitude, latitude),4326)::geography END
) STORED;
CREATE INDEX IF NOT EXISTS poi_markets_geom_gist ON amenities.poi_markets USING gist(geom);

CREATE OR REPLACE VIEW amenities.housing_poi AS
SELECT poi_id, poi_type, poi_subtype, name, address_old, address_new, old_province_id, old_district_id, old_ward_id, new_province_id, new_ward_id, latitude, longitude, mapping_status, source_file, source_sha256, raw_record, imported_at, geom FROM amenities.poi_schools
UNION ALL
SELECT poi_id, poi_type, poi_subtype, name, address_old, address_new, old_province_id, old_district_id, old_ward_id, new_province_id, new_ward_id, latitude, longitude, mapping_status, source_file, source_sha256, raw_record, imported_at, geom FROM amenities.poi_hospitals
UNION ALL
SELECT poi_id, poi_type, poi_subtype, name, address_old, address_new, old_province_id, old_district_id, old_ward_id, new_province_id, new_ward_id, latitude, longitude, mapping_status, source_file, source_sha256, raw_record, imported_at, geom FROM amenities.poi_markets;

CREATE OR REPLACE FUNCTION amenities.nearby(
    query_longitude double precision,
    query_latitude double precision,
    radius_m double precision DEFAULT 1000,
    filter_type text DEFAULT NULL
) RETURNS TABLE(poi_id text, poi_type text, name text, distance_m double precision)
LANGUAGE plpgsql STABLE AS $$
DECLARE origin geography;
BEGIN
    IF query_longitude IS NULL OR query_latitude IS NULL OR radius_m IS NULL
       OR NOT query_longitude BETWEEN -180 AND 180
       OR NOT query_latitude BETWEEN -90 AND 90
       OR radius_m < 0 OR radius_m >= 'Infinity'::double precision THEN
        RAISE EXCEPTION 'Invalid longitude, latitude or radius (meters)';
    END IF;
    origin := ST_SetSRID(ST_MakePoint(query_longitude, query_latitude),4326)::geography;
    RETURN QUERY
    SELECT p.poi_id, p.poi_type, p.name, ST_Distance(p.geom, origin)
    FROM amenities.housing_poi p
    WHERE ST_DWithin(p.geom, origin, radius_m)
      AND (filter_type IS NULL OR p.poi_type = filter_type)
    ORDER BY ST_Distance(p.geom, origin), p.poi_id;
END;
$$;
