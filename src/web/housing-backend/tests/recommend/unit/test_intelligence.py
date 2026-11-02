"""Intent mới của chatbot gợi ý (chat-intelligence.md 3.3): chitchat, other_mode, appraise.

Quy tắc kiểm chứng và ListingValuer chạy không cần DB; luồng RecommendationService dùng DB thật
(housing_dev) và TurnPlan giả, predictor giả."""

import asyncio

import pytest
from fakes import AS_OF, FakeEmbeddingClient, FakeInterpreter, plan

from app.services.formatting import format_price
from app.services.prediction.geocoder import Location
from app.services.prediction.predictor import PriceEstimate
from app.services.recommendation.schemas import SearchConstraints
from app.services.recommendation.service import RecommendationService
from app.services.recommendation.text_rules import MessageRules
from app.services.valuation import ListingValuer

FORBIDDEN = ("đắt", "rẻ", "hợp lý", "nên mua")
BASE_ROW = {
    "listing_id": "111", "position": 1, "price": 3300.0, "area": 50.0, "property_type":
    "Căn hộ chung cư", "district_old": "Quận 7", "latitude": 10.73, "longitude": 106.72,
    "quality_flags": [], "bedrooms": 2, "floors": None, "frontage": None,
}


class FakePredictor:
    """Luôn ước tính 60 triệu/m² (khoảng 50-70); ghi lại PriceInput đã nhận."""

    def __init__(self):
        self.inputs = []

    def predict(self, data):
        self.inputs.append(data)
        return PriceEstimate(
            price_per_m2=60.0, total_price=60.0 * data.area, price_per_m2_low=50.0,
            price_per_m2_high=70.0, distance_to_center_km=5.0, district_median_per_m2=55.0)


class FakeGeocoder:
    def __init__(self):
        self.calls = []

    async def locate(self, address, district_code, hint=None):
        self.calls.append((address, district_code))
        return Location(latitude=10.76, longitude=106.70, source="district_centroid")


def make_valuer():
    return ListingValuer(FakePredictor(), FakeGeocoder())


def appraise(valuer, *rows):
    return asyncio.run(valuer.appraise([{**BASE_ROW, **row} for row in rows]))


def correct(message, proposed, current=None, areas=()):
    current = current or SearchConstraints()
    return MessageRules(message).correct(proposed, current, list(areas), [], ["Quận 7"]).plan


# ---- quy tắc kiểm chứng intent -------------------------------------------------------------

@pytest.mark.parametrize("message", ["hi", "cảm ơn bạn nhé", "bạn làm được gì?"])
def test_chitchat_without_conditions_stays_chitchat_even_if_llm_echoes_old_conditions(message):
    echoed = plan("chitchat", price_max=4000, district_names=["Quận 7"], property_kinds=["can_ho"],
                  area_min=60, bedrooms_min=2)  # LLM chép lại điều kiện đang có
    current = SearchConstraints(price_max=4000, property_types=["Căn hộ chung cư"],
                                district_ids=[59], area_min=60, bedrooms_min=2)
    assert correct(message, echoed, current, areas=["Quận 7"]).intent == "chitchat"


@pytest.mark.parametrize("current, intent", [
    (SearchConstraints(), "search"), (SearchConstraints(price_max=3000), "refine"),
])
def test_chitchat_with_search_conditions_becomes_a_search(current, intent):
    corrected = correct("chào bạn, mình cần căn hộ Quận 7 dưới 3 tỷ",
                        plan("chitchat", price_max=3000, district_names=["Quận 7"]), current)
    assert corrected.intent == intent and corrected.set_fields.price_max == 3000


def test_other_mode_with_search_conditions_is_a_search_but_own_home_valuation_is_not():
    conditions = plan("other_mode", price_max=3000, district_names=["Quận 7"])
    assert correct("tìm căn hộ Quận 7 dưới 3 tỷ", conditions).intent == "search"
    own_home = plan("other_mode", district_names=["Quận 7"], area_min=60)
    assert correct("định giá nhà tôi 60m2 quận 7", own_home).intent == "other_mode"
    assert correct("nhà tôi bán được bao nhiêu", plan("other_mode")).intent == "other_mode"


def test_appraise_is_kept_when_the_question_names_no_new_condition():
    assert correct("căn 2 giá có hợp lý không", plan("appraise")).intent == "appraise"


# ---- ListingValuer -------------------------------------------------------------------------

