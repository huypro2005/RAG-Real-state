"""Geocoder: Goong lỗi hoặc không key → tâm quận từ listings (cần DATABASE_URL), không thì None."""

import asyncio
import os

import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from app.services.prediction.geocoder import DistrictArea, Geocoder


def locate(geocoder, address="Nguyễn Trãi", district_code=16, hint=None):
    return asyncio.run(geocoder.locate(address, district_code, hint))


def test_without_key_and_without_db_returns_none_instead_of_inventing():
    assert locate(Geocoder(None, None)) is None


def test_goong_failure_falls_back_to_district_centroid_from_listings():
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("chưa đặt DATABASE_URL (vd. ...@localhost:5432/housing_dev)")

    async def run():
        engine = create_async_engine(url)
        try:
            # key sai: Goong trả 4xx → phải dùng tâm quận 5 (mã 16)
            return await Geocoder("khong-hop-le", engine).locate("Nguyễn Trãi", 16)
        finally:
            await engine.dispose()

    location = asyncio.run(run())
    assert location.source == "district_centroid"
    assert 10.7 < location.latitude < 10.8 and 106.6 < location.longitude < 106.7


class SeededGeocoder(Geocoder):
    """Geocoder với khung quận dựng sẵn và điểm Goong giả (không mạng, không DB)."""

    def __init__(self, point, areas):
        super().__init__("key", None)
        self.point, self._areas = point, areas

    async def _goong(self, query):
        return self.point


QUAN_3 = DistrictArea(center=(10.783, 106.684), lat=(10.76, 10.80), lon=(106.66, 106.70))


def test_goong_point_is_accepted_only_inside_the_chosen_district():
    inside = locate(SeededGeocoder((10.78, 106.68), {14: QUAN_3}), "Lê Lợi", 14)
    assert inside.source == "goong" and inside.latitude == 10.78
    # Goong trả điểm ở Quận 7 (18 km) cho địa chỉ gán Quận 3: bỏ điểm đó, dùng tâm quận
    outside = locate(SeededGeocoder((10.73, 106.72), {14: QUAN_3}), "Lê Lợi", 14)
    assert (outside.source, outside.latitude) == ("district_centroid", 10.783)


def test_goong_failure_uses_centroid_and_never_crashes_when_db_is_down():
    assert locate(SeededGeocoder(None, {14: QUAN_3}), "x", 14).source == "district_centroid"
    down = create_async_engine("postgresql+asyncpg://u:p@127.0.0.1:1/none")
    assert locate(Geocoder(None, down)) is None


def test_district_only_address_uses_centroid_without_calling_goong():
    geocoder = SeededGeocoder((10.78, 106.68), {14: QUAN_3})
    geocoder._goong = None  # gọi tới là lỗi
    location = locate(geocoder, "Quận 3", 14)
    assert (location.source, location.latitude) == ("district_centroid", 10.783)


def test_type_hint_is_tried_when_the_bare_name_finds_nothing():
    queries = []

    class HintGeocoder(SeededGeocoder):
        async def _goong(self, query):
            queries.append(query)
            return (10.78, 106.68) if query.startswith("chung cư") else None

    location = locate(HintGeocoder(None, {14: QUAN_3}), "Botanica", 14, hint="chung cư")
    assert location.source == "goong"
    assert queries == ["Botanica, Quận 3, Hồ Chí Minh", "chung cư Botanica, Quận 3, Hồ Chí Minh"]
