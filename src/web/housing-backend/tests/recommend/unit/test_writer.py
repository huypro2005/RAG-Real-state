"""Writer + grounding: câu trả lời chi tiết/so sánh và kết quả tìm do code viết."""

from datetime import date

import pytest

from app.services.formatting import format_price
from app.services.recommendation.grounding import asked_attributes, detail_answer
from app.services.recommendation.schemas import ListingHit, PoiConstraint, SearchConstraints
from app.services.recommendation.writer import (
    describe_changes,
    describe_constraints,
    details_answer,
    refs_not_found,
    results_answer,
)

# Hai tin giống C01#5: căn 1 = 53 m², căn 3 = 52 m²; căn 3 có nhiều cột NULL
ROWS = [
    {"position": 1, "listing_id": "45640933", "title": "Ehome 2", "price": 2060.0,
     "price_per_m2": 38.87, "area": 53.0, "bedrooms": 1, "bathrooms": 1, "floors": None,
     "legal": "Hợp đồng mua bán", "interior": "Full", "old_address": "Quận 9",
     "new_address": "Phường Phước Long, Hồ Chí Minh mới",
     "listing_url": "https://x/pr45640933", "posted_at": date(2026, 9, 1),
     "description": "Căn hộ yên tĩnh, view sông. " + "x" * 400,
     "nearest_market_m": 350.0, "nearest_market_name": "Chợ A"},
    {"position": 3, "listing_id": "46146964", "title": None, "price": 2570.0,
     "price_per_m2": 49.42, "area": 52.0, "bedrooms": 2, "bathrooms": 2, "floors": None,
     "legal": None, "interior": None, "old_address": None, "new_address": None,
     "listing_url": "https://x/pr46146964", "posted_at": None, "description": None,
     "nearest_market_m": 1250.0, "nearest_market_name": None},
]


def reply(question: str, rows=ROWS) -> str:
    return detail_answer(question, rows)[0]


@pytest.mark.parametrize(("million", "text"), [(2800, "2,8 tỷ"), (900, "900 triệu"),
                                                (2065, "2,065 tỷ"), (3000, "3 tỷ")])
def test_format_price(million, text):
    assert format_price(million) == text


@pytest.mark.parametrize(("question", "columns"), [
    ("can thu 1 co bao nhieu phong tam", ["bathrooms"]),
    ("Pháp lý căn 2 thế nào?", ["legal"]),
    ("lô 2 với lô 4 lô nào rẻ hơn tính theo m2", ["price_per_m2"]),
    ("Vậy căn thứ 2 với căn thứ 3 so sánh giá trên mét vuông", ["price_per_m2"]),
    ("Căn 2 diện tích bao nhiêu, giá thế nào?", ["price", "area"]),
    ("Căn thứ 1 nằm ở đâu vậy?", ["address"]),
    ("Căn đầu tiên gần trường nào nhất, cách bao xa?", ["nearest_school_m"]),
    ("So sánh căn 1 và căn 3 giúp mình", []),
    ("Căn đầu tiên và căn thứ ba khác nhau chỗ nào?", []),  # "chỗ" không phải "chợ"
])
def test_asked_attributes(question, columns):
    assert [a.column for a in asked_attributes(question)] == columns


def test_single_attribute_is_a_short_list_with_one_label():
    text = reply("can thu 1 co bao nhieu phong tam")
    assert text.startswith("Số phòng tắm:\n- Căn 1 [Tin 45640933]: 1 phòng tắm\n"
                           "- Căn 3 [Tin 46146964]: 2 phòng tắm")
    assert "Căn 3 (2 phòng tắm) nhiều hơn Căn 1 (1 phòng tắm), chênh 1 phòng tắm" in text
    assert text.lower().count("số phòng tắm") == 1


def test_address_question_lists_old_and_new_address_with_tin_id():
    text = reply("Căn 1 và căn 3 nằm ở đâu?")
    assert ("Căn 1 [Tin 45640933]: địa chỉ cũ: Quận 9; "
            "địa chỉ mới: Phường Phước Long, Hồ Chí Minh mới") in text
    assert "Căn 3 [Tin 46146964]: tin không ghi" in text


