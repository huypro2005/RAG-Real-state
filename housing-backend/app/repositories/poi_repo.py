from dataclasses import dataclass

from sqlalchemy import Float, Integer, Text, column, func, select
from sqlalchemy.ext.asyncio import AsyncSession

# Các cột mà function nearby() trả về (tạo trong migrations/versions/0001_baseline.py)
_nearby_cols = (
    column("poi_id", Integer),  # = pois.id
    column("poi_type", Text),
    column("name", Text),
    column("distance_m", Float),
)


@dataclass(frozen=True)
class NearbyPoi:
    poi_id: int
    poi_type: str
    name: str
    distance_m: float


class PoiRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def nearby(
        self,
        longitude: float,
        latitude: float,
        radius_m: float = 1000,
        poi_type: str | None = None,
        limit: int = 50,
    ) -> list[NearbyPoi]:
        fn = (
            func.nearby(longitude, latitude, radius_m, poi_type)
            .table_valued(*_nearby_cols)
            .alias("n")
        )
        stmt = select(fn).limit(limit)
        rows = await self.session.execute(stmt)
        return [NearbyPoi(**r._mapping) for r in rows]

