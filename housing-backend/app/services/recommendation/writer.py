"""Mọi câu trả lời gửi người dùng, do CODE viết hoàn toàn (không gọi LLM).

Kết quả tìm, 0 kết quả, câu hỏi bổ sung: câu soạn sẵn tại đây; hỏi chi tiết/so sánh: grounding.
"""

import re
from collections.abc import Callable

from app.services.recommendation.grounding import MISSING, detail_answer
from app.services.recommendation.schemas import (
    POI_NAMES,
    ListingHit,
    RelaxOption,
    SearchConstraints,
    format_distance,
    format_number,
    format_price,
)

MAX_RELAX_HINTS = 2      # lượt ok ít tin: tối đa 2 dòng gợi ý nới (spec 9 #27d)
PRICE_NOTE = "Giá là giá rao bán tham khảo."
DEGRADED_NOTE = (
    "Lưu ý: chức năng xếp hạng theo mô tả nhu cầu đang gián đoạn, các tin dưới đây vẫn đúng "
    "điều kiện nhưng được sắp theo ngày đăng mới nhất."
)
# "gần trung tâm" chưa lọc được theo khoảng cách (spec 9 #27e): chỉ là sở thích mềm
CENTER_PATTERN = re.compile(r"trung tâm(?! thương mại)")
CENTER_NOTE = "Mình chưa lọc theo khoảng cách tới trung tâm, chỉ xếp theo mô tả của tin."
OUT_OF_SCOPE_ANSWER = (
    "Mình chỉ hỗ trợ tìm mua nhà đất tại TP.HCM (không hỗ trợ tỉnh khác, thuê nhà, đấu giá hay "
    "tư vấn pháp lý/tài chính). Các điều kiện tìm kiếm trước đó của bạn vẫn được giữ, bạn có "
    "thể tiếp tục."
)


def _price_range(constraints: SearchConstraints) -> str:
    """'2,4 tỷ – 3,15 tỷ' hoặc '3 tỷ' khi chỉ có giá tối đa."""
    if constraints.price_min is None:
        return format_price(constraints.price_max)
    return f"{format_price(constraints.price_min)} – {format_price(constraints.price_max)}"


def _bounds(
    label: str, low: float | None, high: float | None, render: Callable[[float], str]
) -> list[str]:
    """'giá từ A đến B' / 'giá tối đa B' / 'giá từ A'; rỗng khi không có cận nào."""
    if low is not None and high is not None:
        return [f"{label} từ {render(low)} đến {render(high)}"]
    if high is not None:
        return [f"{label} tối đa {render(high)}"]
    return [f"{label} từ {render(low)}"] if low is not None else []


def describe_constraints(constraints: SearchConstraints, areas: list[str]) -> str:
    """'Căn hộ chung cư; khu vực Quận 7; giá khoảng 2,4 tỷ – 3,15 tỷ; từ 2 phòng ngủ'."""
    c = constraints
    parts = [", ".join(c.property_types)] if c.property_types else []
    parts += ["khu vực " + ", ".join(areas)] if areas else ["toàn TP.HCM"]
    if c.price_min_derived:  # khoảng do "tầm X" sinh ra (spec 9 #15)
        parts.append(f"giá khoảng {_price_range(c)}")
    else:
        parts += _bounds("giá", c.price_min, c.price_max, format_price)
    parts += _bounds("diện tích", c.area_min, c.area_max, lambda v: f"{format_number(v)} m²")
    if c.bedrooms_min is not None:
        parts.append(f"từ {c.bedrooms_min} phòng ngủ")
    parts += [
        f"gần {POI_NAMES[p.poi_type]} trong bán kính {format_distance(p.max_distance_m)}"
        for p in c.near_pois
    ]
    return "; ".join(parts)


