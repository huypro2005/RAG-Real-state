"""Dựng document RAG cho từng tin và lưu embedding vào pgvector (bảng rag.listing_embeddings).

Model không chạy trên máy này: vector được lấy từ API embedding chạy trên Kaggle
(notebook src/kaggle/embedding_server.ipynb).
"""
import hashlib
import re
import time

import numpy as np
import requests
from pgvector.psycopg import register_vector
from psycopg.rows import dict_row


class ListingEmbedder:
    """Dựng embedding_text + rag_document, gọi API embedding (Kaggle), upsert vào pgvector.

    Embedding tăng dần: tin nào content_hash không đổi thì không embed lại (chỉ cập nhật
    rag_document, ví dụ khi đặc trưng POI thay đổi). Mỗi request được commit riêng, nên nếu
    API hoặc tunnel Kaggle đứt giữa chừng thì chạy lại sẽ tiếp tục từ phần chưa embed.

    API: POST {api_url}/embed, header X-API-Key, body {"texts": [...]}
         → {"model": "...", "dimension": 1024, "embeddings": [[...], ...]} (đã chuẩn hóa L2)
    """

    MODEL_NAME = 'BAAI/bge-m3'      # phải trùng model API báo về; đổi model thì embed lại hết
    DIMENSION = 1024                # phải trùng vector(1024) trong schema.sql
    REQUEST_BATCH = 128             # số text mỗi request (API Kaggle nhận tối đa 256)
    REQUEST_TIMEOUT = 120           # giây; tunnel Cloudflare tự cắt request quá 100 giây,
                                    # một request 128 text trên GPU T4 chỉ mất vài giây
    MAX_ATTEMPTS = 3                # thử lại khi mất kết nối, timeout hoặc lỗi 5xx của tunnel
    # Số điện thoại không mang ngữ nghĩa, bỏ khỏi embedding_text. Ba dạng: số đầy đủ
    # ('0912.345.678'), số bị website che ('0901 326 ***'), và phần che còn sót ('***').
    PHONE_PATTERN = re.compile(
        r'(?:\+84|0)\d(?:[ .]?\d){8,9}'
        r'|(?:\+84|0)\d(?:[ .]?\d){3,8} ?\*+'
        r'|\*{3,}')

    SOURCE_QUERY = """
        SELECT l.listing_id, l.listing_url, l.title, l.description, l.property_type,
               l.price, l.price_per_m2, l.area, l.frontage, l.bedrooms, l.bathrooms,
               l.road_width, l.floors, l.legal, l.interior, l.district_old,
               l.old_address, l.new_address, l.posted_at, l.expired_at, l.geom IS NOT NULL AS has_geom,
               f.school_count_1km, f.hospital_count_1km, f.market_count_1km,
               f.school_count_3km, f.hospital_count_3km, f.market_count_3km,
               f.nearest_school_name, f.nearest_school_m, f.nearest_hospital_name,
               f.nearest_hospital_m, f.nearest_market_name, f.nearest_market_m
          FROM listing.listings l
          LEFT JOIN listing.listing_spatial_features f USING (listing_id)
         ORDER BY l.listing_id
    """
    UPSERT = """
        INSERT INTO rag.listing_embeddings
               (listing_id, model_name, content_hash, embedding_text, rag_document, embedding)
        VALUES (%(listing_id)s, %(model_name)s, %(content_hash)s, %(embedding_text)s,
                %(rag_document)s, %(embedding)s)
        ON CONFLICT (listing_id) DO UPDATE SET
            model_name = EXCLUDED.model_name, content_hash = EXCLUDED.content_hash,
            embedding_text = EXCLUDED.embedding_text, rag_document = EXCLUDED.rag_document,
            embedding = EXCLUDED.embedding, embedded_at = now()
    """

    def __init__(self, conn, api_url=None, api_key=None, model_name=MODEL_NAME):
        self.conn = conn
        self.model_name = model_name
        self.api_url = (api_url or '').rstrip('/')
        self.session = requests.Session()
        self.session.headers['X-API-Key'] = api_key or ''

    def encode(self, texts):
        """Gọi API lấy vector đã chuẩn hóa (dùng cosine). Cũng dùng để embed câu hỏi khi truy vấn RAG."""
        for attempt in range(1, self.MAX_ATTEMPTS + 1):
            try:
                response = self.session.post(f'{self.api_url}/embed', json={'texts': texts},
                                             timeout=self.REQUEST_TIMEOUT)
                response.raise_for_status()
                break
            except requests.RequestException as error:
                status = error.response.status_code if error.response is not None else None
                if attempt == self.MAX_ATTEMPTS or (status is not None and status < 500):
                    raise      # 401 sai API key, 422 sai dữ liệu...: thử lại cũng vô ích
                print(f'  API lỗi ({error}); thử lại lần {attempt + 1}...', flush=True)
                time.sleep(10 * attempt)

        body = response.json()
        embeddings = np.asarray(body['embeddings'], dtype=np.float32)
        if body['model'] != self.model_name or embeddings.shape != (len(texts), self.DIMENSION):
            raise RuntimeError(
                f"API trả về model {body['model']!r}, shape {embeddings.shape}; "
                f'cần {self.model_name!r}, shape {(len(texts), self.DIMENSION)}')
        return embeddings

    def embed_pending(self):
        """Embed các tin mới hoặc đã đổi nội dung; trả về số liệu."""
        register_vector(self.conn)
        with self.conn.cursor(row_factory=dict_row) as cur:
            cur.execute(self.SOURCE_QUERY)
            documents = [self.build_document(row) for row in cur.fetchall()]
            cur.execute('SELECT listing_id, content_hash FROM rag.listing_embeddings')
            existing = {row['listing_id']: row['content_hash'] for row in cur.fetchall()}
        self.conn.commit()

        pending = [d for d in documents if existing.get(d['listing_id']) != d['content_hash']]
        unchanged = [d for d in documents if existing.get(d['listing_id']) == d['content_hash']]

        for start in range(0, len(pending), self.REQUEST_BATCH):
            batch = pending[start:start + self.REQUEST_BATCH]
            vectors = self.encode([d['embedding_text'] for d in batch])
            with self.conn.transaction(), self.conn.cursor() as cur:
                cur.executemany(self.UPSERT, [
                    {**d, 'model_name': self.model_name, 'embedding': vector}
                    for d, vector in zip(batch, vectors)])
            print(f'  embedded {start + len(batch)}/{len(pending)}', flush=True)

        # Nội dung ngữ nghĩa không đổi nhưng document hiển thị có thể đổi (giá, POI...).
        with self.conn.transaction(), self.conn.cursor() as cur:
            cur.executemany(
                'UPDATE rag.listing_embeddings SET rag_document = %(rag_document)s '
                'WHERE listing_id = %(listing_id)s AND rag_document IS DISTINCT FROM %(rag_document)s',
                unchanged)

        return {'model': self.model_name, 'listings': len(documents),
                'embedded': len(pending), 'unchanged': len(unchanged)}

    def build_document(self, row):
        """Từ một dòng SOURCE_QUERY, dựng embedding_text, rag_document và content_hash."""
        def vn(value, digits=2):
            """Số kiểu Việt Nam: 24.9 -> '24,9', 150.0 -> '150'."""
            return f'{value:.{digits}f}'.rstrip('0').rstrip('.').replace('.', ',')

        def distance(meters):
            return f'{vn(meters / 1000, 1)} km' if meters >= 1000 else f'{meters:.0f} m'

        # Phần ngữ nghĩa: loại, khu vực, tiêu đề, mô tả. Số liệu (giá, diện tích...) để SQL lọc.
        semantic = '\n'.join(filter(None, [
            f"Loại: {row['property_type']}. Khu vực: {row['district_old']}.",
            row['title'], row['description']]))
        embedding_text = re.sub(r'[ \t]+', ' ', self.PHONE_PATTERN.sub('', semantic)).strip()

        price = row['price']
        price_text = f'{vn(price / 1000)} tỷ' if price >= 1000 else f'{vn(price)} triệu'
        if row['price_per_m2']:
            price_text += f" ({vn(row['price_per_m2'])} triệu/m²)"
        details = [f"{label}: {row[field]}" for field, label in (
            ('bedrooms', 'Phòng ngủ'), ('bathrooms', 'Phòng vệ sinh'), ('floors', 'Số tầng'))
            if row[field] is not None]
        details += [f"{label}: {vn(row[field])} m" for field, label in (
            ('frontage', 'Mặt tiền'), ('road_width', 'Đường vào')) if row[field] is not None]

        if row['has_geom'] and row['school_count_1km'] is not None:
            # Tên POI thường đã có tiền tố ('Chợ Phú Nhuận'), nên ghi 'nhãn: tên' để khỏi lặp.
            nearest = [f"{kind}: {row[f'nearest_{key}_name']} ({distance(row[f'nearest_{key}_m'])})"
                       for key, kind in (('school', 'trường học'), ('hospital', 'bệnh viện'),
                                         ('market', 'chợ'))
                       if row[f'nearest_{key}_name']]
            amenities = (
                f"Tiện ích trong 1 km / 3 km: {row['school_count_1km']}/{row['school_count_3km']} "
                f"trường học, {row['hospital_count_1km']}/{row['hospital_count_3km']} bệnh viện, "
                f"{row['market_count_1km']}/{row['market_count_3km']} chợ.\n"
                f"Gần nhất: {'; '.join(nearest)}.")
        else:
            amenities = 'Tiện ích: chưa có tọa độ tin cậy, không tính khoảng cách.'

        dates = ' | '.join(f"{label}: {row[field]:%d/%m/%Y}" for field, label in (
            ('posted_at', 'Ngày đăng'), ('expired_at', 'Hết hạn')) if row[field])
        address = row['old_address'] or ''
        if row['new_address']:
            address += f" (địa chỉ mới: {row['new_address']})"

        rag_document = '\n'.join(filter(None, [
            f"[Tin {row['listing_id']}] {row['title']}",
            f"Loại: {row['property_type']} | Giá: {price_text} | Diện tích: {vn(row['area'])} m²",
            ' | '.join(details),
            ' | '.join(f'{label}: {row[field]}' for field, label in (
                ('legal', 'Pháp lý'), ('interior', 'Nội thất')) if row[field]),
            f'Địa chỉ: {address}',
            amenities,
            dates,
            f"Nguồn: {row['listing_url']}",
            f"Mô tả: {row['description']}" if row['description'] else None,
        ]))

        content_hash = hashlib.sha256(f'{self.model_name}\n{embedding_text}'.encode()).hexdigest()
        return {'listing_id': row['listing_id'], 'embedding_text': embedding_text,
                'rag_document': rag_document, 'content_hash': content_hash}
