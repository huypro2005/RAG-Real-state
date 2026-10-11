"""MessageRules: quy tắc tất định trên câu người dùng, bác đề xuất sai của LLM (không DB/OpenAI)."""

import pytest
from fakes import plan

from app.services.recommendation.schemas import PoiConstraint, PoiRequest, SearchConstraints
from app.services.recommendation.text_rules import MessageRules

LAST_RESULTS = ["a", "b", "c", "d", "e"]
OLD_EMPTY = SearchConstraints()
WARDS = ["Bình Trưng", "Thủ Đức", "An Khánh", "Long Trường", "Tân Sơn Nhì"]
DISTRICTS = ["Quận 2", "Quận 7", "Quận 9", "Huyện Củ Chi", "Thành phố Thủ Đức"]
OLD = SearchConstraints(
    price_max=4000, property_types=["Căn hộ chung cư"], district_ids=[59], bedrooms_min=2,
    near_pois=[PoiConstraint(poi_type="cho", max_distance_m=1000)], soft_query="yên tĩnh",
)


def correct(message, proposed, current=OLD, areas=("Quận 7",)):
    return MessageRules(message).correct(proposed, current, list(areas), WARDS, DISTRICTS).plan


@pytest.mark.parametrize("message", [
    "Thôi tìm lại từ đầu nhé", "thoi tim lai tu dau", "Làm lại từ đầu, bỏ hết điều kiện cũ",
    "Xóa điều kiện đi", "bat dau lai", "Bỏ hết các điều kiện",
])
def test_reset_phrases_force_reset_and_drop_echoed_conditions(message):
    echoed = plan("search", price_max=4000, district_names=["Quận 7"], bedrooms_min=2,
                  property_kinds=["can_ho"], soft_query="yên tĩnh")
    corrected = correct(message, echoed)
    assert corrected.intent == "reset"
    assert corrected.set_fields == plan("reset").set_fields  # không còn điều kiện cũ nào


def test_reset_keeps_new_conditions_of_the_same_message():
    corrected = correct("Tìm lại từ đầu, căn hộ Quận 3 dưới 4 tỷ",
                        plan("search", price_max=4000, district_names=["Quận 3"]))
    assert corrected.intent == "reset"
    assert corrected.set_fields.price_max == 4000
    assert corrected.set_fields.district_names == ["Quận 3"]


def test_not_a_reset_keeps_llm_intent():
    assert correct("Loại nào cũng được", plan("relax")).intent == "relax"


@pytest.mark.parametrize(("message", "ids", "missing"), [
    ("Căn thứ 2 có mấy phòng ngủ?", ["b"], []),
    ("So sánh căn 1, 2 và 4", ["a", "b", "d"], []),
    ("Vậy căn thứ 2 với căn thứ 3 so sánh giá", ["b", "c"], []),
    ("lô 2 với lô 4 lô nào rẻ hơn tính theo m2", ["b", "d"], []),
    ("So sánh 3 căn đầu giúp mình", ["a", "b", "c"], []),
    ("Căn đầu tiên gần trường nào nhất?", ["a"], []),
    ("Căn thứ nhất có mấy tầng?", ["a"], []),
    ("can thu hai dang bao gio", ["b"], []),
    ("Căn cuối thế nào", ["e"], []),
    ("Căn thứ mười có view đẹp không?", [], ["căn thứ 10"]),
    ("Căn thứ 7 thì sao?", [], ["căn thứ 7"]),
    # Không có tham chiếu tường minh: xét cả các tin vừa trả (spec 9 #25)
    ("Căn đó đăng lúc nào?", LAST_RESULTS, []),
    ("Căn nào gần chợ nhất trong 5 căn này?", LAST_RESULTS, []),
    ("Mấy căn này căn nào rẻ nhất?", LAST_RESULTS, []),
])
def test_references_by_position(message, ids, missing):
    assert MessageRules(message).references(LAST_RESULTS) == (ids, missing)


