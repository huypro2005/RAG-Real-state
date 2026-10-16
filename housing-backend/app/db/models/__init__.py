"""Tất cả model. Import từ đây:  from app.db.models import Listing, WardNew, ...

File này import mọi model để Base.metadata có đủ bảng (Alembic cần).

    admin_units.py -> provinces_old, districts_old, wards_old, streets_old,
                      provinces_new, wards_new, streets_new, ward_mappings
    district.py    -> district_label (nhãn quận cho model dự đoán giá)
    poi.py         -> pois
    listing.py     -> listings, listing_spatial_features, listing_embeddings
"""

from app.db.models.admin_units import (
    DistrictOld,
    ProvinceNew,
    ProvinceOld,
    StreetNew,
    StreetOld,
    WardMapping,
    WardNew,
    WardOld,
)
from app.db.models.district import DistrictLabel
from app.db.models.listing import Listing, ListingEmbedding, ListingSpatialFeatures
from app.db.models.poi import Poi

__all__ = [
    "DistrictLabel",
    "DistrictOld",
    "Listing",
    "ListingEmbedding",
    "ListingSpatialFeatures",
    "Poi",
    "ProvinceNew",
    "ProvinceOld",
    "StreetNew",
    "StreetOld",
    "WardMapping",
    "WardNew",
    "WardOld",
]
