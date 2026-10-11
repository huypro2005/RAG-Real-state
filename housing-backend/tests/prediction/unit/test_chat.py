"""PredictionChat: hội thoại nhiều lượt với FakeExtractor; kiểm tra quy tắc do code quyết định."""

import asyncio

import pytest
from prediction_fakes import FakeExtractor, FakeGeocoder, ext, make_predictor

from app.services.prediction.chat import PredictionChat

FULL = {"property_type": "nhà riêng", "district_name": "Quận 1", "area_m2": 80}


def make_chat(*extractions, geocoder=None):
    extractor = FakeExtractor(list(extractions))
    chat = PredictionChat(extractor, make_predictor(), geocoder or FakeGeocoder())
    return chat, extractor


def say(chat, message, conversation_id="c1"):
    return asyncio.run(chat.turn(conversation_id, message))


def test_full_message_then_ok_predicts_with_consistent_numbers():
    chat, extractor = make_chat(ext(**FULL, bedrooms=3, floors=2, frontage_m=4))
    first = say(chat, "nhà riêng Q1 80m2 3PN 2 tầng ngang 4m")
    assert first.status == "ready" and first.missing == [] and first.prediction is None
    assert "ok" in first.answer
    second = say(chat, "ok")
    assert len(extractor.calls) == 1  # "ok" thuần không tốn lượt LLM
    assert second.status == "predicted"
    p = second.prediction
    assert p.total_price == pytest.approx(p.price_per_m2 * 80)
    assert f"{p.price_per_m2:.2f} triệu VND/m²" in second.answer
    assert f"{p.total_price:.1f} triệu VND" in second.answer
    assert f"{p.total_price / 1000:.2f} tỷ" in second.answer
    assert f"{p.distance_to_center_km:.1f} km" in second.answer
    assert "median" in second.answer  # so với median quận


def test_step_by_step_asks_exactly_one_question_and_never_repeats_known_fields():
    chat, extractor = make_chat(
        ext(property_type="căn hộ chung cư"), ext(district_name="Q7"), ext(area_m2=70))
    turn = say(chat, "căn hộ chung cư")
    assert turn.status == "collecting" and turn.missing == ["district", "area"]
    assert "quận/huyện" in turn.answer and "Diện tích" not in turn.answer
    turn = say(chat, "q7")
    assert turn.missing == ["area"] and "Diện tích" in turn.answer
    assert "quận/huyện nào" not in turn.answer
    turn = say(chat, "70")
    assert extractor.calls[2][1] == "area"  # LLM được biết trợ lý vừa hỏi diện tích
    assert turn.status == "ready" and "phòng ngủ" in turn.answer  # chung cư chỉ hỏi phòng ngủ
    assert "số tầng" not in turn.answer and "mặt tiền" not in turn.answer


def test_ok_too_early_never_predicts_while_required_fields_are_missing():
    chat, _ = make_chat(ext(property_type="nhà riêng"), ext(wants_confirm=True))
    say(chat, "nhà riêng")
    for message in ("ok", "nhà riêng, chốt luôn", "OK!"):
        turn = say(chat, message)
        assert turn.status == "collecting" and turn.prediction is None
        assert turn.missing == ["district", "area"]
        assert "chưa dự đoán được" in turn.answer


def test_out_of_bounds_values_are_asked_again_not_guessed():
    chat, _ = make_chat(ext(**{**FULL, "area_m2": 5000}), ext(area_m2=90))
    turn = say(chat, "nhà riêng Q1 5000m2")
    assert turn.status == "collecting" and turn.missing == ["area"]
    assert "ngoài khoảng 10–2.000" in turn.answer
    assert say(chat, "ok").prediction is None
    assert say(chat, "90m2").status == "ready"


@pytest.mark.parametrize("field, value", [
    ("floors", 21), ("floors", 0), ("bedrooms", 21), ("frontage_m", 51), ("frontage_m", 0.5),
])
def test_optional_values_out_of_bounds_are_dropped_with_a_notice(field, value):
    chat, _ = make_chat(ext(**FULL, **{field: value}))
    turn = say(chat, f"nhà riêng Q1 80m2 {field} {value}")
    assert "nằm ngoài khoảng" in turn.answer
    assert turn.status == "ready"