def test_valuer_gap_and_range_follow_the_estimate():
    valuer = make_valuer()
    cheap, high, outside = appraise(
        valuer, {"price": 2700.0}, {"price": 3300.0, "listing_id": "222"},
        {"price": 4000.0, "listing_id": "333"})
    assert cheap.estimate.total_price == 3000.0  # 60 triệu/m² x 50 m²
    assert cheap.gap_pct == pytest.approx(-10.0) and cheap.in_range is True  # khoảng 2500-3500
    assert high.gap_pct == pytest.approx(10.0) and high.in_range is True
    assert outside.gap_pct == pytest.approx((4000 / 3000 - 1) * 100) and outside.in_range is False


def test_valuer_maps_property_types_and_district_to_model_codes():
    valuer = make_valuer()
    rows = [("Căn hộ chung cư", 0), ("Nhà riêng", 2), ("Nhà biệt thự, liền kề", 3),
            ("Nhà mặt phố", 4), ("Bán đất", 7)]
    appraise(valuer, *({"property_type": name} for name, _ in rows))
    assert [i.property_code for i in valuer.predictor.inputs] == [code for _, code in rows]
    assert valuer.predictor.inputs[0].district_code == 18  # Quận 7


@pytest.mark.parametrize("row", [
    {"property_type": "Shophouse, nhà phố thương mại"}, {"property_type": "Đất nền dự án"},
    {"property_type": "Kho, nhà xưởng"}, {"property_type": None}, {"district_old": None},
    {"district_old": "Quận Lạ"}, {"area": 5000.0},
])
def test_valuer_marks_unsupported_rows_without_calling_the_model(row):
    valuer = make_valuer()
    (item,) = appraise(valuer, row)
    assert item.estimate is None and item.unsupported and valuer.predictor.inputs == []
    assert "chưa ước tính được" in valuer.answer([item])


@pytest.mark.parametrize("row, calls", [
    ({}, 0), ({"latitude": None, "longitude": None}, 1),
    ({"quality_flags": ["coords_outside_hcm"]}, 1),
])
def test_valuer_uses_listing_coordinates_only_when_reliable_else_district_centre(row, calls):
    valuer = make_valuer()
    appraise(valuer, row)
    assert len(valuer.geocoder.calls) == calls
    used = valuer.predictor.inputs[0]
    assert (used.latitude, used.longitude) == ((10.73, 106.72) if not calls else (10.76, 106.70))
    if calls:
        assert valuer.geocoder.calls == [("Quận 7", 18)]  # chỉ tên quận nên không gọi Goong


def test_valuer_drops_out_of_range_optional_fields():
    valuer = make_valuer()
    appraise(valuer, {"property_type": "Nhà riêng", "floors": 99, "frontage": 200.0, "bedrooms": 3})
    used = valuer.predictor.inputs[0]
    assert (used.floors, used.frontage, used.bedrooms) == (None, None, 3)


def test_valuer_answer_quotes_listing_and_model_numbers_and_avoids_judgement_words():
    valuer = make_valuer()
    items = appraise(
        valuer, {"price": 3300.0}, {"listing_id": "222", "position": 2, "price": 4000.0},
        {"listing_id": "333", "position": 3, "property_type": "Kho, nhà xưởng"})
    answer = valuer.answer(items, ["Ghi chú trước."])
    assert answer.startswith("Ghi chú trước.")
    assert f"giá rao {format_price(3300.0)}; mô hình ước tính {format_price(3000.0)}" in answer
    assert "khoảng tham khảo 2,5 tỷ – 3,5 tỷ" in answer and "cao hơn ước tính 10%" in answer
    assert "nằm trong khoảng tham khảo" in answer and "nằm ngoài khoảng tham khảo" in answer
    assert "Căn 3 (tin 333): giá rao 3,3 tỷ; loại" in answer
    assert "không phải giá giao dịch" in answer
    assert ("Mọi căn đều có giá rao cao hơn hoặc xấp xỉ ước tính; chênh ít nhất: căn 1 "
            "(cao hơn ước tính 10%)") in answer
    assert not any(word in answer.lower() for word in FORBIDDEN)


def test_valuer_summary_names_the_listing_most_below_the_estimate():
    valuer = make_valuer()
    answer = valuer.answer(appraise(valuer, {"price": 2700.0},
                                    {"listing_id": "222", "position": 2, "price": 3300.0}))
    assert "Giá rao thấp hơn ước tính nhiều nhất: căn 1 (thấp hơn ước tính 10%)" in answer


def test_valuer_says_approximately_equal_when_gap_rounds_to_zero():
    valuer = make_valuer()
    answer = valuer.answer(appraise(valuer, {"price": 3010.0}))
    assert "giá rao xấp xỉ ước tính" in answer


