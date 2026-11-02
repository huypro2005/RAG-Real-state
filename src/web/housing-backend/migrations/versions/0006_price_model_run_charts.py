"""price_model_runs.charts: dữ liệu biểu đồ dashboard theo phiên bản mô hình

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-31

Cột jsonb nullable (phiên bản cũ chưa có thì để NULL, server dựng lại bằng
POST /api/v1/models/{id}/charts/rebuild). Tối đa khoảng 150 KB mỗi dòng.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("price_model_runs",
                  sa.Column("charts", postgresql.JSONB(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    op.drop_column("price_model_runs", "charts")