def test_edit_after_prediction_predicts_again_with_new_value():
    chat, _ = make_chat(ext(**FULL), ext(area_m2=100))
    say(chat, "nhà riêng Q1 80m2")
    first = say(chat, "ok")
    edited = say(chat, "đổi diện tích 100m2")
    assert edited.status == "predicted"
    assert edited.fields["area"] == 100
    assert edited.prediction.total_price == pytest.approx(edited.prediction.price_per_m2 * 100)
    assert edited.prediction != first.prediction


def test_district_change_drops_old_address_and_geocodes_again():
    geocoder = FakeGeocoder()
    chat, _ = make_chat(
        ext(**FULL, address_text="Nguyễn Trãi"), ext(district_name="Quận 7"), geocoder=geocoder)
    say(chat, "nhà riêng 80m2 Nguyễn Trãi Quận 1")
    say(chat, "ok")
    say(chat, "ok")
    assert geocoder.calls == [("Nguyễn Trãi", 9)]  # lần "ok" thứ hai dùng lại tọa độ đã có
    turn = say(chat, "đổi sang quận 7")
    assert turn.fields["district"] == "Quận 7" and turn.fields["address"] == "Quận 7"
    assert geocoder.calls[-1] == ("Quận 7", 18)
    assert turn.status == "predicted"


def test_unclear_address_asks_for_district_and_remembers_other_fields():
    chat, _ = make_chat(
        ext(property_type="nhà riêng", area_m2=80), ext(district_name="Quận 7"))
    turn = say(chat, "nhà riêng 80m2, cách trung tâm 10km")
    assert turn.status == "collecting" and turn.missing == ["district"]
    assert say(chat, "quận 7").status == "ready"


def test_reset_clears_everything_and_reset_word_skips_the_llm():
    chat, extractor = make_chat(ext(**FULL))
    say(chat, "nhà riêng Q1 80m2")
    turn = say(chat, "Reset!")
    assert len(extractor.calls) == 1
    assert turn.status == "collecting" and turn.missing == ["property_type", "district", "area"]
    assert all(v is None for v in turn.fields.values())


def test_wants_reset_from_llm_starts_a_new_property_in_the_same_turn():
    chat, _ = make_chat(ext(**FULL), ext(wants_reset=True, property_type="bán đất"))
    say(chat, "nhà riêng Q1 80m2")
    turn = say(chat, "thôi làm lại, tôi muốn định giá lô đất")
    assert turn.fields["property_type"] == "bán đất" and turn.fields["area"] is None


@pytest.mark.parametrize("extraction", [
    ext(refusal="off_topic"),
    ext(refusal="other_province", property_type="nhà riêng", area_m2=80),
])
def test_out_of_scope_is_refused_briefly_and_state_is_untouched(extraction):
    chat, _ = make_chat(ext(**FULL), extraction)
    say(chat, "nhà riêng Q1 80m2")
    turn = say(chat, "viết cho tôi bài thơ")
    assert turn.status == "out_of_scope" and turn.prediction is None
    assert turn.fields["district"] == "Quận 1" and turn.fields["area"] == 80
    assert "Diện tích" not in turn.answer and "quận/huyện nào" not in turn.answer  # L1
    assert len(turn.answer) < 200


def test_no_location_available_asks_instead_of_inventing_coordinates():
    chat, _ = make_chat(ext(**FULL))
    chat.geocoder.location = None
    say(chat, "nhà riêng Q1 80m2")
    turn = say(chat, "ok")
    assert turn.status == "collecting" and turn.prediction is None
    assert "chưa xác định được vị trí" in turn.answer


def test_land_and_apartment_do_not_list_irrelevant_unknowns():
    chat, _ = make_chat(ext(property_type="bán đất", district_name="Củ Chi", area_m2=200))
    say(chat, "đất Củ Chi 200m2")
    turn = say(chat, "ok")
    assert "mặt tiền" in turn.answer and "số tầng" not in turn.answer
    assert "phòng ngủ" not in turn.answer


def test_conversations_are_isolated_and_ids_are_generated():
    chat, _ = make_chat(ext(**FULL), ext(property_type="nhà riêng"))
    a = say(chat, "nhà riêng Q1 80m2", "a")
    b = say(chat, "nhà riêng", None)
    assert a.status == "ready" and b.status == "collecting"
    assert b.conversation_id and b.conversation_id != "a"


