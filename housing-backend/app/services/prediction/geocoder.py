"""Geocoder: địa chỉ → tọa độ bằng Goong, nhưng chỉ nhận điểm nằm trong quận đã chọn;
ngoài quận hoặc lỗi thì dùng tâm các tin đăng của quận đó."""

import logging
from typing import Literal, NamedTuple

import httpx
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine

from app.services.prediction.constants import DISTRICT_NAMES, HCM_LAT, HCM_LON
from app.services.prediction.text import plain

logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)  # httpx ghi INFO cả URL có api_key

GOONG_URL = "https://rsapi.goong.io/v2/geocode"
TIMEOUT_S = 8
BBOX_MARGIN_DEG = 0.03  # ~3 km: tin đăng chưa phủ hết ranh giới quận
BOUNDS_PERCENTILE = 0.02  # bỏ 2% tin ở mỗi đầu để toạ độ nhập sai không nới khung
AREA_SQL = text(
    "SELECT avg(latitude), avg(longitude), "
    "percentile_cont(CAST(:p AS float)) WITHIN GROUP (ORDER BY latitude), "
    "percentile_cont(1 - CAST(:p AS float)) WITHIN GROUP (ORDER BY latitude), "
    "percentile_cont(CAST(:p AS float)) WITHIN GROUP (ORDER BY longitude), "
    "percentile_cont(1 - CAST(:p AS float)) WITHIN GROUP (ORDER BY longitude) "
    "FROM listings WHERE district_old = :district AND latitude IS NOT NULL"
)


class Location(BaseModel):
    latitude: float
    longitude: float
    source: Literal["goong", "district_centroid"]


class DistrictArea(NamedTuple):
    """Tâm và khung (min, max) toạ độ của quận, suy từ các tin đăng trong DB."""

    center: tuple[float, float]
    lat: tuple[float, float]
    lon: tuple[float, float]


class Geocoder:
    """Không bịa tọa độ: không có Goong lẫn dữ liệu quận thì trả None để chat báo lại."""

    def __init__(self, api_key: str | None, engine: AsyncEngine | None):
        self.api_key = api_key
        self.engine = engine
        self._areas: dict[int, DistrictArea] = {}
        self._points: dict[str, tuple[float, float]] = {}  # chỉ cache kết quả thành công

    async def locate(
        self, address: str, district_code: int, hint: str | None = None
    ) -> Location | None:
        """Toạ độ của địa chỉ trong quận `district_code`.

        Args:
            address: địa chỉ đã làm sạch hoặc tên quận. Chỉ có tên quận thì dùng thẳng tâm quận
                (khỏi gọi Goong, kết quả ổn định).
            district_code: mã quận 0-23; điểm Goong ngoài quận này bị bỏ.
            hint: loại nhà ("chung cư"...), thử thêm làm tiền tố nếu tên trần không ra điểm.

        Returns:
            Location (source "goong" hoặc "district_centroid"), None nếu không có cả hai.
        """
        district = DISTRICT_NAMES[district_code]
        area = await self._area(district_code)
        (lat_lo, lat_hi), (lon_lo, lon_hi) = (area.lat, area.lon) if area else (HCM_LAT, HCM_LON)
        if plain(address) != plain(district):  # chỉ có tên quận thì khỏi gọi Goong
            for name in [address, *([f"{hint} {address}"] if hint else [])]:
                point = await self._goong(f"{name}, {district}, Hồ Chí Minh")
                if point and lat_lo <= point[0] <= lat_hi and lon_lo <= point[1] <= lon_hi:
                    return Location(latitude=point[0], longitude=point[1], source="goong")
        if area:
            return Location(latitude=area.center[0], longitude=area.center[1],
                            source="district_centroid")
        return None

    async def _goong(self, query: str) -> tuple[float, float] | None:
        if query in self._points:
            return self._points[query]
        if not self.api_key:
            return None
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT_S) as client:
                response = await client.get(
                    GOONG_URL, params={"address": query, "api_key": self.api_key}
                )
            response.raise_for_status()
            point = response.json()["results"][0]["geometry"]["location"]
            self._points[query] = float(point["lat"]), float(point["lng"])
            return self._points[query]
        except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as error:
            # Không log URL (có api_key trong query string)
            status = getattr(getattr(error, "response", None), "status_code", None)
            logger.warning("Goong lỗi (%s %s), dùng tâm quận", type(error).__name__, status)
            return None

    async def _area(self, district_code: int) -> DistrictArea | None:
        """Tâm + khung quận từ listings (có cache); lỗi DB hoặc quận chưa có tin thì None."""
        if district_code in self._areas or self.engine is None:
            return self._areas.get(district_code)
        params = {"district": DISTRICT_NAMES[district_code], "p": BOUNDS_PERCENTILE}
        try:
            async with self.engine.connect() as connection:
                row = (await connection.execute(AREA_SQL, params)).one()
        except (SQLAlchemyError, OSError):
            logger.warning("Không đọc được tâm quận từ DB")
            return None
        if row[0] is None:
            return None
        margin = BBOX_MARGIN_DEG
        self._areas[district_code] = DistrictArea(
            center=(row[0], row[1]), lat=(row[2] - margin, row[3] + margin),
            lon=(row[4] - margin, row[5] + margin),
        )
        return self._areas[district_code]
