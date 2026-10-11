"""PredictionChat: hội thoại nhiều lượt định giá BĐS (docs/tasks/prediction-mode.md).

LLM chỉ trích xuất trường (FieldExtractor). Việc kiểm chứng trường có trong tin nhắn, kiểm tra
biên, chọn câu hỏi, quyết định khi nào dự đoán và viết câu trả lời đều do code; câu trả lời chỉ
dùng số của PricePredictor nên không bịa lý do.
"""

import logging
from collections import OrderedDict
from uuid import uuid4

from app.services.prediction.constants import (
    DISTRICT_NAMES,
    OPTIONAL_FIELDS,
    OPTIONALS_BY_TYPE,
    PROPERTY_PHRASES,
    PROPERTY_TYPES,
)
from app.services.prediction.extractor import FieldExtractor
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
NEAR_MEDIAN_PCT = 5          # lệch dưới mức này so với median thì nói "xấp xỉ"
PROPERTY_NAMES = {code: name for name, code in PROPERTY_TYPES.items()}
# Biên hợp lệ (nhỏ nhất, lớn nhất, nhãn, đơn vị); ngoài biên thì hỏi lại, không đoán
BOUNDS = {
    "area": (10, 2000, "Diện tích", "m²"),
    "floors": (1, 20, "Số tầng", "tầng"),
    "bedrooms": (0, 20, "Số phòng ngủ", "phòng"),
    "frontage": (1, 50, "Mặt tiền", "m"),
}
REQUIRED = ["property_type", "district", "area"]
FIELD_LABELS = {"property_type": "loại nhà", "district": "quận", "address": "địa chỉ",
                "area": "diện tích", "frontage": "mặt tiền", "bedrooms": "phòng ngủ",
                "floors": "số tầng"}
SUMMARY_FORMATS = {"area": "{:g} m²", "frontage": "mặt tiền {:g} m", "bedrooms": "{} phòng ngủ",
                   "floors": "{} tầng"}

QUESTIONS = {
    "property_type": "Bạn muốn định giá loại nhà đất nào: căn hộ chung cư, nhà riêng, "
                     "nhà biệt thự/liền kề, nhà mặt phố hay đất?",
    "district": "Bất động sản nằm ở quận/huyện nào của TP.HCM? (có thể kèm tên đường, "
                "vd. \"Nguyễn Trãi, Quận 5\")",
    "area": "Diện tích bao nhiêu m² (từ 10 đến 2.000 m²)?",
}
OUT_OF_SCOPE_ANSWER = ("Mình chỉ hỗ trợ định giá nhà đất để bán ở 24 quận/huyện TP.HCM "
                       "(địa giới cũ). ")
OUT_OF_SCOPE_FOLLOW_UP = "Bạn có thể sửa thông tin hoặc gõ ok để dự đoán."
RESET_ANSWER = "Đã xoá thông tin cũ, mình bắt đầu một bất động sản mới. "
NOT_ENOUGH = "Mình chưa dự đoán được vì còn thiếu thông tin bắt buộc. "
NO_LOCATION = ("Mình chưa xác định được vị trí. Bạn cho mình tên đường hoặc quận/huyện cụ thể "
               "hơn nhé?")
FOOTER = ("Đây là ước tính tham khảo từ mô hình học máy trên tin đăng batdongsan, không phải giá "
          "giao dịch thực tế.\nBạn có thể sửa thông tin (vd. \"đổi diện tích 100m2\") để dự đoán "
          "lại, hoặc gõ reset để định giá BĐS khác.")
SOURCE_NOTES = {
    "goong": "tọa độ lấy từ địa chỉ qua Goong",
    "district_centroid": "không xác định được địa chỉ cụ thể, dùng tâm quận",
}