def _listing_block(position: int, hit: ListingHit) -> str:
    """Khối tin số `position` trong danh sách kết quả (khớp "căn thứ N")."""
    facts = [format_price(hit.price), f"{format_number(hit.area)} m²"]
    if hit.bedrooms is not None:
        facts.append(f"{hit.bedrooms} phòng ngủ")
    if hit.property_type:
        facts.append(hit.property_type)
    address = hit.old_address or MISSING
    if hit.new_address:
        address += f" (địa chỉ mới: {hit.new_address})"
    posted = hit.posted_at.strftime("%d/%m/%Y") if hit.posted_at else MISSING
    lines = [f"{position}. [Tin {hit.listing_id}] {hit.title}",
             f"   {' · '.join(facts)}",
             f"   Địa chỉ: {address}"]
    if hit.poi_distances:
        lines.append("   Gần nhất: " + ", ".join(
            f"{POI_NAMES[poi_type]} {format_distance(meters)}"
            for poi_type, meters in hit.poi_distances.items()))
    lines.append(f"   Đăng {posted} · {hit.listing_url}")
    if hit.similar_ids:
        lines.append("   Tin đăng lại tương tự: "
                     + ", ".join(f"[Tin {sid}]" for sid in hit.similar_ids))
    return "\n".join(lines)


def _relax_lines(options: list[RelaxOption]) -> list[str]:
    """Mỗi phương án nới một dòng "Nếu <mô tả>: có N tin"."""
    return [f"- Nếu {o.description}: có {o.result_count} tin" for o in options]


def results_answer(
    hits: list[ListingHit], constraints: SearchConstraints, areas: list[str],
    changes: list[str], degraded: bool, relax_options: list[RelaxOption],
    with_listings: bool = True,
) -> str:
    """Lượt ok: thay đổi + điều kiện đang áp (nêu rõ bán kính POI) + tin 1..N; ít hơn 5 tin
    mà nới được thêm thì kèm tối đa 2 dòng gợi ý nới. Sở thích mềm chỉ là thứ tự xếp.
    `with_listings=False` bỏ khối từng tin: đó là `summary` cho UI vẽ tin bằng thẻ."""
    intro = (f"Mình tìm được {len(hits)} tin phù hợp với điều kiện: "
             f"{describe_constraints(constraints, areas)}.")
    if constraints.soft_query:
        intro += (f" Tin được xếp ưu tiên theo mong muốn \"{constraints.soft_query}\" "
                  "(bạn xem mô tả từng tin để kiểm tra).")
        if CENTER_PATTERN.search(constraints.soft_query):
            intro += " " + CENTER_NOTE
    blocks = [_listing_block(i, hit) for i, hit in enumerate(hits, start=1)] * with_listings
    more = [o for o in relax_options if o.result_count > len(hits)][:MAX_RELAX_HINTS]
    hints = ["Bạn có thể nới điều kiện để có thêm tin:", *_relax_lines(more)] if more else []
    head = ([DEGRADED_NOTE] if degraded else []) + [" ".join(changes + [intro])]
    return "\n\n".join(head + blocks + ["\n".join(hints)] * bool(hints) + [PRICE_NOTE])


def no_results_answer(
    relax_options: list[RelaxOption], changes: list[str], conditions: str
) -> str:
    """Nêu điều kiện đang áp rồi đúng các phương án nới và số tin do SQL đếm (spec 9 #27a)."""
    lines = [*changes, f"Chưa có tin nào thỏa toàn bộ điều kiện: {conditions}."]
    if relax_options:
        lines += ["Bạn có thể nới một điều kiện:", *_relax_lines(relax_options)]
    else:
        lines.append("Nới riêng từng điều kiện cũng chưa có tin; bạn thử đổi nhu cầu nhé.")
    return "\n".join(lines) + f"\n\n{PRICE_NOTE}"


def details_answer(rows: list[dict], question: str, notes: list[str]) -> tuple[str, list[str]]:
    """Trả lời `question` về `rows` (dòng DB kèm "position"); `notes` nêu trước (vd. tham
    chiếu không tồn tại)."""
    text, winners = detail_answer(question, rows)
    return "\n\n".join([*notes, text, PRICE_NOTE]), winners


