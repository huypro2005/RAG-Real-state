"""HybridSearch trên DB thật (DATABASE_URL), client embedding giả: không gọi Kaggle/OpenAI.

Mỗi test so với một truy vấn oracle viết riêng, không dùng lại SQL của HybridSearch.
"""

import httpx
from fakes import AS_OF, FakeEmbeddingClient
from sqlalchemy import text

from app.services.recommendation.schemas import PoiConstraint, SearchConstraints
from app.services.recommendation.search import boost_lexical, group_reposts

HOSPITAL_2KM = PoiConstraint(poi_type="benh_vien", max_distance_m=2000)


async def district_ids(session, *aliases) -> list[int]:
    rows = await session.execute(
        text("SELECT id FROM districts_old WHERE alias = ANY(:a) ORDER BY id"), {"a": list(aliases)}
    )
    return list(rows.scalars())


async def violations(session, hits, constraints: SearchConstraints) -> list[str]:
    """Oracle [S1]/[S6]: tin nào trong hits vi phạm điều kiện cứng thì trả listing_id."""
    bad = []
    for hit in hits:
        row = (await session.execute(text(
            "SELECT * FROM listings WHERE listing_id = :id"), {"id": hit.listing_id}
        )).mappings().one()
        ok = (
            row["posted_at"] <= AS_OF <= row["expired_at"]
            and (constraints.price_max is None or row["price"] <= constraints.price_max)
            and (constraints.price_min is None or row["price"] >= constraints.price_min)
            and (not constraints.property_types
                 or row["property_type"] in constraints.property_types)
            and (not constraints.district_ids or row["old_district_id"] in constraints.district_ids)
            and (constraints.bedrooms_min is None
                 or (row["bedrooms"] or 0) >= constraints.bedrooms_min)
        )
        for poi in constraints.near_pois:
            ok = ok and (await session.execute(text(
                "SELECT min(ST_Distance(p.geom, l.geom)) FROM pois p, listings l"
                " WHERE l.listing_id = :id AND p.poi_type = :t"),
                {"id": hit.listing_id, "t": poi.poi_type},
            )).scalar() <= poi.max_distance_m
        if not ok:
            bad.append(hit.listing_id)
    return bad


def test_resolve_areas_thu_duc_abbreviation_unaccent_and_unknown(run_db, make_search):
    async def check(session):
        search = make_search(session)
        districts, wards, unknown = await search.resolve_areas(
            ["Thủ Đức", "Q7", "binh thanh", "Hà Nội"], ["phường sài gòn"]
        )
        expected = await district_ids(session, "quan-2", "quan-9", "thu-duc", "quan-7",
                                      "binh-thanh")
        # "Quận 9" chỉ là Quận 9, không mở rộng thành cả TP Thủ Đức
        only_q9, _, _ = await search.resolve_areas(["Quận 9"], [])
        assert only_q9 == await district_ids(session, "quan-9")
        ward = (await session.execute(text(
            "SELECT id FROM wards_new WHERE name = 'Sài Gòn' AND province_id ="
            " (SELECT id FROM provinces_new WHERE code = 'SG')"
        ))).scalar_one()
        assert (districts, wards, unknown) == (expected, [ward], ["Hà Nội"])

    run_db(check)


def test_search_returns_only_listings_matching_hard_constraints(run_db, make_search):
    async def check(session):
        constraints = SearchConstraints(
            price_max=3000, property_types=["Căn hộ chung cư"], bedrooms_min=2,
            district_ids=await district_ids(session, "quan-2", "quan-9", "thu-duc"),
            near_pois=[HOSPITAL_2KM], soft_query="yên tĩnh",
        )
        hits, degraded = await make_search(session).search(constraints, AS_OF)
        assert not degraded and 1 <= len(hits) <= 5
        assert await violations(session, hits, constraints) == []
        assert all(hit.score is not None for hit in hits)

    run_db(check)


def test_embed_failure_falls_back_to_newest_first_and_marks_degraded(run_db, make_search):
    async def check(session):
        constraints = SearchConstraints(
            price_max=5000, district_ids=await district_ids(session, "quan-7")
        )
        client = FakeEmbeddingClient(embed_error=httpx.ReadTimeout("Kaggle chậm"))
        hits, degraded = await make_search(session, client).search(constraints, AS_OF)
        assert degraded and len(hits) == 5
        assert await violations(session, hits, constraints) == []
        posted = [hit.posted_at for hit in hits]
        assert posted == sorted(posted, reverse=True)
        assert all(hit.score is None for hit in hits)

    run_db(check)


