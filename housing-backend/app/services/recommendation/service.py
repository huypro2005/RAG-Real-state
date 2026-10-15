"""RecommendationService: điều phối một lượt hội thoại (docs/tasks/hybrid-search.md mục 1).

LLM chỉ dùng ở TurnInterpreter; chọn nhánh, merge, kiểm tra và viết câu trả lời là code tất định.
"""

import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.services.assistant_text import assistant_reply
from app.services.embedding import EmbeddingClient
from app.services.formatting import format_price
from app.services.openai_client import openai_client
from app.services.places import PlaceOutcome, PlaceResolver
from app.services.recommendation.grounding import is_vague_question
from app.services.recommendation.interpreter import TurnInterpreter
from app.services.recommendation.schemas import (
    PROPERTY_TYPES,
    ChatTurnResult,
    ConstraintDelta,
    ConversationState,
    PoiConstraint,
    PoiRequest,
    SearchConstraints,
    TurnPlan,
)
from app.services.recommendation.search import TOP_K, HybridSearch
from app.services.recommendation.text_rules import Correction, MessageRules, phrases
from app.services.recommendation.writer import (
    OUT_OF_SCOPE_ANSWER,
    ask_budget_or_area,
    ask_confirm_budget,
    ask_which_listing,
    describe_changes,
    describe_constraints,
    details_answer,
    no_results_answer,
    refs_not_found,
    results_answer,
)
from app.services.valuation import NO_LISTINGS, NO_VALUER, ListingValuer

MAX_MESSAGE_CHARS = 1000
HISTORY_MESSAGES = 12        # 6 lượt gần nhất (người dùng + trợ lý)
CHEAPER_FACTOR = 0.9         # "rẻ hơn chút" = hạ giá 10% (cả hai biên nếu có khoảng)
PRICE_RANGE = (100, 500_000)       # triệu VND: 100 triệu - 500 tỷ
AREA_RANGE = (10, 10_000)          # m²
POI_DISTANCE_RANGE = (100, 20_000)  # mét
DEFAULT_POI_DISTANCE_M = 2000      # "gần bệnh viện" không nói khoảng cách (spec 9.11)
KEEP_BUDGET_ANSWER = "Mình giữ nguyên ngân sách hiện tại. Bạn cần điều chỉnh gì cứ nói nhé."
LAND_KINDS = {"dat", "dat_nen_du_an"}
RESET_NOTE = "Mình đã xoá điều kiện cũ và tìm lại từ đầu. "
VIETNAM_TZ = timezone(timedelta(hours=7))  # "hôm nay" theo giờ Việt Nam, không theo giờ máy chủ


class ConversationStore:
    """Trạng thái hội thoại trong bộ nhớ (GĐ8: bảng chat_sessions); luôn trả/lưu bản sao."""

    def __init__(self):
        self._states: dict[str, ConversationState] = {}

    def get(self, conversation_id: str) -> ConversationState:
        """Bản sao state của hội thoại (state trống nếu chưa có)."""
        state = self._states.get(conversation_id)
        return (state or ConversationState(conversation_id=conversation_id)).model_copy(deep=True)

    def save(self, state: ConversationState) -> None:
        """Lưu bản sao của state."""
        self._states[state.conversation_id] = state.model_copy(deep=True)


def merge_constraints(
    current: SearchConstraints, plan: TurnPlan, district_ids: list[int], new_ward_ids: list[int]
) -> SearchConstraints:
    """Áp TurnPlan lên điều kiện hiện tại: bỏ trước (clear_fields), đặt/ghi đè sau (set_fields).

    district_ids/new_ward_ids là ID đã tra từ tên; khu vực mới thay hẳn khu vực cũ.
    """
    merged = SearchConstraints() if plan.intent == "reset" else current.model_copy(deep=True)
    delta = plan.set_fields
    _clear_fields(merged, plan.clear_fields)
    for field in ("area_min", "area_max", "bedrooms_min"):
        if getattr(delta, field) is not None:
            setattr(merged, field, getattr(delta, field))
    _merge_price(merged, delta)
    if delta.property_kinds:
        merged.property_types = list(
            dict.fromkeys(t for kind in delta.property_kinds for t in PROPERTY_TYPES[kind])
        )
        if set(delta.property_kinds) <= LAND_KINDS and delta.bedrooms_min is None:
            merged.bedrooms_min = None  # đất không có phòng ngủ: điều kiện cũ không còn nghĩa
    if delta.district_names or delta.new_ward_names:
        merged.district_ids, merged.new_ward_ids = district_ids, new_ward_ids
    _merge_near_pois(merged, delta.near_pois)
    if delta.soft_query:  # sở thích mềm cộng dồn theo cụm; LLM hay chép lại cụm cũ
        both = phrases(merged.soft_query) + phrases(delta.soft_query)
        merged.soft_query = ", ".join(dict.fromkeys(p.lower() for p in both))
    return merged


