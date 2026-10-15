"""Truy vấn tin cho hội thoại gợi ý: lọc cứng SQL/PostGIS -> sắp theo vector -> gộp tin đăng lại.

Lọc cứng luôn chạy trong SQL trước khi sắp xếp, nên điều kiện cứng đúng kể cả khi API embedding
(Kaggle) lỗi; khi đó tin được sắp theo ngày đăng mới nhất và kết quả gắn cờ degraded.
"""

import logging
import math
import re
from datetime import date
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.embedding import EmbeddingClient
from app.services.formatting import format_price
from app.services.places import PlaceResolver
from app.services.recommendation.schemas import (
    POI_NAMES,
    ListingHit,
    RelaxOption,
    SearchConstraints,
)
from app.services.recommendation.text_rules import fold, phrases

logger = logging.getLogger(__name__)

TOP_K = 5
CANDIDATE_LIMIT = 50          # lấy dư để còn đủ 5 tin sau khi gộp tin đăng lại
RERANK_TOP_N = 20
RERANK_SNIPPET_CHARS = 500
EARTH_RADIUS_M = 6_371_000     # bán kính Trái Đất để đổi độ lệch tọa độ ra mét
REPOST_DISTANCE_M = 30        # hai tin cùng khóa, cách nhau < 30 m coi là một tin đăng lại
RELAX_BUDGET_FACTOR = 1.2     # phương án nới: tăng ngân sách 20%
LEXICAL_BOOST = 0.10          # mỗi cụm sở thích có trong tiêu đề/mô tả cộng vào điểm (spec 9 #20)
# "Thủ Đức" là TP Thủ Đức = 3 quận cũ của batdongsan (theo alias, không phụ thuộc ID).
# Chỉ mở rộng khi người dùng nói "Thủ Đức"; nói "Quận 2"/"Quận 9" thì chỉ quận đó.
THU_DUC_ALIAS = "thu-duc"
THU_DUC_ALIASES = ("quan-2", "quan-9", "thu-duc")
POI_DISTANCE_COLUMNS = {  # poi_type -> cột khoảng cách tới POI gần nhất
    "truong_hoc": "nearest_school_m", "benh_vien": "nearest_hospital_m",
    "cho": "nearest_market_m",
}

HIT_COLUMNS = """
    l.listing_id, l.title, l.price, l.area, l.property_type, l.bedrooms, l.district_old,
    l.old_address, l.new_address, l.listing_url, l.posted_at, l.expired_at,
    l.latitude, l.longitude, l.quality_flags, left(coalesce(l.description, ''), 3000) AS body,
    f.nearest_school_m, f.nearest_hospital_m, f.nearest_market_m
"""
DETAIL_COLUMNS = """
    l.listing_id, l.title, l.price, l.price_per_m2, l.area, l.property_type, l.bedrooms,
    l.bathrooms, l.floors, l.frontage, l.road_width, l.legal, l.interior, l.district_old,
    l.old_address, l.new_address, l.listing_url, l.posted_at, l.expired_at,
    l.latitude, l.longitude, l.quality_flags, left(coalesce(l.description, ''), 800) AS description,
    f.nearest_school_name, f.nearest_school_m, f.nearest_hospital_name, f.nearest_hospital_m,
    f.nearest_market_name, f.nearest_market_m
"""
FULL_NAME_SQL = "concat_ws(' ', nullif(prefix, ''), name)"  # "Quận 7", "Phường Tân Phong"
AREA_MATCH_SQL = f"""
    SELECT id, alias FROM {{table}}
     WHERE province_code = 'SG'
       AND (lower(unaccent(name)) = lower(unaccent(:name))
            OR lower(unaccent({FULL_NAME_SQL})) = lower(unaccent(:name)))
"""


def _to_hit(row: dict, position: int, as_of: date, constraints: SearchConstraints) -> ListingHit:
    """Dòng SQL -> ListingHit (khoảng cách tới POI gần nhất mỗi loại, vị trí, ngày còn lại)."""
    distances = {poi_type: row[column] for poi_type, column in POI_DISTANCE_COLUMNS.items()
                 if row[column] is not None}
    fields = {k: row[k] for k in ListingHit.model_fields if k in row}
    expired = row["expired_at"]
    reliable = None not in (row["latitude"], row["longitude"]) and (
        "coords_outside_hcm" not in row["quality_flags"])
    return ListingHit(
        **fields, poi_distances=distances, position=position, coords_reliable=reliable,
        place_distances={p.name: row[f"place_{i}"] for i, p in enumerate(constraints.near_places)},
        days_left=(expired - as_of).days if expired else None,
    )


