"""RetrainService: quyết định có retrain không, huấn luyện, ghi lịch sử và kích hoạt model thắng."""
import logging
import os
import traceback
from pathlib import Path

import joblib

from src.prediction_server.core.settings import ServerSettings
from src.prediction_server.db.runs import RunRepository
from src.prediction_server.services.registry.registry import ModelRegistry
from src.prediction_server.services.training.policy import RetrainPolicy
from src.prediction_server.services.training.trainer import PriceModelTrainer

logger = logging.getLogger(__name__)


class RetrainService:
    """run(trigger, force) giữ khóa tư vấn suốt quá trình; nơi duy nhất ghi price_model_runs."""

    def __init__(self, settings: ServerSettings, runs: RunRepository, registry: ModelRegistry):
        self.settings = settings
        self.runs = runs
        self.registry = registry
        self.policy = RetrainPolicy(settings)
        self.trainer = PriceModelTrainer(settings)

    def run(self, trigger: str, force: bool = False) -> dict:
        """Trả {status: busy|skipped|succeeded|failed, ...}; lỗi huấn luyện không bị ném ra."""
        lock = self.runs.try_lock()
        if lock is None:
            return {"status": "busy", "reason": "Đang có một retrain khác chạy"}
        with lock:  # đóng kết nối = nhả khóa, kể cả khi lỗi
            return self._run_locked(trigger, force)

    def _run_locked(self, trigger: str, force: bool) -> dict:
        now = self.runs.listings_count()
        active = self.runs.active()
        # Ép retrain bỏ qua ngưỡng "tin mới" nhưng vẫn cần đủ tin để chia train/test
        if force:
            go, reason = self.policy.enough_data(now)
        else:
            go, reason = self.policy.should_retrain(
                now, self.runs.last_snapshot(), active is not None)
        if not go:
            return {"status": "skipped", "reason": reason,
                    "run_id": self.runs.insert_skipped(trigger, now, reason)}
        if active is None and trigger != "manual":
            trigger = "bootstrap"
        run_id = self.runs.insert_running(trigger, now)
        try:
            return self._train_and_register(run_id, now, active["metrics"] if active else None)
        except Exception as error:
            logger.exception("Retrain %s lỗi", run_id)
            trace = f"{error!r}\n{traceback.format_exc()}"
            self.runs.finish(run_id, status="failed", error=trace[:4000])
            return {"status": "failed", "run_id": run_id, "error": repr(error)}

    def _train_and_register(self, run_id: int, listings_now: int, active_metrics) -> dict:
        outcome = self.trainer.train(self.registry.current())
        promote, reason = self.policy.should_promote(outcome, active_metrics)
        path = self._write_artifact(run_id, {**outcome.bundle, "run_id": run_id})
        decision = {"decision": "promoted" if promote else "not_promoted", "reason": reason,
                    "baseline": outcome.baseline}
        self.runs.finish(
            run_id, status="succeeded", train_rows=outcome.train_rows, test_rows=outcome.test_rows,
            listings_snapshot=listings_now, best_candidate=outcome.bundle["candidate"],
            metrics=outcome.metrics, candidates=[*outcome.candidates, decision],
            charts=outcome.charts,
            artifact_path=str(path))
        if promote:
            self.registry.activate(run_id)
        self._prune_artifacts()
        return {"status": "succeeded", "run_id": run_id, "promoted": promote, "reason": reason,
                "best_candidate": outcome.bundle["candidate"], "metrics": outcome.metrics}

    def _write_artifact(self, run_id: int, bundle: dict) -> Path:
        """Ghi tệp tạm rồi đổi tên: process khác không bao giờ đọc phải file ghi dở."""
        self.settings.models_dir.mkdir(parents=True, exist_ok=True)
        path = self.settings.models_dir / f"price_run_{run_id}.joblib"
        temp = path.with_suffix(".joblib.tmp")
        joblib.dump(bundle, temp)
        os.replace(temp, path)
        return path

    def _prune_artifacts(self) -> None:
        """Giữ KEEP_ARTIFACTS bản gần nhất và bản đang hoạt động; xóa file còn lại."""
        for artifact_path, is_active in self.runs.artifacts()[self.settings.keep_artifacts:]:
            if not is_active:
                Path(artifact_path).unlink(missing_ok=True)