def _clear_fields(merged: SearchConstraints, fields: list[str]) -> None:
    """Đưa các trường bị bỏ về mặc định; "near_pois.<loại>" chỉ bỏ POI của loại đó."""
    for field in fields:
        if field == "price_min":
            merged.price_min_derived = False
        if field.startswith("near_pois."):
            poi_type = field.removeprefix("near_pois.")
            merged.near_pois = [p for p in merged.near_pois if p.poi_type != poi_type]
        else:
            setattr(merged, field, getattr(SearchConstraints(), field))


def _merge_near_pois(merged: SearchConstraints, requests: list[PoiRequest]) -> None:
    """Cùng loại POI thì điều kiện mới thay điều kiện cũ; không nói khoảng cách thì mặc định."""
    for request in requests:
        distance = request.max_distance_m
        poi = PoiConstraint(
            poi_type=request.poi_type,
            max_distance_m=DEFAULT_POI_DISTANCE_M if distance is None else distance,
        )
        merged.near_pois = [p for p in merged.near_pois if p.poi_type != poi.poi_type] + [poi]


def _merge_price(merged: SearchConstraints, delta: ConstraintDelta) -> None:
    """Giá: khoảng xấp xỉ, đổi giá sau khoảng xấp xỉ, "rẻ hơn" (spec 9 #15, #16)."""
    if delta.price_approx:  # price_min do xấp xỉ sinh ra, không được vượt khoảng hợp lệ
        merged.price_min = max(delta.price_min, PRICE_RANGE[0])
        merged.price_max, merged.price_min_derived = delta.price_max, True
    else:
        if delta.price_min is not None:
            merged.price_min, merged.price_min_derived = delta.price_min, False
        if delta.price_max is not None:
            merged.price_max = delta.price_max
            if delta.price_min is None and merged.price_min_derived:  # khoảng cũ dựng quanh giá cũ
                merged.price_min, merged.price_min_derived = None, False
    if delta.cheaper and merged.price_max is not None:
        merged.price_max = round(merged.price_max * CHEAPER_FACTOR, 2)
        if merged.price_min is not None:
            merged.price_min = round(merged.price_min * CHEAPER_FACTOR, 2)


def validate_constraints(constraints: SearchConstraints) -> list[str]:
    """Lỗi của điều kiện SAU merge (không tự sửa: service hỏi lại người dùng)."""
    problems = []
    for field, label, (low, high), unit in (
        ("price_min", "giá tối thiểu", PRICE_RANGE, "triệu"),
        ("price_max", "giá tối đa", PRICE_RANGE, "triệu"),
        ("area_min", "diện tích tối thiểu", AREA_RANGE, "m²"),
        ("area_max", "diện tích tối đa", AREA_RANGE, "m²"),
    ):
        value = getattr(constraints, field)
        if value is not None and not low <= value <= high:
            problems.append(f"{label} {value:g} {unit} nằm ngoài khoảng {low:g}-{high:g} {unit}")
    pairs = (("price_min", "price_max", "giá"), ("area_min", "area_max", "diện tích"))
    for low_field, high_field, label in pairs:
        low, high = getattr(constraints, low_field), getattr(constraints, high_field)
        if low is not None and high is not None and low > high:
            problems.append(f"{label} tối thiểu lớn hơn {label} tối đa")
    low, high = POI_DISTANCE_RANGE
    problems += [f"khoảng cách {poi.max_distance_m} m phải trong {low}-{high} m"
                 for poi in constraints.near_pois + constraints.near_places
                 if not low <= poi.max_distance_m <= high]
    return problems


