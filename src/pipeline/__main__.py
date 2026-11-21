"""Chạy pipeline đưa tin đăng vào database cho RAG, mỗi bước in số dòng vào/ra.

    thô → làm sạch → listings (upsert) → FK địa chỉ → đặc trưng POI → (--embed) listing_embeddings

Bảng nằm ở schema public, do Alembic tạo (housing-backend: alembic upgrade head).

Cách chạy (tại thư mục gốc dự án):
    python -m src.pipeline                      # làm sạch, nạp DB, FK địa chỉ, POI
    python -m src.pipeline --embed              # thêm embedding qua API Kaggle
    python -m src.pipeline --embed-only         # chỉ embed tin đã có trong DB
    python -m src.pipeline --input CrawlData/data.json CrawlData/data1.json   # ghép nhiều file

Database: --db-url, nếu không có thì biến DATABASE_URL, nếu không có nữa thì database housing_dev
trên localhost, user postgres (mật khẩu lấy từ PGPASSWORD, đặt trong shell hoặc src/pipeline/.env). Pipeline
không tự chọn database `housing` thật; muốn ghi vào đó phải truyền --db-url.
Embedding: đặt EMBEDDING_API_URL và EMBEDDING_API_KEY (notebook src/notebook/kaggle/embedding_server.ipynb) vào src/pipeline/.env.
Giao diện web kéo thả file: python -m src.pipeline.server (cổng 8200, xem src/pipeline/README.md).
"""
import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

from .listing_pipeline import ListingPipeline


def main():
    for stream in (sys.stdout, sys.stderr):     # console Windows mặc định cp1252
        stream.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description='Làm sạch tin đăng, nạp PostgreSQL và tạo embedding RAG.')
    parser.add_argument('--input', type=Path, nargs='+', default=['./input/data.json'],
                        help='file JSON Lines từ crawler (mặc định CrawlData/data.json)')
    parser.add_argument('--output-dir', type=Path, default='./output/listings',
                        help='nơi ghi file tin sạch/tin bị loại/báo cáo làm sạch')
    parser.add_argument('--db-url', help='mặc định: DATABASE_URL, rồi database housing_dev')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--embed', action='store_true', help='sau khi nạp, tạo embedding qua API Kaggle')
    mode.add_argument('--embed-only', action='store_true',
                      help='bỏ qua làm sạch + nạp, chỉ embed tin đã có trong database')
    load_dotenv(Path(__file__).resolve().parent / '.env')  # .env riêng của pipeline
    args = parser.parse_args()
    ListingPipeline(args.db_url).run(args.input, args.output_dir, args.embed, args.embed_only)


if __name__ == '__main__':
    main()
