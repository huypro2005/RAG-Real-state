"""Merge điều kiện, validator và gộp tin đăng lại: hàm thuần, không cần DB hay OpenAI."""

from datetime import date

import pytest
from fakes import plan

from app.services.recommendation.schemas import PoiConstraint, PoiRequest, SearchConstraints
from app.services.recommendation.search import group_reposts
from app.services.recommendation.service import (
    DEFAULT_POI_DISTANCE_M,
    merge_constraints,
    validate_constraints,
)

HOSPITAL_2KM = PoiConstraint(poi_type="benh_vien", max_distance_m=2000)
MARKET_1KM = PoiConstraint(poi_type="cho", max_distance_m=1000)


def base() -> SearchConstraints:
    return SearchConstraints(
        price_max=3000, property_types=["Căn hộ chung cư"], district_ids=[54, 61, 71],
        new_ward_ids=[7692], bedrooms_min=2, near_pois=[HOSPITAL_2KM, MARKET_1KM],
        soft_query="yên tĩnh",
    )


def test_search_sets_fields_and_resolved_area_ids():
    merged = merge_constraints(
        SearchConstraints(), plan(price_max=3000, district_names=["Thủ Đức"]), [54, 61, 71], []
    )
    assert merged == SearchConstraints(price_max=3000, district_ids=[54, 61, 71])


def test_switch_area_replaces_area_and_keeps_other_conditions():
    merged = merge_constraints(base(), plan("refine", district_names=["Quận 7"]), [59], [])
    expected = base().model_copy(update={"district_ids": [59], "new_ward_ids": []})
    assert merged == expected


def test_cheaper_lowers_price_max_by_ten_percent():
    assert merge_constraints(base(), plan("refine", cheaper=True), [], []).price_max == 2700


def test_new_price_max_overrides_and_keeps_rest():
    merged = merge_constraints(base(), plan("relax", price_max=4000), [], [])
    assert merged == base().model_copy(update={"price_max": 4000})


def test_clear_one_poi_type_keeps_the_others():
    merged = merge_constraints(base(), plan("relax", clear=["near_pois.benh_vien"]), [], [])
    assert merged.near_pois == [MARKET_1KM]
    assert merged.model_copy(update={"near_pois": base().near_pois}) == base()


def test_any_district_clears_both_area_fields():
    merged = merge_constraints(
        base(), plan("relax", clear=["district_ids", "new_ward_ids"]), [], []
    )
    assert merged.district_ids == [] and merged.new_ward_ids == []
    assert merged.price_max == 3000 and merged.near_pois == base().near_pois


def test_property_kinds_map_to_db_values_without_duplicates():
    merged = merge_constraints(
        SearchConstraints(), plan(property_kinds=["nha_rieng", "nha_mat_pho", "nha_rieng"]), [], []
    )
    assert merged.property_types == ["Nhà riêng", "Nhà mặt phố"]


def test_same_poi_type_is_replaced_not_duplicated():
    request = PoiRequest(poi_type="benh_vien", max_distance_m=1000)
    merged = merge_constraints(base(), plan("refine", near_pois=[request]), [], [])
    assert merged.near_pois == [MARKET_1KM, PoiConstraint(poi_type="benh_vien",
                                                          max_distance_m=1000)]


def test_poi_without_distance_uses_2km_default():
    request = PoiRequest(poi_type="truong_hoc", max_distance_m=None)
    merged = merge_constraints(SearchConstraints(), plan(near_pois=[request]), [], [])
    assert DEFAULT_POI_DISTANCE_M == 2000
    assert merged.near_pois == [PoiConstraint(poi_type="truong_hoc", max_distance_m=2000)]


def test_soft_query_accumulates_once():
    merged = merge_constraints(base(), plan("refine", soft_query="hẻm xe hơi"), [], [])
    assert merged.soft_query == "yên tĩnh, hẻm xe hơi"
    again = merge_constraints(merged, plan("refine", soft_query="hẻm xe hơi"), [], [])
    assert again.soft_query == "yên tĩnh, hẻm xe hơi"


def test_reset_starts_from_empty_constraints():
    merged = merge_constraints(base(), plan("reset", price_max=5000), [], [])
    assert merged == SearchConstraints(price_max=5000)


def test_clear_then_set_in_same_turn():
    merged = merge_constraints(
        base(), plan("relax", clear=["property_types"], property_kinds=["dat"]), [], []
    )
    assert merged.property_types == ["Bán đất"]


