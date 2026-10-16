"""PlaceResolver: tên địa điểm → điểm trên bản đồ (named-places.md 2.4): pois (pg_trgm trên tên
không dấu + bí danh), rồi Goong. Tên chỉ vào SQL qua placeholder; code chọn ứng viên, không LLM."""

import logging
import math
import re
from typing import NamedTuple

import httpx
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.formatting import format_distance
from app.services.prediction.constants import HCM_LAT, HCM_LON
from app.services.recommendation.schemas import PlaceConstraint, PlaceRequest, SearchConstraints
from app.services.recommendation.text_rules import (
    ALIASES,
    GOONG_ONLY,
    NUMBER_WORDS,
    area_key,
    fold,
)

logger = logging.getLogger(__name__)

GOONG_URL = "https://rsapi.goong.io/v2/geocode"
DEFAULT_RADIUS_M, RELAX_RADIUS_FACTOR = 5000, 1.4  # nới bán kính: 5 km -> 7 km
MATCH_MARGIN = 0.1         # điểm nhì kém điểm nhất dưới mức này thì coi là trùng tên, hỏi lại
MAX_CHOICES, SAME_PLACE_DEG = 5, 0.0027  # tối đa 5 ứng viên; ~300 m: hai tên gần thế là một nơi
SAME_CAMPUS_DEG = 0.014    # ~1,5 km: cùng tên + cùng địa chỉ trong khoảng này là một cơ sở
# Từ đệm đứng đầu tên ("trường", "đại học", "bv"...): bỏ khi chấm điểm để không khớp mọi trường
FILLER = re.compile(r"^(?:truong|dai hoc|dh|cao dang|cd|hoc vien|benh vien|bv|cho|thpt|thcs|"
                    r"th|mam non|sieu thi)\s+")
# Tên bắt đầu bằng đại học/cao đẳng/học viện thì chỉ xét trường ĐH/CĐ (không lẫn mầm non, THPT)
UNIVERSITY_NAME = re.compile(r"^(?:truong )?(?:dai hoc|dh|cao dang|cd|hoc vien)\b")
CITY_NAME = re.compile(r"\b(?:tphcm|tp hcm|hcm|ho chi minh)\b")  # "đh luật tphcm" ≠ tên trong pois
EXPAND = {"dh": "dai hoc", "bv": "benh vien", "cd": "cao dang"}
# Goong hay trả điểm ở tỉnh giáp ranh (khung toạ độ HCM_LAT/HCM_LON bao cả chúng), đôi khi ghi
# "Thủ Dầu Một, Hồ Chí Minh": loại theo tên tỉnh VÀ tên thành phố/huyện giáp ranh
OTHER_PROVINCES = (
    "binh duong", "long an", "dong nai", "ba ria", "vung tau", "tay ninh", "tien giang",
    "thu dau mot", "di an", "thuan an", "ben cat", "tan uyen", "bau bang", "bien hoa",
    "long thanh", "nhon trach", "trang bom", "tan an")
NEAR_LISTING_SQL = text("""
    SELECT EXISTS (SELECT 1 FROM listings WHERE ST_DWithin(
        geom, ST_MakePoint(:lon, :lat)::geography, 1000)
        AND NOT ('coords_outside_hcm' = ANY(quality_flags)))""")
POINT_SQL = "ST_MakePoint(:place_lon_{i}, :place_lat_{i})::geography"
MATCH_SQL = text("""
    SELECT p.id, p.name, p.address_old, p.latitude, p.longitude,
           word_similarity(:core, immutable_unaccent(lower(p.name))) AS score,
           (SELECT l.district_old FROM listings l WHERE l.geom IS NOT NULL
             ORDER BY l.geom <-> p.geom LIMIT 1) AS district
      FROM pois p
     WHERE :core <% immutable_unaccent(lower(p.name)) AND p.geom IS NOT NULL
       AND (CAST(:kind AS text) IS NULL OR :kind = 'khac' OR p.poi_type = :kind)
       AND (NOT CAST(:uni AS boolean) OR p.poi_subtype IN ('Đại học', 'Cao đẳng'))
     ORDER BY score DESC, similarity(:core, immutable_unaccent(lower(p.name))) DESC, p.id LIMIT 20
""")  # <% dùng ngưỡng mặc định pg_trgm.word_similarity_threshold = 0,6


