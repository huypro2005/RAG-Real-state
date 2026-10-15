"""Phần phụ trợ của chat gợi ý: bản đồ GeoJSON cho các tin đã gợi ý và xoá hội thoại."""

from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.recommendation.schemas import ConversationState, PlaceConstraint
from app.services.recommendation.service import ConversationStore

POIS_PER_TYPE = 6    # mỗi loại POI, mỗi tin
MAX_POIS = 40        # toàn bộ bản đồ, giữ các POI gần tin nhất

LISTINGS_SQL = text("""
    SELECT listing_id, title, price, area, latitude, longitude, quality_flags
      FROM listings WHERE listing_id = ANY(:ids)
""")
# Với mỗi tin có tọa độ và mỗi loại POI: tối đa POIS_PER_TYPE POI gần nhất trong bán kính
POIS_SQL = text(f"""
    SELECT l.listing_id AS near_listing_id, p.id, p.poi_type, p.name, p.latitude, p.longitude,
           ST_Distance(p.geom, l.geom) AS distance_m
      FROM listings l
     CROSS JOIN unnest(CAST(:poi_types AS text[])) AS t(poi_type)
     CROSS JOIN LATERAL (
           SELECT * FROM pois
            WHERE poi_type = t.poi_type AND ST_DWithin(geom, l.geom, :radius_m)
              AND coalesce(poi_subtype, '') NOT IN ('Đại học', 'Cao đẳng')
            ORDER BY geom <-> l.geom LIMIT {POIS_PER_TYPE}) p
     WHERE l.listing_id = ANY(:ids) AND l.geom IS NOT NULL
""")


class ChatSupport:
    """Bản đồ (`/recommend/map`) và xoá hội thoại (`/recommend/reset`)."""

    def __init__(self, session: AsyncSession | None = None, store: ConversationStore | None = None):
        self.session = session
        self.store = store

    async def geojson(self, ids: list[str], radius_m: float, poi_types: list[str],
                      places: list[PlaceConstraint] = ()) -> dict:
        """FeatureCollection: tin có tọa độ (đánh số theo thứ tự `ids`) + POI quanh chúng + địa
        điểm có tên đang lọc (kind "place", kèm bán kính để giao diện vẽ vòng tròn).

        Tin không có tọa độ (hoặc không tồn tại) không có feature, chỉ nằm trong `missing_ids`.
        """
        rows = (await self.session.execute(LISTINGS_SQL, {"ids": ids})).mappings().all()
        by_id = {row["listing_id"]: row for row in rows}
        features, missing = [], []
        for position, listing_id in enumerate(ids, start=1):
            row = by_id.get(listing_id)
            if row is None or None in (row["latitude"], row["longitude"]):
                missing.append(listing_id)
                continue
            features.append(self._point(row["longitude"], row["latitude"], {
                "kind": "listing", "position": position, "listing_id": listing_id,
                "title": row["title"], "price": row["price"], "area": row["area"],
                "reliable": "coords_outside_hcm" not in row["quality_flags"],
            }))
        features += [self._point(p.longitude, p.latitude, {
            "kind": "place", "name": p.name, "address": p.address, "radius_m": p.max_distance_m,
        }) for p in places]
        return {"type": "FeatureCollection",
                "features": features + await self._poi_features(ids, radius_m, poi_types),
                "missing_ids": missing}

    async def _poi_features(self, ids: list[str], radius_m: float, poi_types: list[str]) -> list:
        """POI gần nhất trước, mỗi POI một lần (gắn với tin gần nó nhất), tối đa MAX_POIS."""
        rows = (await self.session.execute(
            POIS_SQL, {"ids": ids, "radius_m": radius_m, "poi_types": poi_types}
        )).mappings().all()
        nearest: dict[int, Any] = {}
        for row in sorted(rows, key=lambda r: r["distance_m"]):
            nearest.setdefault(row["id"], row)
        return [
            self._point(row["longitude"], row["latitude"], {
                "kind": "poi", "poi_type": row["poi_type"], "name": row["name"],
                "distance_m": round(row["distance_m"]),
                "near_listing_id": row["near_listing_id"],
            })
            for row in list(nearest.values())[:MAX_POIS]
        ]

    def reset(self, conversation_id: str) -> dict:
        """Xoá điều kiện, kết quả và lịch sử của hội thoại (mode do client gửi mỗi lượt)."""
        self.store.save(ConversationState(conversation_id=conversation_id))
        return {"conversation_id": conversation_id}

    @staticmethod
    def _point(longitude: float, latitude: float, properties: dict) -> dict:
        """Feature GeoJSON kiểu Point (thứ tự toạ độ: kinh độ, vĩ độ)."""
        return {"type": "Feature", "properties": properties,
                "geometry": {"type": "Point", "coordinates": [longitude, latitude]}}
