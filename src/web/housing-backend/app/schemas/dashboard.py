"""Dữ liệu dashboard mô hình giá, khớp schema `charts` của Prediction Server.

Spec: docs/tasks/model-dashboard.md.

Backend chỉ proxy và validate, không tính lại.
"""

from datetime import datetime

from pydantic import BaseModel


class DashboardMetrics(BaseModel):
    r2_log: float | None = None
    mae: float | None = None
    mape: float | None = None


class DashboardRun(BaseModel):
    """Một phiên bản mô hình (một dòng price_model_runs), không kèm charts."""

    id: int
    created_at: datetime
    finished_at: datetime | None = None
    trigger: str
    status: str
    is_active: bool
    best_candidate: str | None = None
    train_rows: int | None = None
    test_rows: int | None = None
    metrics: DashboardMetrics | None = None
    has_charts: bool


class PriceBin(BaseModel):
    x0: float
    x1: float
    count: int


class PriceStats(BaseModel):
    n: int
    mean: float
    median: float
    p10: float
    p90: float


class TypeStats(BaseModel):
    label: str
    n: int
    median: float
    p10: float
    p90: float


class PriceDistribution(BaseModel):
    unit: str
    bins: list[PriceBin]
    clipped_above: int
    stats: PriceStats
    by_type: dict[str, TypeStats]


class ScatterPoint(BaseModel):
    actual: float
    predicted: float
    type: int
    district: int


class Scatter(BaseModel):
    points: list[ScatterPoint]
    n_test: int
    r2_log: float
    mae: float
    mape: float
    residual_q90_log: float


class ImportanceItem(BaseModel):
    feature: str
    importance: float
    std: float


class FeatureImportance(BaseModel):
    method: str
    items: list[ImportanceItem]


class DistrictTypeMedian(BaseModel):
    district: int
    district_name: str
    property_type: int
    label: str
    median: float
    n: int


class CandidateRow(BaseModel):
    name: str
    cv_r2: float
    cv_std: float
    test_r2_log: float
    mae: float
    chosen: bool


class GeoPoint(BaseModel):
    lat: float
    lon: float
    price_per_m2: float
    area: float
    type: int


class GeoBounds(BaseModel):
    lat: list[float]
    lon: list[float]


class PriceClip(BaseModel):
    p5: float
    p95: float


class GeoCenter(BaseModel):
    name: str
    lat: float
    lon: float


class GeoScatter(BaseModel):
    """Tin trên bản đồ: x = kinh độ, y = vĩ độ, màu = giá/m², cỡ = diện tích."""

    points: list[GeoPoint]
    n_total: int
    bounds: GeoBounds
    price_clip: PriceClip
    center: GeoCenter


class Charts(BaseModel):
    schema_version: int
    approximate: bool = False  # dựng lại từ test hiện tại, không đúng tập test lúc train
    price_distribution: PriceDistribution
    scatter: Scatter
    feature_importance: FeatureImportance
    district_type_median: list[DistrictTypeMedian]
    geo_scatter: GeoScatter | None = None  # khóa tùy chọn: phiên bản dựng trước khi có thì thiếu
    candidates: list[CandidateRow]


class ModelDetail(BaseModel):
    model: DashboardRun
    charts: Charts
