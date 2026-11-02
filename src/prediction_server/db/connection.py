"""Truy cập PostgreSQL bằng psycopg đồng bộ (job chạy trong thread, không cần async)."""
import psycopg


class Database:
    """Mở kết nối ngắn hạn tới PostgreSQL dùng chung với backend."""

    CONNECT_TIMEOUT_S = 5

    def __init__(self, dsn: str):
        self.dsn = dsn

    def connect(self, **kwargs) -> psycopg.Connection:
        return psycopg.connect(self.dsn, connect_timeout=self.CONNECT_TIMEOUT_S, **kwargs)
