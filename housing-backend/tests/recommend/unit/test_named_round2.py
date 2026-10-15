"""Địa điểm có tên, vòng sửa 2: đại học chỉ khớp ĐH/CĐ, tên bắt đầu bằng "từ"/"nhà", "đa khoa",
kind theo từ loại, đổi bán kính, chọn theo quận, Goong tỉnh khác, dữ liệu import (named-places.md)."""

import asyncio

import pytest
from fakes import plan
from pydantic import SecretStr
from sqlalchemy import text
from test_places import LANDMARK, UIT, FakeGoongResolver, request, resolve, run_chat

from app.services.places import PlaceResolver
from app.services.recommendation.schemas import PlaceConstraint, SearchConstraints
from app.services.recommendation.text_rules import MessageRules

GENERIC = [{"poi_type": kind, "max_distance_m": None}
           for kind in ("truong_hoc", "cho", "benh_vien")]
CURRENT = [PlaceConstraint(name=UIT, latitude=10.87, longitude=106.8034, poi_id=5837),
           PlaceConstraint(name="Bệnh viện Chợ Rẫy", latitude=10.7545, longitude=106.6596)]


def corrected(message, proposed=None, current=None):
    result = MessageRules(message).correct(
        proposed or plan("search", near_pois=GENERIC), current or SearchConstraints(), [], [], [])
    return result.plan.set_fields, result.ignored


# ---- đại học chỉ khớp ĐH/CĐ (N5) ------------------------------------------------------------

@pytest.mark.parametrize("name", [
    "đại học Hoa Sen", "đh hoa sen", "đại học Văn Lang", "đại học Sài Gòn",
    "đại học Nguyễn Tất Thành", "đh luật tphcm", "đại học công nghiệp", "đại học ngân hàng",
])
def test_university_names_only_match_universities_never_kindergartens_or_high_schools(
        run_db, name):
    status, found = resolve(run_db, name, "truong_hoc")
    assert status in ("one", "many") and found
    sql = text("SELECT poi_subtype FROM pois WHERE id = ANY(:ids)")
    subtypes = run_db(lambda s: s.execute(sql, {"ids": [p.poi_id for p in found]})).scalars().all()
    assert set(subtypes) <= {"Đại học", "Cao đẳng"}


def test_hoa_sen_university_is_among_the_candidates(run_db):
    _, found = resolve(run_db, "đại học Hoa Sen", "truong_hoc")
    assert any("Hoa Sen" in p.name and "ĐH" in p.name or "Đại" in p.name for p in found)
    assert all("MN" not in p.name and "MG " not in p.name for p in found)


def test_university_without_a_match_goes_to_goong_instead_of_asking_among_schools(run_db):
    resolver = FakeGoongResolver()
    assert resolve(run_db, "đại học Xyzabc", "truong_hoc", resolver=resolver) == ("none", [])
    assert resolver.calls == ["đại học Xyzabc"]


# ---- tên bắt đầu bằng từ nối, "đa khoa" (N5) --------------------------------------------------

@pytest.mark.parametrize("message, name", [
    ("nhà gần bệnh viện Từ Dũ dưới 8 tỷ", "tu du"),
    ("nhà gần bệnh viện Nhà Bè", "nha be"),
    ("nhà gần chợ Nhà Bè", "nha be"),
    ("nhà gần bệnh viện Đa khoa Sài Gòn", "da khoa sai gon"),
    ("nhà gần đại học công nghiệp", "dai hoc cong nghiep"),
    ("nhà gần đh luật tphcm", "dh luat tphcm"),
])
def test_names_starting_with_connective_words_are_still_names(message, name):
    places = corrected(message)[0].near_places
    assert [p.name for p in places] == [name]


def test_dh_luat_tphcm_core_drops_the_city_and_expands_the_abbreviation():
    assert PlaceResolver.core("đh luật tphcm") == "dai hoc luat"
    assert PlaceResolver.core("ĐH Luật TP.HCM") == "dai hoc luat"
    assert PlaceResolver.core("bv chợ rẫy") == "cho ray"


@pytest.mark.parametrize("message", ["gần bệnh viện đa khoa", "gần bệnh viện đa khoa dưới 5 tỷ"])
def test_da_khoa_alone_is_still_generic(message):
    places, pois = corrected(message)[0].near_places, corrected(message)[0].near_pois
    assert places == [] and pois


# ---- kind theo từ loại, bỏ POI chung (N10) -----------------------------------------------------

def test_kind_follows_the_word_before_the_name_and_generic_pois_of_that_kind_go_away():
    proposed = plan("search", price_max=8000, near_pois=GENERIC[2:],
                    near_places=[request("Hùng Vương", "khac")])
    delta, _ = corrected("nhà gần bệnh viện Hùng Vương dưới 8 tỷ", proposed)
    assert [(p.name, p.kind) for p in delta.near_places] == [("Hùng Vương", "benh_vien")]
    assert delta.near_pois == []


