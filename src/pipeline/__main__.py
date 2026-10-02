"""Chạy toàn bộ pipeline đưa tin đăng vào database cho RAG.

    data.json → ListingCleaner → ListingLoader (listing.*) → ListingEmbedder (rag.*)

Cách chạy (tại thư mục gốc dự án):
    python -m src.pipeline                   # làm sạch, nạp DB, tính POI, embed
    python -m src.pipeline --skip-embed      # chỉ làm sạch + nạp DB + tính POI

Kết nối PostgreSQL qua biến môi trường chuẩn PGHOST/PGPORT/PGDATABASE/PGUSER/PGPASSWORD
(đặt trong shell hoặc file .env). Mặc định: localhost:5432, database housing, user postgres.
Embedding gọi API chạy trên Kaggle (src/kaggle/embedding_server.ipynb): đặt EMBEDDING_API_URL
và EMBEDDING_API_KEY mà notebook in ra vào file .env.
"""
import argparse
import json
import os
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv

from .listing_cleaner import ROOT, ListingCleaner
from .listing_embedder import ListingEmbedder
from .listing_loader import ListingLoader


def main():
    for stream in (sys.stdout, sys.stderr):     # console Windows mặc định cp1252
        stream.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description='Làm sạch tin đăng, nạp PostgreSQL và tạo embedding RAG.')
    parser.add_argument('--input', type=Path, default=ROOT / 'CrawlData/data.json')
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'data/listings',
                        help='nơi ghi file tin sạch/tin bị loại/báo cáo làm sạch')
    parser.add_argument('--skip-embed', action='store_true', help='không tạo embedding')
    args = parser.parse_args()

    load_dotenv(ROOT / '.env')
    for name, value in (('PGHOST', 'localhost'), ('PGPORT', '5432'),
                        ('PGDATABASE', 'housing'), ('PGUSER', 'postgres')):
        os.environ.setdefault(name, value)
    api_url, api_key = os.environ.get('EMBEDDING_API_URL'), os.environ.get('EMBEDDING_API_KEY')
    if not args.skip_embed and not (api_url and api_key):
        parser.error('thiếu EMBEDDING_API_URL hoặc EMBEDDING_API_KEY trong .env. Chạy notebook '
                     'src/kaggle/embedding_server.ipynb để lấy hai giá trị này, hoặc dùng --skip-embed.')

    print('1/3 Làm sạch dữ liệu...', flush=True)
    clean, _, cleaning = ListingCleaner().run(args.input.resolve(), args.output_dir.resolve())
    summary = {'cleaning': {k: cleaning[k] for k in (
        'input_lines', 'duplicates_removed', 'rejected', 'clean', 'reject_reasons')}}

    with psycopg.connect() as conn:
        print('2/3 Nạp database và tính đặc trưng POI...', flush=True)
        source_file = args.input.resolve()
        summary['loading'] = ListingLoader(conn).load(
            clean, source_file.relative_to(ROOT) if source_file.is_relative_to(ROOT) else source_file)

        if args.skip_embed:
            print('3/3 Bỏ qua embedding (--skip-embed).')
        else:
            print(f'3/3 Tạo embedding qua API {api_url} ...', flush=True)
            summary['embedding'] = ListingEmbedder(conn, api_url, api_key).embed_pending()

    print(json.dumps(summary, ensure_ascii=False, indent=2, default=int))


if __name__ == '__main__':
    main()
