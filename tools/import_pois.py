"""Import existing POI CSVs and independent administrative snapshots.

Credentials: standard PGHOST/PGPORT/PGDATABASE/PGUSER/PGPASSWORD variables.
No address conversion, geocoding, model training, or crawler changes.
"""
import argparse
import csv
import hashlib
import json
import math
import os
import unicodedata
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path

import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / 'vietnamadminunits/data/processed'
MODEL = 'hcm_24_user_v1'
LABELS = [
    'bình chánh', 'bình tân', 'bình thạnh', 'cần giờ', 'củ chi', 'gò vấp',
    'hóc môn', 'nhà bè', 'phú nhuận', 'quận 1', 'quận 10', 'quận 11',
    'quận 12', 'quận 2', 'quận 3', 'quận 4', 'quận 5', 'quận 6',
    'quận 7', 'quận 8', 'quận 9', 'thủ đức', 'tân bình', 'tân phú',
]


def key(value):
    """Comparison key only. Original values remain in raw_record."""
    return ' '.join(unicodedata.normalize('NFC', value or '').casefold().split())


def code(value):
    if not value:
        return None
    number = Decimal(value)
    if not number.is_finite() or number != number.to_integral_value():
        raise ValueError(f'Invalid administrative code: {value!r}')
    return str(int(number))


def read_csv(path):
    with path.open(encoding='utf-8-sig', newline='') as stream:
        rows = list(csv.DictReader(stream))
    if any(None in r or any(v is None for v in r.values()) for r in rows):
        raise ValueError(f'Malformed CSV: {path}')
    return rows


def unit_aliases(name, level):
    aliases = {key(name)}
    prefixes = {'province': ['thành phố ', 'tỉnh '],
                'district': ['quận ', 'huyện ', 'thành phố '],
                'ward': ['phường ', 'xã ', 'thị trấn ']}[level]
    for prefix in prefixes:
        if key(name).startswith(prefix):
            aliases.add(key(name)[len(prefix):])
    if key(name) == 'thành phố thủ đức':
        aliases.add('tp thủ đức')
    return aliases