@pytest.mark.parametrize("message, district", [
    ("ở quận 5", "Quận 5"), ("quận 7 nhé", "Quận 7"), ("bình thạnh", "Bình Thạnh"),
    ("tại gò vấp", "Gò Vấp"), ("nhà ở Q.10", "Quận 10"), ("chuyển qua phú nhuận", "Phú Nhuận"),
    ("không, ở tân bình", "Tân Bình"), ("ở thủ đức", "Thủ Đức"),
])
def test_short_district_corrections_survive_a_wrong_llm_refusal(message, district):
    llm_view = ext(refusal="off_topic", district_name=district)
    chat, _ = make_chat(ext(**FULL), llm_view)
    say(chat, "nhà riêng Q1 80m2")
    say(chat, "ok")
    turn = say(chat, message)
    assert turn.status == "predicted" and turn.fields["district"] == district


def test_bare_property_word_and_listing_with_district_survive_wrong_refusal():
    chat, _ = make_chat(ext(refusal="off_topic", property_type="bán đất"),
                        ext(refusal="other_province", property_type="căn hộ chung cư",
                            district_name="Cần Giờ", area_m2=155.8))
    assert say(chat, "đất", "a").fields["property_type"] == "bán đất"
    turn = say(chat, "căn hộ chung cư Cần Giờ 155.8m2", "b")
    assert turn.status == "ready" and turn.fields["area"] == 155.8


@pytest.mark.parametrize("message", [
    "nhà riêng 80m2 ở Thuận An", "đất 100m2 Dĩ An Bình Dương", "nhà riêng 80m2 Biên Hòa",
])
def test_known_other_provinces_are_refused_even_if_llm_picks_a_district(message):
    chat, _ = make_chat(ext(property_type="nhà riêng", district_name="Quận 12", area_m2=80))
    turn = say(chat, message)
    assert turn.status == "out_of_scope" and turn.fields["district"] is None


def test_values_not_in_the_message_are_dropped_not_inferred():
    guessed = ext(property_type="nhà riêng", district_name="Quận 2", area_m2=80, floors=3)
    chat, _ = make_chat(guessed, ext(property_type="nhà riêng"), ext(area_m2=50))
    turn = say(chat, "nhà ở Thảo Điền 80m2")  # "nhà riêng" và "Quận 2" do LLM tự suy
    assert turn.fields["district"] is None and turn.fields["property_type"] is None
    assert turn.fields["area"] == 80 and turn.fields["floors"] is None
    assert say(chat, "tôi cần mua nhà", "fresh").fields["property_type"] is None
    negative = say(chat, "diện tích -50 m2", "other")
    assert negative.fields["area"] is None and "ngoài khoảng" in negative.answer


def test_changing_district_drops_the_old_address_even_if_llm_repeats_it():
    geocoder = FakeGeocoder()
    chat, _ = make_chat(
        ext(**FULL, address_text="Lê Lợi"),
        ext(district_name="Quận 3", address_text="Lê Lợi"), geocoder=geocoder)
    say(chat, "nhà riêng q1 80m2 đường Lê Lợi")
    say(chat, "ok")
    turn = say(chat, "đổi sang quận 3")
    assert geocoder.calls == [("Lê Lợi", 9), ("Quận 3", 14)]
    assert turn.fields["address"] == "Quận 3"


def test_edit_shows_before_after_and_repeat_of_same_value_does_not_predict_again():
    chat, _ = make_chat(ext(**FULL), ext(area_m2=100), ext(area_m2=100))
    say(chat, "nhà riêng Q1 80m2")
    first = say(chat, "ok").prediction
    edited = say(chat, "đổi diện tích 100m2")
    assert "diện tích 80 → 100" in edited.answer
    assert f"{first.total_price:.1f} → {edited.prediction.total_price:.1f}" in edited.answer
    rows = len(chat.predictor.pipeline.rows)
    again = say(chat, "diện tích 100m2 nhé")
    assert again.status == "predicted" and "Bạn vừa đổi" not in again.answer
    assert len(chat.predictor.pipeline.rows) == rows  # không gọi model lần nữa


def test_chatter_after_prediction_repeats_result_with_factors_used():
    chat, _ = make_chat(ext(**FULL), ext())
    say(chat, "nhà riêng Q1 80m2")
    first = say(chat, "ok")
    why = say(chat, "tại sao giá này?")
    assert why.status == "predicted" and why.prediction == first.prediction
    assert "Cách trung tâm" in why.answer and "median" in why.answer


