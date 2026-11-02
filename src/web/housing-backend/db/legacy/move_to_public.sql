-- =====================================================================
-- Chuyển DB housing ĐANG CÓ DỮ LIỆU từ 5 schema (admin, amenities,
-- listing, ml, rag) sang schema public. Dữ liệu giữ nguyên, không copy.
--
-- Chạy (cả file trong 1 transaction, lỗi giữa chừng thì không đổi gì):
--   psql -d housing -1 -v ON_ERROR_STOP=1 -f db/move_to_public.sql
--
-- ALTER TABLE ... SET SCHEMA tự mang theo index, constraint, sequence
-- (unit_id_seq) và FK. View cũng tự trỏ theo vì Postgres lưu view theo OID.
-- Riêng function viết bằng plpgsql lưu dạng text -> phải tạo lại (functions.sql).
-- =====================================================================

-- 0. Dừng ngay nếu public đã có bảng trùng tên
DO $$
DECLARE
    clash text;
BEGIN
    SELECT string_agg(c.relname, ', ') INTO clash
      FROM pg_class c
     WHERE c.relnamespace = 'public'::regnamespace
       AND c.relname IN ('unit', 'ward_transition', 'district_label', 'district_link',
                         'poi_schools', 'poi_hospitals', 'poi_markets', 'housing_poi',
                         'poi_district_features', 'listings', 'listing_spatial_features',
                         'listing_embeddings', 'unit_id_seq');
    IF clash IS NOT NULL THEN
        RAISE EXCEPTION 'public đã có object trùng tên: %', clash;
    END IF;
END;
$$;

-- 1. Xóa function cũ (thân hàm còn trỏ tới schema cũ)
DROP FUNCTION amenities.nearby(double precision, double precision, double precision, text);
DROP FUNCTION listing.refresh_spatial_features();

-- 2. Chuyển bảng
ALTER TABLE admin.unit                        SET SCHEMA public;
ALTER TABLE admin.ward_transition             SET SCHEMA public;
ALTER TABLE ml.district_label                 SET SCHEMA public;
ALTER TABLE ml.district_link                  SET SCHEMA public;
ALTER TABLE amenities.poi_schools             SET SCHEMA public;
ALTER TABLE amenities.poi_hospitals           SET SCHEMA public;
ALTER TABLE amenities.poi_markets             SET SCHEMA public;
ALTER TABLE listing.listings                  SET SCHEMA public;
ALTER TABLE listing.listing_spatial_features  SET SCHEMA public;
-- listing_embeddings dùng kiểu vector (extension pgvector). DB không có pgvector
-- (vd. restore bằng fix_backup khi máy chưa cài) thì bảng này không tồn tại -> bỏ qua.
DO $$
BEGIN
    IF to_regclass('rag.listing_embeddings') IS NOT NULL THEN
        ALTER TABLE rag.listing_embeddings SET SCHEMA public;
    ELSIF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector') THEN
        RAISE EXCEPTION 'Thiếu bảng rag.listing_embeddings';
    ELSE
        RAISE NOTICE 'Bỏ qua listing_embeddings: DB không có pgvector';
    END IF;
END;
$$;

-- 3. Chuyển view
ALTER VIEW amenities.housing_poi        SET SCHEMA public;
ALTER VIEW ml.poi_district_features     SET SCHEMA public;

-- 4. Xóa schema cũ. Không dùng CASCADE: nếu còn sót object nào thì báo lỗi
--    và rollback, tránh xóa nhầm dữ liệu.
DROP SCHEMA admin;
DROP SCHEMA amenities;
DROP SCHEMA listing;
DROP SCHEMA ml;
DROP SCHEMA rag;

-- 5. Tạo lại function trong public
\ir functions.sql