def coordinates(row):
    lat, lon = row['latitude'], row['longitude']
    if not lat and not lon:
        return None, None
    if not lat or not lon:
        raise ValueError(f"Incomplete coordinate pair: {row['poi_id']}")
    lat, lon = float(lat), float(lon)
    if not (math.isfinite(lat) and math.isfinite(lon)
            and -90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError(f"Invalid coordinates: {row['poi_id']}")
    return lat, lon


def load_admin(conn):
    units = {}
    specs = [('legacy_2025', 'legacy_63-province-10040-ward_with_location.csv'),
             ('from_2025', '2025_34-province-3221-ward_with_location.csv')]
    for version, filename in specs:
        for row in read_csv(PROCESSED / filename):
            if code(row['provinceCode']) != '79':
                continue
            parent = None
            levels = ['province', 'district', 'ward'] if version == 'legacy_2025' else ['province', 'ward']
            for level in levels:
                unit_code = code(row[level + 'Code'])
                if unit_code is None:
                    continue
                identity = (version, level, unit_code)
                if identity not in units:
                    unit_id = conn.execute('''
                        INSERT INTO admin.unit(version,level,code,name,parent_id,source_file,raw_record)
                        VALUES (%s,%s,%s,%s,%s,%s,%s)
                        ON CONFLICT(version,level,code) DO UPDATE SET
                          name=excluded.name,parent_id=excluded.parent_id,
                          source_file=excluded.source_file,raw_record=excluded.raw_record
                        RETURNING id
                    ''', (*identity, row[level], parent, filename, Jsonb(row))).fetchone()[0]
                    units[identity] = {'id': unit_id, 'name': row[level], 'parent': parent}
                else:
                    assert units[identity]['parent'] == parent
                    assert units[identity]['name'] == row[level]
                parent = units[identity]['id']

    transition_file = 'convert_legacy_2025_with_location_and_default_ward.csv'
    transition_count = 0
    for row in read_csv(PROCESSED / transition_file):
        if code(row['provinceCode']) != '79':
            continue
        old = units.get(('legacy_2025', 'ward', code(row['wardCode'])))
        new = units.get(('from_2025', 'ward', code(row['newWardCode'])))
        if not old or not new:
            raise ValueError('Transition references a missing administrative unit')
        conn.execute('''INSERT INTO admin.ward_transition
            (old_ward_id,new_ward_id,source_file,raw_record) VALUES (%s,%s,%s,%s)
            ON CONFLICT(old_ward_id,new_ward_id) DO UPDATE SET
              source_file=excluded.source_file,raw_record=excluded.raw_record''',
            (old['id'], new['id'], transition_file, Jsonb(row)))
        transition_count += 1

    for label, name in enumerate(LABELS):
        conn.execute('''INSERT INTO ml.district_label VALUES (%s,%s,%s)
            ON CONFLICT(model_version,label) DO UPDATE SET district_name=excluded.district_name''',
            (MODEL, label, name))
    for (version, level, _), unit in units.items():
        if version != 'legacy_2025' or level != 'district':
            continue
        # The legacy snapshot already contains the merged Thu Duc city.
        # It cannot be assigned label 21 (the earlier Thu Duc district).
        if key(unit['name']) == 'thành phố thủ đức':
            continue
        matches = [i for i, n in enumerate(LABELS) if key(n) in unit_aliases(unit['name'], 'district')]
        if len(matches) == 1:
            conn.execute('''INSERT INTO ml.district_link VALUES (%s,%s,%s,%s)
                ON CONFLICT(admin_district_id,model_version) DO UPDATE SET
                label=excluded.label,evidence=excluded.evidence''',
                (unit['id'], MODEL, matches[0], 'Explicit district name within legacy HCM province 79'))
    return units, transition_count


def make_resolver(units):
    lookup = defaultdict(set)
    for (version, level, _), unit in units.items():
        for alias in unit_aliases(unit['name'], level):
            lookup[version, level, unit['parent'], alias].add(unit['id'])

    def resolve(version, level, parent, name):
        if not name:
            return None, 'missing'
        if level != 'province' and parent is None:
            return None, 'parent_unresolved'
        candidates = lookup.get((version, level, parent, key(name)), set())
        if len(candidates) == 1:
            return next(iter(candidates)), 'matched'
        return None, 'ambiguous' if candidates else 'unmatched'
    return resolve


def load_pois(conn, units):
    resolve = make_resolver(units)
    report = {}
    seen = set()
    conn.execute('CREATE TEMP TABLE poi_import (LIKE amenities.poi_schools INCLUDING DEFAULTS) ON COMMIT DROP')
    columns = ['poi_id', 'poi_type', 'poi_subtype', 'name', 'address_old', 'address_new',
               'old_province_id', 'old_district_id', 'old_ward_id', 'new_province_id', 'new_ward_id',
               'latitude', 'longitude', 'mapping_status', 'source_file', 'source_sha256', 'raw_record']
    with conn.cursor().copy(sql.SQL('COPY poi_import ({}) FROM STDIN').format(
            sql.SQL(',').join(map(sql.Identifier, columns)))) as copy:
        for filename in ['poi_schools.csv', 'poi_hospitals.csv', 'poi_markets.csv']:
            path = ROOT / 'data' / filename
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            rows = read_csv(path)
            status_counts = Counter()
            for row in rows:
                if not row['poi_id'] or row['poi_id'] in seen or not row['name'] or not row['poi_type']:
                    raise ValueError(f"Duplicate/invalid POI: {row['poi_id']}")
                expected_type = {'poi_schools.csv': 'truong_hoc', 'poi_hospitals.csv': 'benh_vien', 'poi_markets.csv': 'cho'}[filename]
                if row['poi_type'] != expected_type:
                    raise ValueError(f'Unexpected POI type in {filename}')
                seen.add(row['poi_id'])
                status = {}
                op, status['old_province'] = resolve('legacy_2025', 'province', None, row['old_province'])
                od, status['old_district'] = resolve('legacy_2025', 'district', op, row['old_district'])
                ow, status['old_ward'] = resolve('legacy_2025', 'ward', od, row['old_ward'])
                np, status['new_province'] = resolve('from_2025', 'province', None, row['new_province'])
                nw = None
                if row['new_ward_code']:
                    candidate = units.get(('from_2025', 'ward', code(row['new_ward_code'])))
                    if candidate and np is not None and candidate['parent'] == np and key(row['new_ward']) in unit_aliases(candidate['name'], 'ward'):
                        nw, status['new_ward'] = candidate['id'], 'matched_code_and_name'
                    else:
                        status['new_ward'] = 'code_name_or_parent_mismatch'
                else:
                    nw, status['new_ward'] = resolve('from_2025', 'ward', np, row['new_ward'])
                lat, lon = coordinates(row)
                for field, state in status.items():
                    status_counts[field + ':' + state] += 1
                copy.write_row((row['poi_id'], row['poi_type'], row['poi_subtype'] or None, row['name'],
                    row['address_old'] or None, row['address_new'] or None, op, od, ow, np, nw,
                    lat, lon, Jsonb(status), filename, digest, Jsonb(row)))
            report[filename] = {'rows': len(rows), 'sha256': digest, 'mapping_counts': dict(status_counts)}
    updates = sql.SQL(',').join(sql.SQL('{0}=excluded.{0}').format(sql.Identifier(c)) for c in columns[1:])
    cols = sql.SQL(',').join(map(sql.Identifier, columns))
    for table, poi_type in [('poi_schools', 'truong_hoc'), ('poi_hospitals', 'benh_vien'), ('poi_markets', 'cho')]:
        conn.execute(sql.SQL('''INSERT INTO amenities.{2} ({0}) SELECT {0} FROM poi_import
            WHERE poi_type=%s ON CONFLICT(poi_id) DO UPDATE SET {1}, imported_at=now()''').format(
                cols, updates, sql.Identifier(table)), (poi_type,))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--create-database', action='store_true')
    parser.add_argument('--skip-spatial', action='store_true', help='Explicitly import before PostGIS is installed')
    parser.add_argument('--spatial-only', action='store_true')
    args = parser.parse_args()
    if args.skip_spatial and args.spatial_only:
        parser.error('--skip-spatial and --spatial-only are mutually exclusive')
    settings = dict(host=os.getenv('PGHOST', 'localhost'), port=os.getenv('PGPORT', '5432'),
                    dbname=os.getenv('PGDATABASE', 'housing'), user=os.getenv('PGUSER', 'postgres'),
                    connect_timeout=10)
    # libpq reads PGPASSWORD / pgpass; never embed or print credentials.
    if args.create_database:
        with psycopg.connect(**{**settings, 'dbname': 'postgres'}, autocommit=True) as conn:
            if not conn.execute('SELECT 1 FROM pg_database WHERE datname=%s', (settings['dbname'],)).fetchone():
                conn.execute(sql.SQL("CREATE DATABASE {} ENCODING 'UTF8' TEMPLATE template0").format(sql.Identifier(settings['dbname'])))
    report = {'database': settings['dbname'], 'host': settings['host'], 'port': settings['port']}
    with psycopg.connect(**settings) as conn:
        conn.execute('SELECT pg_advisory_xact_lock(7400325)')
        if not args.spatial_only:
            schema = (ROOT / 'data/postgres/schema.sql').read_text(encoding='utf-8')
            if conn.execute("SELECT 1 FROM information_schema.columns WHERE table_schema='amenities' AND table_name='housing_poi' AND column_name='geom'").fetchone():
                for table in ['poi_schools', 'poi_hospitals', 'poi_markets']:
                    schema = schema.replace('imported_at FROM amenities.' + table, 'imported_at, geom FROM amenities.' + table)
            conn.execute(schema)
            units, transitions = load_admin(conn)
            report['administrative_units'] = dict(Counter(f'{v}:{l}' for v,l,c in units))
            report['transition_source_rows'] = transitions
            report['files'] = load_pois(conn, units)
        if not args.skip_spatial:
            conn.execute((ROOT / 'data/postgres/enable_postgis.sql').read_text(encoding='utf-8'))
        report['postgis_enabled'] = bool(conn.execute("SELECT 1 FROM pg_extension WHERE extname='postgis'").fetchone())
        report['poi_count'] = conn.execute('SELECT count(*) FROM amenities.housing_poi').fetchone()[0]
        report['model_labels'] = dict(conn.execute('SELECT label_status,count(*) FROM ml.poi_district_features GROUP BY label_status').fetchall())
        for table in ['poi_schools', 'poi_hospitals', 'poi_markets']:
            conn.execute(sql.SQL('ANALYZE amenities.{}').format(sql.Identifier(table)))
    output = ROOT / 'data/postgres' / ('spatial_result.json' if args.spatial_only else 'import_result.json')
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=True, indent=2))


if __name__ == '__main__':
    main()
