"""Pydantic schema cho request/response — tách khỏi model DB.

Đổi cột trong DB không tự làm đổi API contract, và ngược lại.
"""

from datetime import date

from pydantic import BaseModel, ConfigDict, Field


class SpatialFeaturesOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    school_count_1km: int
    school_count_3km: int
    hospital_count_1km: int
    hospital_count_3km: int
    market_count_1km: int
    market_count_3km: int
    nearest_school_name: str | None
    nearest_school_m: float | None
    nearest_hospital_name: str | None
    nearest_hospital_m: float | None
    nearest_market_name: str | None
    nearest_market_m: float | None


class ListingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    listing_id: str
    listing_url: str
    title: str
    transaction_type: str
    property_type: str | None
    price: float = Field(description="triệu VND")
    price_per_m2: float | None = Field(description="triệu VND/m²")
    area: float = Field(description="m²")
    bedrooms: int | None
    bathrooms: int | None
    district_old: str | None
    new_address: str | None
    latitude: float | None
    longitude: float | None
    posted_at: date | None
    quality_flags: list[str]
    spatial_features: SpatialFeaturesOut | None = None
