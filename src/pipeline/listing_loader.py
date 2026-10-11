"""Nạp tin đã làm sạch vào PostgreSQL (bảng public.listings) và tính các cột suy ra.

Cấu trúc bảng do Alembic tạo (housing-backend: alembic upgrade head), loader không tạo bảng.
"""
from typing import ClassVar


class ListingLoader:
    """Upsert tin sạch theo listing_id, điền FK địa chỉ, tính lại đặc trưng không gian.

    Chạy lại an toàn: tin đã có và không đổi thì không bị ghi (kể cả updated_at); tin không
    còn trong file mới vẫn giữ nguyên trong database (không xóa lịch sử). Mỗi phương thức là
    một transaction riêng và trả về số liệu của đúng bước đó.
    """

    COLUMNS: ClassVar[list[str]] = [
        'listing_id', 'listing_url', 'title', 'description', 'transaction_type', 'property_type',
        'price', 'price_per_m2', 'area', 'frontage', 'bedrooms', 'bathrooms', 'road_width',
        'floors', 'legal', 'legal_group', 'interior', 'province_old', 'district_old', 'old_ward',
        'old_address', 'old_address_detail', 'new_ward', 'new_city', 'new_address',
        'latitude', 'longitude', 'posted_at', 'expired_at', 'quality_flags',
    ]

    def __init__(self, conn):
        self.conn = conn

    def upsert(self, listings):
        """Nạp DataFrame tin sạch (đầu ra ListingCleaner); trả về số dòng thêm mới / sửa / giữ nguyên."""
        rows = listings[self.COLUMNS]
        rows = rows.astype(object).where(rows.notna(), None).to_dict('records')
        for row in rows:
            for field in ('bedrooms', 'bathrooms', 'floors'):   # numpy int -> int cho psycopg
                if row[field] is not None:
                    row[field] = int(row[field])

        data_columns = self.COLUMNS[1:]
        updates = ', '.join(f'{c} = EXCLUDED.{c}' for c in data_columns)
        upsert = (
            f"INSERT INTO listings ({', '.join(self.COLUMNS)}) "
            f"VALUES ({', '.join(f'%({c})s' for c in self.COLUMNS)}) "
            f'ON CONFLICT (listing_id) DO UPDATE SET {updates}, updated_at = now() '
            # Chỉ ghi khi có cột khác: chạy lại cùng dữ liệu thì không đổi gì
            f"WHERE ({', '.join(f'listings.{c}' for c in data_columns)}) "
            f"IS DISTINCT FROM ({', '.join(f'EXCLUDED.{c}' for c in data_columns)}) "
            f'RETURNING (xmax = 0) AS inserted')

        with self.conn.transaction(), self.conn.cursor() as cur:
            cur.executemany(upsert, rows, returning=True)
            written = []
            while True:     # executemany + returning: mỗi dòng dữ liệu một result set (rỗng nếu giữ nguyên)
                written += [row[0] for row in cur.fetchall()]
                if not cur.nextset():
                    break
        inserted = sum(written)
        return {'rows_in': len(rows), 'inserted': inserted,
                'updated': len(written) - inserted, 'unchanged': len(rows) - len(written)}

    def link_addresses(self):
        """Điền old_district_id / old_ward_id / new_ward_id bằng function của migration 0001."""
        with self.conn.transaction(), self.conn.cursor() as cur:
            changed = cur.execute('SELECT refresh_listing_address_ids()').fetchone()[0]
            counts = cur.execute(
                'SELECT count(*), count(old_district_id), count(old_ward_id), count(new_ward_id) '
                'FROM listings').fetchone()
        return dict(zip(('listings_in_db', 'old_district_id', 'old_ward_id', 'new_ward_id'),
                        counts, strict=True), fk_changed=changed)

    def refresh_spatial(self):
        """Tính lại 6 biến đếm POI + POI gần nhất (function refresh_spatial_features())."""
        with self.conn.transaction(), self.conn.cursor() as cur:
            refreshed = cur.execute('SELECT refresh_spatial_features()').fetchone()[0]
            with_geom, features = cur.execute(
                'SELECT count(geom), (SELECT count(*) FROM listing_spatial_features) '
                'FROM listings').fetchone()
        return {'listings_with_geom': with_geom, 'spatial_rows': features, 'refreshed': refreshed}
