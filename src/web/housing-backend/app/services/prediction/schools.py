"""SchoolCounter: đếm số trường học quanh toạ độ, dùng chung cho script train và lúc dự đoán
để hai bên tính đặc trưng "trường học 1 km/3 km" bằng đúng một cách."""

import numpy as np
import psycopg

RADII_M = (1000, 3000)
CONNECT_TIMEOUT_S = 3  # DB không phản hồi thì bỏ cuộc sớm, để dự đoán không bị treo
SCHOOL_COLUMNS = ("trường học 1 km", "trường học 3 km")

# Một truy vấn cho cả lô điểm: ST_DWithin dùng index GiST của pois.geom (geography, đơn vị mét)
COUNT_SQL = """
SELECT t.i,
       count(p.id) FILTER (WHERE ST_DWithin(p.geom, t.pt, %s)),
       count(p.id)
FROM (SELECT i, ST_SetSRID(ST_MakePoint(lon, lat), 4326)::geography AS pt
      FROM unnest(%s::int[], %s::float8[], %s::float8[]) AS u(i, lon, lat)) t
LEFT JOIN pois p ON p.poi_type = 'truong_hoc' AND p.geom IS NOT NULL
                AND ST_DWithin(p.geom, t.pt, %s)
GROUP BY t.i
"""


class SchoolCounter:
    """Đếm trường (mọi cấp, công lập lẫn ngoài công lập) trong bán kính 1 km và 3 km."""

    def __init__(self, database_url: str):
        # psycopg không hiểu tiền tố của SQLAlchemy ("postgresql+psycopg://")
        self.dsn = database_url.replace("+asyncpg", "").replace("+psycopg", "")

    def count(self, latitudes, longitudes) -> np.ndarray:
        """Mảng (n, 2): số trường trong 1 km và 3 km quanh từng điểm; NaN nếu thiếu toạ độ.

        Raises:
            psycopg.Error: không kết nối/truy vấn được DB.
        """
        lat = np.asarray(latitudes, dtype=float)
        lon = np.asarray(longitudes, dtype=float)
        result = np.full((len(lat), 2), np.nan)
        valid = np.flatnonzero(~(np.isnan(lat) | np.isnan(lon)))
        if len(valid) == 0:
            return result
        with psycopg.connect(self.dsn, connect_timeout=CONNECT_TIMEOUT_S) as conn:
            cur = conn.cursor()
            cur.execute(COUNT_SQL, (
                RADII_M[0], valid.tolist(), lon[valid].tolist(), lat[valid].tolist(), RADII_M[1],
            ))
            for index, near, far in cur.fetchall():
                result[index] = (near, far)
        return result
