import unittest
from datetime import date
from unittest import mock

import requests

from src.pipeline.listing_embedder import ListingEmbedder


def source_row(**overrides):
    """Một dòng giống kết quả ListingEmbedder.SOURCE_QUERY."""
    row = dict(
        listing_id='46168511', listing_url='https://batdongsan.com.vn/x-pr46168511',
        title='Bán CHDV Tân Bình. Liên hệ 0901 326 ***',
        description='Nhà 6 tầng, 14 phòng.\nGọi 0912.345.678 để xem nhà.',
        property_type='Nhà mặt phố', price=24900, price_per_m2=165.45, area=150.5,
        frontage=5.77, bedrooms=14, bathrooms=14, road_width=8, floors=6,
        legal='Sổ hồng riêng', interior='Đầy đủ tiện nghi', district_old='Tân Bình',
        old_address='34A, Đường Tống Văn Hên, Phường 15, Quận Tân Bình, Hồ Chí Minh',
        new_address='Phường Tân Sơn, Hồ Chí Minh mới',
        posted_at=date(2026, 8, 27), expired_at=date(2026, 9, 11), has_geom=True,
        school_count_1km=12, hospital_count_1km=2, market_count_1km=1,
        school_count_3km=80, hospital_count_3km=15, market_count_3km=6,
        nearest_school_name='THCS A', nearest_school_m=250.4,
        nearest_hospital_name='BV B', nearest_hospital_m=1234.0,
        nearest_market_name='Chợ C', nearest_market_m=640.0,
    )
    row.update(overrides)
    return row


class BuildDocumentTests(unittest.TestCase):
    def setUp(self):
        self.embedder = ListingEmbedder(conn=None)

    def test_embedding_text_is_semantic_only(self):
        text = self.embedder.build_document(source_row())['embedding_text']
        self.assertTrue(text.startswith('Loại: Nhà mặt phố. Khu vực: Tân Bình.'))
        self.assertIn('Nhà 6 tầng, 14 phòng.', text)
        for phone in ('0901', '***', '0912.345.678'):
            self.assertNotIn(phone, text)
        self.assertNotIn('24,9 tỷ', text)   # giá để SQL lọc, không nhúng vector

    def test_rag_document_has_facts_for_llm(self):
        doc = self.embedder.build_document(source_row())['rag_document']
        for expected in ('[Tin 46168511]', 'Giá: 24,9 tỷ (165,45 triệu/m²)', 'Diện tích: 150,5 m²',
                         'Phòng ngủ: 14', 'Mặt tiền: 5,77 m', 'Pháp lý: Sổ hồng riêng',
                         '(địa chỉ mới: Phường Tân Sơn, Hồ Chí Minh mới)',
                         '12/80 trường học', 'bệnh viện: BV B (1,2 km)', 'trường học: THCS A (250 m)',
                         'Ngày đăng: 27/08/2026 | Hết hạn: 11/09/2026',
                         'Nguồn: https://batdongsan.com.vn/x-pr46168511'):
            self.assertIn(expected, doc)

    def test_missing_values_are_omitted(self):
        doc = self.embedder.build_document(source_row(
            price=850, price_per_m2=None, bedrooms=None, frontage=None, legal=None,
            new_address=None, has_geom=False, school_count_1km=None))['rag_document']
        self.assertIn('Giá: 850 triệu |', doc)
        for absent in ('Phòng ngủ', 'Mặt tiền', 'Pháp lý', 'địa chỉ mới', 'triệu/m²'):
            self.assertNotIn(absent, doc)
        self.assertIn('chưa có tọa độ tin cậy', doc)

    def test_hash_changes_with_semantic_text_or_model_only(self):
        base = self.embedder.build_document(source_row())['content_hash']
        self.assertEqual(base, self.embedder.build_document(source_row(price=1))['content_hash'])
        self.assertNotEqual(base, self.embedder.build_document(source_row(title='Khác'))['content_hash'])
        other_model = ListingEmbedder(conn=None, model_name='other').build_document(source_row())
        self.assertNotEqual(base, other_model['content_hash'])


def api_response(status=200, model='BAAI/bge-m3', count=2, dimension=1024):
    """Response giả của API Kaggle; không gọi mạng, không chạy model."""
    response = mock.Mock(status_code=status)
    response.json.return_value = {'model': model, 'dimension': dimension,
                                  'embeddings': [[0.1] * dimension] * count}
    if status >= 400:
        error = requests.HTTPError(f'{status} error')
        error.response = response
        response.raise_for_status.side_effect = error
    return response


class EncodeApiTests(unittest.TestCase):
    def setUp(self):
        self.embedder = ListingEmbedder(None, 'https://x.trycloudflare.com/', 'secret')
        # Bỏ thời gian chờ và thông báo in ra khi thử lại.
        for target in ('src.pipeline.listing_embedder.time.sleep', 'builtins.print'):
            patcher = mock.patch(target)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_sends_texts_with_api_key(self):
        with mock.patch.object(self.embedder.session, 'post', return_value=api_response()) as post:
            vectors = self.embedder.encode(['a', 'b'])
        self.assertEqual(vectors.shape, (2, 1024))
        post.assert_called_once_with('https://x.trycloudflare.com/embed', json={'texts': ['a', 'b']},
                                     timeout=ListingEmbedder.REQUEST_TIMEOUT)
        self.assertEqual(self.embedder.session.headers['X-API-Key'], 'secret')

    def test_retries_tunnel_errors_then_succeeds(self):
        responses = [requests.ConnectionError('tunnel down'), api_response(502), api_response()]
        with mock.patch.object(self.embedder.session, 'post', side_effect=responses) as post:
            self.assertEqual(self.embedder.encode(['a', 'b']).shape, (2, 1024))
        self.assertEqual(post.call_count, 3)

    def test_wrong_api_key_is_not_retried(self):
        with mock.patch.object(self.embedder.session, 'post', return_value=api_response(401)) as post:
            with self.assertRaises(requests.HTTPError):
                self.embedder.encode(['a', 'b'])
        self.assertEqual(post.call_count, 1)

    def test_rejects_wrong_model_or_shape(self):
        for bad in (api_response(model='other'), api_response(count=1), api_response(dimension=768)):
            with self.subTest(bad.json.return_value['model']):
                with mock.patch.object(self.embedder.session, 'post', return_value=bad):
                    with self.assertRaises(RuntimeError):
                        self.embedder.encode(['a', 'b'])


if __name__ == '__main__':
    unittest.main()