def test_answer_has_range_land_phrase_and_median_scope():
    chat, _ = make_chat(ext(property_type="bán đất", district_name="Quận 7", area_m2=100))
    chat.predictor.medians = {"18": 60.0}
    say(chat, "đất quận 7 100m2")
    answer = say(chat, "ok").answer
    assert "Ước tính cho lô đất 100 m² tại Quận 7" in answer
    assert "phân vị 10–90" in answer and "median cả quận Quận 7" in answer
    chat.predictor.medians = {"18": 60.0, "18|7": 55.0}
    chat.reset("c1")
    chat.extractor.extractions = [ext(property_type="bán đất", district_name="Quận 7", area_m2=100)]
    say(chat, "đất quận 7 100m2")
    assert "median lô đất tại Quận 7" in say(chat, "ok").answer


def test_summary_and_fields_hide_features_the_model_ignores():
    extraction = ext(property_type="căn hộ chung cư", district_name="Quận 7", area_m2=70,
                     floors=3, frontage_m=4, bedrooms=2)
    chat, _ = make_chat(extraction)
    turn = say(chat, "chung cư q7 70m2 3 tầng mặt tiền 4m 2 phòng ngủ")
    assert turn.fields["floors"] is None and turn.fields["frontage"] is None
    assert turn.summary == "căn hộ chung cư · Quận 7 · 70 m² · 2 phòng ngủ"


def test_long_message_keeps_head_and_tail():
    chat, extractor = make_chat(ext())
    say(chat, "ĐẦU " + "x" * 3000 + " ĐUÔI")
    sent = extractor.calls[0][0]
    assert sent.startswith("ĐẦU") and sent.endswith("ĐUÔI") and len(sent) < 1100


def test_conversation_store_is_bounded(monkeypatch):
    monkeypatch.setattr("app.services.prediction.chat.MAX_CONVERSATIONS", 3)
    chat, _ = make_chat(*[ext() for _ in range(5)])
    for i in range(5):
        say(chat, "xin chào", f"c{i}")
    assert list(chat._states) == ["c2", "c3", "c4"]


@pytest.mark.parametrize("message", [
    "thuê nhà 5 triệu/tháng quận 1", "cho thuê căn hộ chung cư quận 7 70m2",
    "đấu giá nhà riêng quận 3 80m2",
])
def test_rent_and_auction_are_refused_by_code_even_with_valid_fields(message):
    chat, _ = make_chat(ext(property_type="nhà riêng", district_name="Quận 1", area_m2=80))
    assert say(chat, message).status == "out_of_scope"


def test_english_message_with_district_n_is_understood():
    chat, _ = make_chat(ext(property_type="căn hộ chung cư", district_name="District 7",
                            area_m2=70))
    turn = say(chat, "apartment in district 7, 70 sqm")
    assert turn.status == "ready" and turn.fields["district"] == "Quận 7"


@pytest.mark.parametrize("message, district", [
    ("nhà riêng 80m2 ở Bình Chánh giáp Long An", "Bình Chánh"),
    ("nhà riêng 80m2 Thủ Đức gần Dĩ An", "Thủ Đức"),
    ("nhà riêng 80m2 xa lộ Hà Nội Thủ Đức", "Thủ Đức"),
    ("nhà riêng 80m2 đường Nguyễn Huệ quận 1", "Quận 1"),
])
def test_neighbouring_province_as_landmark_is_not_out_of_scope(message, district):
    llm_view = ext(refusal="other_province", property_type="nhà riêng", district_name=district,
                   area_m2=80)
    chat, _ = make_chat(llm_view)
    turn = say(chat, message)
    assert turn.status == "ready" and turn.fields["district"] == district


def test_llm_miss_on_property_type_is_filled_from_a_single_keyword():
    chat, _ = make_chat(ext(district_name="Thủ Đức", area_m2=80))
    turn = say(chat, "nhà riêng 80m2 Thủ Đức gần Dĩ An")
    assert turn.status == "ready" and turn.fields["property_type"] == "nhà riêng"


