"""PricePredictor: giá trị hợp lý, trường thiếu, mã lạ, tên quận."""

import math

import numpy as np
import pytest
from prediction_fakes import make_predictor

from app.services.prediction.predictor import PricePredictor

BASE = {"property_code": 2, "district_code": 9, "area": 80, "latitude": 10.78, "longitude": 106.70}


def test_estimate_has_total_equal_price_per_m2_times_area():
    estimate = make_predictor().predict(BASE)
    assert estimate.price_per_m2 == 50.0
    assert estimate.total_price == pytest.approx(estimate.price_per_m2 * 80)
    assert estimate.district_median_per_m2 == 100.0  # median quận 9 (mã 9 = Quận 1)
    assert estimate.distance_to_center_km < 2


def test_missing_optional_fields_become_nan_for_the_imputer():
    predictor = make_predictor()
    predictor.predict(BASE)
    row = predictor.pipeline.rows[0]
    assert row.shape == (1, 9)
    assert row[["mặt tiền", "phòng ngủ", "số tầng"]].isna().all(axis=None)


def test_apartment_ignores_floors_and_frontage_and_land_ignores_floors_and_bedrooms():
    predictor = make_predictor()
    extras = {"floors": 5, "frontage": 4, "bedrooms": 2}
    predictor.predict({**BASE, "property_code": 0, **extras})
    predictor.predict({**BASE, "property_code": 7, **extras})
    apartment, land = predictor.pipeline.rows
    assert apartment["số tầng"].isna().all() and apartment["mặt tiền"].isna().all()
    assert apartment["phòng ngủ"].iloc[0] == 2
    assert land["số tầng"].isna().all() and land["phòng ngủ"].isna().all()
    assert land["mặt tiền"].iloc[0] == 4


def test_unknown_codes_raise_clear_errors():
    predictor = make_predictor()
    with pytest.raises(ValueError, match="loại nhà đất"):
        predictor.predict({**BASE, "property_code": 1})
    with pytest.raises(ValueError, match="quận/huyện"):
        predictor.predict({**BASE, "district_code": 24})


def test_median_falls_back_to_district_then_type_specific():
    predictor = make_predictor({"9": 100.0, "9|2": 120.0})
    assert predictor.predict(BASE).district_median_per_m2 == 120.0
    assert predictor.predict({**BASE, "property_code": 4}).district_median_per_m2 == 100.0
    assert predictor.predict({**BASE, "district_code": 0}).district_median_per_m2 is None


def test_distance_to_center_is_haversine():
    assert PricePredictor.distance_to_center(10.7769, 106.7009) == pytest.approx(0, abs=1e-6)
    # Quận 7 cách Nhà thờ Đức Bà khoảng 5-6 km
    assert 4 < PricePredictor.distance_to_center(10.73, 106.72) < 7
    assert not math.isnan(float(np.sum(PricePredictor.distance_to_center(
        np.array([10.8]), np.array([106.7])))))


@pytest.mark.parametrize("name, code", [
    ("Quận 7", 18), ("Q7", 18), ("q.7", 18), ("quan 07", 18), ("Quận 1", 9), ("Quận 10", 10),
    ("Thủ Đức", 21), ("TP Thủ Đức", 21), ("thu duc", 21), ("huyện Bình Chánh", 0),
    ("Bình Thạnh", 2), ("Dĩ An", None), ("Hà Nội", None), ("", None),
])
def test_find_district_handles_abbreviations_and_accents(name, code):
    assert PricePredictor.find_district(name) == code


def test_estimate_includes_tree_percentile_range_around_the_point_estimate():
    estimate = make_predictor().predict(BASE)
    assert estimate.price_per_m2_low <= estimate.price_per_m2 <= estimate.price_per_m2_high


def test_median_by_type_flag_tells_whether_median_is_type_specific():
    predictor = make_predictor({"9": 100.0, "9|2": 120.0})
    assert predictor.predict(BASE).median_by_type is True
    assert predictor.predict({**BASE, "property_code": 4}).median_by_type is False


@pytest.mark.parametrize("override", [
    {"area": None}, {"area": 0}, {"area": float("nan")}, {"area": -5},
    {"latitude": None}, {"longitude": None},
    {"latitude": float("nan")}, {"longitude": float("nan")},
    {"latitude": 21.03, "longitude": 105.85},   # Hà Nội
    {"latitude": 10.79, "longitude": 107.05},   # Long Thành, Đồng Nai
    {"district_code": True}, {"property_code": False}, {"district_code": 9.0},
])
def test_invalid_input_raises_value_error_never_key_error(override):
    with pytest.raises(ValueError):
        make_predictor().predict({**BASE, **override})


def test_missing_required_key_in_dict_input_is_a_clear_error():
    with pytest.raises((ValueError, TypeError)):
        make_predictor().predict({"property_code": 2, "district_code": 9})


def test_warnings_for_sparse_training_data_and_extrapolation():
    predictor = make_predictor({"9": 100.0, "9|2": 120.0})
    assert predictor.predict(BASE).warnings == []
    sparse = predictor.predict({**BASE, "property_code": 4})  # quận 9 x nhà mặt phố: không đủ mẫu
    assert "rất ít" in sparse.warnings[0]
    east = predictor.predict({**BASE, "latitude": 10.84, "longitude": 106.85})  # Q9 đông
    assert east.warnings == []
