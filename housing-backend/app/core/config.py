from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# Key OpenAI / embedding nằm trong .env ở thư mục gốc dự án (dùng chung với src/pipeline);
# .env cạnh backend (nếu có) đọc sau nên ghi đè được.
PROJECT_ENV_FILE = Path(__file__).resolve().parents[4] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(PROJECT_ENV_FILE, ".env"), extra="ignore")

    database_url: str = "postgresql+asyncpg://postgres:123456789@localhost:5432/housing"
    db_echo: bool = False
    db_pool_size: int = 10
    db_max_overflow: int = 20

    district_model_version: str = "hcm_24_user_v1"
    embedding_model_name: str = "BAAI/bge-m3"
    embedding_dim: int = 1024

    # Hội thoại gợi ý (GĐ7). SecretStr để key không lộ khi in/log Settings.
    openai_api_key: SecretStr | None = None
    openai_model: str = "gpt-4o-mini"
    embedding_api_url: str | None = None
    embedding_api_key: SecretStr | None = None
    rerank_enabled: bool = False

    # Mode dự đoán giá: Goong geocode địa chỉ → tọa độ (biến GOONG_API_KEY)
    goong_api_key: SecretStr | None = None

    # Các nguồn frontend được gọi API (CORS), ngăn cách bằng dấu phẩy: biến môi trường CORS_ORIGINS
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    @property
    def sync_database_url(self) -> str:
        """URL cho Alembic / script import (driver sync psycopg)."""
        return self.database_url.replace("+asyncpg", "+psycopg")


@lru_cache
def get_settings() -> Settings:
    return Settings()
