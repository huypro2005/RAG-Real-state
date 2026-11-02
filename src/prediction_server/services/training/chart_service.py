"""ChartService: dựng lại `charts` cho phiên bản đã train (chưa có charts hoặc muốn làm mới)."""
from src.prediction_server.db.runs import RunRepository
from src.prediction_server.services.registry.registry import ModelNotFoundError, ModelRegistry
from src.prediction_server.services.training.charts import ChartBuilder
from src.prediction_server.services.training.trainer import SPLIT_RULE, PriceModelTrainer


class ChartService:
    """Dựng từ file artifact + dữ liệu hiện tại. Tập test cố định theo crc32(listing_id) nên chỉ
    chính xác khi model train bằng luật chia này và số tin chưa đổi; ngược lại ghi
    `approximate: true` (test hiện tại có thể gồm tin model cũ đã thấy lúc train)."""

    def __init__(self, runs: RunRepository, registry: ModelRegistry, trainer: PriceModelTrainer):
        self.runs = runs
        self.registry = registry
        self.trainer = trainer

    def rebuild(self, run_id: int) -> dict:
        """Dựng và lưu charts của run; trả {run_id, approximate, bytes}.

        Raises:
            ModelNotFoundError: không có run đã train xong.
            ModelFileMissingError: file mô hình không còn.
        """
        run = self.runs.run(run_id)
        if run is None or run["status"] != "succeeded":
            raise ModelNotFoundError(f"Không có run {run_id} đã train xong")
        bundle = self.registry.load_bundle(run["artifact_path"], run_id)
        table = self.trainer.load_table()
        _, test = self.trainer.split(table)
        charts = ChartBuilder().build(
            table, test, bundle["pipeline"], bundle["features"], bundle["metrics"],
            bundle["residual_q90"], run["candidates"] or [])
        exact = (bundle.get("split_rule") == SPLIT_RULE
                 and self.runs.listings_count() == run["listings_snapshot"])
        if not exact:
            charts["approximate"] = True
        self.runs.set_charts(run_id, charts)
        return {"run_id": run_id, "approximate": not exact}

    def ensure_active(self) -> int | None:
        """Khi khởi động: dựng charts cho run đang hoạt động nếu còn thiếu; trả run_id đã dựng."""
        active = self.runs.active()
        if active is None or active["has_charts"]:
            return None
        self.rebuild(active["id"])
        return active["id"]
