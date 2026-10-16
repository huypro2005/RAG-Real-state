"""Truy vấn chỉ đọc database housing cho FastAPI: tin bất động sản, tiện ích (POI), RAG, đơn vị hành chính.

Mọi bảng nằm trong schema public (cấu trúc do Alembic ở housing-backend tạo). Ghi dữ liệu do
pipeline (python -m src.pipeline) và housing-backend/scripts/*.py đảm nhiệm; mọi connection
ở đây đặt default_transaction_read_only=on nên API không thể sửa database dù có lỗi code.

Dùng trong FastAPI:

    repo = HousingRepository()

    @asynccontextmanager
    async def lifespan(app):
        await repo.open()
        yield
        await repo.close()

Kết nối đọc từ biến môi trường libpq (PGHOST, PGPORT, PGDATABASE, PGUSER, PGPASSWORD hoặc pgpass),
mặc định database housing như src/pipeline/__main__.py.
"""
import os
from typing import ClassVar

import numpy as np
from pgvector.psycopg import register_vector_async
from psycopg import sql
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool


class HousingRepository:
    """Repository chỉ đọc trên pool connection async; mỗi method trả list[dict] sẵn cho Pydantic.

    Đơn vị giữ như database: price (triệu VND), price_per_m2 (triệu/m²), area (m²), khoảng cách (mét).
    """

    POI_TYPES = ('truong_hoc', 'benh_vien', 'cho')
    # Cột trả về khi tìm kiếm; bỏ description cho nhẹ (lấy đủ qua get_listings).
    LISTING_COLUMNS: ClassVar[list[str]] = [
        'listing_id', 'listing_url', 'title', 'transaction_type', 'property_type', 'price',
        'price_per_m2', 'area', 'frontage', 'bedrooms', 'bathrooms', 'road_width', 'floors',
        'legal', 'legal_group', 'interior', 'province_old', 'district_old', 'old_ward',
        'old_address', 'new_ward', 'new_city', 'new_address', 'latitude', 'longitude',
        'posted_at', 'expired_at',
    ]
    DETAIL_COLUMNS: ClassVar[list[str]] = LISTING_COLUMNS + [
        'description', 'old_address_detail', 'quality_flags', 'first_loaded_at', 'updated_at',
    ]
    SPATIAL_COLUMNS: ClassVar[list[str]] = [
        'school_count_1km', 'hospital_count_1km', 'market_count_1km',
        'school_count_3km', 'hospital_count_3km', 'market_count_3km',
        'nearest_school_name', 'nearest_school_m', 'nearest_hospital_name', 'nearest_hospital_m',
        'nearest_market_name', 'nearest_market_m',
    ]
    POI_COLUMNS: ClassVar[list[str]] = [
        'id', 'poi_type', 'poi_subtype', 'name', 'address_old', 'address_new', 'latitude',
        'longitude', 'ownership', 'school_level_codes',
    ]
    # Bảng địa chỉ -> (cột khóa, cột khóa cha); tỉnh không có cha. Khóa là `id` tự tăng
    # (mã batdongsan nằm ở cột code / source_id).
    ADDRESS_TABLES: ClassVar[dict[str, tuple[str, str | None]]] = {
        'provinces_old': ('id', None), 'districts_old': ('id', 'province_id'),
        'wards_old': ('id', 'district_id'), 'streets_old': ('id', 'district_id'),
        'provinces_new': ('id', None), 'wards_new': ('id', 'province_id'),
        'streets_new': ('id', 'ward_id'),
    }

    def __init__(self, conninfo='', min_size=1, max_size=10):
        os.environ.setdefault('PGDATABASE', 'housing')
        self.pool = AsyncConnectionPool(
            conninfo, min_size=min_size, max_size=max_size, open=False,
            kwargs={'autocommit': True, 'row_factory': dict_row,
                    'options': '-c default_transaction_read_only=on'},
            configure=register_vector_async)

    async def open(self):
        await self.pool.open(wait=True)

    async def close(self):
        await self.pool.close()

    async def search_listings(self, *, query_embedding=None, transaction_type=None,
                              property_type=None, district_old=None, min_price=None,
                              max_price=None, min_area=None, max_area=None, min_bedrooms=None,
                              near=None, radius_m=None, active_only=True, limit=20):
        """Lọc cứng tin đăng, tùy chọn xếp hạng ngữ nghĩa bằng pgvector (hybrid search).

        - property_type, district_old: một giá trị hoặc list giá trị, so khớp chính xác với database.
        - near=(latitude, longitude): thêm distance_m; kèm radius_m thì chỉ lấy tin trong bán kính.
        - query_embedding: vector 1024 chiều của câu hỏi (ListingEmbedder.encode, cùng model với
          corpus). Khi có, chỉ xét tin đã embed và xếp theo similarity (cosine) giảm dần.
        - active_only: bỏ tin đã hết hạn (expired_at < hôm nay), mặc định không gợi ý tin hết hạn.

        Không có embedding thì xếp theo khoảng cách nếu có near, ngược lại theo ngày đăng mới nhất.
        Mỗi kết quả kèm 6 biến đếm POI và POI gần nhất từ listing_spatial_features (có thể None).
        """
        conditions, params = [], {'limit': limit}
        for column, value in (('transaction_type', transaction_type),
                              ('property_type', property_type), ('district_old', district_old)):
            if value is not None:
                params[column] = [value] if isinstance(value, str) else list(value)
                conditions.append(sql.SQL('l.{} = ANY({})').format(
                    sql.Identifier(column), sql.Placeholder(column)))
        for column, operator, value in (('price', '>=', min_price), ('price', '<=', max_price),
                                        ('area', '>=', min_area), ('area', '<=', max_area),
                                        ('bedrooms', '>=', min_bedrooms)):
            if value is not None:
                key = f'{column}_{"min" if operator == ">=" else "max"}'
                params[key] = value
                conditions.append(sql.SQL('l.{} {} {}').format(
                    sql.Identifier(column), sql.SQL(operator), sql.Placeholder(key)))
        if active_only:
            conditions.append(sql.SQL('(l.expired_at IS NULL OR l.expired_at >= current_date)'))

        columns = [sql.SQL('l.{}').format(sql.Identifier(c)) for c in self.LISTING_COLUMNS]
        columns += [sql.SQL('f.{}').format(sql.Identifier(c)) for c in self.SPATIAL_COLUMNS]
        joins = [sql.SQL('LEFT JOIN listing_spatial_features f ON f.listing_pk = l.id')]
        order = [sql.SQL('l.posted_at DESC NULLS LAST'), sql.SQL('l.listing_id')]

        if near is not None:
            params['lat'], params['lon'] = near
            point = sql.SQL('ST_SetSRID(ST_MakePoint(%(lon)s, %(lat)s), 4326)::geography')
            columns.append(sql.SQL('ST_Distance(l.geom, {}) AS distance_m').format(point))
            if radius_m is not None:
                params['radius_m'] = radius_m
                conditions.append(sql.SQL('ST_DWithin(l.geom, {}, %(radius_m)s)').format(point))
            order.insert(0, sql.SQL('distance_m NULLS LAST'))
        if query_embedding is not None:
            params['embedding'] = np.asarray(query_embedding, dtype=np.float32)
            columns += [sql.SQL('1 - (e.embedding <=> %(embedding)s) AS similarity'),
                        sql.SQL('e.rag_document')]
            joins.append(sql.SQL('JOIN listing_embeddings e ON e.listing_pk = l.id'))
            order.insert(0, sql.SQL('e.embedding <=> %(embedding)s'))

        query = sql.SQL('SELECT {} FROM listings l {} {} ORDER BY {} LIMIT %(limit)s').format(
            sql.SQL(', ').join(columns), sql.SQL(' ').join(joins),
            sql.SQL('WHERE ') + sql.SQL(' AND ').join(conditions) if conditions else sql.SQL(''),
            sql.SQL(', ').join(order))
        async with self.pool.connection() as conn:
            return await (await conn.execute(query, params)).fetchall()

    async def get_listings(self, listing_ids):
        """Chi tiết đầy đủ (gồm description, đặc trưng POI) theo đúng thứ tự listing_ids.

        Mã không tồn tại bị bỏ qua; dùng cho trang chi tiết và get_map_results.
        """
        ids = [listing_ids] if isinstance(listing_ids, str) else list(listing_ids)
        if not ids:
            return []
        query = sql.SQL(
            'SELECT {}, {} FROM listings l '
            'LEFT JOIN listing_spatial_features f ON f.listing_pk = l.id '
            'JOIN unnest(%(ids)s::text[]) WITH ORDINALITY AS wanted(listing_id, position) USING (listing_id) '
            'ORDER BY wanted.position').format(
            sql.SQL(', ').join(sql.SQL('l.{}').format(sql.Identifier(c)) for c in self.DETAIL_COLUMNS),
            sql.SQL(', ').join(sql.SQL('f.{}').format(sql.Identifier(c)) for c in self.SPATIAL_COLUMNS))
        async with self.pool.connection() as conn:
            return await (await conn.execute(query, {'ids': ids})).fetchall()

    async def nearby_pois(self, latitude, longitude, *, radius_m=1000, poi_types=None, limit=50):
        """POI (truong_hoc / benh_vien / cho) trong bán kính radius_m quanh một điểm, gần nhất trước.

        Đọc bảng pois (một bảng cho cả 3 loại, phân biệt bằng poi_type).
        """
        types = list(self.POI_TYPES if poi_types is None
                     else [poi_types] if isinstance(poi_types, str) else poi_types)
        unknown = set(types) - set(self.POI_TYPES)
        if unknown:
            raise ValueError(f'poi_type không hợp lệ: {sorted(unknown)}; chỉ nhận {self.POI_TYPES}')
        query = sql.SQL(
            'SELECT {}, ST_Distance(p.geom, point.g) AS distance_m '
            'FROM pois p, '
            '(SELECT ST_SetSRID(ST_MakePoint(%(lon)s, %(lat)s), 4326)::geography AS g) point '
            'WHERE p.poi_type = ANY(%(types)s) AND ST_DWithin(p.geom, point.g, %(radius_m)s) '
            'ORDER BY distance_m, p.id LIMIT %(limit)s').format(
            sql.SQL(', ').join(sql.SQL('p.{}').format(sql.Identifier(c)) for c in self.POI_COLUMNS))
        params = {'lat': latitude, 'lon': longitude, 'types': types,
                  'radius_m': radius_m, 'limit': limit}
        async with self.pool.connection() as conn:
            return await (await conn.execute(query, params)).fetchall()

    async def admin_units(self, table, *, parent=None, ids=None, name=None):
        """Đơn vị hành chính / đường từ một bảng địa chỉ (khóa là `id`; mã batdongsan ở code / source_id).

        table: một khóa của ADDRESS_TABLES, vd. 'districts_old', 'wards_new'.
        parent: id của khóa cha (province_id / district_id / ward_id), bỏ qua với bảng tỉnh.
        ids: tra theo khóa (old_district_id, new_ward_id... của listings).
        name: tìm gần đúng, không phân biệt hoa thường.
        """
        if table not in self.ADDRESS_TABLES:
            raise ValueError(
                f'table không hợp lệ: {table!r}; chỉ nhận {sorted(self.ADDRESS_TABLES)}')
        key, parent_column = self.ADDRESS_TABLES[table]
        conditions, params = [], {}
        if parent is not None and parent_column is not None:
            params['parent'] = parent
            conditions.append(sql.SQL('{} = %(parent)s').format(sql.Identifier(parent_column)))
        if ids is not None:
            params['ids'] = list(ids)
            conditions.append(sql.SQL('{} = ANY(%(ids)s)').format(sql.Identifier(key)))
        if name is not None:
            params['name'] = f'%{name}%'
            conditions.append(sql.SQL('name ILIKE %(name)s'))
        query = sql.SQL('SELECT * FROM {} {} ORDER BY name').format(
            sql.Identifier(table),
            sql.SQL('WHERE ') + sql.SQL(' AND ').join(conditions) if conditions else sql.SQL(''))
        async with self.pool.connection() as conn:
            return await (await conn.execute(query, params)).fetchall()