def _context(state: ConversationState, areas: list[str]) -> dict:
    """Ngữ cảnh cho TurnInterpreter: khu vực dạng tên (LLM không thấy ID)."""
    constraints = state.constraints.model_dump(exclude={"district_ids", "new_ward_ids"})
    constraints["areas"] = areas
    return {
        "current_constraints": constraints,
        "last_results": [
            {"position": i, "listing_id": listing_id}
            for i, listing_id in enumerate(state.last_results, start=1)
        ],
        "pending_question": state.pending_question,
        "history": state.history,
    }


def _result(state: ConversationState, status: str, answer: str, **fields) -> ChatTurnResult:
    """Kết quả một lượt, mang điều kiện của state SAU lượt này."""
    return ChatTurnResult(
        conversation_id=state.conversation_id, status=status,
        constraints=state.constraints, answer=answer, **fields,
    )


class RecommendationService:
    """Một lượt: đọc state -> hiểu câu -> chọn nhánh -> tìm/trả lời -> lưu state."""

    def __init__(
        self, store: ConversationStore | None = None,
        interpreter: TurnInterpreter | None = None,
        embedding_client: EmbeddingClient | None = None, engine: AsyncEngine | None = None,
        rerank_enabled: bool | None = None, valuer: ListingValuer | None = None,
        places: PlaceResolver | None = None,
    ):
        settings = get_settings()
        self.interpreter = interpreter or TurnInterpreter(
            openai_client(settings), settings.openai_model
        )
        self.store = store or ConversationStore()
        self.valuer = valuer  # None: chưa có mô hình định giá, intent appraise báo chưa bật
        self.places = places or PlaceResolver(settings.goong_api_key)  # key Goong của Geocoder
        self.embedding_client = embedding_client or EmbeddingClient(settings)
        # Tự dựng engine thì không giữ pool: người gọi (script, harness) có thể chạy mỗi lượt
        # bằng một asyncio.run riêng, kết nối pool gắn với event loop cũ sẽ hỏng.
        self.engine = engine or create_async_engine(settings.database_url, poolclass=NullPool)
        self.rerank_enabled = (
            settings.rerank_enabled if rerank_enabled is None else rerank_enabled
        )

    async def chat(
        self, conversation_id: str | None, message: str, as_of: date | None = None
    ) -> ChatTurnResult:
        """Xử lý một tin nhắn; `as_of` là "hôm nay" (mặc định theo giờ Việt Nam)."""
        state = self.store.get(conversation_id or uuid.uuid4().hex)
        as_of = as_of or datetime.now(VIETNAM_TZ).date()
        prefix = ""
        if len(message) > MAX_MESSAGE_CHARS:  # không gửi nguyên văn câu quá dài vào LLM
            message = message[:MAX_MESSAGE_CHARS]
            prefix = f"(Tin nhắn dài hơn {MAX_MESSAGE_CHARS} ký tự nên mình chỉ đọc phần đầu.) "

        async with AsyncSession(self.engine) as session:
            search = HybridSearch(session, self.embedding_client, self.rerank_enabled)
            result = await self._route(state, message, as_of, search)

        if result.status in ("ok", "no_results"):
            state.last_status = result.status
        result.summary = prefix + (result.summary or result.answer)
        result.answer = prefix + result.answer
        state.history = (state.history + [
            {"role": "user", "content": message},
            {"role": "assistant", "content": result.answer},
        ])[-HISTORY_MESSAGES:]
        self.store.save(state)
        return result

    async def _route(
        self, state: ConversationState, message: str, as_of: date, search: HybridSearch
    ) -> ChatTurnResult:
        """Hiểu câu (hoặc xử lý câu xác nhận ngân sách) rồi chọn nhánh trả lời."""
        areas = await search.area_names(state.constraints)
        rules = MessageRules(message)  # LLM chỉ đề xuất; quy tắc tất định có quyền bác
        pending_places, state.pending_places = state.pending_places, []  # câu khác: bỏ chờ
        picked = self.places.choose(state.constraints, pending_places, message,
                                    rules.confirmation() == "yes")  # chọn bằng code, khỏi gọi LLM
        if picked == "retry":  # chưa hiểu chọn ai: hỏi lại, giữ danh sách
            state.pending_places = pending_places
            question, chips = self.places.ask("", pending_places, True, retry=True)
            return _result(state, "need_clarification", question, suggestions=chips)
        if picked:
            empty = Correction(TurnPlan(intent="refine", set_fields=ConstraintDelta()), [], None)
            return await self._search_turn(state, empty, rules, areas, as_of, search)
        pending, state.pending_value = state.pending_value, None  # câu khác: bỏ giá trị chờ
        confirmed = rules.confirmation() if pending is not None else None
        if confirmed:
            state.pending_question = None
        if confirmed == "yes":  # B4: "ừ" áp giá đang chờ xác nhận, không cần gọi LLM
            fixed = Correction(TurnPlan(
                intent="refine", set_fields=ConstraintDelta(price_max=pending)), [], None)
        else:
            fixed = None if confirmed else await self._interpret(
                state, message, rules, areas, search)
        if fixed is None:
            return _result(state, "answered", KEEP_BUDGET_ANSWER)
        if fixed.plan.intent == "out_of_scope":  # giữ nguyên điều kiện và kết quả cũ
            return _result(state, "out_of_scope", OUT_OF_SCOPE_ANSWER)
        if fixed.plan.intent in ("chitchat", "other_mode"):  # giữ nguyên điều kiện và kết quả cũ
            return _result(state, "answered", assistant_reply(
                fixed.plan.intent, "recommendation", bool(state.last_results)))
        if fixed.plan.intent in ("ask_detail", "compare", "appraise"):
            return await self._answer_about_results(
                state, rules, message, search, fixed.plan.intent)
        return await self._search_turn(state, fixed, rules, areas, as_of, search)

    async def _interpret(
        self, state: ConversationState, message: str, rules: MessageRules, areas: list[str],
        search: HybridSearch,
    ) -> Correction:
        """TurnPlan do LLM đề xuất rồi qua quy tắc tất định của câu."""
        plan = await self.interpreter.interpret(message, _context(state, areas))
        return rules.correct(plan, state.constraints, areas, *await search.known_areas())

    async def _search_turn(
        self, state: ConversationState, fixed: Correction, rules: MessageRules,
        old_areas: list[str], as_of: date, search: HybridSearch,
    ) -> ChatTurnResult:
        """search/refine/relax/answer_clarification/reset: merge -> kiểm tra -> tìm."""
        plan, note = fixed.plan, ""
        if plan.intent == "reset":  # spec 9.1, #21: xóa ngay, kể cả khi điều kiện mới bị hỏi lại
            state.constraints, state.last_results, old_areas = SearchConstraints(), [], []
            note = RESET_NOTE
        old, delta = state.constraints, plan.set_fields
        found = await self.places.resolve_all(search.session, delta.near_places, rules.text,
                                              delta.district_names or old_areas, old.near_places)
        merged = await self._merge_or_ask(state, fixed, rules, note, search, found)
        if isinstance(merged, ChatTurnResult):
            return merged
        if found.question:  # trùng tên / điểm Goong: điều kiện khác đã áp, hỏi rồi mới tìm
            state.constraints, state.pending_places = merged, found.pending
            result = self._clarify(state, "place", note + found.question)
            return result.model_copy(update={"suggestions": found.suggestions})

        state.constraints, state.pending_question = merged, None
        new_areas = await search.area_names(merged)
        changes = [note.strip()] if note else describe_changes(  # sau reset không so với state cũ
            old, merged, old_areas, new_areas, cheaper=delta.cheaper,
        )
        changes += found.notes
        if fixed.ignored:  # spec 9 #32d: nói rõ điều kiện chưa hiểu, không bỏ im
            unknown = ", ".join(fixed.ignored)
            changes.append(f"Mình chưa hiểu rõ điều kiện {unknown} nên chưa áp dụng.")
        hits, degraded = await search.search(merged, as_of)
        if hits:
            state.last_results = [hit.listing_id for hit in hits]
            # Ít hơn TOP_K tin: tìm thêm phương án nới để gợi ý (spec 9 #27d)
            relax = await search.relax_options(merged, as_of) if len(hits) < TOP_K else []
            args = (hits, merged, new_areas, changes, degraded, relax)
            return _result(state, "ok", results_answer(*args), listings=hits,
                           degraded=degraded, summary=results_answer(*args, with_listings=False))

        state.last_results = []
        relax_options = await search.relax_options(merged, as_of)
        answer = no_results_answer(
            relax_options, changes, describe_constraints(merged, new_areas)
        )
        return _result(state, "no_results", answer, relax_options=relax_options,
                       degraded=degraded)

    async def _merge_or_ask(
        self, state: ConversationState, fixed: Correction, rules: MessageRules, note: str,
        search: HybridSearch, found: PlaceOutcome,
    ) -> SearchConstraints | ChatTurnResult:
        """Điều kiện sau merge, hoặc câu hỏi lại khi thiếu/sai/mâu thuẫn (không áp delta)."""
        plan = fixed.plan
        old, delta = state.constraints, plan.set_fields
        district_ids, ward_ids, unknown = await search.resolve_areas(
            delta.district_names, delta.new_ward_names
        )
        if unknown:
            return self._clarify(state, "area", note + (
                f"Mình không tìm thấy khu vực {', '.join(unknown)} ở TP.HCM. Bạn kiểm tra lại "
                "tên quận/huyện (hoặc phường mới) giúp mình nhé."))
        if delta.cheaper and old.price_max is None and delta.price_max is None:
            return self._clarify(state, "price_max", note
                                 + "Bạn cho mình biết ngân sách tối đa để mình giảm bớt nhé.")
        if not delta.price_approx and rules.reverses_budget(delta.price_max, old.price_max):
            state.pending_value = delta.price_max
            return self._clarify(state, "confirm_budget", note
                                 + ask_confirm_budget(delta.price_max, old.price_max))

        merged = merge_constraints(old, plan, district_ids, ward_ids)
        merged.near_places = PlaceResolver.merge(merged.near_places, found.places)
        merged.soft_query = ", ".join([*phrases(merged.soft_query), *found.soft_names]) or None
        if problems := validate_constraints(merged):  # spec 9.3: không áp delta
            if fixed.typed_price and any("giá" in p and "ngoài khoảng" in p for p in problems):
                low, high = (format_price(limit) for limit in PRICE_RANGE)
                typed = format_price(fixed.typed_price)
                problems = [f"mức giá {typed} nằm ngoài khoảng {low}-{high}",
                            *(p for p in problems if "giá" not in p)]  # báo số khách gõ ("3tr8")
            return self._clarify(state, "fix_constraints", note + (
                f"Mình chưa dùng được điều kiện này: {'; '.join(problems)}. "
                "Bạn nói lại giúp mình nhé."))
        if (merged.price_min is None and merged.price_max is None and not merged.district_ids
                and not merged.new_ward_ids and not merged.near_places and not found.pending):
            state.constraints = merged  # điều kiện một phần vẫn giữ cho lượt sau
            known = ", ".join(merged.property_types)
            repeated = state.pending_question == "budget_or_area"
            return self._clarify(state, "budget_or_area",
                                 ask_budget_or_area(note, repeated, known))
        return merged

    async def _answer_about_results(
        self, state: ConversationState, rules: MessageRules, message: str,
        search: HybridSearch, intent: str,
    ) -> ChatTurnResult:
        """ask_detail/compare/appraise: chỉ dùng tin trong last_results; tham chiếu sai thì báo."""
        total = len(state.last_results)
        if intent == "appraise" and (total == 0 or self.valuer is None):
            return _result(state, "answered", NO_LISTINGS if total == 0 else NO_VALUER)
        ids, missing = rules.references(state.last_results)
        not_found = refs_not_found(missing, total, state.last_status == "no_results")
        if not ids:
            return _result(state, "answered", not_found)
        if (intent == "ask_detail" and total > 1 and not rules.names_listing(total)
                and is_vague_question(message)):  # không chỉ căn nào, cũng không hỏi cả danh sách
            return _result(state, "answered", ask_which_listing(total))
        notes = [not_found] if missing else []
        details = await search.fetch_details(ids)
        for row in details:  # "Căn N" trong câu trả lời khớp đúng thứ tự đã gợi ý
            row["position"] = state.last_results.index(row["listing_id"]) + 1
        if intent == "appraise":  # so giá rao với ước tính của mô hình, không qua grounding
            answer = self.valuer.answer(await self.valuer.appraise(details), notes)
            return _result(state, "answered", answer, referenced_ids=ids)
        answer, winners = details_answer(details, message, notes)
        return _result(state, "answered", answer, referenced_ids=winners or ids)

    def _clarify(self, state: ConversationState, pending: str, answer: str) -> ChatTurnResult:
        """Hỏi lại người dùng; pending_question cho TurnInterpreter biết câu sau là trả lời."""
        state.pending_question = pending
        return _result(state, "need_clarification", answer)
