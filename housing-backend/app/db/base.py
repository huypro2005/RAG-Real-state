"""Base class cho mọi model.

Mọi bảng nằm trong schema mặc định (public) nên model không khai báo schema.

NAMING_CONVENTION đặt tên constraint giống hệt cách Postgres tự đặt
(listings_pkey, wards_old_district_id_fkey, ...), để tên trong DB đoán được từ model
và `alembic check` không báo khác biệt thừa.
"""

from datetime import datetime
from typing import Annotated

from sqlalchemy import DateTime, Double, MetaData, Text
from sqlalchemy.orm import DeclarativeBase, mapped_column

# Khóa chính tự tăng:  id: Mapped[IntPk]  -> cột `id integer` SERIAL.
# Bảng địa chỉ dùng ID batdongsan nên KHÔNG dùng IntPk (khai báo autoincrement=False).
IntPk = Annotated[int, mapped_column(primary_key=True)]

NAMING_CONVENTION = {
    "pk": "%(table_name)s_pkey",
    "uq": "%(table_name)s_%(column_0_N_name)s_key",
    "fk": "%(table_name)s_%(column_0_N_name)s_fkey",
    "ix": "%(table_name)s_%(column_0_N_name)s_idx",  # cột khai báo index=True
    # CHECK và index GiST/nhiều cột đặt tên trực tiếp trong từng model
}

# Kiểu Python -> kiểu cột Postgres. Nhờ bảng này, chỉ cần viết
# `name: Mapped[str]` là ra cột text NOT NULL, `Mapped[str | None]` là text NULL.
TYPE_MAP = {
    str: Text,                         # mặc định SQLAlchemy dùng VARCHAR, DB dùng text
    float: Double,                     # double precision
    datetime: DateTime(timezone=True), # timestamp with time zone
}


class Base(DeclarativeBase):
    """Base cho mọi bảng. Alembic quản lý những gì kế thừa class này."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    type_annotation_map = TYPE_MAP