def test_references_by_listing_id():
    assert MessageRules("Tin 12345678 có sổ hồng chưa?").references(LAST_RESULTS) == (
        [], ["tin 12345678"]
    )
    found = MessageRules("Cho mình chi tiết tin 45704615").references(["45704615", "b"])
    assert found == (["45704615"], [])
    assert MessageRules("Căn thứ 2 thì sao?").references([]) == ([], ["căn thứ 2"])


@pytest.mark.parametrize(("message", "proposed", "areas", "districts", "wards"), [
    # Không tự suy quận từ phường (bảng trích điều kiện, vòng 1)
    ("Tìm căn hộ ở phường Bình Trưng giá 8 tỷ",
     plan(price_max=8000, district_names=["Quận 2"]), [], [], ["Bình Trưng"]),
    # C35#4: "phường Thủ Đức" là phường mới, không phải 3 quận cũ
    ("Thử phường Thủ Đức xem", plan("refine", district_names=["Thủ Đức"]),
     ["Phường An Khánh"], [], ["Thủ Đức"]),
    # Tên trần là quận cũ, kể cả khi LLM xếp vào phường
    ("Còn Thủ Đức thì sao, cả khu luôn", plan("refine", new_ward_names=["Thủ Đức"]),
     ["Phường Thủ Đức"], ["Thủ Đức"], []),
    ("tim dat o phuong long truong", plan(), [], [], ["Long Trường"]),
    # LLM được nhắc lại khu vực đang chọn
    ("Xem thêm cả Quận 10 nữa", plan("refine", district_names=["Quận 3", "Quận 10"]),
     ["Quận 3"], ["Quận 3", "Quận 10"], []),
    ("2 phòng ngủ", plan("refine", new_ward_names=["Bình Trưng"]),
     ["Phường Bình Trưng"], [], ["Bình Trưng"]),
    ("Tầm 3 tỷ, khu Thủ Đức",
     plan(price_max=3000, district_names=["Quận 2", "Quận 9", "Thủ Đức"]), [], ["Thủ Đức"], []),
    ("can ho q8 tam 3 ty", plan(district_names=["Quận 8"]), [], ["Quận 8"], []),
])
def test_areas(message, proposed, areas, districts, wards):
    delta = correct(message, proposed, SearchConstraints(), areas).set_fields
    assert (delta.district_names, delta.new_ward_names) == (districts, wards)


@pytest.mark.parametrize(("message", "cheaper"), [
    ("Rẻ hơn chút nữa", True), ("Có căn nào rẻ hơn chút không", True),
    ("giam gia xuong chut", True), ("Diện tích từ 90 tới 120m2", False),  # C11#4
])
def test_cheaper_only_when_message_asks(message, cheaper):
    assert correct(message, plan("refine", cheaper=True)).set_fields.cheaper is cheaper


@pytest.mark.parametrize(("message", "proposed", "expected"), [
    ("Nhà riêng 1 trệt 2 lầu ở Quận 12 tầm 4 tỷ", 2, None),
    ("Nhà xây năm 2015, hẻm 5m, tầng 12", 5, None),
    ("2PN 3 tỷ", 2, 2),
    ("3 ty 2pn", 2, 2),
    ("Bốn phòng ngủ", 4, 4),
    ("it nhat 3 phong ngu", 3, 3),
    ("Nhà 4 lầu có 3 phòng ngủ", 4, 3),  # LLM lấy nhầm số lầu: code lấy số đi với "phòng ngủ"
    ("Căn 2 phòng tắm", 2, None),
])
def test_bedrooms_need_number_with_pn_or_phong(message, proposed, expected):
    assert correct(message, plan(bedrooms_min=proposed)).set_fields.bedrooms_min == expected


def test_price_is_dropped_when_message_mentions_no_money():
    assert correct("Thêm 2 phòng ngủ", plan("refine", price_max=4000)).set_fields.price_max is None
    assert correct("Tối đa 8 tỏi", plan(price_max=8000)).set_fields.price_max == 8000
    assert correct("duoi 6 ty", plan(price_max=6000)).set_fields.price_max == 6000