def ask_budget_or_area(prefix: str = "", repeated: bool = False, known: str = "") -> str:
    """Hỏi ngân sách/khu vực; lần hỏi lặp lại đổi lời và ghi nhận điều kiện đã có (#27c)."""
    if not repeated:
        return (prefix + "Bạn cho mình biết ngân sách (ví dụ: dưới 3 tỷ) hoặc khu vực muốn "
                "mua (quận/huyện ở TP.HCM) để mình tìm tin phù hợp nhé.")
    recorded = f" Mình đã ghi nhận: {known}." if known else ""
    return (prefix + "Cảm ơn bạn đã chia sẻ." + recorded + " Để bắt đầu tìm, mình chỉ cần "
            "thêm một trong hai thông tin: mức giá bạn có thể chi (ví dụ: khoảng 3 tỷ) hoặc "
            "quận/huyện bạn muốn ở (ví dụ: Quận 7).")


def ask_confirm_budget(new_max: float, current_max: float) -> str:
    """Nâng/giảm ngược chiều (spec 9 #26): hỏi lại, không áp."""
    direction = "thấp hơn" if new_max < current_max else "cao hơn"
    return (f"Bạn muốn đặt ngân sách tối đa {format_price(new_max)} ({direction} mức "
            f"{format_price(current_max)} hiện tại) đúng không? Bạn xác nhận giúp mình nhé.")


def ask_which_listing(available: int) -> str:
    """Câu hỏi chi tiết không nói căn nào mà có nhiều tin: hỏi lại, không tìm lại."""
    return f"Bạn muốn hỏi căn nào (1–{available})?"


def refs_not_found(missing: list[str], available: int, after_no_results: bool = False) -> str:
    """Báo tham chiếu không có trong danh sách vừa gợi ý."""
    if after_no_results:
        return "Lượt trước chưa có tin nào khớp, bạn nới điều kiện nhé."
    if not available:  # spec 9 #27b
        return "Mình chưa gợi ý tin nào để hỏi chi tiết."
    return (f"Không tìm thấy {', '.join(missing)} trong danh sách vừa gợi ý "
            f"(hiện chỉ có {available} tin).")


def describe_changes(
    old: SearchConstraints, new: SearchConstraints, old_areas: list[str],
    new_areas: list[str], cheaper: bool,
) -> list[str]:
    """Câu ngắn về điều kiện vừa đổi ("Đã giảm ngân sách xuống 2,7 tỷ"), tính bằng code."""
    changes = []
    if (new.price_min, new.price_max) != (old.price_min, old.price_max):
        if new.price_max is None:
            changes.append("Đã bỏ giới hạn ngân sách tối đa.")
        elif cheaper:
            changes.append(f"Đã giảm giá 10%, còn {_price_range(new)}.")
        elif old.price_max is not None and new.price_min_derived:
            changes.append(f"Đã áp khoảng giá {_price_range(new)}.")
        elif old.price_max is not None and new.price_max != old.price_max:
            verb = ("tăng ngân sách lên" if new.price_max > old.price_max
                    else "giảm ngân sách xuống")
            changes.append(f"Đã {verb} {format_price(new.price_max)}.")
    if old_areas and new_areas != old_areas:
        changes.append("Đã đổi khu vực sang " + ", ".join(new_areas) + "."
                       if new_areas else "Đã bỏ giới hạn khu vực (toàn TP.HCM).")
    if old.property_types and new.property_types != old.property_types:
        changes.append("Đã đổi loại nhà đất: " + ", ".join(new.property_types) + "."
                       if new.property_types else "Đã bỏ điều kiện loại nhà đất.")
    dropped_pois = {p.poi_type for p in old.near_pois} - {p.poi_type for p in new.near_pois}
    changes += [f"Đã bỏ điều kiện gần {POI_NAMES[poi_type]}." for poi_type in sorted(dropped_pois)]
    return changes
