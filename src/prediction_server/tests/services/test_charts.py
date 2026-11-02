"""D2: dữ liệu charts đúng schema, ≤ 150 KB, scatter/độ quan trọng chỉ tính trên test."""
import json

import pytest
from app.services.prediction.constants import HCM_LAT, HCM_LON

from src.prediction_server.services.training.charts import (
    MAX_BYTES,
    MAX_GEO_POINTS,
    MAX_POINTS,
    ChartBuilder,
)
from src.prediction_server.services.training.trainer import PriceModelTrainer
from src.prediction_server.tests.conftest import make_table


@pytest.fixture(scope="module")
def outcome(settings):
    return PriceModelTrainer(settings).train_table(make_table(1500))


def test_outcome_carries_charts_within_size_limit(outcome):
    assert len(json.dumps(outcome.charts, ensure_ascii=False)) <= MAX_BYTES


def test_schema_has_all_blocks(outcome):
    charts = outcome.charts
    assert charts["schema_version"] == 1
    assert set(charts) == {"schema_version", "price_distribution", "scatter",
                           "feature_importance", "district_type_median", "geo_scatter",
                           "candidates"}
    dist = charts["price_distribution"]
    assert 30 <= len(dist["bins"]) <= 40 and dist["unit"] == "triệu/m²"
    assert {"n", "mean", "median", "p10", "p90"} <= set(dist["stats"])
    assert sum(b["count"] for b in dist["bins"]) + dist["clipped_above"] == dist["stats"]["n"]
    assert all({"label", "median", "p10", "p90", "n"} <= set(v) for v in dist["by_type"].values())


def test_scatter_and_importance_use_the_fixed_test_set(outcome):
    scatter = outcome.charts["scatter"]
    assert scatter["n_test"] == outcome.test_rows
    assert len(scatter["points"]) == min(MAX_POINTS, outcome.test_rows)
    assert {"actual", "predicted", "type", "district"} == set(scatter["points"][0])
    assert {"r2_log", "mae", "mape", "residual_q90_log"} <= set(scatter)
    items = outcome.charts["feature_importance"]["items"]
    values = [i["importance"] for i in items]
    assert values == sorted(values, reverse=True)
    assert {i["feature"] for i in items} == set(outcome.bundle["features"])


def test_district_type_median_only_groups_with_five_or_more(outcome):
    rows = outcome.charts["district_type_median"]
    assert rows and all(r["n"] >= 5 for r in rows)
    assert {"district", "district_name", "property_type", "label", "median", "n"} == set(rows[0])


def test_candidates_block_marks_the_chosen_one(outcome):
    candidates = outcome.charts["candidates"]
    assert sum(c["chosen"] for c in candidates) == 1
    assert {"name", "cv_r2", "cv_std", "test_r2_log", "mae", "chosen"} == set(candidates[0])


def test_geo_scatter_shape_rounding_and_frame(outcome):
    geo = outcome.charts["geo_scatter"]
    assert 0 < len(geo["points"]) <= MAX_GEO_POINTS and geo["n_total"] >= len(geo["points"])
    assert {"lat", "lon", "price_per_m2", "area", "type"} == set(geo["points"][0])
    for point in geo["points"]:
        assert HCM_LAT[0] <= point["lat"] <= HCM_LAT[1]
        assert HCM_LON[0] <= point["lon"] <= HCM_LON[1]
        assert round(point["lat"], 4) == point["lat"] and round(point["price_per_m2"], 1) == point[
            "price_per_m2"] and round(point["area"], 1) == point["area"]
    assert geo["price_clip"]["p5"] < geo["price_clip"]["p95"]
    assert geo["bounds"]["lat"][0] < geo["bounds"]["lat"][1]
    assert geo["center"] == {"name": "Nhà thờ Đức Bà", "lat": 10.7769, "lon": 106.7009}


def test_geo_scatter_keeps_every_house_type_and_is_deterministic():
    table = make_table(3000)
    first, second = ChartBuilder.geo_scatter(table), ChartBuilder.geo_scatter(table)
    assert first == second
    assert len(first["points"]) <= MAX_GEO_POINTS
    assert {p["type"] for p in first["points"]} == set(table["loại nhà đất"])


def test_geo_scatter_keeps_rare_type_when_table_is_large():
    table = make_table(4000)
    table.loc[:9, "loại nhà đất"] = 9  # loại hiếm: 10 tin trên 4.000
    points = ChartBuilder.geo_scatter(table)["points"]
    assert sum(p["type"] == 9 for p in points) == 10
