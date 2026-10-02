"""One-time transactional migration from the shared POI table to three tables.

Back up housing with pg_dump before running. Uses standard PG* credentials.
Existing unknown dependencies block the migration rather than being cascaded.
"""
import os

import psycopg
from psycopg import sql

from import_pois import ROOT


def main():
    with psycopg.connect(host=os.getenv('PGHOST', 'localhost'),
                         port=os.getenv('PGPORT', '5432'),
                         dbname=os.getenv('PGDATABASE', 'housing'),
                         user=os.getenv('PGUSER', 'postgres')) as conn:
        conn.execute('SELECT pg_advisory_xact_lock(7400325)')
        kind = conn.execute("SELECT relkind FROM pg_class WHERE oid=to_regclass('amenities.housing_poi')").fetchone()
        if kind == ('v',):
            print('Already split; no changes.')
            return
        if kind != ('r',):
            raise RuntimeError('Expected original amenities.housing_poi table')
        conn.execute('LOCK TABLE amenities.housing_poi IN ACCESS EXCLUSIVE MODE')
        schema = (ROOT / 'data/postgres/schema.sql').read_text(encoding='utf-8')
        tables_sql, views_sql = schema.split('-- COMMON_VIEW_START', 1)
        conn.execute(tables_sql)
        columns = [r[0] for r in conn.execute("""SELECT column_name FROM information_schema.columns
            WHERE table_schema='amenities' AND table_name='housing_poi'
              AND is_generated='NEVER' ORDER BY ordinal_position""")]
        cols = sql.SQL(',').join(map(sql.Identifier, columns))
        tables = [('poi_schools', 'truong_hoc'), ('poi_hospitals', 'benh_vien'), ('poi_markets', 'cho')]
        for table, poi_type in tables:
            conn.execute(sql.SQL('INSERT INTO amenities.{} ({}) SELECT {} FROM amenities.housing_poi WHERE poi_type=%s').format(
                sql.Identifier(table), cols, cols), (poi_type,))
        union = sql.SQL(' UNION ALL ').join(sql.SQL('SELECT {} FROM amenities.{}').format(cols, sql.Identifier(t)) for t, _ in tables)
        different = conn.execute(sql.SQL('''WITH old AS (SELECT {0} FROM amenities.housing_poi), new AS ({1})
            SELECT EXISTS((SELECT * FROM old EXCEPT ALL SELECT * FROM new)
            UNION ALL (SELECT * FROM new EXCEPT ALL SELECT * FROM old))''').format(cols, union)).fetchone()[0]
        if different:
            raise RuntimeError('Migration does not preserve every source row; rolling back')
        count = conn.execute('SELECT count(*) FROM amenities.housing_poi').fetchone()[0]
        conn.execute('DROP VIEW ml.poi_district_features')
        conn.execute('DROP TABLE amenities.housing_poi')
        conn.execute(views_sql)
        conn.execute((ROOT / 'data/postgres/enable_postgis.sql').read_text(encoding='utf-8'))
    print(f'Migrated {count} rows to three tables; housing_poi is now a UNION ALL view.')


if __name__ == '__main__':
    main()
