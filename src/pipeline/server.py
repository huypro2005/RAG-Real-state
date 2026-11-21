"""Giao diện web nạp dữ liệu: kéo thả file JSON Lines crawl → pipeline chạy nền → dữ liệu vào DB.

Chạy tại thư mục gốc dự án (chỉ nghe 127.0.0.1, cổng 8200, đọc src/pipeline/.env):
    python -m src.pipeline.server
    uvicorn --factory src.pipeline.server:create_app --host 127.0.0.1 --port 8200

Mỗi lần chạy là một thư mục output/pipeline_runs/<run_id>/: run.json (cấu hình, trạng thái, số liệu
từng bước), cleaning_report.json, listings_rejected.jsonl. File tải lên chỉ nằm tạm trong
<run_id>/uploads/ và bị xóa khi chạy xong; lịch sử chỉ giữ tên file.
"""
import json
import os
import re
import secrets
import shutil
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import ClassVar

import psycopg
import requests
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from psycopg.conninfo import make_conninfo

from .listing_cleaner import ROOT
from .listing_loader import ListingLoader
from .listing_pipeline import ListingPipeline

PIPELINE_DIR = Path(__file__).resolve().parent
STATIC_DIR = PIPELINE_DIR / 'static'


class RunManager:
    """Nhận file, kiểm tra cấu hình, chạy pipeline nền (một job mỗi lúc) và giữ lịch sử trên đĩa.

    Trạng thái bước: pending (chờ), running, done, error, skipped (bỏ qua, kèm lý do).
    Worker thread sửa run, API đọc run: mọi truy cập đi qua self.lock.
    """

    STEPS: ClassVar[list[tuple[str, str]]] = [
        ('clean', 'Làm sạch'), ('upsert', 'Nạp listings'), ('link', 'Gắn địa chỉ (FK)'),
        ('spatial', 'Tiện ích quanh nhà (POI)'), ('embed', 'Embedding (Kaggle)'),
        ('retrain', 'Retrain mô hình giá'),
    ]
    # Công tắc gửi từ form và giá trị mặc định (embedding, retrain mặc định tắt theo spec)
    FLAGS: ClassVar[dict[str, bool]] = {
        'dry_run': False, 'upsert': True, 'link': True, 'spatial': True, 'embed': False, 'retrain': False}
    BLOCKED_DATABASES: ClassVar[set[str]] = {'housing'}   # DB cũ, chỉ đọc: chặn ở server, không chỉ ở UI
    DEFAULT_DATABASE = 'housing_dev'
    DOWNLOADS: ClassVar[tuple[str, ...]] = ('cleaning_report.json', 'listings_rejected.jsonl')
    UPLOAD_SUFFIXES: ClassVar[tuple[str, ...]] = ('.json', '.jsonl')
    CHUNK = 1024 * 1024

    def __init__(self, runs_dir, database_url, max_upload_mb=100, prediction_url='', prediction_key=''):
        self.runs_dir = Path(runs_dir)
        self.database_url = ListingPipeline(database_url).db_url
        self.max_upload_bytes = int(max_upload_mb * 1024 * 1024)
        self.prediction_url = (prediction_url or '').rstrip('/')
        self.prediction_key = prediction_key or ''
        self.runs = {}
        self.active_id = None
        self.lock = threading.Lock()

    @classmethod
    def from_env(cls):
        """Đọc src/pipeline/.env (biến môi trường của shell được ưu tiên, như CLI)."""
        load_dotenv(PIPELINE_DIR / '.env')
        return cls(
            runs_dir=os.environ.get('PIPELINE_RUNS_DIR') or ROOT / 'output' / 'pipeline_runs',
            database_url=os.environ.get('DATABASE_URL'),
            max_upload_mb=float(os.environ.get('PIPELINE_MAX_UPLOAD_MB') or 100),
            prediction_url=os.environ.get('PREDICTION_SERVER_URL', ''),
            prediction_key=os.environ.get('PREDICTION_SERVER_API_KEY', ''))

    # ---- Cấu hình -------------------------------------------------------------------------

    def settings(self):
        """Dữ liệu cho khung cấu hình của trang (không trả URL/khóa bí mật)."""
        databases = self.databases()
        return {
            'databases': databases,
            'default_database': self.DEFAULT_DATABASE if self.DEFAULT_DATABASE in databases
            else (databases or [None])[0],
            'flags': self.FLAGS,
            'max_upload_mb': self.max_upload_bytes / 1024 / 1024,
            'embedding_configured': bool(os.environ.get('EMBEDDING_API_URL') and os.environ.get('EMBEDDING_API_KEY')),
            'retrain_configured': bool(self.prediction_url and self.prediction_key),
            'active_run_id': self.active_id,
        }

    def target_url(self, database):
        return make_conninfo(self.database_url, dbname=database)

    def databases(self):
        """Các DB trên cùng Postgres với DATABASE_URL có bảng public.listings, trừ DB bị chặn."""
        with psycopg.connect(self.database_url, connect_timeout=5) as conn:
            names = [row[0] for row in conn.execute(
                'SELECT datname FROM pg_database WHERE datallowconn AND NOT datistemplate ORDER BY datname')]
        usable = []
        for name in names:
            if name in self.BLOCKED_DATABASES:
                continue
            try:
                with psycopg.connect(self.target_url(name), connect_timeout=5) as conn:
                    if conn.execute("SELECT to_regclass('public.listings') IS NOT NULL").fetchone()[0]:
                        usable.append(name)
            except psycopg.Error:
                continue    # không có quyền vào DB đó thì coi như không dùng được
        return usable

    # ---- Nhận job --------------------------------------------------------------------------

    async def start(self, form):
        """Kiểm tra cấu hình + file, lưu file vào thư mục lần chạy, rồi chạy nền. Lỗi trả 4xx."""
        config = {key: form.get(key, str(default).lower()) == 'true' for key, default in self.FLAGS.items()}
        database = form.get('database') or None
        if database in self.BLOCKED_DATABASES:
            raise HTTPException(403, f'DB "{database}" là DB cũ chỉ đọc, pipeline không được ghi vào.')
        if config['dry_run']:
            database = None
        elif database not in self.databases():
            raise HTTPException(400, f'DB đích "{database}" không có trong danh sách (cần có bảng listings).')
        uploads = form.getlist('files')
        if not uploads:
            raise HTTPException(400, 'Chưa chọn file nào.')

        run_id = f"{datetime.now():%Y%m%d-%H%M%S}-{secrets.token_hex(2)}"
        with self.lock:
            if self.active_id:
                raise HTTPException(409, f'Đang bận: lần chạy {self.active_id} chưa xong, chờ xong rồi chạy tiếp.')
            self.active_id = run_id     # giữ chỗ ngay để hai request cùng lúc không cùng chạy
        run_dir = self.runs_dir / run_id
        try:
            files, inputs = await self.save_uploads(uploads, run_dir / 'uploads')
        except BaseException:
            shutil.rmtree(run_dir, ignore_errors=True)  # file bị từ chối: không để lại gì
            with self.lock:
                self.active_id = None
            raise

        run = {
            'id': run_id, 'created_at': datetime.now().astimezone().isoformat(timespec='seconds'),
            'finished_at': None, 'seconds': None, 'status': 'running', 'database': database,
            'config': config, 'files': files, 'error': None, 'downloads': [],
            'steps': [{'key': key, 'name': name, **self.plan(key, config)} for key, name in self.STEPS],
        }
        with self.lock:
            self.runs[run_id] = run
        self.save(run)
        threading.Thread(target=self.execute, args=(run, inputs), daemon=True).start()
        return self.snapshot(run)

    async def save_uploads(self, uploads, upload_dir):
        """Ghi từng file theo khối với tên do server đặt (input_1.jsonl...), không dùng tên người gửi
        làm đường dẫn; kiểm tra đuôi, dung lượng tổng và dòng đầu là object JSON (JSON Lines)."""
        upload_dir.mkdir(parents=True)
        files, inputs, total = [], [], 0
        for number, upload in enumerate(uploads, 1):
            name = re.split(r'[\\/]', upload.filename or '')[-1] or f'file {number}'
            if not name.lower().endswith(self.UPLOAD_SUFFIXES):
                raise HTTPException(400, f'"{name}": chỉ nhận file .json hoặc .jsonl (JSON Lines).')
            path, size = upload_dir / f'input_{number}.jsonl', 0
            with path.open('wb') as stream:
                while chunk := await upload.read(self.CHUNK):
                    size += len(chunk)
                    total += len(chunk)
                    if total > self.max_upload_bytes:
                        raise HTTPException(413, f'Tổng dung lượng vượt {self.max_upload_bytes // 1024 // 1024} MB.')
                    stream.write(chunk)
            self.check_json_lines(name, path)
            files.append({'name': name, 'bytes': size})
            inputs.append(path)
        return files, inputs

    @staticmethod
    def check_json_lines(name, path):
        """Từ chối file rỗng hoặc không phải JSON Lines (dòng đầu phải là một object JSON).
        Dòng hỏng ở giữa file không chặn cả file: ListingCleaner đếm vào malformed_lines."""
        try:
            with path.open(encoding='utf-8') as stream:
                first = next((line for line in stream if line.strip()), None)
        except UnicodeDecodeError:
            raise HTTPException(400, f'"{name}": không đọc được dạng UTF-8.') from None
        if first is None:
            raise HTTPException(400, f'"{name}": file rỗng.')
        try:
            record = json.loads(first)
        except json.JSONDecodeError:
            record = None
        if not isinstance(record, dict):
            raise HTTPException(400, f'"{name}": không phải JSON Lines (mỗi dòng phải là một object JSON '
                                     'như data.json của crawler).')

    def plan(self, key, config):
        """Trạng thái ban đầu của một bước: pending nếu sẽ chạy, skipped kèm lý do nếu không."""
        reason = None
        if key == 'clean':
            pass
        elif config['dry_run']:
            reason = 'Chạy thử: không ghi DB'
        elif key != 'upsert' and not config['upsert']:
            reason = 'Bước nạp listings đang tắt'
        elif not config[key]:
            reason = 'Đã tắt'
        return {'status': 'skipped' if reason else 'pending', 'numbers': None, 'error': reason,
                'seconds': None}

    # ---- Chạy nền ---------------------------------------------------------------------------

    def execute(self, run, inputs):
        """Worker thread: bước 1 rồi các bước DB; bước nào còn chờ khi kết thúc là do bước trước lỗi."""
        run_dir, started = self.runs_dir / run['id'], time.monotonic()
        cleaned = {}

        def clean():
            cleaned['frame'], numbers, reasons = ListingPipeline().clean(inputs, run_dir)
            return {**numbers, 'reject_reasons': reasons}

        try:
            if self.run_step(run, 'clean', clean):
                self.load(run, cleaned['frame'])
        except Exception as error:  # noqa: BLE001 - lỗi ngoài dự kiến: ghi lịch sử thay vì treo "đang chạy"
            run['error'] = f'{type(error).__name__}: {error}'
        finally:
            # Không giữ dữ liệu thô; tin sạch đã nằm trong DB, chỉ giữ báo cáo + tin bị loại
            shutil.rmtree(run_dir / 'uploads', ignore_errors=True)
            (run_dir / 'listings_clean.jsonl').unlink(missing_ok=True)
            with self.lock:
                for step in run['steps']:
                    if step['status'] == 'pending':
                        step.update(status='skipped', error='Bước phụ thuộc bị lỗi')
                failed = run['error'] or any(step['status'] == 'error' for step in run['steps'])
                run.update(status='error' if failed else 'done', seconds=round(time.monotonic() - started, 1),
                           finished_at=datetime.now().astimezone().isoformat(timespec='seconds'),
                           downloads=[name for name in self.DOWNLOADS if (run_dir / name).exists()])
                self.active_id = None
            self.save(run)

    def load(self, run, frame):
        """Bước 2–6 trên một kết nối tới DB đích (mỗi bước của loader là một transaction riêng)."""
        if self.step(run, 'upsert')['status'] != 'pending':
            return
        pipeline = ListingPipeline(self.target_url(run['database']))
        try:
            conn = psycopg.connect(pipeline.db_url, connect_timeout=10)
        except psycopg.Error as error:
            self.finish_step(run, 'upsert', error=f'Không kết nối được DB {run["database"]}: {error}')
            return
        with conn:
            loader = ListingLoader(conn)
            if not self.run_step(run, 'upsert', lambda: loader.upsert(frame)):
                return
            actions = {'link': loader.link_addresses, 'spatial': loader.refresh_spatial,
                       'embed': lambda: pipeline.embed(conn), 'retrain': self.retrain}
            for key, action in actions.items():
                if self.step(run, key)['status'] == 'pending':
                    self.run_step(run, key, action)

    def run_step(self, run, key, action):
        """Chạy một bước, ghi số liệu hoặc lý do lỗi; trả True nếu xong.

        Bắt cả SystemExit vì ListingPipeline.embed / ListingEmbedder.check_health báo lỗi bằng sys.exit.
        """
        with self.lock:
            self.step(run, key).update(status='running', started=time.monotonic())
        self.save(run)
        try:
            numbers = action()
        except (Exception, SystemExit) as error:  # noqa: BLE001 - lỗi bất kỳ của bước: bánh răng đỏ kèm lý do
            self.finish_step(run, key, error=str(error) or type(error).__name__)
            return False
        self.finish_step(run, key, numbers=numbers)
        return True

    def finish_step(self, run, key, numbers=None, error=None):
        with self.lock:
            step = self.step(run, key)
            started = step.pop('started', None)
            step.update(status='error' if error else 'done', numbers=numbers, error=error,
                        seconds=round(time.monotonic() - started, 1) if started else None)
        self.save(run)

    def retrain(self):
        """Bước 6: chỉ gửi yêu cầu; Prediction Server retrain nền và trả job_id để theo dõi."""
        if not (self.prediction_url and self.prediction_key):
            raise RuntimeError('Thiếu PREDICTION_SERVER_URL hoặc PREDICTION_SERVER_API_KEY trong src/pipeline/.env.')
        try:
            response = requests.post(f'{self.prediction_url}/api/v1/retrain',
                                     headers={'X-API-Key': self.prediction_key}, timeout=15)
        except requests.RequestException as error:
            raise RuntimeError(f'Prediction Server không phản hồi tại {self.prediction_url} '
                               f'({type(error).__name__}). Bật Prediction Server rồi chạy lại, hoặc tắt retrain.'
                               ) from None
        if response.status_code == 401:
            raise RuntimeError('Prediction Server từ chối: sai PREDICTION_SERVER_API_KEY.')
        if response.status_code != 202:
            raise RuntimeError(f'Prediction Server trả HTTP {response.status_code}: {response.text[:200]}')
        job_id = response.json()['job_id']
        return {'job_id': job_id, 'note': 'Đã gửi yêu cầu; retrain chạy nền ở Prediction Server',
                'status_url': f'{self.prediction_url}/api/v1/jobs/{job_id}'}

    # ---- Lịch sử -----------------------------------------------------------------------------

    @staticmethod
    def step(run, key):
        return next(step for step in run['steps'] if step['key'] == key)

    def snapshot(self, run):
        """Bản sao an toàn để trả API trong khi worker còn sửa run."""
        with self.lock:
            return json.loads(json.dumps(run, default=str))

    def save(self, run):
        """Ghi run.json qua file tạm rồi đổi tên, để server tắt ngang không để lại file hỏng."""
        path = self.runs_dir / run['id'] / 'run.json'
        text = json.dumps(self.snapshot(run), ensure_ascii=False, indent=2)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.with_suffix('.tmp').write_text(text, encoding='utf-8')
        path.with_suffix('.tmp').replace(path)

    def load_history(self):
        """Đọc lại các lần chạy cũ khi khởi động; lần đang chạy dở lúc server tắt thì đánh dấu dừng."""
        for path in sorted(self.runs_dir.glob('*/run.json')):
            run = json.loads(path.read_text(encoding='utf-8'))
            self.runs[run['id']] = run
            if run['status'] == 'running':
                for step in run['steps']:
                    if step['status'] in ('running', 'pending'):
                        step.update(status='error', error='Server dừng khi bước này chưa xong')
                        step.pop('started', None)
                run['status'] = 'interrupted'
                shutil.rmtree(path.parent / 'uploads', ignore_errors=True)
                self.save(run)

    def history(self):
        with self.lock:
            runs = sorted(self.runs.values(), key=lambda run: run['id'], reverse=True)
        return [self.snapshot(run) for run in runs]

    def get(self, run_id):
        run = self.runs.get(run_id)
        if run is None:
            raise HTTPException(404, 'Không có lần chạy này.')
        return run

    def download_path(self, run_id, name):
        """Chỉ cho tải các file báo cáo cố định trong thư mục lần chạy (tên lấy từ danh sách, không từ URL)."""
        run = self.get(run_id)
        if name not in self.DOWNLOADS or not (self.runs_dir / run['id'] / name).exists():
            raise HTTPException(404, 'Không có file báo cáo này.')
        return self.runs_dir / run['id'] / name