# ---- RecommendationService với DB thật -----------------------------------------------------

def run_chat(run_db, plans, messages, valuer=None):
    interpreter = FakeInterpreter(plans)

    async def chat(session):
        service = RecommendationService(
            interpreter=interpreter, embedding_client=FakeEmbeddingClient(), engine=session.bind,
            rerank_enabled=False, valuer=valuer)
        results = []
        for message in messages:
            conversation_id = results[-1].conversation_id if results else None
            results.append(await service.chat(conversation_id, message, AS_OF))
        return results

    return run_db(chat)


def test_chitchat_and_other_mode_keep_conditions_and_results(run_db):
    found, hello, other, again = run_chat(run_db, [
        plan(price_max=5000, district_names=["Quận 7"]), plan("chitchat"), plan("other_mode"),
        plan("ask_detail"),
    ], ["Nhà Quận 7 dưới 5 tỷ", "hi", "định giá nhà tôi 60m2 quận 7", "căn 1 thế nào"])
    assert hello.status == "answered" and hello.listings == []
    assert hello.answer.startswith("Rất vui")  # đã có tin gợi ý: chỉ một câu ngắn
    assert other.status == "answered" and "tab *Dự đoán giá*" in other.answer
    assert hello.constraints == other.constraints == found.constraints
    assert again.referenced_ids == [found.listings[0].listing_id]  # kết quả cũ vẫn còn


def test_appraise_numbers_match_the_valuer_and_the_database_price(run_db):
    valuer = make_valuer()
    found, answer = run_chat(run_db, [
        plan(price_max=6000, district_names=["Quận 7"], property_kinds=["can_ho"]),
        plan("appraise"),
    ], ["Căn hộ Quận 7 dưới 6 tỷ", "căn 2 giá có hợp lý không?"], valuer)
    hit = found.listings[1]
    estimate = valuer.predictor.inputs[0]
    assert len(valuer.predictor.inputs) == 1 and estimate.area == hit.area  # chỉ căn 2
    assert answer.status == "answered" and answer.referenced_ids == [hit.listing_id]
    assert f"Căn 2 (tin {hit.listing_id}): giá rao {format_price(hit.price)}" in answer.answer
    assert format_price(60.0 * hit.area) in answer.answer
    assert not any(word in answer.answer.lower() for word in FORBIDDEN)
    assert answer.constraints == found.constraints  # so giá không đổi điều kiện


def test_appraise_without_reference_compares_every_listing_of_the_last_search(run_db):
    valuer = make_valuer()
    found, answer = run_chat(run_db, [
        plan(price_max=6000, district_names=["Quận 7"], property_kinds=["can_ho"]),
        plan("appraise"),
    ], ["Căn hộ Quận 7 dưới 6 tỷ", "căn nào rẻ so với thị trường?"], valuer)
    assert answer.referenced_ids == [hit.listing_id for hit in found.listings]
    assert len(valuer.predictor.inputs) == len(found.listings)


def test_appraise_reports_unsupported_type_before_any_search_and_missing_model(run_db):
    first, = run_chat(run_db, [plan("appraise")], ["căn 2 giá có cao không"], make_valuer())
    assert first.status == "answered"
    assert first.answer == "Chưa có tin để so giá, bạn tìm trước nhé."
    found, no_model = run_chat(run_db, [
        plan(price_max=6000, district_names=["Quận 7"]), plan("appraise"),
    ], ["Nhà Quận 7 dưới 6 tỷ", "căn 1 giá có cao không"], valuer=None)
    assert "chưa bật mô hình định giá" in no_model.answer and found.listings
    found, wrong = run_chat(run_db, [
        plan(price_max=6000, district_names=["Quận 7"]), plan("appraise"),
    ], ["Nhà Quận 7 dưới 6 tỷ", "căn 9 giá có cao không"], make_valuer())
    assert "Không tìm thấy căn thứ 9" in wrong.answer and wrong.referenced_ids == []


def test_appraise_says_so_for_a_property_type_the_model_does_not_support(run_db):
    valuer = make_valuer()
    found, answer = run_chat(run_db, [
        plan(property_kinds=["shophouse"], price_max=500_000), plan("appraise"),
    ], ["Shophouse dưới 500 tỷ", "căn 1 giá có cao không"], valuer)
    if not found.listings:
        pytest.skip("housing_dev không có shophouse")
    assert "chưa hỗ trợ" in answer.answer and "chưa ước tính được" in answer.answer
    assert valuer.predictor.inputs == []