def test_whole_city_clears_area_and_keeps_property_type():
    """C42#2: LLM bỏ nhầm loại BĐS và giữ quận khi người dùng chọn "toàn thành phố"."""
    proposed = plan("relax", clear=["property_types"], district_names=["Quận 1"])
    corrected = correct("Vậy mở rộng ra toàn thành phố đi", proposed, areas=["Quận 1"])
    assert corrected.clear_fields == ["district_ids", "new_ward_ids"]
    assert corrected.set_fields.district_names == []
    kept = correct("Không nhất thiết căn hộ, loại nào cũng được",
                   plan("relax", clear=["property_types"]))
    assert kept.clear_fields == ["property_types"]


@pytest.mark.parametrize(("message", "base", "low", "high"), [
    ("Tầm 3 tỷ cho căn hộ ở Quận 7", 3000, 2400, 3150),
    ("Cần mua nhà riêng Gò Vấp khoảng 2,5 tỷ", 2500, 2000, 2625),
    ("Đất Củ Chi cỡ 900 triệu", 900, 720, 945),
    ("Nhà mặt phố Quận 3 độ 20 tỷ", 20000, 16000, 21000),
    ("Mình xấp xỉ 6 tỷ, tìm căn hộ Bình Thạnh", 6000, 4800, 6300),
    ("Biệt thự liền kề Quận 9 gần 15 tỷ", 15000, 12000, 15750),
    ("Căn hộ Quận 10 khoảng 3 tỷ 8", 3800, 3040, 3990),
    ("tim can ho tam 3 ty", 3000, 2400, 3150),          # "tam" không dấu (#17)
    ("Căn hộ Quận 9 tầm 3 tỷ lệch 10% thôi", 3000, 2700, 3300),  # tỷ lệ người dùng nói
    ("Căn hộ Quận 9 tầm 3 tỷ lệch 10% thôi", 3300, 2700, 3300),  # LLM đã tự nhân: gốc từ câu
    ("Nhà tầm 2 tỷ rưỡi ở Gò Vấp", 2600, 2000, 2625),
])
def test_approximate_price_becomes_a_range_computed_by_code(message, base, low, high):
    delta = correct(message, plan(price_max=base, price_approx=True)).set_fields
    assert (delta.price_min, delta.price_max, delta.price_approx) == (low, high, True)


@pytest.mark.parametrize("message", [
    "Căn hộ Quận 7 dưới 3 tỷ", "Mình có 3 tỷ", "Tối đa 3 tỷ", "Tài chính tầm 3 tỷ đổ lại",
    "Nâng ngân sách lên 3 tỷ", "Có 3 tỷ", "Nhà riêng Quận 8, giá 4 tỷ 2",
])
def test_code_rejects_llm_approx_flag_without_approximate_keyword(message):
    delta = correct(message, plan(price_max=3000, price_approx=True)).set_fields
    assert (delta.price_min, delta.price_max, delta.price_approx) == (None, 3000, False)


def test_range_prices_are_kept_as_said():
    delta = correct("Nhà Gò Vấp từ 4 đến 6 tỷ",
                    plan(price_min=4000, price_max=6000, price_approx=True)).set_fields
    assert (delta.price_min, delta.price_max, delta.price_approx) == (4000, 6000, False)


@pytest.mark.parametrize(("message", "poi"), [
    ("Gần trung tâm thương mại nữa", "trung tâm thương mại, tttm"),
    ("gan TTTM", "trung tâm thương mại, tttm"),
    ("Cạnh công viên và siêu thị", "công viên"),
])
def test_places_outside_three_poi_types_become_soft_preferences(message, poi):
    llm = plan("refine", near_pois=[PoiRequest(poi_type="cho", max_distance_m=None)])
    delta = correct(message, llm).set_fields
    assert delta.near_pois == [] and poi in delta.soft_query


