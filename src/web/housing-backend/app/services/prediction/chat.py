"""PredictionChat: hội thoại nhiều lượt định giá BĐS (docs/tasks/prediction-mode.md).

LLM chỉ trích xuất trường và gán intent (FieldExtractor). Việc kiểm chứng trường và intent có
trong tin nhắn, kiểm tra biên, chọn câu hỏi, quyết định khi nào dự đoán và viết câu trả lời đều
do code; câu trả lời chỉ dùng số của PricePredictor nên không bịa lý do.
"""

import logging
from collections import OrderedDict
from uuid import uuid4

from app.services import assistant_text as texts  # câu cố định dùng chung
from app.services.prediction.constants import (
    APARTMENT,
    BOUNDS,
    DISTRICT_NAMES,
    FIELD_LABELS,
    LAND,
    OPTIONAL_FIELDS,
    OPTIONALS_BY_TYPE,
    PROPERTY_PHRASES,
    PROPERTY_TYPES,
)
from app.services.prediction.extractor import FieldExtractor
from app.services.prediction.facts import PredictionFacts
from app.services.prediction.geocoder import Geocoder
from app.services.prediction.predictor import (
    TREE_PERCENTILES,
    PriceEstimate,
    PriceInput,
    PricePredictor,
)
from app.services.prediction.schemas import (
    Extraction,
    PredictionState,
    PredictionTurn,
    TurnStatus,
)
from app.services.prediction.text import MessageRules, plain

logger = logging.getLogger(__name__)

MAX_CONVERSATIONS = 1000     # quá số này thì bỏ hội thoại lâu không dùng nhất
MAX_MESSAGE_CHARS = 1000
KEEP_HEAD, KEEP_TAIL = 600, 395  # tin quá dài: giữ đầu và đuôi (địa chỉ/số hay ở hai đầu)
APARTMENT_MAX_AREA = 300     # căn hộ rộng hơn mức này là bất thường, phải xác nhận
PROPERTY_NAMES = {code: name for name, code in PROPERTY_TYPES.items()}
REQUIRED = ["property_type", "district", "area"]
SUMMARY_FORMATS = {"area": "{:g} m²", "frontage": "mặt tiền {:g} m", "bedrooms": "{} phòng ngủ",
                   "floors": "{} tầng"}
# Số trong biên nhưng bất thường: (trường liên quan, điều kiện trên state, lý do) → hỏi xác nhận
UNUSUAL = (
    (("area",), lambda s: s.property_code == APARTMENT and (s.area or 0) > APARTMENT_MAX_AREA,
     f"căn hộ trên {APARTMENT_MAX_AREA} m² rất hiếm"),
    (("floors",), lambda s: s.property_code == APARTMENT and s.floors is not None,
     "căn hộ thường không ghi số tầng"),
    (("floors", "bedrooms"),
     lambda s: s.property_code == LAND and (s.floors is not None or s.bedrooms is not None),
     "đất không có số tầng hay phòng ngủ"),
    (("frontage", "area"), lambda s: (s.frontage or 0) > (s.area or float("inf")),
     "mặt tiền lớn hơn diện tích"),
    (("bedrooms", "area"), lambda s: (s.bedrooms or 0) > (s.area or float("inf")) / 10,
     "quá nhiều phòng ngủ so với diện tích"),
)

QUESTIONS = {
    "property_type": "Bạn muốn định giá loại nhà đất nào: căn hộ chung cư, nhà riêng, "
                     "nhà biệt thự/liền kề, nhà mặt phố hay đất?",
    "district": "Bất động sản nằm ở quận/huyện nào của TP.HCM? (có thể kèm tên đường, "
                "vd. \"Nguyễn Trãi, Quận 5\")",
    "area": "Diện tích bao nhiêu m² (từ 10 đến 2.000 m², vd. 60 hoặc 4x15)?",
}
OUT_OF_SCOPE_ANSWER = "Mình chỉ hỗ trợ định giá nhà đất để bán ở 24 quận/huyện cũ của TP.HCM. "
OUT_OF_SCOPE_FOLLOW_UP = "Bạn có thể sửa thông tin hoặc gõ ok để dự đoán."
RESET_ANSWER = "Đã xoá thông tin cũ, mình bắt đầu một bất động sản mới. "
NOT_ENOUGH = "Mình chưa dự đoán được vì còn thiếu thông tin bắt buộc. "
NO_LOCATION = "Mình chưa xác định được vị trí. Bạn cho mình tên đường hoặc quận/huyện rõ hơn nhé?"
WHAT_IF_FOOTER = ("Đây chỉ là giả định, mình chưa lưu thay đổi. Muốn áp dụng thay đổi này, bạn nói "
                  "\"đổi …\" (vd. \"đổi diện tích 100m2\").")
