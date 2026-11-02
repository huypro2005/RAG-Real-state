-- =====================================================================
-- Function của housing DB (nằm trong public = schema mặc định).
-- Nội dung giữ nguyên bản trong DB thật, chỉ bỏ tiền tố schema cũ
-- (amenities., listing.) vì mọi bảng giờ đã ở schema mặc định.
-- =====================================================================

-- POI trong bán kính radius_m (mét) quanh 1 điểm, gần nhất trước.
--   SELECT * FROM nearby(106.70, 10.77, 1000);              -- mọi loại
--   SELECT * FROM nearby(106.70, 10.77, 1000, 'truong_hoc'); -- chỉ trường học
CREATE OR REPLACE FUNCTION nearby(
    query_longitude double precision,
    query_latitude  double precision,
    radius_m        double precision DEFAULT 1000,
    filter_type     text DEFAULT NULL::text
)
RETURNS TABLE(poi_id text, poi_type text, name text, distance_m double precision)
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
    SELECT p.poi_id, p.poi_type, p.name, ST_Distance(p.geom, origin)
    FROM housing_poi p
    WHERE ST_DWithin(p.geom, origin, radius_m)
      AND (filter_type IS NULL OR p.poi_type = filter_type)
    ORDER BY ST_Distance(p.geom, origin), p.poi_id;
END;
$$;

-- Tính lại listing_spatial_features cho mọi tin có tọa độ. Trả về số tin đã tính.
--   SELECT refresh_spatial_features();
CREATE OR REPLACE FUNCTION refresh_spatial_features()
RETURNS integer
LANGUAGE plpgsql
AS $$
DECLARE
    refreshed integer;
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
           sc.count_1km, hc.count_1km, mc.count_1km,
           sc.count_3km, hc.count_3km, mc.count_3km,
           sn.name, sn.distance_m,
           hn.name, hn.distance_m,
           mn.name, mn.distance_m,
           now()
      FROM listings l
      -- Đếm POI trong 3 km, trong đó bao nhiêu POI trong 1 km.
      CROSS JOIN LATERAL (
            SELECT count(*) FILTER (WHERE ST_DWithin(p.geom, l.geom, 1000)) AS count_1km,
                   count(*) AS count_3km
              FROM poi_schools p WHERE ST_DWithin(p.geom, l.geom, 3000)) sc
      CROSS JOIN LATERAL (
            SELECT count(*) FILTER (WHERE ST_DWithin(p.geom, l.geom, 1000)) AS count_1km,
                   count(*) AS count_3km
              FROM poi_hospitals p WHERE ST_DWithin(p.geom, l.geom, 3000)) hc
      CROSS JOIN LATERAL (
            SELECT count(*) FILTER (WHERE ST_DWithin(p.geom, l.geom, 1000)) AS count_1km,
                   count(*) AS count_3km
              FROM poi_markets p WHERE ST_DWithin(p.geom, l.geom, 3000)) mc
      -- POI gần nhất (không giới hạn bán kính), dùng GiST index qua toán tử <->.
      LEFT JOIN LATERAL (
            SELECT p.name, ST_Distance(p.geom, l.geom) AS distance_m
              FROM poi_schools p WHERE p.geom IS NOT NULL
             ORDER BY p.geom <-> l.geom LIMIT 1) sn ON true
      LEFT JOIN LATERAL (
            SELECT p.name, ST_Distance(p.geom, l.geom) AS distance_m
              FROM poi_hospitals p WHERE p.geom IS NOT NULL
             ORDER BY p.geom <-> l.geom LIMIT 1) hn ON true
      LEFT JOIN LATERAL (
            SELECT p.name, ST_Distance(p.geom, l.geom) AS distance_m
              FROM poi_markets p WHERE p.geom IS NOT NULL
             ORDER BY p.geom <-> l.geom LIMIT 1) mn ON true
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