def create_app(manager=None):
    """Tạo app; test truyền RunManager riêng (thư mục tạm), chạy thật thì đọc src/pipeline/.env."""
    manager = manager or RunManager.from_env()

    @asynccontextmanager
    async def lifespan(_app):
        manager.load_history()
        yield

    app = FastAPI(title='Pipeline UI', lifespan=lifespan)
    app.state.manager = manager
    app.mount('/static', StaticFiles(directory=STATIC_DIR), name='static')

    @app.get('/', include_in_schema=False)
    def index():
        return FileResponse(STATIC_DIR / 'index.html')

    @app.get('/api/settings')
    def settings():
        try:
            return manager.settings()
        except psycopg.Error as error:
            raise HTTPException(503, f'Không kết nối được Postgres theo DATABASE_URL: {error}') from None

    @app.get('/api/runs')
    def runs():
        return manager.history()

    @app.get('/api/runs/{run_id}')
    def run(run_id: str):
        return manager.snapshot(manager.get(run_id))

    @app.post('/api/runs', status_code=202)
    async def create_run(request: Request):
        # Chặn sớm theo Content-Length, trước khi đọc body (cộng 1 MB cho phần form ngoài file)
        if int(request.headers.get('content-length') or 0) > manager.max_upload_bytes + 1024 * 1024:
            raise HTTPException(413, f'Tổng dung lượng vượt {manager.max_upload_bytes // 1024 // 1024} MB.')
        async with request.form() as form:
            return await manager.start(form)

    @app.get('/api/runs/{run_id}/files/{name}')
    def download(run_id: str, name: str):
        return FileResponse(manager.download_path(run_id, name), filename=f'{run_id}_{name}')

    return app


def main():
    import uvicorn

    uvicorn.run(create_app(), host='127.0.0.1', port=8200)


if __name__ == '__main__':
    main()
