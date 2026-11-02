"""Lịch sử huấn luyện mô hình dự đoán giá: bảng price_model_runs.

Do Prediction Server (src/prediction_server) ghi; backend chỉ cần biết bảng tồn tại trong
Base.metadata để Alembic quản lý. File mô hình (.joblib) nằm ngoài DB, bảng chỉ lưu đường dẫn.

    SELECT id, best_candidate, metrics->>'r2_log' FROM price_model_runs WHERE is_active;
"""

from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, Index, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Pk


class PriceModelRun(Base):
    """Một lần retrain. Đúng một dòng `is_active` (partial unique index) là model đang phục vụ."""

    __tablename__ = "price_model_runs"
    __table_args__ = (
        CheckConstraint(
            "trigger IN ('ingest', 'manual', 'schedule', 'bootstrap')",
            name="price_model_runs_trigger_check",
        ),
        CheckConstraint(
            "status IN ('running', 'succeeded', 'failed', 'skipped')",
            name="price_model_runs_status_check",
        ),
        # Chỉ các dòng is_active = true vào index, và chúng cùng khóa `true` nên tối đa một dòng
        Index(
            "price_model_runs_one_active_idx", "is_active", unique=True,
            postgresql_where=text("is_active"),
        ),
    )

    id: Mapped[Pk]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    finished_at: Mapped[datetime | None]
    trigger: Mapped[str]
    status: Mapped[str]
    train_rows: Mapped[int | None]
    test_rows: Mapped[int | None]
    listings_snapshot: Mapped[int | None]  # số tin trong listings lúc train
    best_candidate: Mapped[str | None]     # 'extra_trees+school'
    metrics: Mapped[dict[str, Any] | None] = mapped_column(JSONB)     # của ứng viên thắng
    candidates: Mapped[list[Any] | None] = mapped_column(JSONB)       # mọi ứng viên, để so sánh
    charts: Mapped[dict[str, Any] | None] = mapped_column(JSONB)      # dữ liệu dashboard (~100 KB)
    artifact_path: Mapped[str | None]
    is_active: Mapped[bool] = mapped_column(server_default=text("false"))
    error: Mapped[str | None]              # lỗi nếu failed; lý do nếu skipped
