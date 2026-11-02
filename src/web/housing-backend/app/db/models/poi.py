"""Tiện ích (POI): một bảng `pois` cho trường học, bệnh viện, chợ (phân biệt bằng poi_type).

Vị trí POI chỉ dùng tọa độ (`geom`); không nối khóa ngoại sang bảng địa chỉ vì địa chỉ POI
đến từ nguồn khác batdongsan, không nối chắc chắn được sang ID batdongsan.
"""

from typing import Any

from geoalchemy2 import Geography
from sqlalchemy import CheckConstraint, Computed, Index, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IntPk

# geography(Point, 4326): kinh độ/vĩ độ, ST_Distance trả về mét.
# spatial_index=False vì index GiST đã khai báo tường minh trong __table_args__.
GEOGRAPHY_POINT = Geography(geometry_type="POINT", srid=4326, spatial_index=False)

# geom tự tính từ (longitude, latitude); dùng chung cho pois và listings
GEOM_SQL = (
    "CASE WHEN longitude IS NOT NULL AND latitude IS NOT NULL "
    "THEN st_setsrid(st_makepoint(longitude, latitude), 4326)::geography "
    "ELSE NULL::geography END"
)


class Poi(Base):
    """Một điểm tiện ích. poi_type: 'truong_hoc' | 'benh_vien' | 'cho'."""

    __tablename__ = "pois"
    __table_args__ = (
        CheckConstraint(
            "poi_type IN ('truong_hoc', 'benh_vien', 'cho')", name="pois_poi_type_check"
        ),
        CheckConstraint("(latitude IS NULL) = (longitude IS NULL)", name="pois_check"),
        CheckConstraint("latitude >= -90 AND latitude <= 90", name="pois_latitude_check"),
        CheckConstraint("longitude >= -180 AND longitude <= 180", name="pois_longitude_check"),
        Index("pois_geom_gist", "geom", postgresql_using="gist"),
        Index("pois_poi_type_idx", "poi_type"),
        # Tra địa điểm theo tên không dấu (migration 0002 tạo hàm immutable_unaccent)
        Index("pois_name_trgm", text("immutable_unaccent(lower(name)) gin_trgm_ops"),
              postgresql_using="gin"),
    )

    id: Mapped[IntPk]
    poi_type: Mapped[str]
    poi_subtype: Mapped[str | None]       # 'Bệnh viện', 'Phòng khám'...
    name: Mapped[str]
    address_old: Mapped[str | None]
    address_new: Mapped[str | None]
    latitude: Mapped[float | None]
    longitude: Mapped[float | None]
    ownership: Mapped[str | None]           # chỉ trường học/bệnh viện: 'Công lập'...
    school_level_codes: Mapped[str | None]  # chỉ trường học: 'mn', 'th', 'thcs'...

    # Tự tính từ latitude/longitude — không gán trực tiếp
    geom: Mapped[Any | None] = mapped_column(
        GEOGRAPHY_POINT, Computed(GEOM_SQL, persisted=True)
    )
