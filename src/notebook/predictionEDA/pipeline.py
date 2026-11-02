import numpy as np
import pandas as pd
import psycopg
from psycopg import sql

DSN = "postgresql://postgres:123456789@localhost:5432/housing"


def dem_tien_ich(df, bang_poi, ban_kinh_km, dieu_kien=None, dsn=DSN,
                 cot_lat="tọa độ x", cot_lon="tọa độ y"):
    """Đếm số tiện ích (POI) trong bán kính `ban_kinh_km` quanh từng bất động sản.

    Dữ liệu POI nằm trong PostGIS (cột `geom` geography), đếm bằng ST_DWithin + index GiST.

    df          : DataFrame tin đăng (price_training.csv), có cột vĩ độ / kinh độ.
    bang_poi    : bảng POI, ví dụ "amenities.poi_schools", "amenities.poi_hospitals",
                  "amenities.poi_markets".
    ban_kinh_km : bán kính tìm kiếm (km).
    dieu_kien   : dict {cột POI: giá trị hoặc list giá trị}, có thể None/{} (không lọc).
                  Ví dụ {"ownership": "Công lập"}, {"poi_subtype": ["THCS", "THPT"]}.
    cot_lat, cot_lon : tên cột tọa độ trong df. Dữ liệu gốc đang nhân 1e9
                  (10803384659 -> 10.8033...) nên hàm tự chia lại khi |giá trị| > 180.

    Trả về pd.Series (index = df.index): số POI thỏa điều kiện trong bán kính; 0 nếu
    không có POI, NaN nếu tin thiếu tọa độ.
    """
    lat = pd.to_numeric(df[cot_lat], errors="coerce")
    lon = pd.to_numeric(df[cot_lon], errors="coerce")
    lat = lat.where(lat.abs() <= 180, lat / 1e9)
    lon = lon.where(lon.abs() <= 180, lon / 1e9)
    co_toa_do = (lat.notna() & lon.notna()).to_numpy()
    chi_so = np.flatnonzero(co_toa_do)

    ket_qua = np.full(len(df), np.nan)
    if len(chi_so) == 0:
        return pd.Series(ket_qua, index=df.index)

    # Mỗi điều kiện: cột = ANY(%s); tên bảng/cột đi qua sql.Identifier để tránh injection
    loc, tham_so = [], []
    for cot, gia_tri in (dieu_kien or {}).items():
        if gia_tri is None:
            continue
        gia_tri = list(gia_tri) if isinstance(gia_tri, (list, tuple, set)) else [gia_tri]
        loc.append(sql.SQL(" AND {} = ANY(%s)").format(sql.Identifier(cot)))
        tham_so.append(gia_tri)

    truy_van = sql.SQL(
        """
        SELECT t.i, count(p.geom)
        FROM unnest(%s::int[], %s::float8[], %s::float8[]) AS t(i, lon, lat)
        LEFT JOIN {bang} p
          ON p.geom IS NOT NULL
         AND ST_DWithin(p.geom, ST_SetSRID(ST_MakePoint(t.lon, t.lat), 4326)::geography, %s)
         {loc}
        GROUP BY t.i
        """
    ).format(
        bang=sql.SQL(".").join(sql.Identifier(x) for x in bang_poi.split(".")),
        loc=sql.SQL("").join(loc),
    )

    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            truy_van,
            [chi_so.tolist(), lon.to_numpy()[chi_so].tolist(), lat.to_numpy()[chi_so].tolist(),
             ban_kinh_km * 1000, *tham_so],
        )
        for i, so_luong in cur.fetchall():
            ket_qua[i] = so_luong

    return pd.Series(ket_qua, index=df.index)


if __name__ == "__main__":
    du_lieu = pd.read_csv("data/price_training.csv")
    du_lieu["truong_cong_lap_2km"] = dem_tien_ich(
        du_lieu, "amenities.poi_schools", 2, {"ownership": "Công lập"}
    )
    du_lieu["benh_vien_3km"] = dem_tien_ich(
        du_lieu, "amenities.poi_hospitals", 3, {"poi_subtype": "Bệnh viện"}
    )
    du_lieu["cho_1km"] = dem_tien_ich(du_lieu, "amenities.poi_markets", 1)
    print(du_lieu[["truong_cong_lap_2km", "benh_vien_3km", "cho_1km"]].describe())
