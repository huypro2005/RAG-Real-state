"""JobStore: chạy việc nền trong thread pool, giữ trạng thái job trong bộ nhớ."""
import logging
import threading
import traceback
import uuid
from collections import OrderedDict
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

logger = logging.getLogger(__name__)

MAX_JOBS_KEPT = 200  # job cũ bị quên dần; lịch sử retrain bền vững nằm ở price_model_runs


class JobStore:
    """`submit(kind, work)`: work(job) cập nhật job["steps"] và trả status cuối (mặc định
    "succeeded"). Mất job đang chạy khi restart là chấp nhận được (spec mục 3)."""

    def __init__(self, workers: int = 3):
        self.executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="job")
        self.jobs: OrderedDict[str, dict] = OrderedDict()
        self.lock = threading.Lock()

    def submit(self, kind: str, work: Callable[[dict], str | None]) -> str:
        job = {"job_id": uuid.uuid4().hex[:12], "kind": kind, "status": "queued", "steps": {},
               "error": None, "created_at": self._now(), "finished_at": None}
        with self.lock:
            self.jobs[job["job_id"]] = job
            while len(self.jobs) > MAX_JOBS_KEPT:
                self.jobs.popitem(last=False)
        self.executor.submit(self._execute, job, work)
        return job["job_id"]

    def get(self, job_id: str) -> dict | None:
        return self.jobs.get(job_id)

    def running(self) -> list[dict]:
        return [job for job in list(self.jobs.values()) if job["status"] in ("queued", "running")]

    def shutdown(self) -> None:
        self.executor.shutdown(wait=False, cancel_futures=True)

    def _execute(self, job: dict, work: Callable[[dict], str | None]) -> None:
        job["status"] = "running"
        try:
            job["status"] = work(job) or "succeeded"
        except Exception as error:
            logger.exception("Job %s lỗi", job["job_id"])
            job["status"], job["error"] = "failed", f"{error!r}\n{traceback.format_exc()}"[:4000]
        job["finished_at"] = self._now()

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat(timespec="seconds")