def boost_lexical(candidates: list[dict], soft_query: str | None) -> list[dict]:
    """Điểm vector + LEXICAL_BOOST cho mỗi cụm sở thích có trong tiêu đề/mô tả (C38#2: vector
    của cụm ngắn xếp tin có đúng chữ đó thấp hơn tin dài không liên quan)."""
    wanted = [p for p in map(fold, phrases(soft_query)) if p]
    if not wanted:
        return candidates

    def adjusted_score(row: dict) -> float:
        haystack = f" {fold(row['title'] + ' ' + row['body'])} "
        matches = sum(f" {phrase} " in haystack for phrase in wanted)
        return (row.get("score") or 0.0) + LEXICAL_BOOST * matches

    return sorted(candidates, key=adjusted_score, reverse=True)


def _filters(constraints: SearchConstraints, as_of: date) -> tuple[str, dict]:
    """WHERE cho điều kiện cứng + tin còn hiệu lực tại as_of; mọi giá trị qua placeholder."""
    clauses = ["l.expired_at >= :as_of", "l.posted_at <= :as_of"]
    params: dict[str, Any] = {"as_of": as_of}
    for column, operator, key in (
        ("price", ">=", "price_min"), ("price", "<=", "price_max"),
        ("area", ">=", "area_min"), ("area", "<=", "area_max"),
        ("bedrooms", ">=", "bedrooms_min"),
    ):
        value = getattr(constraints, key)
        if value is not None:
            clauses.append(f"l.{column} {operator} :{key}")
            params[key] = value
    if constraints.property_types:
        clauses.append("l.property_type = ANY(:property_types)")
        params["property_types"] = constraints.property_types
    # Có cả quận cũ và phường mới thì tin phải thỏa cả hai (AND, spec 9.6)
    if constraints.district_ids:
        clauses.append("l.old_district_id = ANY(:district_ids)")
        params["district_ids"] = constraints.district_ids
    if constraints.new_ward_ids:
        clauses.append("l.new_ward_id = ANY(:new_ward_ids)")
        params["new_ward_ids"] = constraints.new_ward_ids
    # Tin không có geom tự bị loại vì ST_DWithin(NULL) không đúng
    for i, poi in enumerate(constraints.near_pois):
        clauses.append(
            f"EXISTS (SELECT 1 FROM pois p WHERE p.poi_type = :poi_type_{i}"  # trường chung chung:
            " AND coalesce(p.poi_subtype, '') NOT IN ('Đại học', 'Cao đẳng')"  # không tính ĐH/CĐ
            f" AND ST_DWithin(p.geom, l.geom, :poi_distance_{i}))"
        )
        params[f"poi_type_{i}"] = poi.poi_type
        params[f"poi_distance_{i}"] = poi.max_distance_m
    where, _, place_params = PlaceResolver.sql(constraints.near_places)  # bán kính quanh địa điểm
    return " AND ".join(clauses + where), params | place_params


