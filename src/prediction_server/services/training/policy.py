"""RetrainPolicy: các quyết định thuần túy (không đụng DB) nên test được bằng số."""
from src.prediction_server.core.settings import ServerSettings
from src.prediction_server.services.training.trainer import TrainingOutcome


class RetrainPolicy:
    """Đủ dữ liệu không, có retrain không, và model mới có được kích hoạt không."""

    def __init__(self, settings: ServerSettings):
        self.settings = settings

    def enough_data(self, listings_now: int):
        """(có/không, lý do). Áp cả khi ép retrain: quá ít tin thì không chia nổi train/test."""
        if listings_now < self.settings.min_train_rows:
            return False, f"Mới có {listings_now} tin, cần >= {self.settings.min_train_rows}"
        return True, ""

    def should_retrain(self, listings_now: int, snapshot: int | None, has_model: bool):
        """(có/không, lý do). snapshot = số tin lúc lần train thành công gần nhất (None = chưa)."""
        enough, reason = self.enough_data(listings_now)
        if not enough:
            return False, reason
        if snapshot is None or not has_model:
            return True, "Chưa có model nào"
        new = listings_now - snapshot
        need = min(self.settings.retrain_min_new, self.settings.retrain_min_ratio * listings_now)
        if new >= need:
            return True, f"{new} tin mới >= ngưỡng {need:.0f}"
        return False, f"Chỉ có {new} tin mới so với lần train trước, ngưỡng {need:.0f}"

    def should_promote(self, outcome: TrainingOutcome, active_metrics: dict | None):
        """(có/không, lý do) so với model đang hoạt động (`active_metrics` None = chưa có).

        - Có baseline (model cũ train cùng luật chia nên không thấy test mới): đo trên CÙNG test,
          kích hoạt khi R² log không kém (gain >= 0, hòa thì ưu tiên model mới vì dữ liệu mới hơn),
          hoặc hơn metric đã ghi của model cũ ít nhất PROMOTE_MIN_GAIN.
        - Không có baseline (model cũ train bằng cách chia ngẫu nhiên cũ): đo lại trên test mới là
          thiên vị, còn metric đã ghi nằm trên một test khác nên không so được. Coi đây là lần
          chuyển giao sang luật chia cố định: kích hoạt model mới một lần.
        - Có baseline: MAE không được tệ hơn PROMOTE_MAX_REGRESSION.
        """
        if active_metrics is None:
            return True, "Chưa có model hoạt động"
        new, baseline = outcome.metrics, outcome.baseline
        if baseline is None:
            return True, "Chuyển giao: model cũ chưa có luật chia cố định nên không so được"
        recorded_gain = new["r2_log"] - active_metrics.get("r2_log", float("inf"))
        reference, source = baseline, "cùng test"
        better = (new["r2_log"] - baseline["r2_log"] >= 0
                  or recorded_gain >= self.settings.promote_min_gain)
        if not better:
            return False, (f"not_promoted: R² log mới {new['r2_log']} kém model cũ "
                           f"{reference['r2_log']} ({source})")
        limit = reference["mae"] * (1 + self.settings.promote_max_regression)
        if new["mae"] > limit:
            return False, (f"not_promoted: MAE {new['mae']} tệ hơn quá {limit:.4f} "
                           f"(model cũ {reference['mae']}, {source})")
        return True, f"R² log {new['r2_log']} so với {reference['r2_log']} ({source})"
