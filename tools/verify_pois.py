"""Read-only integration checks against imported CSVs; optionally require PostGIS."""
import argparse
import hashlib
import json
import os
from pathlib import Path

import psycopg

from import_pois import ROOT, LABELS, MODEL, coordinates, read_csv


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--require-spatial', action='store_true')
    args = parser.parse_args()
    expected = {}
    for path in (ROOT / 'data').glob('poi_*.csv'):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        for row in read_csv(path):
            assert row['poi_id'] not in expected
            expected[row['poi_id']] = (row, digest)
    settings = dict(host=os.getenv('PGHOST', 'localhost'), port=os.getenv('PGPORT', '5432'),
                    dbname=os.getenv('PGDATABASE', 'housing'), user=os.getenv('PGUSER', 'postgres'))
    with psycopg.connect(**settings) as conn:
        conn.execute('SET TRANSACTION READ ONLY')
        assert conn.execute("SELECT relkind FROM pg_class WHERE oid='amenities.housing_poi'::regclass").fetchone()[0] == 'v'
        for table, poi_type in [('poi_schools', 'truong_hoc'), ('poi_hospitals', 'benh_vien'), ('poi_markets', 'cho')]:
            assert conn.execute('SELECT relkind FROM pg_class WHERE oid=%s::regclass', ('amenities.' + table,)).fetchone()[0] == 'r'
            actual = conn.execute(psycopg.sql.SQL('SELECT poi_id,poi_type FROM amenities.{}').format(psycopg.sql.Identifier(table))).fetchall()
            source = read_csv(ROOT / 'data' / (table + '.csv'))
            assert {r[0] for r in actual} == {r['poi_id'] for r in source}
            assert all(r[1] == poi_type for r in actual)
        assert conn.execute("SELECT count(*) FROM amenities.poi_schools WHERE student_count IS DISTINCT FROM NULLIF(raw_record->>'student_count','')::integer").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM amenities.poi_markets WHERE manual_review_required IS DISTINCT FROM NULLIF(raw_record->>'manual_review_required','')::boolean").fetchone()[0] == 0
        rows = conn.execute('SELECT poi_id,raw_record,source_sha256,latitude,longitude FROM amenities.housing_poi').fetchall()
        assert len(rows) == len(expected)
        for identity, raw, digest, lat, lon in rows:
            assert (raw, digest) == expected[identity], identity
            assert (lat, lon) == coordinates(raw), identity
        labels = conn.execute('SELECT label,district_name FROM ml.district_label WHERE model_version=%s ORDER BY label', (MODEL,)).fetchall()
        assert labels == list(enumerate(LABELS))
        assert conn.execute('''SELECT count(*) FROM ml.poi_district_features f
            JOIN admin.unit u ON u.id=f.old_district_id
            WHERE u.name='Thành phố Thủ Đức' AND f.district_label IS NOT NULL''').fetchone()[0] == 0
        assert conn.execute('''SELECT count(*) FROM amenities.housing_poi p
            LEFT JOIN admin.unit ow ON ow.id=p.old_ward_id
            LEFT JOIN admin.unit od ON od.id=p.old_district_id
            LEFT JOIN admin.unit nw ON nw.id=p.new_ward_id
            WHERE (ow.id IS NOT NULL AND ow.parent_id IS DISTINCT FROM p.old_district_id)
               OR (od.id IS NOT NULL AND od.parent_id IS DISTINCT FROM p.old_province_id)
               OR (nw.id IS NOT NULL AND nw.parent_id IS DISTINCT FROM p.new_province_id)''').fetchone()[0] == 0
        spatial = bool(conn.execute("SELECT 1 FROM information_schema.columns WHERE table_schema='amenities' AND table_name='housing_poi' AND column_name='geom'").fetchone())
        result = {'rows_verified_against_csv': len(rows), 'raw_and_coordinates_exact': True,
                  'labels_and_parent_links_valid': True, 'spatial_verified': False}
        if args.require_spatial:
            assert spatial, 'PostGIS not enabled: run tools/import_pois.py --spatial-only after installing it'
        if spatial:
            assert conn.execute('''SELECT count(*) FROM amenities.housing_poi WHERE
                (latitude IS NOT NULL AND geom IS NULL) OR
                (geom IS NOT NULL AND (ST_SRID(geom::geometry) <> 4326
                 OR ST_X(geom::geometry) <> longitude OR ST_Y(geom::geometry) <> latitude))''').fetchone()[0] == 0
            identity, lat, lon = conn.execute('SELECT poi_id,latitude,longitude FROM amenities.housing_poi WHERE geom IS NOT NULL LIMIT 1').fetchone()
            nearby = conn.execute('SELECT * FROM amenities.nearby(%s,%s,1)', (lon,lat)).fetchall()
            assert any(r[0] == identity and r[3] == 0 for r in nearby)
            count = conn.execute('SELECT count(*) FROM amenities.nearby(%s,%s,1000)', (lon,lat)).fetchone()[0]
            brute = conn.execute('''SELECT count(*) FROM amenities.housing_poi WHERE
                ST_Distance(geom,ST_SetSRID(ST_MakePoint(%s,%s),4326)::geography)<=1000''', (lon,lat)).fetchone()[0]
            assert count == brute
            conn.execute('SET LOCAL enable_seqscan=off')
            plan = conn.execute('''EXPLAIN SELECT poi_id FROM amenities.housing_poi WHERE
                ST_DWithin(geom,ST_SetSRID(ST_MakePoint(%s,%s),4326)::geography,1000)''', (lon,lat)).fetchall()
            for table in ['poi_schools', 'poi_hospitals', 'poi_markets']:
                assert table + '_geom_gist' in str(plan), plan
            for params in [(181,10,1000), (106,91,1000), (106,10,-1), (106,10,float('nan'))]:
                try:
                    with conn.transaction():
                        conn.execute('SELECT * FROM amenities.nearby(%s,%s,%s)', params).fetchall()
                except psycopg.errors.RaiseException:
                    pass
                else:
                    raise AssertionError(f'Invalid spatial arguments accepted: {params}')
            result['spatial_verified'] = True
            result['radius_1km_matches_brute_force'] = count
        print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
