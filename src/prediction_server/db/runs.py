"""RunRepository: mọi câu SQL trên bảng price_model_runs (và đếm listings) nằm ở đây."""
import json

from psycopg.rows import dict_row

from src.prediction_server.db.connection import Database

LOCK_KEY = 7_201_001  # khóa tư vấn Postgres: một retrain tại một thời điểm, kể cả nhiều worker


class RunRepository:
    """Lịch sử retrain + model đang hoạt động. Server không tạo bảng (Alembic của backend tạo)."""

    def __init__(self, database: Database):
        self.database = database

    def schema_ready(self) -> bool:
        """False nếu chưa chạy `alembic upgrade head` (thiếu migration 0005)."""
        with self.database.connect() as conn:
            return conn.execute("SELECT to_regclass('public.price_model_runs')").fetchone()[0] \
                is not None

    # --- đọc ---
    def active(self) -> dict | None:
        """Dòng đang hoạt động (id, artifact_path, best_candidate, metrics, finished_at)."""
        with self.database.connect(row_factory=dict_row) as conn:
            return conn.execute(
                "SELECT id, artifact_path, best_candidate, metrics, finished_at, "
                "charts IS NOT NULL AS has_charts FROM price_model_runs WHERE is_active"
            ).fetchone()

    def running_count(self) -> int:
        with self.database.connect() as conn:
            return conn.execute(
                "SELECT count(*) FROM price_model_runs WHERE status = 'running'").fetchone()[0]

    def succeeded(self, run_id: int) -> dict | None:
        with self.database.connect(row_factory=dict_row) as conn:
            return conn.execute(
                "SELECT id, artifact_path FROM price_model_runs "
                "WHERE id = %s AND status = 'succeeded'", (run_id,)).fetchone()

    def history(self, limit: int) -> list[dict]:
        """Mọi cột trừ `charts` (nặng): chỉ báo `has_charts`."""
        with self.database.connect(row_factory=dict_row) as conn:
            return conn.execute(
                "SELECT id, created_at, finished_at, trigger, status, train_rows, test_rows, "
                "listings_snapshot, best_candidate, metrics, candidates, artifact_path, is_active, "
                "error, charts IS NOT NULL AS has_charts "
                "FROM price_model_runs ORDER BY id DESC LIMIT %s", (limit,)).fetchall()

    def run(self, run_id: int) -> dict | None:
        """Dòng run không kèm charts (để dựng lại charts)."""
        with self.database.connect(row_factory=dict_row) as conn:
            return conn.execute(
                "SELECT id, status, artifact_path, listings_snapshot, candidates, metrics, "
                "is_active FROM price_model_runs WHERE id = %s", (run_id,)).fetchone()

    def charts(self, run_id: int | None) -> dict | None:
        """charts của run (None = run đang hoạt động); None nếu không có run hoặc chưa có charts."""
        where, args = ("is_active", ()) if run_id is None else ("id = %s", (run_id,))
        with self.database.connect() as conn:
            row = conn.execute(
                f"SELECT charts FROM price_model_runs WHERE {where}", args).fetchone()
        return row[0] if row else None

    def set_charts(self, run_id: int, charts: dict) -> None:
        with self.database.connect(autocommit=True) as conn:
            conn.execute("UPDATE price_model_runs SET charts = %s WHERE id = %s",
                         (json.dumps(charts, ensure_ascii=False), run_id))

    def listings_count(self) -> int:
        with self.database.connect() as conn:
            return conn.execute("SELECT count(*) FROM listings").fetchone()[0]

    def last_snapshot(self) -> int | None:
        """Số tin lúc lần train thành công gần nhất (None nếu chưa có)."""
        with self.database.connect() as conn:
            row = conn.execute(
                "SELECT listings_snapshot FROM price_model_runs WHERE status = 'succeeded' "
                "ORDER BY id DESC LIMIT 1").fetchone()
        return row[0] if row else None

    def artifacts(self) -> list[tuple[str, bool]]:
        """(đường dẫn file, is_active) của mọi run còn file, mới nhất trước."""
        with self.database.connect() as conn:
            return conn.execute(
                "SELECT artifact_path, is_active FROM price_model_runs "
                "WHERE artifact_path IS NOT NULL ORDER BY id DESC").fetchall()

    # --- ghi ---
    def set_active(self, run_id: int) -> None:
        with self.database.connect() as conn, conn.transaction():
            # Bỏ cờ cũ trước, partial unique index mới không chặn
            conn.execute("UPDATE price_model_runs SET is_active = false WHERE is_active")
            conn.execute("UPDATE price_model_runs SET is_active = true WHERE id = %s", (run_id,))

    def insert_running(self, trigger: str, listings_now: int) -> int:
        with self.database.connect(autocommit=True) as conn:
            return conn.execute(
                "INSERT INTO price_model_runs (trigger, status, listings_snapshot) "
                "VALUES (%s, 'running', %s) RETURNING id", (trigger, listings_now)).fetchone()[0]

    def insert_skipped(self, trigger: str, listings_now: int, reason: str) -> int:
        with self.database.connect(autocommit=True) as conn:
            return conn.execute(
                "INSERT INTO price_model_runs (trigger, status, listings_snapshot, finished_at, "
                "error) VALUES (%s, 'skipped', %s, now(), %s) RETURNING id",
                (trigger, listings_now, reason)).fetchone()[0]

    def finish(self, run_id: int, **columns) -> None:
        for key in ("metrics", "candidates", "charts"):
            if key in columns:
                columns[key] = json.dumps(columns[key], ensure_ascii=False)
        assignments = ", ".join(f"{name} = %({name})s" for name in columns)
        with self.database.connect(autocommit=True) as conn:
            conn.execute(f"UPDATE price_model_runs SET {assignments}, finished_at = now() "
                         f"WHERE id = %(id)s", {**columns, "id": run_id})

    # --- khóa tư vấn ---
    def try_lock(self):
        """Kết nối giữ khóa (đóng nó là nhả khóa) hoặc None nếu đang có retrain khác chạy."""
        conn = self.database.connect(autocommit=True)
        if conn.execute("SELECT pg_try_advisory_lock(%s)", (LOCK_KEY,)).fetchone()[0]:
            return conn
        conn.close()
        return None

    def clean_orphans(self) -> int:
        """Dọn dòng `running` mồ côi sau restart; chỉ khi giữ được khóa, tức không có retrain
        nào đang chạy thật (kể cả ở worker khác)."""
        conn = self.try_lock()
        if conn is None:
            return 0
        with conn:
            return conn.execute(
                "UPDATE price_model_runs SET status = 'failed', finished_at = now(), "
                "error = 'orphaned: server khởi động lại khi đang train' "
                "WHERE status = 'running'").rowcount