class PredictionChat:
    """State hội thoại giữ trong bộ nhớ, có giới hạn số hội thoại (LRU)."""

    def __init__(self, extractor: FieldExtractor, predictor: PricePredictor, geocoder: Geocoder):
        self.extractor = extractor
        self.predictor = predictor
        self.geocoder = geocoder
        self._states: OrderedDict[str, PredictionState] = OrderedDict()

    def reset(self, conversation_id: str) -> None:
        self._states.pop(conversation_id, None)

    async def turn(self, conversation_id: str | None, message: str) -> PredictionTurn:
        """Một lượt: trích xuất → kiểm chứng và cập nhật state → hỏi / chờ ok / dự đoán.

        `conversation_id` None thì tạo hội thoại mới; trả PredictionTurn với status
        collecting / ready / predicted / out_of_scope.

        Raises:
            openai.OpenAIError: gọi LLM lỗi.
        """
        state = self._load(conversation_id)
        command = MessageRules.command(message)
        if command == "reset":
            return self._reply(self._fresh(state), "collecting",
                               RESET_ANSWER + QUESTIONS["property_type"])
        lead, problems, done = "", [], command == "confirm"
        before = (self._fields(state), state.prediction)
        if not done:  # "ok" thuần không cần gọi LLM
            extraction = await self.extractor.extract(
                self._clip(message), state.asking, self._fields(state)
            )
            if extraction.wants_reset and MessageRules.asks_reset(message):
                state, lead = self._fresh(state), RESET_ANSWER
                before = (self._fields(state), None)
            if self._out_of_scope(state, extraction, message):
                return self._refuse(state)
            problems = self._apply(state, extraction, message)
            lead += self._derive_area(state, message)
            done = extraction.wants_confirm and MessageRules.confirms(message)
        return await self._respond(state, lead, problems, done, before)

    async def _respond(
        self, state: PredictionState, lead: str, problems: list[str], done: bool,
        before: tuple[dict, PriceEstimate | None],
    ) -> PredictionTurn:
        """Chọn nhánh sau khi state đã cập nhật. before = (trường, kết quả) trước lượt này."""
        fields_before, previous = before
        changed = fields_before != self._fields(state)
        if changed or problems:
            state.prediction = None  # số liệu đổi thì kết quả cũ hết giá trị
        lead += "".join(f"{problem} " for problem in problems)
        missing = self._missing(state)
        if missing:
            state.asking = missing[0]
            return self._reply(state, "collecting",
                               lead + (NOT_ENOUGH if done else "") + QUESTIONS[missing[0]])
        if done or (previous and changed and not problems):  # sửa thông tin: dự đoán lại ngay
            compare = (fields_before, previous) if previous and changed else None
            return await self._predict(state, lead, compare)
        if state.prediction is not None:  # không có gì đổi: nhắc lại kết quả và các yếu tố đã dùng
            return self._reply(state, "predicted", lead + self._explain(state, state.prediction))
        return self._reply(state, "ready", lead + self._ready_prompt(state))

    def _out_of_scope(self, state: PredictionState, extraction: Extraction, message: str) -> bool:
        """LLM hay từ chối nhầm câu ngắn ("bình thạnh", "đất"), nên code có quyền bác bỏ.

        Tỉnh khác do code quyết (other_province); tỉnh lạ chưa có trong danh sách chỉ làm
        thiếu quận nên vẫn bị hỏi lại, không dự đoán."""
        if MessageRules.other_province(message) or MessageRules.out_of_domain(message):
            return True
        if extraction.refusal == "none":
            return False
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
        problems = []
        for key, value in numbers.items():
            if value is None:
                continue
            status = MessageRules.number_status(value, message, state.asking == key)
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

    async def _predict(
        self, state: PredictionState, lead: str, compare: tuple[dict, PriceEstimate] | None
    ) -> PredictionTurn:
        """Geocode (có cache theo địa chỉ + quận) rồi gọi model; compare = (trường, kết quả) cũ."""
        key = (state.address_text, state.district_code)
        if state.located_for != key or state.location is None:
            state.location = await self.geocoder.locate(
                state.address_text, state.district_code, PROPERTY_PHRASES[state.property_code]
            )
            state.located_for = key
        estimate = None
        if state.location is not None:
            try:
                estimate = self.predictor.predict(PriceInput(
                    property_code=state.property_code, district_code=state.district_code,
                    area=state.area, latitude=state.location.latitude,
                    longitude=state.location.longitude, frontage=state.frontage,
                    bedrooms=state.bedrooms, floors=state.floors,
                ))
            except ValueError:  # trường đã qua kiểm tra biên nên chỉ còn toạ độ có thể sai
                logger.exception("Toạ độ không dùng được cho dự đoán")
        if estimate is None:
            state.location, state.asking = None, "district"
            return self._reply(state, "collecting", lead + NO_LOCATION)
        state.prediction, state.asking = estimate, None
        note = self._change_note(state, estimate, *compare) if compare else ""
        return self._reply(state, "predicted", lead + note + self._explain(state, estimate))

    def _change_note(
        self, state: PredictionState, estimate: PriceEstimate, fields_before: dict,
        previous: PriceEstimate,
    ) -> str:
        """Hiển thị "trước → sau" cho các trường vừa sửa và cho giá."""
        after = self._fields(state)
        changes = [
            f"{label} {self._show(fields_before[key])} → {self._show(after[key])}"
            for key, label in FIELD_LABELS.items()
            if fields_before[key] != after[key]
            and not (key == "address" and fields_before["district"] != after["district"])
        ]
        return (f"Bạn vừa đổi {', '.join(changes)}. "
                f"Giá/m² trước → sau: {previous.price_per_m2:.2f} → {estimate.price_per_m2:.2f} "
                f"triệu; tổng giá: {previous.total_price:.1f} → {estimate.total_price:.1f} "
                "triệu VND.\n")

    def _explain(self, state: PredictionState, estimate: PriceEstimate) -> str:
        """Câu trả lời chỉ chứa số của mô hình và dữ liệu đầu vào, không có lý do suy diễn thêm."""
        district = DISTRICT_NAMES[state.district_code]
        phrase, area = PROPERTY_PHRASES[state.property_code], state.area
        low_pct, high_pct = TREE_PERCENTILES
        lines = [
            f"Ước tính cho {phrase} {area:g} m² tại {district}:",
            f"- Giá/m²: {estimate.price_per_m2:.2f} triệu VND/m²",
            (f"- Tổng giá: {estimate.total_price:.1f} triệu VND "
             f"(khoảng {estimate.total_price / 1000:.2f} tỷ)"),
            (f"- Khoảng tham khảo, không phải khoảng tin cậy (phân vị {low_pct}–{high_pct} "
             "của các cây trong mô hình): "
             f"{estimate.price_per_m2_low:.2f}–{estimate.price_per_m2_high:.2f} triệu/m², "
             f"tức {estimate.price_per_m2_low * area:.1f}–"
             f"{estimate.price_per_m2_high * area:.1f} triệu VND"),
            (f"- Cách trung tâm (Nhà thờ Đức Bà): {estimate.distance_to_center_km:.1f} km "
             f"({SOURCE_NOTES[state.location.source]})"),
        ]
        median = estimate.district_median_per_m2
        if median:
            gap = (estimate.price_per_m2 / median - 1) * 100
            verdict = ("xấp xỉ median" if abs(gap) < NEAR_MEDIAN_PCT
                       else f"{'cao' if gap > 0 else 'thấp'} hơn median {abs(gap):.0f}%")
            scope = (f"median {phrase} tại {district}" if estimate.median_by_type
                     else f"median cả quận {district}")
            lines.append(f"- So với {scope} trong dữ liệu huấn luyện ({median:.1f} triệu/m²): "
                         f"{verdict}")
        lines += [f"- Lưu ý: {warning}" for warning in estimate.warnings]
        unknown = [FIELD_LABELS[key] for key in self._missing_optionals(state)]
        if unknown:
            lines.append(f"- Chưa có {', '.join(unknown)} nên mô hình dùng giá trị trung vị.")
        return "\n".join(lines + [FOOTER])

    def _ready_prompt(self, state: PredictionState) -> str:
        optionals = self._missing_optionals(state)
        if optionals and not state.asked_optional:
            state.asked_optional, state.asking = True, "optional"
            names = ", ".join(FIELD_LABELS[key] for key in optionals)
            return (f"Đã đủ thông tin bắt buộc. Bạn có thể thêm {names} để ước tính sát hơn, "
                    "hoặc gõ ok để dự đoán ngay.")
        state.asking = None
        return "Gõ ok để mình dự đoán giá, hoặc bổ sung thêm thông tin nếu bạn muốn."

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

    def _missing_optionals(self, state: PredictionState) -> list[str]:
        used = OPTIONALS_BY_TYPE.get(state.property_code, OPTIONAL_FIELDS)
        return [key for key in used if getattr(state, key) is None]

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

    def _reply(self, state: PredictionState, status: TurnStatus, answer: str) -> PredictionTurn:
        """Lưu state rồi dựng phản hồi của lượt (tóm tắt trường đã biết, trường còn thiếu)."""
        self._remember(state)
        fields = self._fields(state)
        known = [fields["property_type"], fields["district"]] + [
            template.format(fields[key]) for key, template in SUMMARY_FORMATS.items()
            if fields[key] is not None
        ]
        return PredictionTurn(
            conversation_id=state.conversation_id, status=status, answer=answer,
            summary=" · ".join(part for part in known if part), fields=fields,
            missing=self._missing(state), prediction=state.prediction,
        )
