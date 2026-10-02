"""Nạp tin đã làm sạch vào PostgreSQL (schema listing) và tính đặc trưng không gian."""
from pathlib import Path

from psycopg.types.json import Jsonb


class ListingLoader:
    """Tạo schema, upsert tin sạch theo listing_id, tính lại 6 biến đếm POI.

    Chạy lại an toàn: tin đã có được cập nhật, không nhân bản; tin không còn trong file
    mới vẫn giữ nguyên trong database (không xóa lịch sử).
    """

    SCHEMA_FILE = Path(__file__).with_name('schema.sql')
    COLUMNS = [
        'listing_id', 'listing_url', 'title', 'description', 'transaction_type', 'property_type',
        'price', 'price_per_m2', 'area', 'frontage', 'bedrooms', 'bathrooms', 'road_width',
        'floors', 'legal', 'legal_group', 'interior', 'province_old', 'district_old', 'old_ward',
        'old_address', 'old_address_detail', 'new_ward', 'new_city', 'new_address',
        'latitude', 'longitude', 'posted_at', 'expired_at', 'quality_flags', 'raw_record',
        'source_file',
    ]

    def __init__(self, conn):
        self.conn = conn

    def load(self, listings, source_file):
        """Nạp DataFrame tin sạch (đầu ra ListingCleaner) trong một transaction; trả về số liệu."""
        rows = listings.assign(source_file=str(source_file))[self.COLUMNS]
        rows = rows.astype(object).where(rows.notna(), None).to_dict('records')
        for row in rows:
            row['raw_record'] = Jsonb(row['raw_record'])
            for field in ('bedrooms', 'bathrooms', 'floors'):   # numpy int -> int cho psycopg
                if row[field] is not None:
                    row[field] = int(row[field])

        columns = ', '.join(self.COLUMNS)
        placeholders = ', '.join(f'%({c})s' for c in self.COLUMNS)
        updates = ', '.join(f'{c} = EXCLUDED.{c}' for c in self.COLUMNS if c != 'listing_id')
        upsert = (f'INSERT INTO listing.listings ({columns}) VALUES ({placeholders}) '
                  f'ON CONFLICT (listing_id) DO UPDATE SET {updates}, updated_at = now() '
                  f'RETURNING (xmax = 0) AS inserted')

        with self.conn.transaction(), self.conn.cursor() as cur:
            cur.execute(self.SCHEMA_FILE.read_text(encoding='utf-8'))
            cur.executemany(upsert, rows, returning=True)
            inserted = 0
            while True:     # executemany + returning: mỗi dòng dữ liệu một result set
                inserted += cur.fetchone()[0]
                if not cur.nextset():
                    break
            cur.execute('SELECT listing.refresh_spatial_features()')
            spatial = cur.fetchone()[0]
            cur.execute('SELECT count(*), count(geom) FROM listing.listings')
            total, with_geom = cur.fetchone()

        return {'loaded': len(rows), 'inserted': inserted, 'updated': len(rows) - inserted,
                'listings_in_db': total, 'listings_with_geom': with_geom,
                'spatial_features_refreshed': spatial}
