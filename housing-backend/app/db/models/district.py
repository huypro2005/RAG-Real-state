"""Nhãn quận cho model dự đoán giá: bảng district_label.

Mỗi dòng: với phiên bản model X, quận cũ có ID batdongsan Y mang nhãn Z.

    SELECT d.name, l.label
      FROM district_label l
      JOIN districts_old d ON d.id = l.district_id
     WHERE l.model_version = 'hcm_24_user_v1';
"""

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, SmallInteger, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Pk


class DistrictLabel(Base):
    __tablename__ = "district_label"
    __table_args__ = (
        # Mỗi nhãn của một phiên bản model là duy nhất
        UniqueConstraint("model_version", "label"),
        # Trong một phiên bản model, mỗi quận chỉ có một nhãn
        UniqueConstraint("model_version", "district_id"),
        # Không chặn trên 23: phiên bản model sau có thể có nhiều nhãn hơn
        CheckConstraint("label >= 0", name="district_label_label_check"),
    )

    id: Mapped[Pk]
    model_version: Mapped[str]                                             # 'hcm_24_user_v1'
    label: Mapped[int] = mapped_column(SmallInteger)                       # 0..23
    district_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("districts_old.id"))
