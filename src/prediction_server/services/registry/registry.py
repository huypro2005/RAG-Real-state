"""ModelRegistry: giữ đúng một mô hình đang phục vụ, nạp nóng khi kích hoạt/rollback."""
import logging
import threading
import time
from pathlib import Path

import joblib
from app.services.prediction.schools import SchoolCounter

from src.prediction_server.db.runs import RunRepository
from src.prediction_server.services.prediction.served_predictor import ServedPredictor

logger = logging.getLogger(__name__)


class ModelNotFoundError(Exception):
    """Không có run nào (đã train xong) với id này."""


class ModelFileMissingError(Exception):
    """Run có trong DB nhưng file .joblib đã bị dọn (KEEP_ARTIFACTS) hoặc xóa tay."""


class ModelRegistry:
    """Tham chiếu `_active` được gán nguyên tử (một phép gán), nên request đang chạy vẫn dùng
    mô hình cũ đến hết, request kế tiếp dùng mô hình mới, không cần khóa hay restart.

    Nhiều worker: mỗi worker tự hỏi DB ai đang `is_active` sau tối đa `check_seconds`.
    """

    def __init__(self, runs: RunRepository, dsn: str, models_dir: Path, check_seconds: float = 5):
        self.runs = runs
        self.models_dir = models_dir.resolve()
        self.check_seconds = check_seconds
        self.school_counter = SchoolCounter(dsn)
        self._active: ServedPredictor | None = None
        self._checked_at = 0.0
        self._lock = threading.Lock()  # chỉ để hai request không cùng nạp một file

    def current(self) -> ServedPredictor | None:
        """Mô hình đang phục vụ; None nếu chưa có (-> 503) hoặc DB/bảng chưa sẵn sàng."""
        if time.monotonic() - self._checked_at >= self.check_seconds:
            with self._lock:
                if time.monotonic() - self._checked_at >= self.check_seconds:
                    self._checked_at = time.monotonic()
                    self._sync_with_db()
        return self._active

    def activate(self, run_id: int) -> ServedPredictor:
        """Đặt run làm model hoạt động (rollback hoặc model mới thắng) và nạp nóng.

        Raises:
            ModelNotFoundError: không có run này.
            ModelFileMissingError: file mô hình của run đã bị xóa.
        """
        with self._lock:  # để _sync_with_db không ghi đè lại bằng model cũ giữa chừng
            row = self.runs.succeeded(run_id)
            if row is None:
                raise ModelNotFoundError(f"Không có run {run_id} đã train xong")
            predictor = self._load(row["artifact_path"], run_id)
            self.runs.set_active(run_id)
            self._active, self._checked_at = predictor, time.monotonic()
        return predictor

    def _sync_with_db(self) -> None:
        try:
            row = self.runs.active()
            if row is None:
                self._active = None
            elif self._active is None or self._active.run_id != row["id"]:
                self._active = self._load(row["artifact_path"], row["id"])
        except Exception as error:  # noqa: BLE001 - DB lỗi/thiếu bảng/mất file: giữ model đang có
            logger.warning("Không đồng bộ được model đang hoạt động: %r", error)

    def load_bundle(self, artifact_path: str | None, run_id: int) -> dict:
        """Nội dung file .joblib. Chỉ nạp file nằm trong MODELS_DIR: joblib.load chạy được mã tùy ý
        nên không tin đường dẫn lấy từ DB một cách mù quáng."""
        path = Path(artifact_path).resolve() if artifact_path else None
        if path is None or not path.is_relative_to(self.models_dir) or not path.is_file():
            raise ModelFileMissingError(
                f"File mô hình của run {run_id} không còn tồn tại hoặc nằm ngoài MODELS_DIR")
        return joblib.load(path)

    def _load(self, artifact_path: str | None, run_id: int) -> ServedPredictor:
        return ServedPredictor(self.load_bundle(artifact_path, run_id), self.school_counter)
