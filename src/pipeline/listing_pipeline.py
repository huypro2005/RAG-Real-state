"""Các bước pipeline dùng chung cho CLI (`python -m src.pipeline`) và giao diện web (`src.pipeline.server`).

    thô → làm sạch → listings (upsert) → FK địa chỉ → đặc trưng POI → (embed) listing_embeddings

Logic nằm ở ListingCleaner / ListingLoader / ListingEmbedder; lớp này chỉ ghép chúng và trả số liệu
từng bước, để CLI in ra và server hiện lên bánh răng cùng một bộ số.
"""
import os
import re
import sys

import psycopg

from .listing_cleaner import ListingCleaner
from .listing_embedder import ListingEmbedder
from .listing_loader import ListingLoader

DEFAULT_DB = 'dbname=housing_dev host=localhost port=5433 user=postgres'


class ListingPipeline:
    """Điều phối các bước; mỗi bước trả một dict số liệu để đối chiếu giữa các lần chạy."""

    CLEAN_NUMBERS = ('input_lines', 'duplicates_removed', 'unique_listings', 'rejected', 'clean')

    def __init__(self, db_url=None):
        self.db_url = db_url or os.environ.get('DATABASE_URL') or DEFAULT_DB
        # DATABASE_URL của backend có dạng postgresql+asyncpg://, psycopg chỉ hiểu postgresql://
        self.db_url = re.sub(r'^postgresql\+\w+://', 'postgresql://', self.db_url)

    def run(self, inputs, output_dir, embed=False, embed_only=False):
        """Chạy cho CLI: in mỗi bước một dòng."""
        with psycopg.connect(self.db_url) as conn:
            print(f'Database: {conn.info.dbname}@{conn.info.host}', flush=True)
            if not embed_only:
                clean, numbers, reasons = self.clean(inputs, output_dir)
                self.report('1/5 Làm sạch', numbers)
                print(f'     lý do loại: {reasons}', flush=True)
                loader = ListingLoader(conn)
                self.report('2/5 Nạp listings', loader.upsert(clean))
                self.report('3/5 FK địa chỉ', loader.link_addresses())
                self.report('4/5 Đặc trưng POI', loader.refresh_spatial())
            if embed or embed_only:
                self.report('5/5 Embedding', self.embed(conn))
            else:
                print('5/5 Bỏ qua embedding (thêm --embed để chạy).')

    def clean(self, inputs, output_dir):
        """Bước 1: làm sạch, ghi file tin sạch / tin bị loại / báo cáo vào output_dir.

        Trả về (DataFrame tin sạch, số liệu chính, lý do loại).
        """
        clean, _, report = ListingCleaner().run([path.resolve() for path in inputs], output_dir.resolve())
        return clean, {key: report[key] for key in self.CLEAN_NUMBERS}, report['reject_reasons']

    @staticmethod
    def embed(conn):
        """Bước 5: embed tin mới hoặc đổi nội dung; model chạy trên Kaggle, không chạy cục bộ.

        Thiếu cấu hình hoặc server Kaggle tắt thì dừng bằng SystemExit kèm lý do (CLI in ra rồi thoát,
        server ghi lý do vào bánh răng).
        """
        api_url, api_key = os.environ.get('EMBEDDING_API_URL'), os.environ.get('EMBEDDING_API_KEY')
        if not (api_url and api_key):
            sys.exit('Thiếu EMBEDDING_API_URL hoặc EMBEDDING_API_KEY trong src/pipeline/.env. Chạy notebook '
                     'src/notebook/kaggle/embedding_server.ipynb để lấy hai giá trị này.')
        embedder = ListingEmbedder(conn, api_url, api_key)
        embedder.check_health()
        result = embedder.embed_pending()
        result['embeddings_in_db'] = conn.execute('SELECT count(*) FROM listing_embeddings').fetchone()[0]
        return result

    @staticmethod
    def report(step, numbers):
        print(f"{step}: {', '.join(f'{k}={v}' for k, v in numbers.items())}", flush=True)
