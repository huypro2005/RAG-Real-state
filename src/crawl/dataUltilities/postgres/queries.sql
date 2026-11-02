-- Longitude first; radius and distance are in meters.
-- Three storage tables; housing_poi is the read-only combined view.
SELECT poi_id, name, school_level_codes, student_count FROM amenities.poi_schools LIMIT 10;
SELECT poi_id, name, ownership FROM amenities.poi_hospitals LIMIT 10;
SELECT poi_id, name, manual_review_required FROM amenities.poi_markets LIMIT 10;
SELECT * FROM amenities.nearby(106.7009, 10.7769, 1000);
SELECT poi_type, count(*) FROM amenities.nearby(106.7009, 10.7769, 1000)
GROUP BY poi_type;
SELECT * FROM amenities.nearby(106.7009, 10.7769, 3000, 'benh_vien') LIMIT 10;

-- Separate model labels; unresolved labels remain NULL.
SELECT * FROM ml.poi_district_features WHERE district_label = 13;
SELECT label_status, count(*) FROM ml.poi_district_features GROUP BY label_status;
SELECT poi_id, name, mapping_status, raw_record FROM amenities.housing_poi
WHERE mapping_status->>'old_ward' <> 'matched'
   OR mapping_status->>'new_ward' <> 'matched_code_and_name';

-- Inspect every candidate, never choose isDefaultNewWard automatically.
SELECT o.name AS old_ward, n.name AS new_ward, t.raw_record
FROM admin.ward_transition t
JOIN admin.unit o ON o.id = t.old_ward_id
JOIN admin.unit n ON n.id = t.new_ward_id;
