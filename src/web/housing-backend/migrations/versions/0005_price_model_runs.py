"""Bảng price_model_runs: lịch sử retrain mô hình dự đoán giá của Prediction Server

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-31

Chỉ thêm bảng mới, không đụng bảng cũ. Partial unique index đảm bảo tối đa một dòng
`is_active = true`. File mô hình (.joblib) nằm ngoài DB; bảng chỉ lưu đường dẫn.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "price_model_runs",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
                  nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("trigger", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("train_rows", sa.Integer(), nullable=True),
        sa.Column("test_rows", sa.Integer(), nullable=True),
        sa.Column("listings_snapshot", sa.Integer(), nullable=True),
        sa.Column("best_candidate", sa.Text(), nullable=True),
        sa.Column("metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("candidates", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("artifact_path", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.CheckConstraint("status IN ('running', 'succeeded', 'failed', 'skipped')",
                           name="price_model_runs_status_check"),
        sa.CheckConstraint("trigger IN ('ingest', 'manual', 'schedule', 'bootstrap')",
                           name="price_model_runs_trigger_check"),
        sa.PrimaryKeyConstraint("id", name=op.f("price_model_runs_pkey")),
    )
    op.create_index("price_model_runs_one_active_idx", "price_model_runs", ["is_active"],
                    unique=True, postgresql_where=sa.text("is_active"))


def downgrade() -> None:
    op.drop_index("price_model_runs_one_active_idx", table_name="price_model_runs",
                  postgresql_where=sa.text("is_active"))
    op.drop_table("price_model_runs")