def test_several_attributes_make_one_block_per_listing_with_address():
    text = reply("Căn 1 và căn 3 diện tích bao nhiêu, giá thế nào?")
    first, second, comparison = text.split("\n\n")
    assert first == ("Căn 1 [Tin 45640933] Ehome 2\n- địa chỉ cũ: Quận 9; địa chỉ mới: "
                     "Phường Phước Long, Hồ Chí Minh mới\n- giá: 2,06 tỷ\n- diện tích: 53 m²")
    assert second.startswith("Căn 3 [Tin 46146964]\n- địa chỉ: tin không ghi")  # NULL, không title
    assert "pháp lý" not in text and "phòng ngủ" not in text
    assert "- diện tích: Căn 1 (53 m²) lớn hơn Căn 3 (52 m²), chênh 1 m²" in comparison
    assert "- giá: Căn 3 (2,57 tỷ) đắt hơn Căn 1 (2,06 tỷ), chênh 510 triệu" in comparison


def test_general_comparison_prints_default_attributes_without_description():
    for question in ("So sánh căn 1 và căn 3", "Căn đầu tiên và căn thứ ba khác nhau chỗ nào?"):
        text = reply(question)
        assert "- pháp lý: Hợp đồng mua bán" in text and "- pháp lý: tin không ghi" in text
        assert "- chợ gần nhất: Chợ A, cách 350 m" in text
        assert "- chợ gần nhất: không rõ tên, cách 1,2 km" in text
        assert "So sánh:" in text and "yên tĩnh" not in text


def test_lo_dau_is_not_an_address_question():  # E5
    assert [a.column for a in asked_attributes("So sánh 3 lô đầu giúp anh")] == []
    assert [a.column for a in asked_attributes("Tin này ở đâu?")] == ["address"]


def test_comparative_names_the_winner_and_does_not_set_referenced_ids():
    text, winners = detail_answer("Căn nào rẻ hơn tính theo giá/m2?", ROWS)
    assert text.startswith("Theo giá/m², Căn 1 [Tin 45640933] rẻ hơn (38,87 triệu/m²).")
    assert winners == []  # chỉ câu "nhất" mới thu hẹp referenced_ids


def test_superlative_returns_winner_ids():  # X05
    assert detail_answer("Căn nào rẻ nhất?", ROWS)[1] == ["45640933"]
    assert detail_answer("Căn nào đắt nhất?", ROWS)[1] == ["46146964"]
    assert detail_answer("Căn nào gần chợ nhất?", ROWS)[1] == ["45640933"]


def test_rank_clause_and_other_clauses_are_all_answered():  # F5
    text, _ = detail_answer(
        "Căn 2 với căn 3 cái nào rộng hơn, có sổ hồng ko, view sông ko?", ROWS)
    assert text.startswith("Theo diện tích, Căn 1 [Tin 45640933] rộng hơn (53 m²).")
    assert "- pháp lý: Hợp đồng mua bán" in text and "- pháp lý: tin không ghi" in text
    assert '- view sông: "Căn hộ yên tĩnh, view sông."' in text  # Căn 1 trích mô tả
    assert "- view sông: tin không ghi mục này" in text  # Căn 3 không có mô tả


def test_closing_remark_does_not_become_a_topic():  # F8 "anh lấy"
    text, winners = detail_answer("ok vậy căn nào rẻ nhất, anh lấy", ROWS)
    assert "lấy" not in text and winners == ["45640933"]


def test_two_rank_clauses_without_accents():  # G5
    text, _ = detail_answer("can 2 va can 4 cai nao re hon, cai nao gan cho hon", ROWS)
    assert "Theo giá, Căn 1 [Tin 45640933] rẻ hơn (2,06 tỷ)." in text
    assert "Theo chợ gần nhất, Căn 1 [Tin 45640933] gần hơn (Chợ A, cách 350 m)." in text