class HybridSearch:
    """Mọi truy vấn DB của mode recommendation. Giá trị người dùng luôn qua placeholder."""

    def __init__(
        self, session: AsyncSession, client: EmbeddingClient, rerank_enabled: bool = False
    ):
        self.session = session
        self.client = client
        self.rerank_enabled = rerank_enabled

    async def resolve_areas(
        self, district_names: list[str], new_ward_names: list[str]
    ) -> tuple[list[int], list[int], list[str]]:
        """Tên khu vực -> (district_ids, new_ward_ids, tên không tra được); bỏ qua hoa/thường."""
        district_ids, ward_ids, unknown = [], [], []
        for names, table, ids in (
            (district_names, "districts_old", district_ids),
            (new_ward_names, "wards_new", ward_ids),
        ):
            for raw_name in names:
                # "Q7", "q.7", "quận 7" -> "Quận 7"; "TP Thủ Đức" -> "Thủ Đức"
                name = re.sub(
                    r"^(?:q\.?|quận)\s*(\d+)$", r"Quận \1", raw_name.strip(), flags=re.IGNORECASE
                )
                name = re.sub(r"^(?:tp\.?|thành phố)\s+", "", name, flags=re.IGNORECASE)
                rows = (await self.session.execute(
                    text(AREA_MATCH_SQL.format(table=table)), {"name": name}
                )).all()
                if not rows:
                    unknown.append(raw_name)
                elif table == "districts_old" and rows[0].alias == THU_DUC_ALIAS:
                    ids.extend((await self.session.execute(
                        text("SELECT id FROM districts_old WHERE alias = ANY(:aliases)"),
                        {"aliases": list(THU_DUC_ALIASES)},
                    )).scalars())
                else:
                    ids.extend(row.id for row in rows)
        return sorted(set(district_ids)), sorted(set(ward_ids)), unknown

    async def known_areas(self) -> tuple[list[str], list[str]]:
        """(tên phường/xã mới, tên đầy đủ quận/huyện cũ) của TP.HCM, để code tìm tên trong câu."""
        wards = await self.session.execute(
            text("SELECT name FROM wards_new WHERE province_code = 'SG'"))
        districts = await self.session.execute(text(
            f"SELECT {FULL_NAME_SQL} FROM districts_old WHERE province_code = 'SG'"))
        return list(wards.scalars()), list(districts.scalars())

    async def area_names(self, constraints: SearchConstraints) -> list[str]:
        """Tên đầy đủ các khu vực đang chọn (để LLM và câu trả lời hiển thị, không phải ID)."""
        rows = await self.session.execute(
            text(
                f"SELECT {FULL_NAME_SQL} FROM districts_old WHERE id = ANY(:district_ids)"
                f" UNION ALL SELECT {FULL_NAME_SQL} FROM wards_new WHERE id = ANY(:ward_ids)"
            ),
            {"district_ids": constraints.district_ids, "ward_ids": constraints.new_ward_ids},
        )
        return list(rows.scalars())

    async def search(
        self, constraints: SearchConstraints, as_of: date
    ) -> tuple[list[ListingHit], bool]:
        """Top 5 tin thỏa điều kiện cứng; trả (tin, degraded)."""
        query = await self._query_text(constraints)
        vector = await self._embed_or_none(query)
        rows = await self._rank_sql(constraints, as_of, vector)
        candidates = boost_lexical(rows, constraints.soft_query)
        degraded = vector is None
        if self.rerank_enabled and not degraded and candidates and not constraints.near_places:
            candidates, reranked = await self._rerank(query, candidates)
            degraded = not reranked
        top = group_reposts(candidates)[:TOP_K]
        return [_to_hit(r, i, as_of, constraints) for i, r in enumerate(top, 1)], degraded

    async def relax_options(
        self, constraints: SearchConstraints, as_of: date
    ) -> list[RelaxOption]:
        """Số tin (sau khi gộp tin đăng lại) khi nới ĐÚNG MỘT điều kiện; chỉ phương án có tin."""
        result = []
        for field, description, relaxed in relaxed_variants(constraints):
            where, params = _filters(relaxed, as_of)
            rows = (await self.session.execute(
                text(
                    "SELECT l.listing_id, l.property_type, l.price, l.area, l.bedrooms,"
                    " l.latitude, l.longitude, l.posted_at FROM listings l"
                    f" WHERE {where} ORDER BY l.posted_at DESC, l.listing_id"
                ),
                params,
            )).mappings().all()
            if count := len(group_reposts([dict(row) for row in rows])):
                result.append(
                    RelaxOption(field=field, description=description, result_count=count,
                                message=description)
                )
        return result

    async def fetch_details(self, listing_ids: list[str]) -> list[dict]:
        """Dữ liệu đầy đủ của các tin (cho ask_detail/compare), giữ đúng thứ tự listing_ids."""
        rows = await self.session.execute(
            text(
                f"SELECT {DETAIL_COLUMNS} FROM listings l"
                " LEFT JOIN listing_spatial_features f USING (listing_id)"
                " WHERE l.listing_id = ANY(:ids)"
            ),
            {"ids": listing_ids},
        )
        by_id = {row["listing_id"]: dict(row) for row in rows.mappings()}
        return [by_id[i] for i in listing_ids if i in by_id]

    async def _embed_or_none(self, query: str) -> list[float] | None:
        """Vector của câu hỏi; None khi API embedding lỗi (sẽ sắp theo ngày đăng)."""
        try:
            return await self.client.embed(query)
        except Exception:  # API embedding lỗi bất kỳ kiểu nào -> phương án dự phòng
            logger.warning("embed câu hỏi lỗi, sắp theo ngày đăng", exc_info=True)
            return None

    async def _rank_sql(
        self, constraints: SearchConstraints, as_of: date, vector: list[float] | None
    ) -> list[dict]:
        """Lọc cứng trong SQL rồi sắp theo khoảng cách vector (hoặc ngày đăng khi không có)."""
        where, params = _filters(constraints, as_of)
        if vector is None:
            score, order = "NULL::float AS score", "l.posted_at DESC, l.listing_id"
        else:
            params["qvec"] = "[" + ",".join(map(str, vector)) + "]"
            distance = "(e.embedding <=> CAST(:qvec AS vector))"
            # Tin chưa có embedding vẫn được trả, xếp sau tin đã có
            score = f"1 - {distance} AS score"
            order = f"{distance} NULLS LAST, l.posted_at DESC, l.listing_id"
        places = PlaceResolver.sql(constraints.near_places)[1]
        order = "place_0, " * bool(constraints.near_places and not constraints.soft_query) + order
        rows = (await self.session.execute(
            text(
                f"SELECT {HIT_COLUMNS}, {score}{places} FROM listings l"
                " LEFT JOIN listing_spatial_features f USING (listing_id)"
                " LEFT JOIN listing_embeddings e USING (listing_id)"
                f" WHERE {where} ORDER BY {order} LIMIT {CANDIDATE_LIMIT}"
            ),
            params,
        )).mappings().all()
        return [dict(row) for row in rows]

    async def _rerank(self, query: str, candidates: list[dict]) -> tuple[list[dict], bool]:
        """Rerank RERANK_TOP_N tin đầu; lỗi thì giữ thứ tự vector và trả False."""
        head, tail = candidates[:RERANK_TOP_N], candidates[RERANK_TOP_N:]
        try:
            scores = await self.client.rerank(
                query, [f"{c['title']}\n{c['body'][:RERANK_SNIPPET_CHARS]}" for c in head]
            )
        except Exception:
            logger.warning("rerank lỗi, giữ thứ tự vector", exc_info=True)
            return candidates, False
        ranked = sorted(zip(scores, range(len(head)), head, strict=True), reverse=True)
        return [c for _, _, c in ranked] + tail, True

    async def _query_text(self, constraints: SearchConstraints) -> str:
        """Câu đem embed: sở thích mềm, không có thì tóm tắt điều kiện."""
        if constraints.soft_query:
            return constraints.soft_query
        parts = [", ".join(constraints.property_types) or "Nhà đất"]
        if names := await self.area_names(constraints):
            parts.append("tại " + ", ".join(names))
        return " ".join(parts)


