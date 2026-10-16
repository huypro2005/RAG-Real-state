"""Tin đăng: listings, listing_spatial_features, listing_embeddings."""

from datetime import date, datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import BigInteger, CheckConstraint, Computed, ForeignKey, Index, func, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Text

from app.db.base import Base, Pk
from app.db.models.poi import GEOGRAPHY_POINT, GEOM_SQL

EMBEDDING_DIM = 1024  # bge-m3


class Listing(Base):
    """Một tin batdongsan. `listing_id` là mã tin của batdongsan (UNIQUE), dùng trong API/chat."""

    __tablename__ = "listings"
    __table_args__ = (
        CheckConstraint("price > 0", name="listings_price_check"),
        CheckConstraint("area > 0", name="listings_area_check"),
        CheckConstraint("(latitude IS NULL) = (longitude IS NULL)", name="listings_check"),
        Index("listings_geom_gist", "geom", postgresql_using="gist"),
        # Lọc Hybrid Search theo loại nhà + quận (FK) + giá
        Index("listings_filter_idx", "property_type", "old_district_id", "price"),
        Index("listings_expired_at_idx", "expired_at"),
    )

    id: Mapped[Pk]
    listing_id: Mapped[str] = mapped_column(unique=True)  # '44521542'
    listing_url: Mapped[str]
    title: Mapped[str]
    description: Mapped[str | None]
    transaction_type: Mapped[str]
    property_type: Mapped[str | None]   # nguyên văn: 'Nhà riêng', 'Căn hộ chung cư'...

    # Thông số
    price: Mapped[float]                # triệu VND
    price_per_m2: Mapped[float | None]  # triệu VND / m²
    area: Mapped[float]                 # m²
    frontage: Mapped[float | None]
    bedrooms: Mapped[int | None]
    bathrooms: Mapped[int | None]
    road_width: Mapped[float | None]
    floors: Mapped[int | None]
    legal: Mapped[str | None]
    legal_group: Mapped[str | None]
    interior: Mapped[str | None]

    # Địa chỉ dạng chữ như tin ghi
    province_old: Mapped[str | None]
    district_old: Mapped[str | None]
    old_ward: Mapped[str | None]
    old_address: Mapped[str | None]
    old_address_detail: Mapped[str | None]
    new_ward: Mapped[str | None]
    new_city: Mapped[str | None]
    new_address: Mapped[str | None]

    # Do function refresh_listing_address_ids() điền: tên khớp chính xác đúng 1 dòng
    # (sau NFC), không khớp thì NULL
    old_district_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("districts_old.id"), index=True
    )
    old_ward_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("wards_old.id"), index=True
    )
    new_ward_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("wards_new.id"), index=True
    )

    # Tọa độ + thời gian
    latitude: Mapped[float | None]
    longitude: Mapped[float | None]
    posted_at: Mapped[date | None]
    expired_at: Mapped[date | None]

    # Theo dõi dữ liệu
    quality_flags: Mapped[list[str]] = mapped_column(
        ARRAY(Text), server_default=text("'{}'::text[]")
    )
    first_loaded_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    # Tự tính từ latitude/longitude — không gán trực tiếp
    geom: Mapped[Any | None] = mapped_column(
        GEOGRAPHY_POINT, Computed(GEOM_SQL, persisted=True)
    )

    spatial_features: Mapped["ListingSpatialFeatures | None"] = relationship(
        back_populates="listing", passive_deletes=True
    )
    embedding: Mapped["ListingEmbedding | None"] = relationship(
        back_populates="listing", passive_deletes=True
    )


class ListingSpatialFeatures(Base):
    """Số POI quanh tin + POI gần nhất (1 tin : 0..1 dòng), do refresh_spatial_features() ghi."""

    __tablename__ = "listing_spatial_features"

    id: Mapped[Pk]
    listing_pk: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("listings.id", ondelete="CASCADE"), unique=True
    )
    school_count_1km: Mapped[int]
    hospital_count_1km: Mapped[int]
    market_count_1km: Mapped[int]
    school_count_3km: Mapped[int]
    hospital_count_3km: Mapped[int]
    market_count_3km: Mapped[int]
    nearest_school_name: Mapped[str | None]
    nearest_school_m: Mapped[float | None]
    nearest_hospital_name: Mapped[str | None]
    nearest_hospital_m: Mapped[float | None]
    nearest_market_name: Mapped[str | None]
    nearest_market_m: Mapped[float | None]
    computed_at: Mapped[datetime] = mapped_column(server_default=func.now())

    listing: Mapped[Listing] = relationship(back_populates="spatial_features")


class ListingEmbedding(Base):
    """Vector embedding của tin (1 tin : 0..1 dòng), dùng cho RAG / tìm kiếm theo nghĩa."""

    __tablename__ = "listing_embeddings"

    id: Mapped[Pk]
    listing_pk: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("listings.id", ondelete="CASCADE"), unique=True
    )
    model_name: Mapped[str]
    content_hash: Mapped[str]  # sha256(model_name + embedding_text)
    embedding_text: Mapped[str]
    rag_document: Mapped[str]
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM))
    embedded_at: Mapped[datetime] = mapped_column(server_default=func.now())

    listing: Mapped[Listing] = relationship(back_populates="embedding")
