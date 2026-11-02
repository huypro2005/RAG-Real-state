"""Container: dựng một lần mọi thành phần dùng chung; router lấy ra qua api/deps.py."""
from src.prediction_server.core.settings import ServerSettings
from src.prediction_server.db.connection import Database
from src.prediction_server.db.runs import RunRepository
from src.prediction_server.services.ingest.service import IngestService
from src.prediction_server.services.jobs.runner import JobRunner
from src.prediction_server.services.jobs.store import JobStore
from src.prediction_server.services.registry.registry import ModelRegistry
from src.prediction_server.services.training.chart_service import ChartService
from src.prediction_server.services.training.retrain import RetrainService


class Container:
    """Giữ settings, DB, registry và job runner của một server."""

    def __init__(self, settings: ServerSettings):
        self.settings = settings
        self.database = Database(settings.dsn)
        self.runs = RunRepository(self.database)
        self.registry = ModelRegistry(
            self.runs, settings.dsn, settings.models_dir, settings.active_check_seconds)
        self.store = JobStore()
        retrain = RetrainService(settings, self.runs, self.registry)
        self.runner = JobRunner(
            settings, self.runs, self.registry, retrain, IngestService(self.database),
            self.store, ChartService(self.runs, self.registry, retrain.trainer))