def relaxed_variants(
    constraints: SearchConstraints,
) -> list[tuple[str, str, SearchConstraints]]:
    """Các điều kiện nới ĐÚNG MỘT điều kiện: (field, mô tả, điều kiện đã nới) (spec 9.5)."""
    variants = [  # nhiều POI: mỗi POI một phương án
        ("near_pois", f"bỏ điều kiện gần {POI_NAMES[poi.poi_type]}", constraints.model_copy(
            update={"near_pois": [p for p in constraints.near_pois if p != poi]}))
        for poi in constraints.near_pois
    ]
    variants += [("near_places", text, constraints.model_copy(update={"near_places": places}))
                 for text, places in PlaceResolver.relaxed(constraints.near_places)]
    if constraints.price_max is not None:
        budget = constraints.price_max * RELAX_BUDGET_FACTOR  # không làm tròn (spec 9.5)
        variants.append(("price_max", f"tăng ngân sách lên {format_price(budget)}",
                         constraints.model_copy(update={"price_max": budget})))
    if constraints.property_types:
        variants.append(("property_types", "bỏ điều kiện loại nhà đất",
                         constraints.model_copy(update={"property_types": []})))
    if constraints.district_ids or constraints.new_ward_ids:
        variants.append(("location", "mở rộng ra toàn TP.HCM", constraints.model_copy(
            update={"district_ids": [], "new_ward_ids": []})))
    return variants


def _is_repost(row: dict, first: dict) -> bool:
    """Cùng loại/giá/diện tích/phòng ngủ và cách nhau < REPOST_DISTANCE_M."""
    if any(row[key] != first[key] for key in ("property_type", "price", "area", "bedrooms")):
        return False
    if None in (row["latitude"], row["longitude"], first["latitude"], first["longitude"]):
        return False
    # Xấp xỉ phẳng: đủ chính xác ở khoảng cách vài chục mét
    dy = math.radians(row["latitude"] - first["latitude"])
    dx = math.radians(row["longitude"] - first["longitude"]) * math.cos(
        math.radians(first["latitude"])
    )
    return EARTH_RADIUS_M * math.hypot(dx, dy) < REPOST_DISTANCE_M


def group_reposts(candidates: list[dict]) -> list[dict]:
    """Gộp tin đăng lại (xem _is_repost) vào tin mới nhất của nhóm."""
    groups: list[list[dict]] = []
    for row in candidates:
        group = next((g for g in groups if _is_repost(row, g[0])), None)
        if group is None:
            groups.append([row])
        else:
            group.append(row)
    result = []
    for group in groups:
        newest = max(group, key=lambda r: r["posted_at"] or date.min)
        result.append(
            {**newest, "similar_ids": [r["listing_id"] for r in group if r is not newest]}
        )
    return result