def test_soft_place_replaces_llm_wording_and_keeps_other_preferences():
    llm = plan("refine", soft_query="yên tĩnh, gần trung tâm thương mại")
    delta = correct("Gần trung tâm thương mại nữa", llm).set_fields
    assert delta.soft_query == "yên tĩnh, trung tâm thương mại, tttm"


@pytest.mark.parametrize(("message", "kept"), [
    ("Gần chợ nhé", True), ("cách chợ dưới 1km", True), ("gan cho 2km", True),
    ("Mình cho con đi học", False), ("Gần siêu thị", False),
])
def test_poi_needs_the_word_in_the_message(message, kept):
    llm = plan("refine", near_pois=[PoiRequest(poi_type="cho", max_distance_m=None)])
    assert bool(correct(message, llm).set_fields.near_pois) is kept


@pytest.mark.parametrize(("message", "kinds"), [
    ("tim dat o phuong long truong", ["dat"]),          # C37: LLM bỏ loại
    ("Tìm đất nền dự án Quận 9", ["dat_nen_du_an"]),
    ("can ho chung cu quan 7", ["can_ho"]),
    ("Mình cần nhà mặt phố hoặc biệt thự", ["biet_thu_lien_ke", "nha_mat_pho"]),
    ("Không cần căn hộ nữa, tìm nhà", []),
    ("duoi 8 ty", []),
])
def test_property_kind_is_inferred_from_keywords_when_llm_returns_none(message, kinds):
    delta = correct(message, plan(), SearchConstraints(), []).set_fields
    assert sorted(delta.property_kinds) == sorted(kinds)


@pytest.mark.parametrize(("message", "keeps_min"), [
    ("Đất Hóc Môn trên 100m2 dưới 5 tỷ", False),   # số đi với m2 không bao giờ là giá
    ("Nhà Gò Vấp từ 3 tỷ đến 4 tỷ", True),
    ("tối thiểu phải 8 tỷ", True),
])
def test_price_min_needs_explicit_lower_bound_words(message, keeps_min):
    delta = correct(message, plan(price_min=100, price_max=5000)).set_fields
    assert (delta.price_min is not None) is keeps_min


def test_reversed_budget_direction_is_detected():
    assert MessageRules("Nâng ngân sách lên 4 tỷ rưỡi").reverses_budget(4500, 6000)
    assert MessageRules("Giảm xuống 7 tỷ").reverses_budget(7000, 6000)
    assert not MessageRules("Nâng ngân sách lên 7 tỷ").reverses_budget(7000, 6000)
    assert not MessageRules("Dưới 4 tỷ rưỡi").reverses_budget(4500, 6000)


def test_districts_in_message_are_added_when_llm_returns_none():  # C35#5
    delta = correct("Còn Thủ Đức thì sao, cả khu luôn", plan("refine")).set_fields
    assert delta.district_names == ["Thành phố Thủ Đức"]
    delta = correct("Thử Quận 7 xem", plan("refine"), areas=()).set_fields
    assert delta.district_names == ["Quận 7"]
    assert correct("Căn 7 phòng ngủ", plan("refine"), areas=()).set_fields.district_names == []


def test_reset_keeps_property_kind_named_in_the_same_message():  # B6
    llm = plan("reset", clear=["property_types"], property_kinds=["dat_nen_du_an"])
    corrected = correct("Bỏ hết điều kiện, tìm lại: đất nền Quận 9 khoảng 5 tỷ", llm)
    assert corrected.set_fields.property_kinds == ["dat_nen_du_an"]


@pytest.mark.parametrize(("message", "answer"), [
    ("ừ đúng rồi", "yes"), ("Ok", "yes"), ("vâng", "yes"), ("chuẩn", "yes"),
    ("không, thôi", "no"), ("giữ nguyên nhé", "no"), ("Thôi", "no"),
    ("Nâng lên 4 tỷ", None), ("ừ nhưng cho mình xem thêm căn hộ ở Quận 2 đi nhé bạn", None),
])
def test_confirmation_only_for_short_yes_no_messages(message, answer):
    assert MessageRules(message).confirmation() == answer


