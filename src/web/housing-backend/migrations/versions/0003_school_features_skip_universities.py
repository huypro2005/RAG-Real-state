"""refresh_spatial_features(): biến đếm/gần nhất của "trường học" không tính đại học, cao đẳng

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-15

scripts/import_universities.py thêm ĐH/CĐ vào pois (poi_type 'truong_hoc'). "Gần trường học" chung
chung vẫn phải như trước (gia đình có con nhỏ), nên biến đếm trường 1 km/3 km và nearest_school_*
bỏ poi_subtype 'Đại học'/'Cao đẳng' (NULL tính là trường thường). Hàm cũ lấy từ 0001 và thay đúng
điều kiện trường học, không sao chép lại cả hàm.
"""

import importlib

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

SCHOOL = "p.poi_type = 'truong_hoc'"
GENERIC_SCHOOL = SCHOOL + " AND coalesce(p.poi_subtype, '') NOT IN ('Đại học', 'Cao đẳng')"
OLD_SQL = importlib.import_module("migrations.versions.0001_baseline").REFRESH_SPATIAL_FEATURES_SQL


def upgrade() -> None:
    assert OLD_SQL.count(SCHOOL) == 3  # đếm 3 km, đếm 1 km, trường gần nhất
    op.get_bind().exec_driver_sql(OLD_SQL.replace(SCHOOL, GENERIC_SCHOOL))


def downgrade() -> None:
    op.get_bind().exec_driver_sql(OLD_SQL)