def test_kind_is_not_overridden_when_the_llm_already_chose_a_real_one():
    proposed = plan("search", near_places=[request("Hùng Vương", "truong_hoc")])
    assert corrected("nhà gần bệnh viện Hùng Vương", proposed)[0].near_places[0].kind == "truong_hoc"


# ---- đổi bán kính của địa điểm đang có (mục 5, 8) ---------------------------------------------

@pytest.mark.parametrize("message, meters", [
    ("gần hơn nữa, 1 km thôi", 1000), ("mở rộng ra 8 km", 8000), ("tầm 12 km nhé", 12000),
    ("chỉ 500m thôi", 500), ("ra 3 cây số", 3000),
])
def test_distance_phrase_resets_the_radius_of_the_only_current_place(message, meters):
    delta, ignored = corrected(message, plan("refine"), SearchConstraints(near_places=CURRENT[:1]))
    assert [(p.name, p.max_distance_m) for p in delta.near_places] == [(UIT, meters)]
    assert ignored == []


def test_with_two_places_the_radius_goes_to_the_one_the_message_names_else_asks():
    current = SearchConstraints(near_places=CURRENT)
    named = corrected("mở rộng quanh chợ rẫy ra 8 km", plan("refine"), current)
    assert [(p.name, p.max_distance_m) for p in named[0].near_places] == [
        ("Bệnh viện Chợ Rẫy", 8000)]
    delta, ignored = corrected("mở rộng ra 8 km", plan("refine"), current)
    assert delta.near_places == [] and ignored == ["bán kính (quanh địa điểm nào?)"]


def test_a_distance_for_a_generic_poi_does_not_touch_the_named_place():
    delta, _ = corrected("gần bệnh viện 1 km", plan("refine", near_pois=GENERIC[2:]),
                         SearchConstraints(near_places=CURRENT[:1]))
    assert delta.near_places == [] and delta.near_pois


def test_widening_without_the_llm_naming_the_place_changes_the_radius_end_to_end(run_db):
    resolver = FakeGoongResolver()
    (first, wider), _ = run_chat(run_db, [
        plan(price_max=6000, near_places=[request("đại học công nghệ thông tin", "truong_hoc")]),
        plan("refine"),  # LLM không chép lại tên địa điểm
    ], ["nhà dưới 6 tỷ gần đại học công nghệ thông tin", "mở rộng ra 8 km"], resolver)
    assert first.constraints.near_places[0].max_distance_m == 5000
    assert [(p.name, p.max_distance_m) for p in wider.constraints.near_places] == [(UIT, 8000)]
    assert resolver.calls == []


# ---- chọn ứng viên theo quận (N10) -----------------------------------------------------------

PENDING = [
    PlaceConstraint(name="Trường Đại học Bách khoa", latitude=10.77, longitude=106.66,
                    address="268, Lý Thường Kiệt, 10, Ho Chi Minh City, 70000", district="Quận 10"),
    PlaceConstraint(name="Trường Đại học Kinh tế", latitude=10.76, longitude=106.69,
                    address=None, district="Quận 3"),
    PlaceConstraint(name="Trường Đại học Kinh tế (cơ sở B)", latitude=10.80, longitude=106.70,
                    address="Phường 11, Quận Bình Thạnh", district="Bình Thạnh"),
]


@pytest.mark.parametrize("message, index", [
    ("quận 10", 0), ("ở quận 10", 0), ("quan 3", 1), ("q3", 1), ("bình thạnh", 2),
    ("ở Bình Thạnh nhé", 2), ("số 2", 1),
])
def test_candidates_are_chosen_by_the_district_even_when_the_address_lacks_it(message, index):
    constraints = SearchConstraints()
    assert PlaceResolver.choose(constraints, PENDING, message, False) == "chosen"
    assert constraints.near_places == [PENDING[index]]


def test_a_district_no_candidate_is_in_asks_again_but_a_new_search_drops_the_list():
    assert PlaceResolver.choose(SearchConstraints(), PENDING, "ở quận 5", False) == "retry"
    assert PlaceResolver.choose(SearchConstraints(), PENDING, "quận 12", False) == "retry"
    assert PlaceResolver.choose(
        SearchConstraints(), PENDING, "thôi tìm nhà quận 7 dưới 5 tỷ", False) == ""


def test_candidate_labels_show_the_approximate_district_only_in_the_list():
    assert PlaceResolver.label(PENDING[1], area=True) == "Trường Đại học Kinh tế – khu vực Quận 3"
    assert PlaceResolver.label(PENDING[1]) == "Trường Đại học Kinh tế"
    assert PlaceResolver.label(PENDING[0], area=True) == (
        "Trường Đại học Bách khoa – 268, Lý Thường Kiệt, Phường 10, khu vực Quận 10")
    assert PlaceResolver.label(PENDING[2], area=True) == (
        "Trường Đại học Kinh tế (cơ sở B) – Phường 11, Quận Bình Thạnh")


