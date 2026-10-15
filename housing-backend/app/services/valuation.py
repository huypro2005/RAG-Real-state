"""ListingValuer: so giá rao của tin với ước tính của mô hình định giá (chat-intelligence.md 3.1).

Chỉ nói "cao/thấp hơn ước tính X%" và "trong/ngoài khoảng tham khảo"; không kết luận đắt/rẻ
vì mô hình chỉ là tham khảo. Mọi số trong câu trả lời lấy từ Appraisal, không do LLM viết.
"""

from pydantic import BaseModel

from app.services.formatting import format_price
from app.services.prediction.constants import BOUNDS, DISTRICT_NAMES, PROPERTY_TYPES
from app.services.prediction.geocoder import Geocoder
from app.services.prediction.predictor import PriceEstimate, PriceInput, PricePredictor

SAME_PCT = 0.5  # lệch dưới mức này (sau khi làm tròn còn 0%) thì nói "xấp xỉ"
NO_LISTINGS = "Chưa có tin để so giá, bạn tìm trước nhé."
NO_VALUER = "Mình chưa bật mô hình định giá nên chưa so giá tin rao được."
FOOTER = "Ước tính tham khảo từ mô hình học máy trên tin đăng, không phải giá giao dịch."


class Appraisal(BaseModel):
    """Kết quả so giá một tin; unsupported khác None thì không có estimate."""

    listing_id: str
    position: int = 0
    price: float                       # giá rao, triệu VND
    area: float                        # m²
    estimate: PriceEstimate | None = None
    gap_pct: float | None = None       # (giá rao / ước tính - 1) x 100
    in_range: bool | None = None       # giá rao nằm trong [low, high] x diện tích
    unsupported: str | None = None


class ListingValuer:
    """Dùng chung predictor và geocoder với chatbot dự đoán giá (nạp model một lần)."""

    def __init__(self, predictor: PricePredictor, geocoder: Geocoder):
        self.predictor = predictor
        self.geocoder = geocoder

    async def appraise(self, rows: list[dict]) -> list[Appraisal]:
        """So giá từng dòng `fetch_details` (kèm "position") với ước tính của mô hình."""
        return [await self._appraise_one(row) for row in rows]

    async def _appraise_one(self, row: dict) -> Appraisal:
        base = {"listing_id": row["listing_id"], "position": row.get("position", 0),
                "price": row["price"], "area": row["area"]}
        kind = PROPERTY_TYPES.get((row["property_type"] or "").lower())  # tên DB viết hoa đầu
        district = PricePredictor.find_district(row["district_old"] or "")
        low, high = BOUNDS["area"][:2]
        if kind is None:
            return Appraisal(**base, unsupported=f"loại \"{row['property_type']}\" chưa hỗ trợ")
        if district is None or not low <= row["area"] <= high:
            return Appraisal(**base, unsupported="thiếu quận hoặc diện tích ngoài khoảng hỗ trợ")
        reliable = None not in (row["latitude"], row["longitude"]) and (
            "coords_outside_hcm" not in (row["quality_flags"] or []))
        place = (row["latitude"], row["longitude"]) if reliable else await self._centroid(district)
        optional = {key: row[key] if row[key] is not None
                    and BOUNDS[key][0] <= row[key] <= BOUNDS[key][1] else None
                    for key in ("frontage", "bedrooms", "floors")}
        try:
            estimate = self.predictor.predict(PriceInput(
                property_code=kind, district_code=district, area=row["area"],
                latitude=place[0], longitude=place[1], **optional))
        except (ValueError, TypeError):  # không có toạ độ dùng được
            return Appraisal(**base, unsupported="không xác định được vị trí")
        return Appraisal(
            **base, estimate=estimate, gap_pct=(row["price"] / estimate.total_price - 1) * 100,
            in_range=(estimate.price_per_m2_low * row["area"] <= row["price"]
                      <= estimate.price_per_m2_high * row["area"]))

    async def _centroid(self, district: int) -> tuple[float | None, float | None]:
        """Tin thiếu toạ độ tin cậy: dùng tâm quận (chỉ có tên quận thì Geocoder khỏi gọi Goong)."""
        location = await self.geocoder.locate(DISTRICT_NAMES[district], district)
        return (location.latitude, location.longitude) if location else (None, None)

    def answer(self, appraisals: list[Appraisal], notes: list[str] = ()) -> str:
        """Câu trả lời từ số liệu của Appraisal; `notes` nêu trước (vd. tham chiếu không có)."""
        lines, supported = list(notes), [a for a in appraisals if a.estimate]
        for item in appraisals:
            head = (f"Căn {item.position} (tin {item.listing_id}): "
                    f"giá rao {format_price(item.price)}")
            if item.estimate is None:
                lines.append(f"{head}; {item.unsupported} nên mình chưa ước tính được.")
                continue
            est = item.estimate
            low, high = (format_price(p * item.area) for p in
                         (est.price_per_m2_low, est.price_per_m2_high))
            lines.append(
                f"{head}; mô hình ước tính {format_price(est.total_price)} (khoảng tham khảo "
                f"{low} – {high}): giá rao {self._gap_text(item.gap_pct)}, "
                f"{'nằm trong' if item.in_range else 'nằm ngoài'} khoảng tham khảo.")
        if len(supported) > 1:
            lowest = min(supported, key=lambda a: a.gap_pct)  # câu không mâu thuẫn khi mọi căn > 0
            label = ("Giá rao thấp hơn ước tính nhiều nhất" if lowest.gap_pct < -SAME_PCT
                     else "Mọi căn đều có giá rao cao hơn hoặc xấp xỉ ước tính; chênh ít nhất")
            lines.append(f"{label}: căn {lowest.position} ({self._gap_text(lowest.gap_pct)}).")
        return "\n".join(lines + [FOOTER])

    @staticmethod
    def _gap_text(gap: float) -> str:
        if abs(gap) < SAME_PCT:
            return "xấp xỉ ước tính"
        return f"{'cao' if gap > 0 else 'thấp'} hơn ước tính {abs(gap):.0f}%"