FOOTER = ("Đây là ước tính tham khảo từ mô hình học máy trên tin đăng batdongsan, không phải giá "
          "giao dịch thực tế.\nBạn có thể sửa thông tin (vd. \"đổi diện tích 100m2\") để dự đoán "
          "lại, hoặc gõ reset để định giá BĐS khác.")


class PredictionChat:
    """State hội thoại giữ trong bộ nhớ, có giới hạn số hội thoại (LRU)."""

    def __init__(self, extractor: FieldExtractor, predictor: PricePredictor, geocoder: Geocoder):
        self.extractor = extractor
        self.predictor = predictor
        self.geocoder = geocoder
        self.facts = PredictionFacts(predictor)
        self._states: OrderedDict[str, PredictionState] = OrderedDict()

    def reset(self, conversation_id: str) -> None:
        self._states.pop(conversation_id, None)

    async def turn(self, conversation_id: str | None, message: str) -> PredictionTurn:
        """Một lượt: trích xuất → kiểm chứng intent/trường → trả lời ngoài luồng hoặc cập nhật
        state rồi hỏi / chờ ok / dự đoán. `conversation_id` None thì tạo hội thoại mới.

        Raises:
            openai.OpenAIError: gọi LLM lỗi.
        """
        state = self._load(conversation_id)
        old, command = state.model_copy(deep=True), MessageRules.command(message)
        pending, state.pending_values = state.pending_values, {}  # câu khác thì bỏ chờ xác nhận
        if command == "reset":
            return self._reply(self._fresh(state), "collecting",
                               RESET_ANSWER + QUESTIONS["property_type"])
        if pending and command == "agree":  # chỉ "đúng/ừ" mới ghi số bất thường ("ok" thì bỏ)
            for key, value in pending.items():
                setattr(state, key, value)
            return await self._respond(state, "", [], False, old)
        lead, problems, done = "", [], command in ("confirm", "agree")
        if command is None:  # lệnh thuần ("ok", "bỏ qua") không cần gọi LLM
            extraction = await self.extractor.extract(
                self._clip(message), state.asking, self._fields(state)
            )
            if (extraction.wants_reset or extraction.intent == "reset") and (
                    MessageRules.asks_reset(message)):
                state, lead = self._fresh(state), RESET_ANSWER
                old = state.model_copy(deep=True)
            if self._out_of_scope(state, extraction, message):
                return self._refuse(state)
            trial = state.model_copy(deep=True)  # thử ghi trường; intent ngoài luồng thì bỏ bản này
            problems = self._apply(trial, extraction, message)
            lead += self._derive_area(trial, message)
            if reply := await self._side_turn(state, trial, extraction, message, problems):
                return reply
            state = trial
            self._flag_unusual(state, old)
            done = (extraction.wants_confirm or extraction.intent == "confirm") and (
                MessageRules.confirms(message))
        return await self._respond(state, lead, problems, done, old)

    async def _respond(self, state: PredictionState, lead: str, problems: list[str], done: bool,
                       old: PredictionState) -> PredictionTurn:
        """Chọn nhánh sau khi state đã cập nhật. old = state trước lượt này."""
        changed = self._fields(old) != self._fields(state)
        if changed or problems:
            state.prediction = None  # số liệu đổi thì kết quả cũ hết giá trị
        lead += "".join(f"{problem} " for problem in problems)
        if state.pending_values:  # có số bất thường: hỏi xác nhận trước khi hỏi/dự đoán tiếp
            return self._reply(state, None, lead + state.pending_check)
        missing = self._missing(state)
        if missing:
            state.asking = missing[0]
            return self._reply(state, "collecting",
                               lead + (NOT_ENOUGH if done else "") + QUESTIONS[missing[0]])
        if done or (old.prediction and changed and not problems):  # sửa thông tin: dự đoán lại
            compare = (self._fields(old), old.prediction) if old.prediction and changed else None
            return await self._predict(state, lead, compare)
        if state.prediction is not None:  # không có gì đổi: nhắc lại kết quả và các yếu tố đã dùng
            return self._reply(state, "predicted", lead + self._explain(state, state.prediction))
        return self._reply(state, "ready", lead + self._ready_prompt(state))

    async def _side_turn(
        self, state: PredictionState, trial: PredictionState, extraction: Extraction,
        message: str, problems: list[str],
    ) -> PredictionTurn | None:
        """Intent không ghi state (câu hỏi, giả định, chào, chuyển chế độ) sau khi code kiểm chứng.

        None nghĩa là coi như provide_info: có trường mới thì ghi trường trước."""
        intent = extraction.intent
        changed = bool(problems) or self._fields(trial) != self._fields(state)
        if intent == "other_mode" and MessageRules.asks_other_mode(message):  # không xét trường mới
            return self._reply(state, None, texts.assistant_reply("other_mode", "prediction"))
        if intent == "what_if":
            if self._missing(state) or not (changed and MessageRules.hypothetical(message)):
                return None
            unknown = [k for k in BOUNDS if getattr(state, k) is None and getattr(trial, k)]
            if not (unknown and MessageRules.relative(message)):
                return await self._what_if(state, trial, problems)
            state.asking = unknown[0]  # "thêm 1 tầng" khi chưa biết số tầng: hỏi, không tính từ 0
            return self._reply(state, None, texts.RELATIVE_UNKNOWN.format(FIELD_LABELS[unknown[0]]))
        found = MessageRules.districts(message)  # chỉ quận có thật trong tin nhắn
        compare = extraction.question_topic == "compare_district" or len(found) > 1
        if intent == "question" and compare:  # nêu nhiều quận là so sánh, không đổi quận
            named = {PricePredictor.find_district(name) for name in extraction.compare_districts}
            answer = self.facts.answer("compare_district", state,
                                       [code for code in found if code in named] or found)
        elif changed:
            return None
        elif intent == "question":
            answer = self.facts.answer(extraction.question_topic or "other", state, [])
        elif intent == "chitchat":
            answer = texts.assistant_reply("chitchat", "prediction", state.prediction is not None)
        else:
            return None
        return self._reply(state, None, answer + self._follow_up(state))

    async def _what_if(self, state: PredictionState, trial: PredictionState,
                       problems: list[str]) -> PredictionTurn:
        """Dự đoán trên bản sao state với trường giả định; state thật không đổi."""
        if problems:
            return self._reply(state, None, " ".join(problems))
        before = state.prediction or await self._estimate(state)
        after = await self._estimate(trial)
        if before is None or after is None:
            return self._reply(state, None, NO_LOCATION)
        note = self._change_note(trial, after, self._fields(state), before, "Nếu bạn đổi")
        return self._reply(state, None, note + WHAT_IF_FOOTER)

    def _follow_up(self, state: PredictionState) -> str:
        """Sau câu trả lời ngoài luồng: quay lại hỏi trường bắt buộc còn thiếu hoặc mời gõ ok."""
        missing = self._missing(state)
        if missing:
            state.asking = missing[0]
            return "\n\n" + QUESTIONS[missing[0]]
        return "" if state.prediction else "\n\nKhi sẵn sàng, bạn gõ ok để mình dự đoán nhé."

    @staticmethod
    def _flag_unusual(state: PredictionState, old: PredictionState) -> None:
        """Số trong biên nhưng bất thường: chưa ghi (giữ giá trị cũ), chờ người dùng xác nhận."""
        reasons, held = [], {}
        for fields, is_unusual, reason in UNUSUAL:
            changed = [key for key in fields if getattr(state, key) != getattr(old, key)]
            if changed and is_unusual(state):
                reasons.append(reason)
                held |= {key: getattr(state, key) for key in changed}
        for key in held:
            setattr(state, key, getattr(old, key))
        if held:
            state.pending_values = held
            state.pending_check = (f"Số liệu này hơi bất thường ({'; '.join(reasons)}). Bạn xác "
                                   "nhận đúng không? Gõ \"đúng\" để ghi nhận, hoặc nhập lại.")

    def _out_of_scope(self, state: PredictionState, extraction: Extraction, message: str) -> bool:
        """LLM hay từ chối nhầm câu ngắn ("bình thạnh", "đất"), nên code có quyền bác bỏ.

        Tỉnh khác do code quyết (other_province); tỉnh lạ chưa có trong danh sách chỉ làm
        thiếu quận nên vẫn bị hỏi lại, không dự đoán."""
        if MessageRules.other_province(message) or MessageRules.out_of_domain(message):
            return True
        refused = extraction.refusal != "none" or extraction.intent == "off_topic"
        if not refused or extraction.intent in ("chitchat", "other_mode"):
            return False  # chào hỏi/tìm mua do _side_turn kiểm chứng tiếp
        numbers = (extraction.area_m2, extraction.floors, extraction.bedrooms,
                   extraction.frontage_m)
        answers_question = state.asking is not None and any(
            v is not None and MessageRules.number_status(v, message, False) == "ok"
            for v in numbers
        )
        has_district = bool(MessageRules.districts(message))
        return not (has_district or MessageRules.mentions_property(message) or answers_question)

    def _refuse(self, state: PredictionState) -> PredictionTurn:
        """Từ chối ngắn, chỉ hỏi tiếp trường còn thiếu (không hỏi lại trường đã có)."""
        missing = self._missing(state)
        follow_up = QUESTIONS[missing[0]] if missing else OUT_OF_SCOPE_FOLLOW_UP
        return self._reply(state, "out_of_scope", OUT_OF_SCOPE_ANSWER + follow_up)

    def _apply(self, state: PredictionState, extraction: Extraction, message: str) -> list[str]:
        """Ghi vào state trường LLM trích mà tin nhắn thật sự chứa; trả câu báo số ngoài biên."""
        found, kind = MessageRules.property_types(message), extraction.property_type
        if kind and (kind in found or state.asking == "property_type"):
            state.property_code = PROPERTY_TYPES[kind]
        elif len(found) == 1 and state.property_code is None:  # LLM bỏ sót, tin chỉ nhắc một loại
            state.property_code = PROPERTY_TYPES[found[0]]
        self._apply_location(state, extraction, message)
        return self._apply_numbers(state, extraction, message)

    @staticmethod
    def _apply_numbers(state: PredictionState, extraction: Extraction, message: str) -> list[str]:
        """Ghi số hợp lệ vào state; số ngoài biên bị xoá kèm câu báo, không dự đoán trên số sai."""
        numbers = {"area": extraction.area_m2, "floors": extraction.floors,
                   "bedrooms": extraction.bedrooms, "frontage": extraction.frontage_m}
        problems, hypothetical = [], MessageRules.hypothetical(message)
        for key, value in numbers.items():
            if value is None:
                continue
            base = getattr(state, key) if hypothetical else None
            status = MessageRules.number_status(value, message, state.asking == key, base)
            low, high, label, unit = BOUNDS[key]
            if status == "absent":  # số LLM trích không có trong tin nhắn: bỏ qua
                continue
            if status == "ok" and low <= value <= high:
                setattr(state, key, value)
                continue
            setattr(state, key, None)  # không giữ số cũ để khỏi dự đoán trên số vừa bị sửa sai
            span = f"{low:,}–{high:,}".replace(",", ".")
            shown = -value if status == "negative" else value
            problems.append(f"{label} {shown:g} {unit} nằm ngoài khoảng {span} {unit} "
                            "nên mình chưa dùng, bạn nhập lại giúp.")
        return problems

    @staticmethod
    def _derive_area(state: PredictionState, message: str) -> str:
        """LLM bỏ trống diện tích thì dựng từ tin nhắn ("300m2", "5x20", "tám mươi mét vuông")."""
        found = MessageRules.area_from_text(message)
        if state.area is not None or found is None:
            return ""
        (area, from_size), (low, high) = found, BOUNDS["area"][:2]
        if not low <= area <= high:
            return ""
        state.area = area
        return f"Mình hiểu diện tích đất là {area:g} m² (ngang x dài). " if from_size else ""

    def _apply_location(self, state: PredictionState, extraction: Extraction, message: str):
        """Quận phải có trong tin nhắn; đổi quận thì bỏ địa chỉ cũ; địa chỉ phải chép từ tin."""
        codes = MessageRules.districts(message)
        named = PricePredictor.find_district(extraction.district_name or "")
        code = named if named in codes else (codes[0] if codes else None)
        address, old_address = extraction.address_text, state.address_text
        if address and plain(address) not in plain(message):
            address = None
        address = MessageRules.clean_address(address) if address else None  # None: giữ địa chỉ cũ
        if code is not None and code != state.district_code:
            state.district_code, state.address_text = code, None
            if address and plain(address) == plain(old_address or ""):
                address = None
        if address:
            state.address_text = address
        if state.address_text is None and state.district_code is not None:
            state.address_text = DISTRICT_NAMES[state.district_code]

    async def _estimate(self, state: PredictionState) -> PriceEstimate | None:
        """Geocode (cache theo địa chỉ + quận) rồi gọi model; None nếu không có toạ độ dùng được."""
        key = (state.address_text, state.district_code)
        if state.located_for != key or state.location is None:
            state.location = await self.geocoder.locate(
                state.address_text, state.district_code, PROPERTY_PHRASES[state.property_code]
            )
            state.located_for = key
        if state.location is None:
            return None
        try:
            return self.predictor.predict(PriceInput(
                property_code=state.property_code, district_code=state.district_code,
                area=state.area, latitude=state.location.latitude,
                longitude=state.location.longitude, frontage=state.frontage,
                bedrooms=state.bedrooms, floors=state.floors,
            ))
        except ValueError:  # trường đã qua kiểm tra biên nên chỉ còn toạ độ có thể sai
            logger.exception("Toạ độ không dùng được cho dự đoán")
            return None

    async def _predict(
        self, state: PredictionState, lead: str, compare: tuple[dict, PriceEstimate] | None
    ) -> PredictionTurn:
        """Dự đoán và ghi vào state; compare = (trường, kết quả) cũ để hiện "trước → sau"."""
        estimate = await self._estimate(state)
        if estimate is None:
            state.location, state.asking = None, "district"
            return self._reply(state, "collecting", lead + NO_LOCATION)
        state.prediction, state.asking = estimate, None
        note = self._change_note(state, estimate, *compare) if compare else ""
        return self._reply(state, "predicted", lead + note + self._explain(state, estimate))

    def _change_note(
        self, state: PredictionState, estimate: PriceEstimate, fields_before: dict,
        previous: PriceEstimate, verb: str = "Bạn vừa đổi",
    ) -> str:
        """Hiển thị "trước → sau" cho các trường vừa sửa (hoặc giả định) và cho giá."""
        after = self._fields(state)
        changes = [
            f"{label} {self._show(fields_before[key])} → {self._show(after[key])}"
            for key, label in FIELD_LABELS.items()
            if fields_before[key] != after[key]
            and not (key == "address" and fields_before["district"] != after["district"])
        ]
        return (f"{verb} {', '.join(changes)}. "
                f"Giá/m² trước → sau: {previous.price_per_m2:.2f} → {estimate.price_per_m2:.2f} "
                f"triệu; tổng giá: {previous.total_price:.1f} → {estimate.total_price:.1f} "
                "triệu VND.\n")

    def _explain(self, state: PredictionState, estimate: PriceEstimate) -> str:
        """Câu trả lời chỉ chứa số của mô hình và dữ liệu đầu vào, không có lý do suy diễn thêm."""
        phrase, area = PROPERTY_PHRASES[state.property_code], state.area
        low_pct, high_pct = TREE_PERCENTILES
        lines = [
            f"Ước tính cho {phrase} {area:g} m² tại {DISTRICT_NAMES[state.district_code]}:",
            f"- Giá/m²: {estimate.price_per_m2:.2f} triệu VND/m²",
            (f"- Tổng giá: {estimate.total_price:.1f} triệu VND "
             f"(khoảng {estimate.total_price / 1000:.2f} tỷ)"),
            (f"- Khoảng tham khảo, không phải khoảng tin cậy (phân vị {low_pct}–{high_pct} "
             "của các cây trong mô hình): "
             f"{estimate.price_per_m2_low:.2f}–{estimate.price_per_m2_high:.2f} triệu/m², "
             f"tức {estimate.price_per_m2_low * area:.1f}–"
             f"{estimate.price_per_m2_high * area:.1f} triệu VND"),
        ]
        return "\n".join(lines + self.facts.details(state, estimate) + [FOOTER])

    def _ready_prompt(self, state: PredictionState) -> str:
        """Hỏi lần lượt trường tuỳ chọn quan trọng nhất chưa có và chưa hỏi; hết thì mời gõ ok."""
        asks = state.missing_optionals()
        if state.district_only():
            asks.append("address")
        key = next((key for key in asks if key not in state.skipped), None)
        state.asking = key
        if key is None:
            return texts.READY_PROMPT
        state.skipped.append(key)  # mỗi trường chỉ hỏi một lần; "bỏ qua" tức là sang trường kế
        return texts.OPTIONAL_QUESTIONS[key] + texts.OPTIONAL_HINT

    def _fields(self, state: PredictionState) -> dict:
        """Trường để hiển thị/so sánh; bỏ trường mô hình không dùng cho loại nhà này."""
        used = OPTIONALS_BY_TYPE.get(state.property_code, OPTIONAL_FIELDS)
        code = state.district_code
        fields = {
            "property_type": PROPERTY_NAMES.get(state.property_code),
            "district": None if code is None else DISTRICT_NAMES[code],
            "address": state.address_text, "area": state.area,
        }
        return fields | {key: getattr(state, key) if key in used else None
                         for key in OPTIONAL_FIELDS}

    def _missing(self, state: PredictionState) -> list[str]:
        fields = self._fields(state)
        return [key for key in REQUIRED if fields[key] is None]

    @staticmethod
    def _show(value) -> str:
        if value is None:
            return "chưa có"
        return f"{value:g}" if isinstance(value, float) else str(value)

    @staticmethod
    def _clip(message: str) -> str:
        """Tin quá dài: giữ cả đầu và đuôi thay vì cắt âm thầm phần đầu."""
        if len(message) <= MAX_MESSAGE_CHARS:
            return message
        return f"{message[:KEEP_HEAD]} … {message[-KEEP_TAIL:]}"

    def _load(self, conversation_id: str | None) -> PredictionState:
        state = self._states.get(conversation_id) if conversation_id else None
        if state:
            return state.model_copy(deep=True)
        return PredictionState(conversation_id=conversation_id or uuid4().hex)

    @staticmethod
    def _fresh(state: PredictionState) -> PredictionState:
        return PredictionState(conversation_id=state.conversation_id)

    def _remember(self, state: PredictionState) -> None:
        """Lưu state; vượt MAX_CONVERSATIONS thì bỏ hội thoại lâu không dùng nhất."""
        self._states[state.conversation_id] = state
        self._states.move_to_end(state.conversation_id)
        while len(self._states) > MAX_CONVERSATIONS:
            self._states.popitem(last=False)

    def _reply(self, state: PredictionState, status: TurnStatus | None,
               answer: str) -> PredictionTurn:
        """Lưu state rồi dựng phản hồi của lượt (tóm tắt trường đã biết, trường còn thiếu).

        status None: suy từ state (đã có dự đoán / còn thiếu bắt buộc / đủ để dự đoán)."""
        self._remember(state)
        fields, missing = self._fields(state), self._missing(state)
        status = status or ("predicted" if state.prediction else "collecting" if missing
                            else "ready")
        known = [fields["property_type"], fields["district"]] + [
            template.format(fields[key]) for key, template in SUMMARY_FORMATS.items()
            if fields[key] is not None
        ]
        return PredictionTurn(
            conversation_id=state.conversation_id, status=status, answer=answer,
            summary=" · ".join(part for part in known if part), fields=fields, missing=missing,
            prediction=state.prediction, suggestions=self._suggestions(state, missing),
        )

    @staticmethod
    def _suggestions(state: PredictionState, missing: list[str]) -> list[str]:
        """Câu trả lời nhanh theo bước đang hỏi, do code chọn (giao diện hiện thành chip)."""
        step = ("confirm" if state.pending_values else "predicted" if state.prediction
                else "property" if state.property_code is None else None)
        if step:
            return texts.SUGGESTIONS[step]
        return [] if missing else (["Bỏ qua"] if state.asking else []) + ["Dự đoán ngay"]
