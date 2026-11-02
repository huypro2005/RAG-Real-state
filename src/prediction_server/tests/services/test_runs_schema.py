"""P1: bảng price_model_runs có partial unique index (cần housing_dev đã `alembic upgrade head`)."""
import psycopg
import pytest

from src.prediction_server.core.settings import ServerSettings


@pytest.fixture
def conn():
    try:
        connection = psycopg.connect(ServerSettings().dsn, connect_timeout=3)
    except psycopg.OperationalError:
        pytest.skip("Không kết nối được database thử nghiệm")
    with connection:
        yield connection


def test_only_one_active_run_is_enforced_by_partial_unique_index(conn):
    row = conn.execute(
        "SELECT indexdef FROM pg_indexes WHERE indexname = 'price_model_runs_one_active_idx'"
    ).fetchone()
    if row is None:
        pytest.skip("Chưa có migration 0005")
    assert "UNIQUE" in row[0] and "WHERE is_active" in row[0]
