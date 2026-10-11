"""Chạy pipeline đưa tin đăng vào database cho RAG, mỗi bước in số dòng vào/ra.

    thô → làm sạch → listings (upsert) → FK địa chỉ → đặc trưng POI → (--embed) listing_embeddings

Bảng nằm ở schema public, do Alembic tạo (housing-backend: alembic upgrade head).

Cách chạy (tại thư mục gốc dự án):
    python -m src.pipeline                      # làm sạch, nạp DB, FK địa chỉ, POI
    python -m src.pipeline --embed              # thêm embedding qua API Kaggle
    python -m src.pipeline --embed-only         # chỉ embed tin đã có trong DB
    python -m src.pipeline --input CrawlData/data.json CrawlData/data1.json   # ghép nhiều file

Database: --db-url, nếu không có thì biến DATABASE_URL, nếu không có nữa thì database housing_dev
trên localhost, user postgres (mật khẩu lấy từ PGPASSWORD, đặt trong shell hoặc .env). Pipeline
không tự chọn database `housing` thật; muốn ghi vào đó phải truyền --db-url.
Embedding: đặt EMBEDDING_API_URL và EMBEDDING_API_KEY (notebook src/kaggle/embedding_server.ipynb) vào .env.
"""
import argparse
import os
import re
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv

from .listing_cleaner import ROOT, ListingCleaner
from .listing_embedder import ListingEmbedder
from .listing_loader import ListingLoader

DEFAULT_DB = 'dbname=housing_dev host=localhost user=postgres'


class ListingPipeline:
    """Điều phối các bước; mỗi bước in một dòng số liệu để đối chiếu giữa các lần chạy."""

    def __init__(self, args):
        self.args = args
        self.db_url = args.db_url or os.environ.get('DATABASE_URL') or DEFAULT_DB
        # DATABASE_URL của backend có dạng postgresql+asyncpg://, psycopg chỉ hiểu postgresql://
        self.db_url = re.sub(r'^postgresql\+\w+://', 'postgresql://', self.db_url)

    def run(self):
        with psycopg.connect(self.db_url) as conn:
            print(f'Database: {conn.info.dbname}@{conn.info.host}', flush=True)
            if not self.args.embed_only:
                clean = self.clean()
                loader = ListingLoader(conn)
                self.report('2/5 Nạp listings', loader.upsert(clean))
                self.report('3/5 FK địa chỉ', loader.link_addresses())
                self.report('4/5 Đặc trưng POI', loader.refresh_spatial())
            if self.args.embed or self.args.embed_only:
                self.embed(conn)
            else:
                print('5/5 Bỏ qua embedding (thêm --embed để chạy).')

    def clean(self):
        """Bước 1: làm sạch, ghi file tin sạch / tin bị loại / báo cáo; trả về DataFrame tin sạch."""
        inputs = [path.resolve() for path in self.args.input]
        clean, _, report = ListingCleaner().run(inputs, self.args.output_dir.resolve())
        self.report('1/5 Làm sạch', {
            k: report[k] for k in ('input_lines', 'duplicates_removed', 'unique_listings',
                                   'rejected', 'clean')})
        print(f"     lý do loại: {report['reject_reasons']}", flush=True)
        return clean

    def embed(self, conn):
        """Bước 5: embed tin mới hoặc đổi nội dung; model chạy trên Kaggle, không chạy cục bộ."""
        api_url, api_key = os.environ.get('EMBEDDING_API_URL'), os.environ.get('EMBEDDING_API_KEY')
        if not (api_url and api_key):
            sys.exit('Thiếu EMBEDDING_API_URL hoặc EMBEDDING_API_KEY trong .env. Chạy notebook '
                     'src/kaggle/embedding_server.ipynb để lấy hai giá trị này.')
        embedder = ListingEmbedder(conn, api_url, api_key)
        embedder.check_health()
        result = embedder.embed_pending()
        result['embeddings_in_db'] = conn.execute('SELECT count(*) FROM listing_embeddings').fetchone()[0]
        self.report('5/5 Embedding', result)

    @staticmethod
    def report(step, numbers):
        print(f"{step}: {', '.join(f'{k}={v}' for k, v in numbers.items())}", flush=True)


def main():
    for stream in (sys.stdout, sys.stderr):     # console Windows mặc định cp1252
        stream.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description='Làm sạch tin đăng, nạp PostgreSQL và tạo embedding RAG.')
    parser.add_argument('--input', type=Path, nargs='+', default=[ROOT / 'CrawlData/data.json'],
                        help='file JSON Lines từ crawler (mặc định CrawlData/data.json)')
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'data/listings',
                        help='nơi ghi file tin sạch/tin bị loại/báo cáo làm sạch')
    parser.add_argument('--db-url', help='mặc định: DATABASE_URL, rồi database housing_dev')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--embed', action='store_true', help='sau khi nạp, tạo embedding qua API Kaggle')
    mode.add_argument('--embed-only', action='store_true',
                      help='bỏ qua làm sạch + nạp, chỉ embed tin đã có trong database')
    load_dotenv(ROOT / '.env')
    ListingPipeline(parser.parse_args()).run()


if __name__ == '__main__':
    main()
