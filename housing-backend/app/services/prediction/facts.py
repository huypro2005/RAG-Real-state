"""PredictionFacts: trả lời câu hỏi về kết quả và mô hình bằng số thật (chat-intelligence.md 3.2.3).

LLM chỉ gán chủ đề; số liệu lấy từ PriceEstimate, metrics.json và state, không suy diễn thêm.
"""

from app.services.assistant_text import PREDICTION_TOPICS
from app.services.prediction.constants import (
    DISTRICT_NAMES,
    FIELD_LABELS,
    PROPERTY_PHRASES,
    SOURCE_NOTES,
)
from app.services.prediction.predictor import (
    FEATURES,
    TREE_PERCENTILES,
    PriceEstimate,
    PricePredictor,
)
from app.services.prediction.schemas import PredictionState, QuestionTopic

NEAR_MEDIAN_PCT = 5      # lệch dưới mức này so với median thì nói "xấp xỉ"
NO_PREDICTION = "Mình chưa dự đoán nên chưa có số liệu để giải thích."


class PredictionFacts:
    """Mỗi chủ đề một phương thức; `answer` chọn phương thức theo question_topic."""

    def __init__(self, predictor: PricePredictor):
        self.predictor = predictor

    def answer(self, topic: QuestionTopic, state: PredictionState, districts: list[int]) -> str:
        """Câu trả lời cho chủ đề `topic`; `districts` là mã quận người dùng nêu để so sánh."""
        if topic in ("why_price", "range") and state.prediction is None:
            return NO_PREDICTION  # chưa có dự đoán thì chưa có số để giải thích
        if topic == "why_price":
            return self.why_price(state)
        if topic == "range":
            return self.price_range(state)
        if topic == "model":
            return self.model_info()
        if topic == "compare_district":
            return self.compare_districts(state, districts)
        if topic == "accuracy_tips":
            return self.accuracy_tips(state)
        return PREDICTION_TOPICS

    @staticmethod
    def details(state: PredictionState, estimate: PriceEstimate) -> list[str]:
        """Khoảng cách trung tâm, so với median, cảnh báo dữ liệu thưa, trường dùng trung vị."""
        lines = [(f"- Cách trung tâm (Nhà thờ Đức Bà): {estimate.distance_to_center_km:.1f} km "
                  f"({SOURCE_NOTES[state.location.source]})")]
        median = estimate.district_median_per_m2
        if median:
            district = DISTRICT_NAMES[state.district_code]
            phrase = PROPERTY_PHRASES[state.property_code]
            gap = (estimate.price_per_m2 / median - 1) * 100
            verdict = ("xấp xỉ median" if abs(gap) < NEAR_MEDIAN_PCT
                       else f"{'cao' if gap > 0 else 'thấp'} hơn median {abs(gap):.0f}%")
            scope = (f"median {phrase} tại {district}" if estimate.median_by_type
                     else f"median cả quận {district}")
            lines.append(f"- So với {scope} trong dữ liệu huấn luyện ({median:.1f} triệu/m²): "
                         f"{verdict}")
        lines += [f"- Lưu ý: {warning}" for warning in estimate.warnings]
        unknown = [FIELD_LABELS[key] for key in state.missing_optionals()]
        if unknown:
            lines.append(f"- Chưa có {', '.join(unknown)} nên mô hình dùng giá trị trung vị.")
        return lines

    def why_price(self, state: PredictionState) -> str:
        estimate = state.prediction
        intro = (f"Mô hình cho {estimate.price_per_m2:.2f} triệu/m² từ {len(FEATURES)} đặc trưng; "
                 "nó không tách riêng phần đóng góp của từng yếu tố, các số liệu liên quan là:")
        return "\n".join([intro, *self.details(state, estimate)])

    def price_range(self, state: PredictionState) -> str:
        low_pct, high_pct = TREE_PERCENTILES
        estimate, area = state.prediction, state.area
        low, high = estimate.price_per_m2_low, estimate.price_per_m2_high
        return (f"Khoảng tham khảo {low:.2f}–{high:.2f} triệu/m² (tức {low * area:.1f}–"
                f"{high * area:.1f} triệu VND) là phân vị {low_pct}–{high_pct} của dự đoán từng "
                f"cây trong rừng ngẫu nhiên: {high_pct - low_pct}% số cây cho giá trong khoảng "
                "này. Đây không phải khoảng tin cậy thống kê; khoảng càng rộng thì các cây càng "
                "bất đồng và ước tính càng kém chắc chắn.")

    def model_info(self) -> str:
        metrics = self.predictor.metrics or {}
        score = (f" Trên {metrics['test_rows']} tin kiểm tra: R² = {metrics['r2']:.2f} (giá/m²), "
                 f"R² = {metrics['r2_log']:.2f} (log giá/m²), sai số tuyệt đối trung bình "
                 f"{metrics['mae']:.1f} triệu/m²." if metrics else "")
        return ("Mình dùng mô hình Random Forest huấn luyện trên tin đăng batdongsan.com.vn, dự "
                f"đoán log(giá/m²) rồi nhân diện tích. {len(FEATURES)} đặc trưng: "
                f"{', '.join(FEATURES)}.{score}")

    def compare_districts(self, state: PredictionState, codes: list[int]) -> str:
        """Median giá/m² của các quận được nêu (cùng loại nhà nếu đã biết và đủ mẫu)."""
        if not codes:
            return "Bạn nêu giúp mình tên các quận cần so sánh (vd. \"quận 2 và quận 7\")."
        medians, kind = self.predictor.medians, state.property_code
        rows = []  # (mã quận, median, True nếu là median riêng cho loại nhà)
        for code in codes:
            by_type = medians.get(f"{code}|{kind}")
            rows.append((code, by_type or medians.get(str(code)), by_type is not None))
        lines = []
        for code, value, typed in rows:
            scope = f"cùng loại {PROPERTY_PHRASES[kind]}" if typed else "cả quận"
            note = f"median {value:.1f} triệu/m² ({scope})" if value else "chưa có median"
            lines.append(f"- {DISTRICT_NAMES[code]}: {note}")
        known = sorted((row for row in rows if row[1]), key=lambda row: row[1], reverse=True)
        if len(known) > 1 and len({typed for *_, typed in known}) == 1:  # cùng phạm vi mới so
            (high_code, high, _), (low_code, low, _) = known[0], known[-1]
            lines.append(f"Trong dữ liệu huấn luyện, {DISTRICT_NAMES[high_code]} có median cao hơn "
                         f"{DISTRICT_NAMES[low_code]} {(high / low - 1) * 100:.0f}%.")
        return "Median giá/m² trong dữ liệu huấn luyện:\n" + "\n".join(lines)

    def accuracy_tips(self, state: PredictionState) -> str:
        if state.property_code is None:
            return "Bạn cho mình biết loại nhà đất trước, mình sẽ nói cần bổ sung gì cho chính xác."
        missing = [FIELD_LABELS[key] for key in state.missing_optionals()]
        if state.district_only():
            missing.append("tên đường/dự án (để tính khoảng cách tới trung tâm chính xác hơn)")
        if not missing:
            return "Bạn đã cung cấp đủ các thông tin mô hình dùng cho loại nhà này."
        return f"Để ước tính sát hơn, bạn có thể bổ sung: {', '.join(missing)}."