@pytest.mark.parametrize("question", [
    "Chi tiết căn thứ 4 đi", "chi tiet can 1 di", "Nói thêm về căn 4 đi",
])
def test_detail_request_is_checked_before_topics(question):  # B1 / X08
    text = reply(question, ROWS[:1])
    assert "- nội thất: Full" in text and "- số phòng tắm: 1 phòng tắm" in text
    assert "- đi" not in text and "mục này" not in text


def test_con_han_is_one_attribute_not_a_new_clause():  # C06#4
    rows = [{**ROWS[0], "expired_at": date(2026, 10, 1)}]
    text = reply("Căn số 1 đăng ngày nào, còn hạn tới khi nào?", rows)
    assert "- ngày đăng: 01/09/2026" in text and "- ngày hết hạn: 01/10/2026" in text
    assert "mục này" not in text


def test_excerpt_matches_whole_accented_words_in_title_and_description():
    desc = "Nhà bán gấp, sống thoải mái. Thương lượng chính chủ. Sân để xe rộng."
    rows = [{**ROWS[0], "title": "Nhà hẻm xe hơi Quận 9", "description": desc}]
    assert "- view sông: tin không ghi mục này" in reply("View sông ko?", rows)  # sống != sông
    assert "- sân thượng: tin không ghi mục này" in reply("Có sân thượng không?", rows)
    assert '- hẻm xe hơi: "Nhà hẻm xe hơi Quận 9"' in reply("Hẻm xe hơi không?", rows)
    rows[0]["title"] = "Nhà Quận 9"
    assert "- hẻm xe hơi: tin không ghi mục này" in reply("Hẻm xe hơi không?", rows)  # khớp 1/3
    assert "- ho boi: tin không ghi mục này" in reply("co ho boi ko", rows)  # gõ không dấu


def test_superlative_answers_one_listing_with_value_and_ranking():
    text = reply("Căn nào rẻ nhất?")
    assert text.startswith("Theo giá, Căn 1 [Tin 45640933] rẻ nhất (2,06 tỷ).")
    assert "giá từ thấp đến cao: Căn 1 (2,06 tỷ), Căn 3 (2,57 tỷ)" in text
    assert reply("Căn nào rộng nhất?").startswith("Theo diện tích, Căn 1 [Tin 45640933] rộng nhất")
    assert "Căn 1 [Tin 45640933] gần nhất (Chợ A, cách 350 m)" in reply("Căn nào gần chợ nhất?")


def test_detail_request_prints_every_attribute_with_data_and_no_disclaimer():
    text = reply("Cho mình chi tiết tin 45640933", ROWS[:1])
    for line in ("- nội thất: Full", "- số phòng tắm: 1 phòng tắm", "- ngày đăng: 01/09/2026",
                 "- đường dẫn: https://x/pr45640933"):
        assert line in text
    assert "số tầng" not in text and "chưa đánh giá" not in text  # cột NULL thì bỏ


def test_clauses_without_attribute_quote_first_matching_sentence_or_say_missing():
    rows = [{**ROWS[0], "description": "Nhà mới xây. Hẻm xe hơi vào tận cửa. Có sân thượng."}]
    text = reply("Hẻm có vào được xe hơi không, pháp lý thế nào?", rows)
    assert '- hẻm xe hơi: "Hẻm xe hơi vào tận cửa."' in text
    assert "- pháp lý: Hợp đồng mua bán" in text
    assert "- view biển: tin không ghi mục này" in reply("Có view biển không?", rows)
    tret = reply("Có mấy tầng, có phòng ngủ dưới trệt không?", rows)  # D4
    assert "- phòng ngủ trệt: tin không ghi mục này" in tret and "số tầng" in tret


def test_quoted_sentence_is_cut_at_word_boundary_with_ellipsis():
    rows = [{**ROWS[0], "description": "Yên tĩnh " + "abc " * 100}]
    quoted = reply("Có yên tĩnh không?", rows).split('yên tĩnh: "')[1].split('"')[0]
    assert quoted.endswith("abc…") and len(quoted) <= 301


def test_three_listings_are_ranked_per_attribute():
    third = {**ROWS[1], "position": 4, "listing_id": "1", "price": 2100.0, "area": 60.0}
    text = reply("So sánh giá 3 căn", [ROWS[0], ROWS[1], third])
    assert "- giá từ thấp đến cao: Căn 1 (2,06 tỷ), Căn 4 (2,1 tỷ), Căn 3 (2,57 tỷ)" in text


