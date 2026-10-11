"""Test nạp database trên housing_dev. Mọi thay đổi nằm trong transaction và bị rollback."""
import os
import re
import unittest

import psycopg

from src.pipeline.listing_cleaner import ListingCleaner
from src.pipeline.listing_loader import ListingLoader
from src.tests.test_listing_cleaner import raw_listing

# Chỉ chạy trên housing_dev, không bao giờ trên database `housing` thật.
DB_URL = re.sub(r'^postgresql\+\w+://', 'postgresql://', os.environ.get('DATABASE_URL', ''))


def connect():
    try:
        conn = psycopg.connect(DB_URL)
    except psycopg.Error:
        return None
    if conn.info.dbname != 'housing_dev':
        conn.close()
        return None
    return conn


class ListingLoaderTests(unittest.TestCase):
    def setUp(self):
        conn = connect()
        if conn is None:
            self.skipTest('cần DATABASE_URL trỏ tới housing_dev đã chạy alembic upgrade head')
        self.addCleanup(conn.close)
        self.transaction = conn.transaction(force_rollback=True)
        self.transaction.__enter__()
        self.addCleanup(self.transaction.__exit__, None, None, None)
        self.loader = ListingLoader(conn)

    @staticmethod
    def clean_frame(*overrides):
        """Tin thử có listing_id 'T…' không trùng tin thật."""
        records = [raw_listing(listing_id=f'T{number}', **fields) for number, fields in enumerate(overrides)]
        clean, rejected = ListingCleaner().clean(records)
        assert rejected.empty
        return clean

    def test_upsert_is_idempotent_and_counts_changes(self):
        tins = self.clean_frame({}, {}, {})
        self.assertEqual(self.loader.upsert(tins),
                         {'rows_in': 3, 'inserted': 3, 'updated': 0, 'unchanged': 0})
        self.assertEqual(self.loader.upsert(tins),
                         {'rows_in': 3, 'inserted': 0, 'updated': 0, 'unchanged': 3})
        tins.loc[1, 'title'] = 'tiêu đề mới'
        tins.loc[2, 'bedrooms'] = None
        self.assertEqual(self.loader.upsert(tins),
                         {'rows_in': 3, 'inserted': 0, 'updated': 2, 'unchanged': 1})
        title = self.loader.conn.execute(
            "SELECT title FROM listings WHERE listing_id = 'T1'").fetchone()[0]
        self.assertEqual(title, 'tiêu đề mới')

    def test_link_addresses_and_spatial_features(self):
        self.loader.upsert(self.clean_frame({}, {'latitude': None, 'longitude': None}))

        addresses = self.loader.link_addresses()
        self.assertGreaterEqual(addresses['listings_in_db'], 2)
        row = self.loader.conn.execute(
            'SELECT old_district_id, old_ward_id, new_ward_id FROM listings '
            "WHERE listing_id = 'T0'").fetchone()
        self.assertTrue(all(row), row)      # Tân Bình / Phường 15 / Phường Tân Sơn đều khớp
        self.assertEqual(self.loader.link_addresses()['fk_changed'], 0)

        self.loader.refresh_spatial()
        has_features = [self.loader.conn.execute(
            'SELECT count(*) FROM listing_spatial_features WHERE listing_id = %s', (listing_id,)
        ).fetchone()[0] for listing_id in ('T0', 'T1')]
        self.assertEqual(has_features, [1, 0])      # tin không có tọa độ thì không có đặc trưng


if __name__ == '__main__':
    unittest.main()
