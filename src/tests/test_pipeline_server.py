"""Test server giao diện pipeline, không cần Postgres, Kaggle hay Prediction Server.

Danh sách DB được giả lập; chỉ chạy thử (chỉ bước làm sạch) nên không mở kết nối DB nào.
"""
import json
import shutil
import tempfile
import time
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from src.pipeline.server import RunManager, create_app
from src.tests.test_listing_cleaner import raw_listing


class FakeDatabasesManager(RunManager):
    def databases(self):
        return ['housing_dev']


def jsonl(*records):
    return ''.join(json.dumps(record, ensure_ascii=False) + '\n' for record in records).encode()


class PipelineServerTests(unittest.TestCase):
    def setUp(self):
        self.runs_dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.runs_dir, ignore_errors=True)
        self.manager = FakeDatabasesManager(self.runs_dir, 'postgresql://u@localhost/x', max_upload_mb=1)
        self.client = TestClient(create_app(self.manager))
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)

    def post(self, files, **fields):
        data = {'database': 'housing_dev', 'dry_run': 'true', **fields}
        return self.client.post('/api/runs', data=data, files=[('files', file) for file in files])

    def wait(self, run_id):
        for _ in range(200):
            run = self.client.get(f'/api/runs/{run_id}').json()
            if run['status'] != 'running':
                return run
            time.sleep(0.05)
        self.fail('lần chạy không xong')

    def test_housing_is_rejected_even_via_api(self):
        body = jsonl(raw_listing())
        for dry_run in ('true', 'false'):
            response = self.post([('a.json', body)], database='housing', dry_run=dry_run)
            self.assertEqual(response.status_code, 403)
        self.assertEqual(self.post([('a.json', body)], database='khac', dry_run='false').status_code, 400)
        self.assertEqual(list(self.runs_dir.iterdir()), [])

    def test_bad_files_are_rejected_with_reason(self):
        cases = {
            ('a.csv', b'x'): (400, '.json'),
            ('a.json', b'\n\n'): (400, 'rỗng'),
            ('a.json', b'[{"a": 1}]\n'): (400, 'JSON Lines'),
            ('a.json', b'{\n "a": 1\n}\n'): (400, 'JSON Lines'),
            ('a.json', b'x' * (1024 * 1024 + 10)): (413, 'MB'),
        }
        for file, (status, text) in cases.items():
            response = self.post([file])
            self.assertEqual(response.status_code, status, file[0])
            self.assertIn(text, response.json()['detail'])
        self.assertEqual(list(self.runs_dir.iterdir()), [])     # file bị từ chối không để lại gì
        self.assertIsNone(self.manager.active_id)

    def test_dry_run_cleans_only_and_keeps_report(self):
        traversal = '..\\..\\x.json'
        response = self.post([(traversal, jsonl(raw_listing(), raw_listing(listing_id='2'))),
                              ('b.jsonl', jsonl(raw_listing(), raw_listing(listing_id='3', area=1)))])
        self.assertEqual(response.status_code, 202, response.text)
        run = self.wait(response.json()['id'])

        self.assertEqual(run['status'], 'done')
        self.assertEqual([f['name'] for f in run['files']], ['x.json', 'b.jsonl'])
        self.assertEqual([s['status'] for s in run['steps']], ['done'] + ['skipped'] * 5)
        self.assertEqual(run['steps'][0]['numbers'], {
            'input_lines': 4, 'duplicates_removed': 1, 'unique_listings': 3, 'rejected': 1, 'clean': 2,
            'reject_reasons': {'area_too_small': 1}})
        run_dir = self.runs_dir / run['id']
        self.assertEqual(sorted(p.name for p in run_dir.iterdir()),
                         ['cleaning_report.json', 'listings_rejected.jsonl', 'run.json'])
        self.assertFalse((self.runs_dir.parent / 'x.json').exists())
        report = self.client.get(f"/api/runs/{run['id']}/files/cleaning_report.json")
        self.assertEqual(report.json()['clean'], 2)
        self.assertEqual(self.client.get(f"/api/runs/{run['id']}/files/run.json").status_code, 404)

    def test_busy_while_running(self):
        self.manager.active_id = 'dang-chay'
        response = self.post([('a.json', jsonl(raw_listing()))])
        self.assertEqual(response.status_code, 409)
        self.assertIn('bận', response.json()['detail'])

    def test_history_survives_restart(self):
        run = self.wait(self.post([('a.json', jsonl(raw_listing()))]).json()['id'])
        # Giả lập một lần chạy dở khi server tắt
        broken = json.loads((self.runs_dir / run['id'] / 'run.json').read_text(encoding='utf-8'))
        broken.update(id='20000101-000000-dead', status='running')
        broken['steps'][0]['status'] = 'running'
        (self.runs_dir / broken['id']).mkdir()
        (self.runs_dir / broken['id'] / 'run.json').write_text(json.dumps(broken), encoding='utf-8')

        with TestClient(create_app(FakeDatabasesManager(self.runs_dir, 'postgresql://u@localhost/x'))) as client:
            runs = client.get('/api/runs').json()
            self.assertEqual([r['id'] for r in runs], [run['id'], broken['id']])    # mới nhất trước
            self.assertEqual(runs[1]['status'], 'interrupted')
            self.assertEqual(runs[1]['steps'][0]['status'], 'error')
            report = client.get(f"/api/runs/{run['id']}/files/listings_rejected.jsonl")
            self.assertEqual(report.status_code, 200)

    def test_retrain_reports_clear_reason(self):
        with self.assertRaisesRegex(RuntimeError, 'PREDICTION_SERVER_URL'):
            self.manager.retrain()
        offline = RunManager(self.runs_dir, '', prediction_url='http://127.0.0.1:9', prediction_key='k')
        with self.assertRaisesRegex(RuntimeError, 'không phản hồi'):
            offline.retrain()


if __name__ == '__main__':
    unittest.main()