def test_details_adds_notes_and_price_note():
    text, winners = details_answer(ROWS, "Căn 1 giá bao nhiêu?", ["Không tìm thấy căn thứ 9."])
    assert winners == []
    assert text.startswith("Không tìm thấy căn thứ 9.\n\nGiá:")
    assert text.endswith("Giá là giá rao bán tham khảo.")


def test_wrong_reference_message():
    assert refs_not_found(["căn thứ 7"], 5) == (
        "Không tìm thấy căn thứ 7 trong danh sách vừa gợi ý (hiện chỉ có 5 tin)."
    )
    assert refs_not_found([], 0) == "Mình chưa gợi ý tin nào để hỏi chi tiết."


def test_results_text_is_written_by_code():
    hit = ListingHit(
        listing_id="45640933", title="Ehome 2", price=2060.0, area=53.0,
        property_type="Căn hộ chung cư", bedrooms=None, district_old="Quận 9",
        old_address=None, new_address=None, listing_url="https://x/pr45640933",
        posted_at=None, expired_at=None, poi_distances={"benh_vien": 1250.0}, score=None,
    )
    constraints = SearchConstraints(
        price_max=3000, property_types=["Căn hộ chung cư"], bedrooms_min=2,
        near_pois=[PoiConstraint(poi_type="benh_vien", max_distance_m=2000)],
        soft_query="yên tĩnh",
    )
    answer = results_answer(
        [hit], constraints, ["Quận 2", "Quận 9", "Thành phố Thủ Đức"],
        ["Đã giảm ngân sách xuống 3 tỷ."], degraded=False, relax_options=[],
    )
    assert answer.startswith(
        "Đã giảm ngân sách xuống 3 tỷ. Mình tìm được 1 tin phù hợp với điều kiện: Căn hộ chung "
        "cư; khu vực Quận 2, Quận 9, Thành phố Thủ Đức; giá tối đa 3 tỷ; từ 2 phòng ngủ; gần "
        "bệnh viện trong bán kính 2 km."
    )
    assert "1. [Tin 45640933] Ehome 2\n   2,06 tỷ · 53 m² · Căn hộ chung cư" in answer
    assert "Gần nhất: bệnh viện 1,2 km" in answer


def test_results_state_the_approximate_price_range():
    constraints = SearchConstraints(price_min=2400, price_max=3150, price_min_derived=True)
    text = describe_constraints(constraints, ["Quận 7"])
    assert "giá khoảng 2,4 tỷ – 3,15 tỷ" in text
    old = SearchConstraints(price_max=3000)
    assert describe_changes(old, constraints, [], [], cheaper=False) == [
        "Đã áp khoảng giá 2,4 tỷ – 3,15 tỷ."
    ]


def test_parking_question_is_searched_with_accented_words():  # "đậu ô tô" != "đâu o to"
    rows = [{**ROWS[0], "description": "Nhà có chỗ đậu ô tô trong hẻm. Sân thượng rộng."}]
    text = reply("Căn 5 có chỗ đậu ô tô không?", rows)
    assert '- đậu ô tô: "Nhà có chỗ đậu ô tô trong hẻm."' in text


def test_street_question_is_an_address_question_not_a_topic():
    text = reply("Căn thứ nhất ở đường nào?", ROWS[:1])
    assert text.startswith("Địa chỉ:\n- Căn 1 [Tin 45640933]: địa chỉ cũ: Quận 9")
    assert "mục này" not in text


def test_same_ranking_is_printed_once_and_single_listing_has_no_tie_sentence():
    text, _ = detail_answer("rộng hơn thì sao, căn 3 vs căn 5 cái nào rộng hơn", ROWS)
    assert text.count("Theo diện tích") == 1
    one = detail_answer("Căn nào rẻ nhất?", ROWS[:1])[0]
    assert one.startswith("Theo giá, Căn 1 [Tin 45640933] rẻ nhất") and "bằng nhau" not in one