def test_rerank_only_runs_when_enabled_and_failure_keeps_vector_order(run_db, make_search):
    async def check(session):
        constraints = SearchConstraints(
            price_max=5000, district_ids=await district_ids(session, "quan-7")
        )
        plain_client = FakeEmbeddingClient()
        plain, _ = await make_search(session, plain_client).search(constraints, AS_OF)
        assert plain_client.rerank_calls == 0

        reranked, degraded = await make_search(
            session, FakeEmbeddingClient(), rerank_enabled=True
        ).search(constraints, AS_OF)
        assert not degraded and [h.listing_id for h in reranked] != [h.listing_id for h in plain]

        failing = FakeEmbeddingClient(rerank_error=httpx.ConnectError("không có /rerank"))
        kept, degraded = await make_search(session, failing, rerank_enabled=True).search(
            constraints, AS_OF
        )
        assert degraded and failing.rerank_calls == 1
        assert [h.listing_id for h in kept] == [h.listing_id for h in plain]

    run_db(check)


def test_top5_never_contains_two_reposts_of_same_listing(run_db, make_search):
    async def check(session):
        # Jamona City (Quận 7) có nhiều tin đăng lại cùng giá/diện tích
        constraints = SearchConstraints(
            price_max=4000, property_types=["Căn hộ chung cư"],
            district_ids=await district_ids(session, "quan-7"), soft_query="Jamona City",
        )
        hits, _ = await make_search(session).search(constraints, AS_OF)
        keys = [(h.property_type, h.price, h.area, h.bedrooms) for h in hits]
        for i, hit in enumerate(hits):
            for j in range(i + 1, len(hits)):
                if keys[i] == keys[j]:  # cùng khóa thì phải cách nhau >= 30 m
                    distance = (await session.execute(text(
                        "SELECT ST_Distance(a.geom, b.geom) FROM listings a, listings b"
                        " WHERE a.listing_id = :a AND b.listing_id = :b"),
                        {"a": hit.listing_id, "b": hits[j].listing_id},
                    )).scalar()
                    assert distance is None or distance >= 30

    run_db(check)


def test_relax_options_counts_match_independent_sql(run_db, make_search):
    async def check(session):
        quan_1 = await district_ids(session, "quan-1")
        constraints = SearchConstraints(
            price_max=1000, property_types=["Nhà mặt phố"], district_ids=quan_1,
            near_pois=[HOSPITAL_2KM],
        )
        search = make_search(session)
        hits, _ = await search.search(constraints, AS_OF)
        assert hits == []
        relax = await search.relax_options(constraints, AS_OF)
        options = {o.field: o.result_count for o in relax}
        assert len(options) == len(relax)  # một POI nên mỗi field một phương án
        assert options.get("price_max") == 1  # tin 1,05 tỷ: có khi tăng ngân sách 20%

        active = "expired_at >= :d AND posted_at <= :d"
        near = ("EXISTS (SELECT 1 FROM pois p WHERE p.poi_type = 'benh_vien'"
                " AND ST_DWithin(p.geom, l.geom, 2000))")
        oracle = {
            "near_pois": f"price <= 1000 AND property_type = 'Nhà mặt phố'"
                                   f" AND old_district_id = {quan_1[0]}",
            "price_max": f"price <= 1200 AND property_type = 'Nhà mặt phố'"
                         f" AND old_district_id = {quan_1[0]} AND {near}",
            "property_types": f"price <= 1000 AND old_district_id = {quan_1[0]} AND {near}",
            "location": f"price <= 1000 AND property_type = 'Nhà mặt phố' AND {near}",
        }
        for field, where in oracle.items():
            rows = (await session.execute(text(
                "SELECT listing_id, property_type, price, area, bedrooms, latitude, longitude,"
                f" posted_at FROM listings l WHERE {active} AND {where}"
                " ORDER BY posted_at DESC, listing_id"), {"d": AS_OF},
            )).mappings().all()
            # result_count tính sau khi gộp tin đăng lại (spec 9.5)
            assert options.get(field, 0) == len(group_reposts([dict(r) for r in rows])), field

    run_db(check)


def test_fetch_details_keeps_requested_order_and_drops_unknown(run_db, make_search):
    async def check(session):
        ids = list((await session.execute(text(
            "SELECT listing_id FROM listings ORDER BY listing_id LIMIT 2"))).scalars())
        rows = await make_search(session).fetch_details([ids[1], "khong-co", ids[0]])
        assert [row["listing_id"] for row in rows] == [ids[1], ids[0]]
        assert "nearest_market_name" in rows[0]

    run_db(check)


def test_lexical_boost_lifts_listings_that_contain_the_preference_phrase():
    rows = [
        {"listing_id": "A", "title": "Nhà đẹp", "body": "rộng rãi", "score": 0.50},
        {"listing_id": "B", "title": "Nhà hẻm", "body": "Khu YÊN TĨNH, an ninh", "score": 0.42},
        {"listing_id": "C", "title": "Nhà ở", "body": "yên tĩnh và hẻm xe hơi", "score": 0.41},
        {"listing_id": "D", "title": "Nhà", "body": "", "score": None},
    ]
    boosted = boost_lexical(rows, "yên tĩnh, hẻm xe hơi")
    assert [r["listing_id"] for r in boosted] == ["C", "B", "A", "D"]  # 0.61 > 0.52 > 0.50
    assert boost_lexical(rows, None) == rows  # không sở thích: giữ thứ tự cũ
    assert boost_lexical(rows, "view sông ")[0]["listing_id"] == "A"