@pytest.mark.parametrize(("message", "llm_max", "low", "high"), [
    ("can ho 1pn q2 khoang 2ty5", 2500, 2000, 2625),       # G1: viết liền
    ("can ho 1pn q2 khoang 2ty5", None, 2000, 2625),       # LLM mất giá: code dựng từ câu
    ("Nhà tầm 3tỷ8 ở Quận 7", 3800, 3040, 3990),
    ("Nhà tầm 3tỷ2 ở Quận 7", 9000, 2560, 3360),           # LLM sai: không tin
    ("Đất tầm 900tr", 900, 720, 945),
    ("Nhà Quận 7 tầm 1ty", 1000, 800, 1050),
])
def test_glued_money_amounts_are_parsed(message, llm_max, low, high):
    delta = correct(message, plan(price_max=llm_max)).set_fields
    assert (delta.price_min, delta.price_max, delta.price_approx) == (low, high, True)


@pytest.mark.parametrize(("message", "price"), [("Nhà dưới 2ty5", 2500), ("giá 900tr thôi", 900)])
def test_glued_money_is_kept_as_price_max(message, price):
    assert correct(message, plan(price_max=price)).set_fields.price_max == price


@pytest.mark.parametrize("message", [
    "Không nhất thiết căn hộ, loại nào cũng được", "loại gì cũng được", "khong nhat thiet nha pho",
])
def test_any_kind_clears_property_types_without_inferring_from_words(message):  # C18
    corrected = correct(message, plan("relax", property_kinds=["can_ho"]))
    assert corrected.set_fields.property_kinds == [] and "property_types" in corrected.clear_fields


def test_nha_pho_maps_to_the_same_kind_on_every_turn():
    for intent in ("search", "reset"):
        llm = plan(intent, property_kinds=["nha_mat_pho"])
        assert correct("nhà phố hẻm xe hơi bình thạnh", llm).set_fields.property_kinds == [
            "nha_rieng"]


def test_trg_is_a_school_and_unknown_new_poi_is_reported():
    near = [PoiRequest(poi_type="truong_hoc", max_distance_m=None)]
    assert correct("2pn gần trg cho con đi học", plan(near_pois=near)).set_fields.near_pois == near
    fixed = MessageRules("tìm nhà gần abc").correct(plan(near_pois=near), OLD_EMPTY, [], WARDS)
    assert fixed.plan.set_fields.near_pois == [] and fixed.ignored == ["gần trường học"]
    # LLM bịa POI cho "gần TTTM" (đã có cụm mềm giải thích) hoặc câu không có "gần": không báo
    fixed = MessageRules("có hồ bơi không, gần tttm càng tốt").correct(
        plan(near_pois=near), OLD_EMPTY, [], WARDS)
    assert fixed.ignored == []


@pytest.mark.parametrize("message", [
    "thôi giảm xuống 3tỷ2", "giảm xuống 3 tỷ", "giảm còn 3 tỷ nhé",
    "hạ ngân sách xuống 3 tỷ 2", "ngân sách chỉ còn 3 tỷ 2", "giảm xuống 3 tỷ thôi",
])
def test_reduce_to_amount_sets_new_max_instead_of_cutting_ten_percent(message):  # H7
    delta = correct(message, plan("relax", price_max=3200, cheaper=True)).set_fields
    assert delta.cheaper is False and delta.price_max == 3200


@pytest.mark.parametrize("message", ["rẻ hơn chút", "giảm bớt chút được không", "rẻ hơn tí"])
def test_cheaper_without_amount_still_means_ten_percent(message):
    assert correct(message, plan("refine", cheaper=True)).set_fields.cheaper is True


def test_typed_price_is_reported_for_out_of_range_amounts():  # I4 "3tr8"
    fixed = MessageRules("khoảng 3tr8 thôi").correct(
        plan(price_max=3.8, price_approx=True), SearchConstraints(), [], WARDS)
    assert fixed.typed_price == 3.8
