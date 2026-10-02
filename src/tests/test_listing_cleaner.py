import unittest

import pandas as pd

from src.pipeline.listing_cleaner import ListingCleaner


def raw_listing(**overrides):
    raw = dict(
        transaction_type='Bán', province_old='Hồ Chí Minh', district_old='Tân Bình',
        old_ward='Phường 15', new_ward='Phường Tân Sơn', new_city='Hồ Chí Minh',
        old_address='34A , Đường Tống Văn Hên, Phường 15, Quận Tân Bình, Hồ Chí Minh',
        old_address_detail='34A, Đường Tống Văn Hên, Phường 15',
        new_address='Phường Tân Sơn, Hồ Chí Minh mới',
        latitude='10.8213708107892', longitude='106.631550023485',
        property_type='Nhà mặt phố', area=150.5, frontage=5.77, bedrooms=14, bathrooms=14,
        road_width=8, legal='Sổ hồng riêng', interior='Đầy đủ tiện nghi.', floors=6,
        price=24900, price_per_m2=165.45, posting_date='27/08/2026',
        expiration_date='11/09/2026', listing_id='46168511',
        listing_url='https://batdongsan.com.vn/x-pr46168511', title='Bán nhà', description='Mô tả',
    )
    raw.update(overrides)
    return raw


def clean_one(**overrides):
    """Làm sạch một tin; trả về (dict tin sạch hoặc None, lý do loại hoặc None)."""
    clean, rejected = ListingCleaner().clean([raw_listing(**overrides)])
    if len(rejected):
        return None, rejected.loc[0, 'reason']
    return clean.iloc[0].to_dict(), None


class NormalizeTests(unittest.TestCase):
    def test_text_and_description(self):
        row, _ = clean_one(old_address='34A , Đường  A,\tPhường 1 ',
                           description='  a  b \n\n\n\n c ', interior='Đầy đủ.')
        self.assertEqual(row['old_address'], '34A, Đường A, Phường 1')
        self.assertEqual(row['description'], 'a b\n\nc')
        self.assertEqual(row['interior'], 'Đầy đủ')
        self.assertEqual(row['raw_record']['interior'], 'Đầy đủ.')
        self.assertEqual(row['new_address'], 'Phường Tân Sơn, Hồ Chí Minh mới')

    def test_legal_group(self):
        cases = {'Sổ đỏ/ Sổ hồng': 'so_do_so_hong', 'SHR': 'so_do_so_hong',
                 'Đang chờ sổ': 'dang_cho_so', 'HĐMB': 'hop_dong_mua_ban',
                 'Pháp lý rõ ràng': 'khac'}
        for legal, expected in cases.items():
            with self.subTest(legal):
                self.assertEqual(clean_one(legal=legal)[0]['legal_group'], expected)
        self.assertTrue(pd.isna(clean_one(legal=None)[0]['legal_group']))

    def test_dates(self):
        row, _ = clean_one(expiration_date='31/02/2026')
        self.assertEqual(row['posted_at'], '2026-08-27')
        self.assertTrue(pd.isna(row['expired_at']))
        self.assertIn('expired_at_invalid', row['quality_flags'])


class FlagTests(unittest.TestCase):
    def test_valid_listing_has_no_flag(self):
        row, reason = clean_one()
        self.assertIsNone(reason)
        self.assertEqual(row['quality_flags'], [])

    def test_out_of_range_values_become_missing(self):
        row, reason = clean_one(floors=3335, road_width=3000, frontage=435,
                                latitude='21.0289486097874', longitude='105.852447225903')
        self.assertIsNone(reason)
        for field in ('floors', 'road_width', 'frontage', 'latitude', 'longitude'):
            self.assertTrue(pd.isna(row[field]), field)
        self.assertEqual(row['raw_record']['floors'], 3335)
        self.assertEqual(set(row['quality_flags']), {
            'floors_out_of_range', 'road_width_out_of_range', 'frontage_out_of_range',
            'coords_outside_hcm'})

    def test_area_thousands_separator(self):
        row, reason = clean_one(price=7500, area=1.437, price_per_m2=5.22)
        self.assertIsNone(reason)
        self.assertEqual(row['area'], 1437)
        self.assertIn('area_thousands_separator_fixed', row['quality_flags'])
        # Không khớp giá/m² của website thì không sửa, vẫn loại.
        self.assertEqual(clean_one(price=1980, area=8, price_per_m2=247.5)[1], 'area_too_small')


class RejectTests(unittest.TestCase):
    def test_reject_reasons(self):
        cases = {
            'missing_price': dict(price=None),
            'area_too_small': dict(area=1),
            'price_equals_price_per_m2': dict(price=66, price_per_m2=66, area=182),
            'price_per_m2_out_of_range': dict(price=13.9, price_per_m2=115.83, area=120),
            'district_outside_old_hcm': dict(district_old='Dĩ An'),
            'missing_listing_id': dict(listing_id=''),
        }
        for expected, overrides in cases.items():
            with self.subTest(expected):
                self.assertEqual(clean_one(**overrides)[1], expected)

    def test_expired_listing_is_kept(self):
        # Lọc tin hết hạn đang tắt: tin hết hạn từ 2020 vẫn được giữ.
        self.assertIsNone(clean_one(expiration_date='01/01/2020')[1])

    def test_deduplicate_keeps_latest(self):
        records = [raw_listing(posting_date='27/08/2026', title='mới'),
                   raw_listing(posting_date='01/08/2026', title='cũ')]
        clean, rejected = ListingCleaner().clean(records)
        self.assertEqual((len(clean), len(rejected)), (1, 0))
        self.assertEqual(clean.loc[0, 'title'], 'mới')


if __name__ == '__main__':
    unittest.main()
