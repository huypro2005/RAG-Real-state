"""Chỉ để tham khảo, không import được (ViewBase đã bỏ).

Model CHỈ ĐỌC cho 2 view (định nghĩa SQL nằm trong db/schema.sql).

Cần viết lại SQL của 2 view cho khớp cấu trúc POI mới (migration 0002).
"""

from datetime import datetime
from typing import Any

from sqlalchemy import SmallInteger
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import ViewBase
from app.db.models.poi import GEOGRAPHY_POINT


class HousingPoi(ViewBase):
    """View housing_poi = poi_schools + poi_hospitals + poi_markets (các cột chung)."""

    __tablename__ = "housing_poi"

    # id riêng từng bảng nên khóa của view là cặp (poi_type, id)
    poi_type: Mapped[str] = mapped_column(primary_key=True)
    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str]
    source_poi_id: Mapped[str]
    poi_subtype: Mapped[str | None]
    name: Mapped[str]
    address_old: Mapped[str | None]
    address_new: Mapped[str | None]
    old_province_id: Mapped[int | None]
    old_district_id: Mapped[int | None]
    old_ward_id: Mapped[int | None]
    new_province_id: Mapped[int | None]
    new_ward_id: Mapped[int | None]
    latitude: Mapped[float | None]
    longitude: Mapped[float | None]
    imported_at: Mapped[datetime]
    geom: Mapped[Any | None] = mapped_column(GEOGRAPHY_POINT)


class PoiDistrictFeature(ViewBase):
    """View poi_district_features: mỗi POI kèm nhãn quận của model 'hcm_24_user_v1'.

    label_status: 'matched_district_name' | 'ambiguous_pre_2021_district' | 'unresolved'
    (Các cột confidence lấy từ raw_record đã bỏ cùng raw_record.)
    """

    __tablename__ = "poi_district_features"

    poi_type: Mapped[str] = mapped_column(primary_key=True)
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    old_district_id: Mapped[int | None]
    district_label: Mapped[int | None] = mapped_column(SmallInteger)
    label_status: Mapped[str]