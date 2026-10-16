"""Địa chỉ theo dữ liệu Batdongsan: 7 bảng + bảng mapping phường cũ -> mới.

    Bộ CŨ  (trước 2025):  provinces_old -> districts_old -> wards_old
                                                       -> streets_old
    Bộ MỚI (từ 2025):     provinces_new -> wards_new -> streets_new

- Khóa chính mọi bảng là `id` bigint tự tăng. Mã của batdongsan giữ nguyên giá trị ở cột
  riêng có UNIQUE: `source_id` (districtId / wardId / streetId), `code` (cityCode 'SG', KHÔNG
  phải mã hành chính '79'). Khóa ngoài trỏ vào `id`, không trỏ vào mã nguồn.
- Mỗi cột map 1-1 từ một field JSON trong address_data/ (ghi ở comment cạnh cột). Field lặp
  thông tin cha (cityName, districtName...) không thành cột vì đã có qua khóa ngoại. Bỏ
  `otherNames`, `areaCode`, `priority`, `countryCode`, `area` theo spec.
- Chữ giữ nguyên như nguồn: prefix tách riêng và có thể rỗng (quận 'Quận 1' có prefix '').
  Tên đầy đủ = prefix + ' ' + name (bỏ prefix nếu rỗng).
"""

from sqlalchemy import BigInteger, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Pk


# --------------------------------------------------------------------- bộ CŨ
class ProvinceOld(Base):
    """Tỉnh/thành trước 2025 — old_cities.json (63 dòng)."""

    __tablename__ = "provinces_old"

    id: Mapped[Pk]
    code: Mapped[str] = mapped_column(unique=True)       # cityCode  'SG'
    name: Mapped[str]                                    # cityName  'Hồ Chí Minh'
    alias: Mapped[str]                                   # cityAlias 'tp-hcm'


class DistrictOld(Base):
    """Quận/huyện cũ của SG — sg_old.json (24 dòng; có cả 'Thành phố Thủ Đức' lẫn Quận 2, 9)."""

    __tablename__ = "districts_old"

    id: Mapped[Pk]
    source_id: Mapped[int] = mapped_column(unique=True)                     # districtId
    province_id: Mapped[int] = mapped_column(                               # cityCode
        BigInteger, ForeignKey("provinces_old.id"), index=True
    )
    name: Mapped[str]                                                       # districtName
    prefix: Mapped[str]                                                     # districtPrefix
    alias: Mapped[str]                                                      # districtAlias


class WardOld(Base):
    """Phường/xã cũ của SG — sg_old_wards.json (346 dòng, wardId không trùng)."""

    __tablename__ = "wards_old"

    id: Mapped[Pk]
    source_id: Mapped[int] = mapped_column(unique=True)                     # wardId
    district_id: Mapped[int] = mapped_column(                               # districtId
        BigInteger, ForeignKey("districts_old.id"), index=True
    )
    name: Mapped[str]                                                       # wardName
    prefix: Mapped[str]                                                     # wardPrefix
    alias: Mapped[str]                                                      # wardAlias


class StreetOld(Base):
    """Đường theo quận cũ của SG — sg_old_streets.json (9.169 dòng).

    Kiểm tra dữ liệu: 9.169 dòng chỉ có 5.504 streetId khác nhau (1.330 ID xuất hiện ở nhiều
    quận, vd. 128 'Phùng Hưng' ở quận 72, 57, 61), không trùng trong cùng một quận
    -> mã nguồn chỉ UNIQUE theo cặp (source_id, district_id).
    """

    __tablename__ = "streets_old"
    __table_args__ = (UniqueConstraint("source_id", "district_id"),)

    id: Mapped[Pk]
    source_id: Mapped[int]                                                  # streetId
    district_id: Mapped[int] = mapped_column(                               # districtId
        BigInteger, ForeignKey("districts_old.id"), index=True
    )
    name: Mapped[str]                                                       # streetName
    prefix: Mapped[str]                                                     # streetPrefix
    alias: Mapped[str]                                                      # streetAlias


# --------------------------------------------------------------------- bộ MỚI
class ProvinceNew(Base):
    """Tỉnh/thành từ 2025 — new_cities.json (34 dòng)."""

    __tablename__ = "provinces_new"

    id: Mapped[Pk]
    code: Mapped[str] = mapped_column(unique=True)       # cityCode  'SG'
    name: Mapped[str]                                    # cityName  'Hồ Chí Minh'
    alias: Mapped[str]                                   # cityAlias 'tp-ho-chi-minh'


class WardNew(Base):
    """Phường/xã/đặc khu mới của SG — sg_new_wards.json (169 dòng, gồm cả Bình Dương,
    Bà Rịa – Vũng Tàu cũ vì batdongsan không tách vùng)."""

    __tablename__ = "wards_new"

    id: Mapped[Pk]
    source_id: Mapped[int] = mapped_column(unique=True)                     # wardId
    province_id: Mapped[int] = mapped_column(                               # cityCode
        BigInteger, ForeignKey("provinces_new.id"), index=True
    )
    name: Mapped[str]                                                       # wardName
    prefix: Mapped[str]                                                     # wardPrefix
    alias: Mapped[str]                                                      # wardAlias


class StreetNew(Base):
    """Đường theo phường mới — sg_new_streets.json (34.091 dòng; response không có ID cha,
    ward_id lấy từ khóa ngoài của file).

    Kiểm tra dữ liệu: chỉ 7.454 streetId khác nhau (5.340 ID xuất hiện ở nhiều phường,
    vd. 3786 'Đường 5' ở 92 phường), không trùng trong cùng một phường
    -> mã nguồn chỉ UNIQUE theo cặp (source_id, ward_id).
    """

    __tablename__ = "streets_new"
    __table_args__ = (UniqueConstraint("source_id", "ward_id"),)

    id: Mapped[Pk]
    source_id: Mapped[int]                                                  # streetId
    ward_id: Mapped[int] = mapped_column(                                   # khóa ngoài file
        BigInteger, ForeignKey("wards_new.id"), index=True
    )
    name: Mapped[str]                                                       # streetName
    prefix: Mapped[str]                                                     # streetPrefix
    alias: Mapped[str]                                                      # streetAlias


# --------------------------------------------------------------------- mapping
class WardMapping(Base):
    """Phường cũ -> phường mới, chỉ lấy từ address_data/ward_mappings.sql (TP.HCM cũ).

    File gốc dùng mã hành chính; seed_address.py nối sang ID batdongsan bằng so khớp tên
    chính xác. Dòng không khớp nằm ở address_data/ward_mappings_unmatched.json.
    """

    __tablename__ = "ward_mappings"

    id: Mapped[Pk]
    old_ward_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("wards_old.id"), unique=True)
    new_ward_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("wards_new.id"), index=True)