class PlaceOutcome(NamedTuple):  # kết quả tra các địa điểm của một câu
    places: list[PlaceConstraint]   # áp ngay
    pending: list[PlaceConstraint]  # ứng viên chờ người dùng chọn/xác nhận
    question: str | None
    suggestions: list[str]
    notes: list[str]                # không tìm thấy: nói rõ chưa lọc theo khoảng cách
    soft_names: list[str]           # tên không tìm thấy, đưa vào sở thích mềm


class PlaceResolver:
    """Tra địa điểm; Goong dùng key của Geocoder, cache trong bộ nhớ."""

    def __init__(self, goong_key: SecretStr | None):
        self.goong_key = goong_key
        self._goong_cache: dict[str, PlaceConstraint | None] = {}

    async def resolve_all(self, session: AsyncSession, requests: list[PlaceRequest], text: str,
                          areas: list[str], current: list[PlaceConstraint]) -> PlaceOutcome:
        out = PlaceOutcome([], [], None, [], [], [])
        for request in requests:
            known = [p for p in current if fold(p.name) == fold(request.name)]  # "mở rộng ra 8 km"
            core = self.core(request.name)  # tên phải có trong câu (nguyên văn hoặc bí danh)
            if not (known or fold(request.name) in text or any(
                    core == v and re.search(rf"\b{k}\b", text) for k, v in ALIASES.items())):
                continue
            status, found = ("one", known) if known else await self.resolve(session, request, areas)
            same = [p.max_distance_m for p in current for c in found[:1]
                    if (p.poi_id, p.name) == (c.poi_id, c.name)]  # đổi tên gọi: giữ bán kính cũ
            radius = request.max_distance_m or (same or [DEFAULT_RADIUS_M])[0]
            found = [c.model_copy(update={"max_distance_m": radius}) for c in found]
            if status == "one":
                out.places.append(found[0])
            elif status == "none":
                out.soft_names.append(request.name)
                out.notes.append(f"Mình không tìm thấy \"{request.name}\" trên bản đồ nên chưa "
                                 "lọc theo khoảng cách, chỉ ưu tiên tin có nhắc tới tên này.")
            elif out.question is None:  # nhiều ứng viên: liệt kê; điểm Goong: luôn xác nhận
                out.pending.extend(found)
                question, chips = self.ask(request.name, found, status == "many")
                out = out._replace(question=question)
                out.suggestions.extend(chips)
        return out

    async def resolve(self, session: AsyncSession, request: PlaceRequest,
                      areas: list[str]) -> tuple[str, list[PlaceConstraint]]:
        """("one"|"many"|"geocoded"|"none", ứng viên): pois (ưu tiên quận đang chọn), rồi Goong."""
        core = self.core(request.name)
        rows = [] if core in GOONG_ONLY else (await session.execute(  # kind "khac" vẫn tra pois
            MATCH_SQL, {"core": core, "kind": request.kind,
                        "uni": bool(UNIVERSITY_NAME.match(fold(request.name)))})).mappings().all()
        if request.kind == "khac":  # "sân bay Tân Sơn Nhất" không được khớp "TH Tân Sơn Nhất"
            rows = [r for r in rows if set(core.split()) <= set(fold(r["name"]).split())]
        keys = {area_key(a) for a in areas}
        keys |= {"2", "9"} if "thu duc" in keys else set()  # TP Thủ Đức = Q2 + Q9 + Thủ Đức cũ
        rows = [r for r in rows if area_key(r["district"] or "") in keys or any(re.search(
            rf"\b(?:quan|huyen) {k}\b" if k.isdigit() else rf"\b{k}\b",
            fold(r["address_old"] or "")) for k in keys)] or rows
        close = []  # điểm sát điểm cao nhất; bỏ điểm cùng chỗ hoặc cùng tên + địa chỉ ở sát nhau
        for r in rows:
            gaps = [math.dist((r["latitude"], r["longitude"]), (c.latitude, c.longitude))
                    for c in close]
            duplicate = any(gap <= SAME_PLACE_DEG or (
                gap <= SAME_CAMPUS_DEG and fold(c.name) == fold(r["name"])
                and c.address == r["address_old"]) for gap, c in zip(gaps, close, strict=True))
            if r["score"] >= rows[0]["score"] - MATCH_MARGIN and not duplicate:
                close.append(PlaceConstraint(  # địa chỉ chỉ lấy từ POI, không đoán từ tin đăng
                    name=r["name"], latitude=r["latitude"], longitude=r["longitude"],
                    poi_id=r["id"], address=r["address_old"], district=r["district"]))
        if close:
            return ("one" if len(close) == 1 else "many"), close[:MAX_CHOICES]
        point = await self._goong(request.name, areas)
        if point and not (await session.execute(NEAR_LISTING_SQL, {
                "lon": point.longitude, "lat": point.latitude})).scalar():
            point = None  # Goong trả điểm xa mọi tin đăng (tỉnh giáp ranh): coi như không thấy
        return ("geocoded", [point]) if point else ("none", [])

    @staticmethod
    def core(name: str) -> str:
        """Tên không dấu, bỏ "tphcm", viết tắt đầu tên thành đủ, bỏ từ đệm ở đầu (nhưng giữ ≥ 2
        từ: "chợ rẫy"), đổi bí danh."""
        first, _, rest = " ".join(CITY_NAME.sub(" ", fold(name).replace(",", " ")).split()
                                  ).partition(" ")
        core = f"{EXPAND.get(first, first)} {rest}".strip()
        while (stripped := FILLER.sub("", core)) != core and (
                stripped in ALIASES or len(stripped.split()) >= 2):
            core = stripped
        if UNIVERSITY_NAME.match(core):  # kind/subtype đã giới hạn ĐH: chỉ so phần tên riêng
            core = FILLER.sub("", core) or core
        return ALIASES.get(core) or ALIASES.get(FILLER.sub("", core)) or core

    @classmethod
    def choose(cls, constraints: SearchConstraints, pending: list[PlaceConstraint], message: str,
               confirmed: bool) -> str:
        """Áp ứng viên người dùng chọn (số thứ tự, tên quận, tên; điểm Goong thì "đúng").

        Trả "chosen"; "retry" khi nhiều ứng viên mà người dùng chỉ nói "đúng" hoặc số ngoài danh
        sách (hỏi lại, giữ nguyên danh sách); "" khi câu không liên quan (bỏ danh sách)."""
        chosen, said, ambiguous = None, fold(message), False
        number = re.search(rf"(?:^|\b(?:so|thu|cai))\s*(\d+|{'|'.join(NUMBER_WORDS)})\b", said)
        if len(pending) == 1:
            chosen = pending[0] if confirmed else None
        elif number:
            chosen = dict(enumerate(pending, 1)).get(NUMBER_WORDS.get(number[1]) or int(number[1]))
        elif pending:
            by_area = [p for p in pending if any(re.search(
                rf"\b(?:quan |q ?){k}\b" if k.isdigit() else rf"\b{k}\b", said)
                for k in cls.areas(p))]
            by_name = [p for p in pending if cls.own_words(p.name) <= set(said.split())]
            named = by_area if len(by_area) == 1 else by_name  # "nhi đồng 2" không cần tên đầy đủ
            chosen = named[0] if len(named) == 1 else None
            ambiguous = len(named) > 1
        if chosen:
            constraints.near_places = cls.merge(constraints.near_places, [chosen])
            return "chosen"
        # câu ngắn chỉ nói quận ("ở quận 10") mà không khớp ai: hỏi lại, đừng coi là tìm mới
        area_only = re.search(r"\b(?:quan|huyen|q)\s?\w+", said) and len(said.split()) <= 5 and (
            not re.search(r"\b(?:nha|can|tim|ty|tr|duoi|tren)\b", said))
        unclear = confirmed or number or area_only or ambiguous
        return "retry" if len(pending) > 1 and unclear else ""

    @staticmethod
    def own_words(name: str) -> set[str]:
        """Các từ riêng của tên (bỏ bệnh viện/trường/đại học/chợ…), để so với câu người dùng."""
        return set(fold(name).split()) - {"truong", "dai", "hoc", "benh", "vien", "cho", "co", "so"}

    @staticmethod
    def shrink_notes(
        old: list[PlaceConstraint], new: list[PlaceConstraint], text: str) -> list[str]:
        """"nới ra 3 km" khi đang 5 km: số mới nhỏ hơn thì là bán kính mới (thu hẹp), nói rõ."""
        before = {(p.poi_id, p.name): p.max_distance_m for p in old}
        return [f"Bạn nói \"nới\" nhưng {format_distance(p.max_distance_m)} nhỏ hơn bán kính "
                f"hiện tại ({format_distance(before[(p.poi_id, p.name)])}) nên mình hiểu là đổi "
                f"bán kính quanh {p.name} thành {format_distance(p.max_distance_m)}."
                for p in new if (p.poi_id, p.name) in before and "noi" in text.split()
                and p.max_distance_m < before[(p.poi_id, p.name)]]

    @staticmethod
    def areas(place: PlaceConstraint) -> set[str]:
        """Khoá quận/huyện của ứng viên: trong địa chỉ POI và quận của tin đăng gần nhất."""
        found = re.findall(r"\b((?:quan|huyen) [a-z0-9 ]+?)(?= ,|$)", fold(place.address or ""))
        return {area_key(a) for a in [*found, place.district or ""] if a}

    @classmethod
    def ask(cls, name: str, found: list[PlaceConstraint], many: bool,
            retry: bool = False) -> tuple[str, list[str]]:
        """(câu hỏi, chip): liệt kê ứng viên trùng tên (hoặc hỏi lại) / xác nhận điểm Goong."""
        labels = [cls.label(c, area=True) for c in found]
        labels = [f"{label} ({c.latitude:.4f}, {c.longitude:.4f})" if labels.count(label) > 1
                  else label for label, c in zip(labels, found, strict=True)]  # y hệt: thêm toạ độ
        choices = [f"{i}. {label}" for i, label in enumerate(labels, 1)]
        if many:
            head = ("Mình chưa hiểu bạn chọn địa điểm nào, các lựa chọn là:" if retry
                    else f"Có {len(found)} địa điểm khớp \"{name}\":")
            return "\n".join([head, *choices,
                              "Bạn chọn số mấy (hoặc nói tên quận)?"]), choices
        return (f"Mình tìm thấy {cls.label(found[0])}. Đúng địa điểm bạn muốn không?",
                ["Đúng", "Không phải"])

    @staticmethod
    def merge(old: list[PlaceConstraint], new: list[PlaceConstraint]) -> list[PlaceConstraint]:
        """Cùng địa điểm (poi_id, tên) thì thay bằng bản mới (bán kính mới), không nhân đôi."""
        keys = {(p.poi_id, p.name) for p in new}
        return [p for p in old if (p.poi_id, p.name) not in keys] + list(new)

    @staticmethod
    def relaxed(places: list[PlaceConstraint]) -> list[tuple[str, list[PlaceConstraint]]]:
        """Phương án nới cho từng địa điểm: (mô tả, near_places sau khi nới)."""
        variants = []
        for place in places:
            wider = place.model_copy(update={
                "max_distance_m": round(place.max_distance_m * RELAX_RADIUS_FACTOR)})
            variants += [((f"mở rộng bán kính quanh {place.name} lên "
                           f"{format_distance(wider.max_distance_m)}"),
                          [wider if p == place else p for p in places]),
                         (f"bỏ điều kiện gần {place.name}", [p for p in places if p != place])]
        return variants

    @staticmethod
    def sql(places: list[PlaceConstraint]) -> tuple[list[str], str, dict]:
        """(điều kiện WHERE bán kính, cột khoảng cách place_i, tham số) cho search.py."""
        params = {f"place_{key}_{i}": value for i, p in enumerate(places) for key, value in
                  (("lon", p.longitude), ("lat", p.latitude), ("r", p.max_distance_m))}
        points = [POINT_SQL.format(i=i) for i in range(len(places))]
        return ([f"ST_DWithin(l.geom, {point}, :place_r_{i})" for i, point in enumerate(points)],
                "".join(f", ST_Distance(l.geom, {p}) AS place_{i}" for i, p in enumerate(points)),
                params)

    @staticmethod
    def label(place: PlaceConstraint, area: bool = False) -> str:
        """"THPT Nguyễn Du – Phường 15, Quận 10": bỏ thành phố, mã bưu chính và phần lặp lại.
        area: thêm "khu vực <quận của tin đăng gần nhất>" khi địa chỉ chưa có quận (gần đúng)."""
        name = fold(place.name)
        parts = [a for a in (place.address or "").split(", ")
                 if a and not re.search(r"Chí Minh|Ho Chi Minh|Việt Nam", a)
                 and not re.fullmatch(r"\d{5,6}", a)
                 and fold(a) not in name and name not in fold(a)]
        parts = [f"Phường {a}" if a.isdigit() and i > 1 else a for i, a in enumerate(parts)]
        if area and place.district and not any(re.match(r"Quận|Huyện|Thành phố", a) for a in parts):
            parts.append(f"khu vực {place.district}")
        return f"{place.name} – {', '.join(dict.fromkeys(parts))}" if parts else place.name

    async def _goong(self, name: str, areas: list[str]) -> PlaceConstraint | None:
        """Điểm Goong đầu tiên nằm trong TP.HCM cũ và có chứa tên truy vấn (Goong trả cả địa danh
        hành chính cho tên vô nghĩa); lỗi, hết hạn mức hay không có key thì None."""
        full = GOONG_ONLY.get(self.core(name), name)  # viết tắt không tra được bằng pois
        query = ", ".join([full, *areas, "Hồ Chí Minh"])
        if query in self._goong_cache or not self.goong_key:
            return self._goong_cache.get(query)
        try:
            async with httpx.AsyncClient(timeout=8) as client:
                response = await client.get(GOONG_URL, params={
                    "address": query, "api_key": self.goong_key.get_secret_value()})
            response.raise_for_status()
            result = response.json()["results"][0]
            lat, lon = (float(result["geometry"]["location"][k]) for k in ("lat", "lng"))
        except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as error:
            logger.warning("Goong lỗi khi tra địa điểm (%s)", type(error).__name__)  # không log URL
            return None
        found = set(fold(f"{result.get('name')} {result.get('formatted_address')}").split())
        words = self.core(full).split()
        inside = HCM_LAT[0] <= lat <= HCM_LAT[1] and HCM_LON[0] <= lon <= HCM_LON[1]
        named = 2 * sum(word in found for word in words) >= len(words)  # đủ nửa số từ của tên
        same_province = not any(re.search(rf"\b{p}\b", fold(
            f"{result.get('name')} {result.get('formatted_address')}")) for p in OTHER_PROVINCES)
        self._goong_cache[query] = PlaceConstraint(
            name=result.get("name") or name, address=result.get("formatted_address"),
            latitude=lat, longitude=lon) if inside and named and same_province else None
        return self._goong_cache[query]
