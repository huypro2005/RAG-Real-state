"""Cấu hình server, đọc từ biến môi trường hoặc .env gốc (tên biến theo spec)."""
import re
from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from src.prediction_server import ROOT

MAX_N_JOBS = 4  # trần số luồng của mỗi mô hình; máy đồ án chỉ có vài nhân


class ServerSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    # Mật khẩu để trong URL (env) hoặc PGPASSWORD, không hard-code. Mặc định là DB thử nghiệm.
    database_url: str = "postgresql://postgres@localhost:5432/housing_dev"
    prediction_server_api_key: SecretStr | None = None
    models_dir: Path = ROOT / "models"
    max_ingest_bytes: int = 20 * 1024 * 1024  # trần body của POST /ingest

    retrain_min_new: int = 200            # đủ chừng này tin mới thì retrain...
    retrain_min_ratio: float = 0.05       # ...hoặc số tin mới >= tỷ lệ này của tổng
    retrain_interval_hours: float = 6     # 0 = tắt lịch
    min_train_rows: int = 300             # ít hơn thì không đủ để chia train/test
    promote_min_gain: float = 0.002       # R² log phải hơn model cũ ít nhất chừng này
    promote_max_regression: float = 0.05  # MAE được tệ hơn model cũ tối đa 5%
    keep_artifacts: int = 5
    candidates: str = "extra_trees,random_forest,hist_gb,xgboost,lightgbm"
    n_jobs: int = MAX_N_JOBS
    cv_folds: int = 5
    scheduler_enabled: bool = True
    active_check_seconds: float = 5       # nhiều worker: tối đa chừng này giây để thấy model mới

    @property
    def dsn(self) -> str:
        """URL cho psycopg: bỏ tiền tố driver của SQLAlchemy (postgresql+asyncpg://)."""
        return re.sub(r"^postgresql\+\w+://", "postgresql://", self.database_url)

    @property
    def candidate_names(self) -> list[str]:
        return [name.strip() for name in self.candidates.split(",") if name.strip()]

    @property
    def jobs(self) -> int:
        return max(1, min(self.n_jobs, MAX_N_JOBS))


@lru_cache
def get_settings() -> ServerSettings:
    return ServerSettings()