@pytest.mark.parametrize(
    ("changes", "problem"),
    [
        ({"price_min": 5000, "price_max": 3000}, "giá tối thiểu lớn hơn"),
        ({"price_max": 50}, "giá tối đa 50"),            # dưới 100 triệu
        ({"price_max": 600_000}, "giá tối đa 600000"),   # trên 500 tỷ
        ({"area_min": 5}, "diện tích tối thiểu 5"),
        ({"area_min": 120, "area_max": 80}, "diện tích tối thiểu lớn hơn"),
        ({"near_pois": [PoiConstraint(poi_type="cho", max_distance_m=50)]}, "khoảng cách 50"),
        ({"near_pois": [PoiConstraint(poi_type="cho", max_distance_m=30_000)]}, "30000"),
    ],
)
def test_validator_reports_invalid_field(changes, problem):
    problems = validate_constraints(SearchConstraints(**changes))
    assert len(problems) == 1 and problem in problems[0]


def test_validator_accepts_valid_constraints():
    assert validate_constraints(base()) == []
    assert validate_constraints(SearchConstraints(price_min=100, price_max=500_000)) == []


def listing(listing_id, posted, lat=10.7, lon=106.7, price=2800.0, bedrooms=2):
    return {"listing_id": listing_id, "property_type": "Căn hộ chung cư", "price": price,
            "area": 55.0, "bedrooms": bedrooms, "latitude": lat, "longitude": lon,
            "posted_at": date(2026, 9, posted)}


def test_reposts_within_30m_are_grouped_and_newest_kept_at_first_rank():
    rows = [
        listing("A", posted=10),
        listing("X", posted=1, price=1500.0),
        listing("B", posted=15, lat=10.70010),  # cách A ~11 m, cùng khóa
    ]
    result = group_reposts(rows)
    assert [r["listing_id"] for r in result] == ["B", "X"]  # nhóm đứng ở hạng của A
    assert result[0]["similar_ids"] == ["A"] and result[1]["similar_ids"] == []


@pytest.mark.parametrize(
    "other",
    [
        listing("B", posted=15, lat=10.7010),         # cách ~110 m
        listing("B", posted=15, bedrooms=1),          # khác số phòng ngủ
        listing("B", posted=15, lat=None, lon=None),  # không có tọa độ thì không gộp
    ],
)
def test_reposts_not_grouped_when_key_or_distance_differs(other):
    result = group_reposts([listing("A", posted=10), other])
    assert [r["listing_id"] for r in result] == ["A", "B"]


def approx(low=2400.0, high=3150.0):
    return plan(price_min=low, price_max=high, price_approx=True)


def test_approximate_price_sets_range_and_derived_flag():
    merged = merge_constraints(SearchConstraints(), approx(), [], [])
    assert (merged.price_min, merged.price_max, merged.price_min_derived) == (2400, 3150, True)


def test_approx_lower_bound_never_goes_below_valid_price_range():
    merged = merge_constraints(SearchConstraints(), approx(96.0, 126.0), [], [])
    assert merged.price_min == 100


def test_new_max_after_approx_drops_derived_min_but_keeps_explicit_min():
    derived = merge_constraints(SearchConstraints(), approx(), [], [])
    changed = merge_constraints(derived, plan("relax", price_max=4000), [], [])
    assert (changed.price_min, changed.price_max, changed.price_min_derived) == (None, 4000, False)
    explicit = SearchConstraints(price_min=2000, price_max=3000)
    kept = merge_constraints(explicit, plan("relax", price_max=4000), [], [])
    assert (kept.price_min, kept.price_max) == (2000, 4000)


def test_explicit_min_after_approx_is_kept_as_user_said():
    derived = merge_constraints(SearchConstraints(), approx(), [], [])
    merged = merge_constraints(derived, plan("refine", price_min=2000), [], [])
    assert (merged.price_min, merged.price_max, merged.price_min_derived) == (2000, 3150, False)


def test_cheaper_lowers_both_bounds_of_a_range():
    derived = merge_constraints(SearchConstraints(), approx(5600.0, 7350.0), [], [])
    merged = merge_constraints(derived, plan("refine", cheaper=True), [], [])
    assert (merged.price_min, merged.price_max) == (5040, 6615)
    assert merged.price_min_derived  # vẫn là khoảng xấp xỉ


def test_clearing_price_min_resets_derived_flag():
    derived = merge_constraints(SearchConstraints(), approx(), [], [])
    merged = merge_constraints(derived, plan("relax", clear=["price_min"]), [], [])
    assert merged.price_min is None and not merged.price_min_derived


def test_land_kinds_drop_old_bedroom_condition_unless_restated():
    assert merge_constraints(base(), plan("refine", property_kinds=["dat"]), [], []
                             ).bedrooms_min is None
    kept = merge_constraints(base(), plan("refine", property_kinds=["nha_rieng"]), [], [])
    assert kept.bedrooms_min == base().bedrooms_min
