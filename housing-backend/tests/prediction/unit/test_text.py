"""MessageRules: kiểm chứng điều LLM trích có thật sự nằm trong tin nhắn."""

import pytest

from app.services.prediction.text import MessageRules, plain


@pytest.mark.parametrize("message, codes", [
    ("ở quận 5", [16]), ("Q.10", [10]), ("q1 và quận 12", [9, 12]), ("nhà ở thủ đức", [21]),
    ("chuyển qua phú nhuận", [8]), ("quận 100", []), ("khu Thảo Điền", []),
    ("Dĩ An Bình Dương", []), ("quan 07", [18]), ("Quận 1 hay quận 10", [9, 10]),
])
def test_districts_scan_whole_words_in_order(message, codes):
    assert MessageRules.districts(message) == codes


@pytest.mark.parametrize("message", [
    "nhà ở Thuận An", "đất Dĩ An", "Biên Hòa 80m2", "ở Hà Nội", "Bình Dương", "Thủ Dầu Một",
])
def test_other_province_hints(message):
    assert MessageRules.other_province(message)
    assert not MessageRules.other_province("nhà quận 7 gần chợ Bình Tân")


def test_property_keywords_need_real_words_not_generic_house():
    assert MessageRules.mentions_property("lô đất 100m2", "bán đất")
    assert MessageRules.mentions_property("mua căn hộ", "căn hộ chung cư")
    assert not MessageRules.mentions_property("tôi cần mua nhà", "nhà riêng")
    assert not MessageRules.mentions_property("tôi cần mua nhà")


@pytest.mark.parametrize("value, message, pending, status", [
    (80, "nhà 80m2", False, "ok"), (155.8, "căn hộ 155.8m2", False, "ok"),
    (50, "diện tích -50 m2", False, "negative"), (2000, "rộng 2.000 m2", False, "ok"),
    (3, "nhà ba tầng", False, "ok"), (3, "cho tôi 5 tầng", False, "absent"),
    (80, "tám mươi", True, "ok"), (1.5, "1,5 phòng", False, "ok"),
    (7, "q7", False, "absent"),
])
def test_number_status(value, message, pending, status):
    assert MessageRules.number_status(value, message, pending) == status


def test_command_and_plain():
    assert MessageRules.command("OK!") == "confirm"
    assert MessageRules.command("Chốt luôn.") == "confirm"
    assert MessageRules.command("Reset") == "reset"
    assert MessageRules.command("ok 80m2") is None
    assert plain("  Đường  Nguyễn Trãi ") == "duong nguyen trai"


@pytest.mark.parametrize("message", [
    "nhà riêng 80m2 ở Bình Chánh giáp Long An", "đất 300m2 huyện Củ Chi giáp Tây Ninh",
    "nhà riêng 80m2 Thủ Đức gần Dĩ An", "nhà mặt phố Nguyễn Huệ quận 1 100m2",
    "xa lộ Hà Nội Thủ Đức", "Quốc lộ 1K gần Biên Hòa", "đường Đồng Nai quận 10",
    "đường Hồ Văn Huê Phú Nhuận", "đường Đà Lạt quận 5", "nhà riêng 80m2 đường Nguyễn Huệ",
    "nhà ở Huế Street quận 3",
])
def test_province_names_used_as_landmarks_or_street_names_are_not_refusals(message):
    assert not MessageRules.other_province(message)


@pytest.mark.parametrize("message", ["nhà ở TP Huế", "nhà riêng 80m2 Thuận An", "Hà Nội 80m2"])
def test_real_other_province_without_hcm_district_is_refused(message):
    assert MessageRules.other_province(message)


@pytest.mark.parametrize("message, codes", [
    ("district 7", [18]), ("dist 7", [18]), ("apartment in District 2", [13]),
    ("quận bảy", [18]), ("quận hai", [13]), ("quận mười hai", [12]), ("quận mười", [10]),
    ("quận Ba Đình", []), ("quận ba", [14]),
])
def test_districts_accept_english_and_spelled_numbers(message, codes):
    assert MessageRules.districts(message) == codes


def test_rent_auction_and_tax_are_out_of_domain():
    for message in ("thuê nhà 5 triệu/tháng quận 1", "cho thuê căn hộ", "đấu giá nhà", "thuế"):
        assert MessageRules.out_of_domain(message)
    assert not MessageRules.out_of_domain("bán nhà quận 1 80m2")


def test_english_property_words_ground_the_type():
    assert MessageRules.mentions_property("apartment in district 7", "căn hộ chung cư")
    assert MessageRules.mentions_property("a villa", "nhà biệt thự, liền kề")


@pytest.mark.parametrize("address, cleaned", [
    ("chung cư", None), ("nhà trong hẻm", None), ("hẻm xe hơi", None),
    ("nhà riêng trong hẻm", None),
    ("chung cư Bình Tân", None), ("Q7", None), ("biệt thự Thảo Điền", "Thảo Điền"),
    ("liền kề Vạn Phúc City", "Vạn Phúc City"), ("đường Tên Lửa", "Tên Lửa"),
    ("căn hộ Botanica Premier", "Botanica Premier"), ("Nguyễn Trãi, Quận 5", "Nguyễn Trãi"),
    ("Hồ Văn Huê, Phú Nhuận", "Hồ Văn Huê"), ("123 Lê Lợi", "123 Lê Lợi"),
])
def test_clean_address_keeps_only_proper_names(address, cleaned):
    assert MessageRules.clean_address(address) == cleaned


def test_same_place_written_differently_cleans_to_the_same_string():
    forms = ["Botanica Premier", "căn hộ Botanica Premier", "chung cư Botanica Premier, Tân Bình"]
    assert len({MessageRules.clean_address(form) for form in forms}) == 1


@pytest.mark.parametrize("message, expected", [
    ("diện tích 300m2", (300, False)), ("rộng 2.000 m2", (2000, False)),
    ("tám mươi mét vuông", (80, False)), ("một trăm hai mươi mét vuông", (120, False)),
    ("nhà 5x20 cần bán", (100, True)), ("4×15", (60, True)), ("-50 m2", None),
    ("nhà riêng quận 1", None),
])
def test_area_from_text(message, expected):
    assert MessageRules.area_from_text(message) == expected


def test_confirm_phrases_and_mat_tien_is_not_a_property_type():
    assert MessageRules.confirms("2 lầu 3pn, ok luôn") and MessageRules.confirms("chốt nhé")
    assert not MessageRules.confirms("căn 2pn giá 5 tỷ 2 hợp lý không")
    assert MessageRules.property_types("nếu mặt tiền 10m thì giá sao") == []
    assert MessageRules.property_types("nhà mặt tiền đường") == ["nhà mặt phố"]


def test_rent_with_intent_to_sell_is_not_out_of_domain():
    assert not MessageRules.out_of_domain("nhà đang cho thuê quận 5 muốn bán")
    assert not MessageRules.out_of_domain("nha dang cho thue quan 5 muon ban")
    assert MessageRules.out_of_domain("bạn cho thuê nhà quận 1")