def test_unknown_province_without_district_asks_for_district_instead_of_predicting():
    chat, _ = make_chat(ext(refusal="other_province", property_type="nhà riêng", area_m2=80))
    turn = say(chat, "nhà riêng 80m2 Quốc lộ 1K gần Biên Hòa")
    assert turn.status == "collecting" and turn.missing == ["district"]


def addresses_sent_to_geocoder(llm_address, message, **fields):
    geocoder = FakeGeocoder()
    chat, _ = make_chat(ext(**{"property_type": "căn hộ chung cư", "district_name": "Bình Tân",
                               "area_m2": 65, **fields}, address_text=llm_address),
                        geocoder=geocoder)
    say(chat, message)
    say(chat, "ok")
    return geocoder.calls


@pytest.mark.parametrize("junk", ["chung cư", "chung cư bình tân", "hẻm xe hơi"])
def test_junk_address_from_llm_falls_back_to_district_centre(junk):
    assert addresses_sent_to_geocoder(junk, "chung cư bình tân 65m2 hẻm xe hơi") == [
        ("Bình Tân", 1)]


def test_same_place_gives_the_same_geocode_query_across_runs():
    runs = [addresses_sent_to_geocoder(form, f"căn hộ {form} bình tân 65m2")
            for form in ("Botanica Premier", "căn hộ Botanica Premier")]
    assert runs[0] == runs[1] == [("Botanica Premier", 1)]


def test_junk_address_never_overwrites_a_specific_one():
    geocoder = FakeGeocoder()
    chat, _ = make_chat(
        ext(district_name="Bình Tân", area_m2=64, address_text="đường Tên Lửa"),
        ext(property_type="nhà riêng", address_text="nhà riêng trong hẻm"), geocoder=geocoder)
    say(chat, "nhà đường Tên Lửa bình tân 64 m vuông")
    say(chat, "nhà riêng trong hẻm")
    say(chat, "ok")
    assert geocoder.calls == [("Tên Lửa", 1)]


def test_frontage_phrase_never_changes_the_property_type():
    chat, _ = make_chat(ext(property_type="bán đất", district_name="Củ Chi", area_m2=500),
                        ext(property_type="nhà mặt phố", frontage_m=10))
    say(chat, "đất củ chi 500m2")
    turn = say(chat, "nếu mặt tiền 10m thì giá sao")
    assert turn.fields["property_type"] == "bán đất" and turn.fields["frontage"] == 10


def test_type_keyword_does_not_override_an_existing_type_unless_llm_agrees():
    chat, _ = make_chat(ext(**FULL), ext(property_type="nhà riêng"))
    say(chat, "nhà riêng Q1 80m2")
    turn = say(chat, "nếu là biệt thự thì sao")  # LLM không đổi loại, chỉ từ khoá lẻ
    assert turn.fields["property_type"] == "nhà riêng"


def test_wants_confirm_needs_a_confirmation_phrase_in_the_message():
    chat, _ = make_chat(ext(**FULL, wants_confirm=True), ext(wants_confirm=True))
    assert say(chat, "nhà riêng Q1 80m2 giá chủ chào 5 tỷ có hợp lý không").status == "ready"
    assert say(chat, "ok luôn nhé").status == "predicted"


@pytest.mark.parametrize("message, area, note", [
    ("nhà riêng Q1 300m2", 300, False), ("nhà riêng Q1 tám mươi mét vuông", 80, False),
    ("nhà riêng Q1 ngang 5 dài 20, 5x20", 100, True),
])
def test_area_is_built_from_the_message_when_llm_leaves_it_empty(message, area, note):
    chat, _ = make_chat(ext(property_type="nhà riêng", district_name="Quận 1"))
    turn = say(chat, message)
    assert turn.fields["area"] == area and ("diện tích đất" in turn.answer) is note


def test_rented_house_the_owner_wants_to_sell_is_not_refused():
    chat, _ = make_chat(ext(refusal="off_topic", property_type="nhà riêng",
                            district_name="Quận 5", area_m2=60))
    assert say(chat, "nhà riêng 60m2 đang cho thuê quận 5 muốn bán").status == "ready"


def test_prediction_warnings_appear_in_the_answer():
    chat, _ = make_chat(ext(**FULL))
    answer = say(chat, "nhà riêng Q1 80m2") and say(chat, "ok").answer
    assert "Lưu ý: Dữ liệu huấn luyện ở khu vực/loại này rất ít" in answer