def test_identical_labels_are_told_apart_by_coordinates_and_same_campus_twins_merge(run_db):
    twin = PENDING[1].model_copy(update={"latitude": 10.7601})
    question, _ = PlaceResolver.ask("kinh tế", [PENDING[1], twin], True)
    assert question.count("Trường Đại học Kinh tế – khu vực Quận 3") == 2
    assert "(10.7600, 106.6900)" in question and "(10.7601, 106.6900)" in question
    status, found = resolve(run_db, "đại học mở", "truong_hoc")  # trước đây 2 dòng hệt nhau
    labels = [PlaceResolver.label(p, area=True) for p in found]
    assert status == "many" and len(set(labels)) == len(labels)


def test_label_does_not_repeat_the_name_inside_the_address():
    place = PlaceConstraint(name="Sân bay Tân Sơn Nhất", latitude=10.8, longitude=106.66,
                            address="Sân bay Tân Sơn Nhất, Phường 2, Tân Bình, Hồ Chí Minh")
    assert PlaceResolver.label(place) == "Sân bay Tân Sơn Nhất – Phường 2, Tân Bình"


# ---- Goong: tỉnh khác, xa tin đăng, viết tắt (N6) ----------------------------------------------

class Client:
    answer = {}

    def __init__(self, **_):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        pass

    async def get(self, *_, **__):
        answer = self.answer

        class Response:
            def raise_for_status(self):
                pass

            def json(self):
                return {"results": [answer]}

        return Response()


def goong_result(name, address, lat, lng):
    return {"name": name, "formatted_address": address,
            "geometry": {"location": {"lat": lat, "lng": lng}}}


@pytest.mark.parametrize("name, result", [
    ("Đại học Thủ Dầu Một", goong_result("Đại học Thủ Dầu Một", "6 Trần Văn Ơn, Phú Hòa, "
                                         "Thủ Dầu Một, Bình Dương", 10.9807, 106.6726)),
    ("Đại học Xa Xôi", goong_result("Đại học Xa Xôi", "Xa Xôi, Hồ Chí Minh", 11.12, 106.99)),
])
def test_goong_points_in_other_provinces_or_far_from_every_listing_are_not_found(
        run_db, monkeypatch, name, result):
    Client.answer = result
    monkeypatch.setattr("app.services.places.httpx.AsyncClient", Client)
    resolver = PlaceResolver(SecretStr("k"))
    assert resolve(run_db, name, "khac", resolver=resolver) == ("none", [])


def test_goong_point_inside_the_city_is_still_offered_for_confirmation(run_db, monkeypatch):
    Client.answer = goong_result("Landmark 81", "208 Nguyễn Hữu Cảnh, Bình Thạnh, Hồ Chí Minh",
                                 10.7949, 106.7218)
    monkeypatch.setattr("app.services.places.httpx.AsyncClient", Client)
    status, found = resolve(run_db, "Landmark 81", "khac", resolver=PlaceResolver(SecretStr("k")))
    assert status == "geocoded" and found[0].name == "Landmark 81"


def test_dhqg_is_left_to_goong_not_to_the_closest_pois_name(run_db):
    resolver = FakeGoongResolver({"dhqg": LANDMARK.model_copy(update={
        "name": "Đại học Quốc gia TP.HCM", "latitude": 10.8700, "longitude": 106.8030})})
    status, found = resolve(run_db, "đhqg", None, resolver=resolver)
    assert status == "geocoded" and resolver.calls == ["đhqg"]
    assert resolve(run_db, "đhqg", None, resolver=FakeGoongResolver(fail=True)) == ("none", [])


# ---- dữ liệu import (N1) -----------------------------------------------------------------------

def test_imported_universities_are_all_inside_the_old_city(run_db):
    sql = text("""SELECT count(*) FILTER (WHERE latitude > 10.885),
                         count(*) FILTER (WHERE name ILIKE '%Dĩ An%' OR address_old ILIKE '%Bình Dương%'),
                         count(*) FILTER (WHERE name ILIKE '%VGU%'),
                         count(*) FILTER (WHERE name = 'Trường Đại học Bách khoa (cơ sở 2)'),
                         count(*) FILTER (WHERE name = 'Trường Đại học Quốc tế'),
                         count(*)
                    FROM pois WHERE poi_subtype IN ('Đại học', 'Cao đẳng')""")
    north, binh_duong, vgu, bach_khoa_di_an, quoc_te, total = run_db(
        lambda s: s.execute(sql)).one()
    assert (north, binh_duong, vgu, bach_khoa_di_an) == (0, 0, 0, 0)
    assert quoc_te == 1 and total >= 100  # ĐH Quốc tế (Thủ Đức) không bị loại nhầm


def test_near_bach_khoa_no_longer_lists_the_di_an_campus(run_db):
    _, found = resolve(run_db, "bách khoa", None)
    assert found and all("Dĩ An" not in p.name and "cơ sở 2" not in p.name for p in found)


def test_asyncio_is_importable_for_the_goong_stub():
    assert asyncio.iscoroutinefunction(PlaceResolver._goong)
