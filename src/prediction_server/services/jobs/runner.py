"""JobRunner: các việc nền (ingest, retrain) và lịch kiểm tra retrain định kỳ."""
import logging
import threading

from src.prediction_server.core.settings import ServerSettings
from src.prediction_server.db.runs import RunRepository
from src.prediction_server.services.ingest.service import IngestService
from src.prediction_server.services.jobs.store import JobStore
from src.prediction_server.services.registry.registry import ModelRegistry
from src.prediction_server.services.training.chart_service import ChartService
from src.prediction_server.services.training.retrain import RetrainService

logger = logging.getLogger(__name__)

# status của kết quả retrain -> status của job
JOB_STATUS = {"busy": "skipped", "skipped": "skipped", "failed": "failed"}


class JobRunner:
    """Nhận việc từ API, đưa vào JobStore; `start()`/`stop()` gắn vào vòng đời FastAPI."""

    def __init__(self, settings: ServerSettings, runs: RunRepository, registry: ModelRegistry,
                 retrain: RetrainService, ingest: IngestService, store: JobStore,
                 charts: ChartService):
        self.settings = settings
        self.runs = runs
        self.registry = registry
        self.retrain = retrain
        self.ingest = ingest
        self.store = store
        self.charts = charts
        self._stop = threading.Event()

    def start(self) -> None:
        """Dọn run mồ côi, nạp model đang hoạt động, bootstrap nếu chưa có, bật lịch retrain."""
        try:
            if not self.runs.schema_ready():
                logger.warning("Thiếu bảng price_model_runs: chạy `alembic upgrade head`")
                return
            self.runs.clean_orphans()
            if self.registry.current() is None:
                self.submit_retrain("bootstrap")
            else:
                self.store.submit("charts", self._ensure_charts)
        except Exception:
            logger.exception("Khởi động chưa kiểm tra được DB")
        if self.settings.scheduler_enabled and self.settings.retrain_interval_hours > 0:
            threading.Thread(target=self._schedule, name="scheduler", daemon=True).start()

    def stop(self) -> None:
        self._stop.set()
        self.store.shutdown()

    def submit_ingest(self, records: list, malformed: int = 0) -> str:
        """Nạp nền, xong thì kiểm tra điều kiện retrain (có thể ghi `skipped`)."""
        def work(job: dict) -> str | None:
            job["steps"] = self.ingest.run(records, malformed)
            result = job["steps"]["retrain"] = self.retrain.run("ingest")
            if result["status"] == "failed":  # đã nạp nhưng retrain lỗi: không báo succeeded
                job["error"] = f"Đã nạp tin nhưng retrain sau đó lỗi: {result['error']}"
                return "partial"
            return None
        return self.store.submit("ingest", work)

    def submit_retrain(self, trigger: str = "manual") -> str:
        """`manual` ép retrain bất kể số tin mới; trigger khác phải qua kiểm tra điều kiện."""
        def work(job: dict) -> str | None:
            result = self.retrain.run(trigger, force=trigger == "manual")
            job["steps"]["retrain"] = result
            return JOB_STATUS.get(result["status"])
        return self.store.submit("retrain", work)

    def submit_charts_rebuild(self, run_id: int) -> str:
        """Dựng lại charts của một phiên bản (nền)."""
        def work(job: dict) -> None:
            job["steps"]["charts"] = self.charts.rebuild(run_id)
        return self.store.submit("charts", work)

    def _ensure_charts(self, job: dict) -> None:
        """Khởi động: phiên bản đang chạy chưa có charts thì dựng nền."""
        rebuilt = self.charts.ensure_active()
        job["steps"]["charts"] = {"run_id": rebuilt} if rebuilt else {"skipped": "đã có charts"}

    def _schedule(self) -> None:
        """Mỗi RETRAIN_INTERVAL_HOURS kiểm tra điều kiện; nhiều worker cùng chạy cũng chỉ một
        retrain thật nhờ khóa tư vấn."""
        while not self._stop.wait(self.settings.retrain_interval_hours * 3600):
            self.submit_retrain("schedule")
