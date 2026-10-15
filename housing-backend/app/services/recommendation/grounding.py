"""Câu trả lời ask_detail/compare do CODE viết (spec 9 #13, #22, #28, #29, #31): facts định dạng
sẵn, so sánh từ số đã làm tròn như hiển thị; không có LLM nên không bịa được chi tiết."""

import re
import unicodedata
from collections.abc import Callable, Sequence
from datetime import date
from typing import Any, NamedTuple

from app.services.formatting import (
    format_distance,
    format_number,
    format_price,
    round_distance,
    round_price,
)
from app.services.recommendation.text_rules import fold

MISSING = "tin không ghi"
DESCRIPTION_CHARS = 300
Renderer = Callable[[Any], str]  # nhận số, chuỗi hoặc ngày tùy cột; trả chữ hiển thị
RANK_WORDS = ("nhat", "hon")  # "rộng nhất" (một căn thắng), "rộng hơn" (so hai căn trở lên)
DETAIL_PATTERN = re.compile(r"\b(?:chi\stiet|them\sve|noi\sthem)\b")  # "chi tiết", "nói thêm về"
# Tách câu hỏi nhiều ý thành các vế; "còn hạn" là một thuộc tính, không phải ý mới
CLAUSE_SPLIT = re.compile(r"[,;?]|\s(?:và|còn(?!\shạn))\s")
POSITION_REF = re.compile(r"\b(?:căn|can|lô|lo|tin|cái|cai)\s+(?:(?:thứ|thu|số|so)\s+)?\w+")
RANKINGS = {  # từ bỏ dấu -> (cột; "poi" = POI được hỏi, lấy lớn nhất?, từ hiển thị)
    "rong": ("area", True, "rộng"), "lon": ("area", True, "lớn"), "to": ("area", True, "to"),
    "nho": ("area", False, "nhỏ"), "re": ("price", False, "rẻ"), "dat": ("price", True, "đắt"),
    "mac": ("price", True, "mắc"), "gan": ("poi", False, "gần"), "xa": ("poi", True, "xa"),
}
# Từ đệm không mang nội dung khi tìm trong mô tả tin. So khớp theo từ khách gõ: gõ có dấu thì chỉ
# từ đệm có dấu ("đậu", "ô", "tô" không bị coi là "đâu", "o", "to"); gõ không dấu thì dạng bỏ dấu.
_FILLERS = set(re.findall(
    r"\w+",
    "có không ko k là thì và còn nào thế gì mà mấy bao nhiêu được vào ra cho chỗ mình anh chị em "
    "tôi tới xin giúp hãy xem các này đó kia đâu tiên cuối cùng nhất hơn rẻ rộng lớn to nhỏ gần xa "
    "đắt mắc cách tất cả căn tin lô cái số thứ nhé a hả vậy sao khác giống nhau chi tiết sánh "
    "dưới trên với ở trong của về nữa đây đi hỏi nói thêm một hai khi lấy mua chốt chọn thích muốn",
))
STOP_WORDS = _FILLERS | {fold(w) for w in _FILLERS}


class Attribute(NamedTuple):
    """Thuộc tính của tin người dùng có thể hỏi."""

    column: str
    label: str
    keywords: re.Pattern  # câu hỏi nhắc tới thuộc tính này; chạy trên bản fold() hoặc bản gốc
    render: Renderer      # giá trị -> chữ trong câu trả lời
    bigger: str = ""  # từ cho bên lớn hơn ("đắt hơn"); rỗng = không so sánh
    name_column: str = ""  # cột tên đi kèm giá trị (POI gần nhất)
    # Làm tròn số đúng như render hiển thị, để hiệu hai số khớp với những gì người đọc thấy
    shown: Callable[[float], float] = float
    raw: bool = False      # keywords chạy trên bản có dấu ("chợ" khác "chỗ", "ở đâu" khác "lô đầu")
    default: bool = False  # in khi người dùng không nêu thuộc tính cụ thể ("so sánh giúp mình")

    def asked_in(self, raw_text: str, folded_text: str) -> bool:
        """Câu hỏi có nhắc thuộc tính này không."""
        return bool(self.keywords.search(raw_text if self.raw else folded_text))


def _with_unit(unit: str) -> Renderer:
    """Hàm định dạng "<số> <đơn vị>"."""
    return lambda value: f"{format_number(value)} {unit}"


def _date(value: date) -> str:
    """Ngày dd/mm/yyyy."""
    return value.strftime("%d/%m/%Y")


ATTRIBUTES = (
    Attribute("price", "giá",
              re.compile(r"\bgia\b(?!\s(?:tren\s|moi\s)?(?:m2|met\svuong))|bao\snhieu\stien"),
              format_price, "đắt hơn", shown=round_price, default=True),
    Attribute("price_per_m2", "giá/m²",
              re.compile(r"\bgia\s(?:tren\s|moi\s)?(?:m2|met\svuong)\b|don\sgia|theo\s(?:m2|met\svuong)"),
              lambda value: format_price(value) + "/m²", "đắt hơn",
              shown=round_price, default=True),
    Attribute("area", "diện tích", re.compile(r"dien\stich|bao\snhieu\sm2"), _with_unit("m²"),
              "lớn hơn", default=True),
    Attribute("bedrooms", "số phòng ngủ", re.compile(r"phong\sngu|\bpn\b"),
              _with_unit("phòng ngủ"), "nhiều hơn", default=True),
    Attribute("bathrooms", "số phòng tắm", re.compile(r"phong\stam|ve\ssinh|\bwc\b|toilet"),
              _with_unit("phòng tắm"), "nhiều hơn"),
    Attribute("floors", "số tầng", re.compile(r"\btang\b|\blau\b"), _with_unit("tầng"),
              "nhiều hơn"),
    Attribute("frontage", "mặt tiền", re.compile(r"mat\stien"), _with_unit("m"),
              "lớn hơn"),
    Attribute("road_width", "đường vào", re.compile(r"duong\svao|do\srong\sduong"),
              _with_unit("m")),
    Attribute("legal", "pháp lý", re.compile(r"phap\sly|so\s(?:hong|do)"), str, default=True),
    Attribute("interior", "nội thất", re.compile(r"noi\sthat"), str),
    Attribute("property_type", "loại hình", re.compile(r"loai\s(?:hinh|nha)"), str),
    Attribute("posted_at", "ngày đăng",
              re.compile(r"dang\s(?:ngay|bao\sgio|luc|khi\snao)|ngay\sdang"), _date),
    Attribute("expired_at", "ngày hết hạn", re.compile(r"het\shan|con\shan"), _date),
    Attribute("listing_url", "đường dẫn", re.compile(r"\blink\b|\burl\b|duong\sdan"), str),
    Attribute("address", "địa chỉ",
              re.compile(r"địa chỉ|dia chi|\b(?:ở|o) (?:đâu|dau)\b|\b(?:nằm|nam) (?:ở|o)\b"
                         r"|thuộc phường|thuoc phuong"
                         r"|(?:quận|quan|đường|duong|phường|phuong) (?:nào|nao)"), str, raw=True),
    Attribute("nearest_school_m", "trường học gần nhất", re.compile(r"\btruong\b"),
              format_distance, "xa hơn", "nearest_school_name", round_distance,
              default=True),
    Attribute("nearest_hospital_m", "bệnh viện gần nhất", re.compile(r"benh\svien"),
              format_distance, "xa hơn", "nearest_hospital_name", round_distance,
              default=True),
    # "chợ nào", "gần chợ"; bản fold sẽ nhầm "chỗ nào" thành "chợ nào" nên chạy trên bản có dấu
    Attribute("nearest_market_m", "chợ gần nhất",
              re.compile(r"\bchợ\b|\b(?:gan|cach|xa)\s+cho\b"), format_distance,
              "xa hơn", "nearest_market_name", round_distance, raw=True,
              default=True),
)


ATTRIBUTES_BY_COLUMN = {a.column: a for a in ATTRIBUTES}
Topic = tuple[str, set[str], Callable[[str], str]]  # (nhãn, từ khóa, cách chuẩn hóa để so khớp)


def asked_attributes(question: str) -> list[Attribute]:
    """Thuộc tính câu hỏi nhắc tới (theo từ khóa của từng thuộc tính)."""
    raw_text, folded_text = unicodedata.normalize("NFC", question).lower(), fold(question)
    return [a for a in ATTRIBUTES if a.asked_in(raw_text, folded_text)]


def is_vague_question(question: str) -> bool:
    """Câu hỏi không nhắc thuộc tính, xếp hạng hay "chi tiết": chỉ trả lời được khi biết căn nào."""
    folded = fold(question)
    return not (asked_attributes(question) or DETAIL_PATTERN.search(folded)
                or set(folded.split()) & set(RANK_WORDS))


def detail_answer(question: str, rows: Sequence[dict]) -> tuple[str, list[str]]:
    """(câu trả lời, id căn thắng nếu có vế "nhất") cho câu hỏi về các tin `rows`.

    "Chi tiết": mọi thuộc tính có dữ liệu. Còn lại tách thành vế: "rộng hơn/rẻ nhất" trả lời
    bằng căn thắng; một thuộc tính thì danh sách ngắn; ngoài ra mỗi căn một khối (thuộc tính
    được hỏi hoặc bộ mặc định) kèm trích mô tả cho vế không khớp thuộc tính nào."""
    detail = bool(DETAIL_PATTERN.search(fold(question)))
    clauses = [] if detail else CLAUSE_SPLIT.split(unicodedata.normalize("NFC", question).lower())
    rankings, winners, rest = [], [], []
    for clause in clauses:
        ranked = _ranking_answer(clause, rows)
        rest += [] if ranked else [clause]
        rankings += [ranked[0]] if ranked else []
        winners += ranked[1] if ranked else []
    rankings = list(dict.fromkeys(rankings))  # hai vế cùng hỏi một thứ không in lặp
    rest_question = " ".join(rest) if rankings else question
    asked, topics = asked_attributes(rest_question), _topics(rest)
    if rankings and not asked and not topics:
        return "\n".join(rankings), winners
    if len(asked) == 1 and not topics:
        body = _single_attribute_answer(asked[0], rows)
    else:
        default = {a.column for a in ATTRIBUTES if a.default}
        data = {a.column for a in ATTRIBUTES if any(r.get(a.column) is not None for r in rows)}
        columns = {a.column for a in asked} or (set() if topics else data if detail else default)
        blocks = _listing_blocks(rows, columns, topics)
        if len(rows) > 1 and not detail and (lines := _comparison_lines(columns, rows)):
            blocks.append("So sánh:\n" + "\n".join(lines))
        body = "\n\n".join(blocks)
    return "\n\n".join([*rankings, body]), winners


def _ranking_answer(clause: str, rows: Sequence[dict]) -> tuple[str, list[str]] | None:
    """Vế "rộng/rẻ/gần... nhất|hơn": căn thắng + giá trị + xếp hạng; ids chỉ khi là "nhất"."""
    tokens = fold(clause).split()
    trigger = next(((w, t) for i, t in enumerate(tokens) if t in RANK_WORDS
                    for w in reversed(tokens[max(0, i - 3):i]) if w in RANKINGS), None)
    if not trigger:
        return None
    column, biggest, word = RANKINGS[trigger[0]]
    asked = [a.column for a in asked_attributes(clause)]
    if column == "poi":
        column = next((c for c in asked if c.startswith("nearest_")), "")
    elif column == "price" and "price_per_m2" in asked:
        column = "price_per_m2"
    attribute = ATTRIBUTES_BY_COLUMN.get(column)
    values = {r["position"]: attribute.shown(r[column]) for r in rows
              if attribute and r.get(column) is not None}
    if not values:
        return None
    best = (max if biggest else min)(values.values())
    winners = [r for r in rows if values.get(r["position"]) == best]
    value = _build_facts(winners[0])[column]
    if len(winners) == len(values) > 1:
        text = f"Về {attribute.label}, các căn bằng nhau ({value})."
    else:
        names = " và ".join(f"Căn {r['position']} [Tin {r['listing_id']}]" for r in winners)
        text = f"Theo {attribute.label}, {names} {word} {'nhất' if trigger[1] == 'nhat' else 'hơn'}"
        text += f" ({value})."
    text = "\n".join([text, *_comparison_lines({column}, rows, ranking=True)])
    return text, [r["listing_id"] for r in winners] if trigger[1] == "nhat" else []


def _topics(clauses: list[str]) -> list[Topic]:
    """Vế không khớp thuộc tính nào ("hẻm xe hơi"): (nhãn, từ khóa, chuẩn hóa). Gõ có dấu thì so
    khớp giữ dấu ("sống" khác "sông"); gõ không dấu thì bỏ dấu."""
    topics = []
    for clause in clauses:
        clause = POSITION_REF.sub(" ", clause)
        words = [w for w in re.findall(r"\w+", clause)
                 if w not in STOP_WORDS and not w.isdigit()]
        matched = any(a.asked_in(clause, fold(clause)) for a in ATTRIBUTES)
        if words and (not matched or "tret" in fold(clause).split()):  # "phòng ngủ dưới trệt"
            normalize = fold if all(fold(w) == w for w in words) else str
            topics.append((" ".join(words), {normalize(w) for w in words}, normalize))
    return topics


def _single_attribute_answer(attribute: Attribute, rows: Sequence[dict]) -> str:
    """Câu hỏi đúng một thuộc tính: mỗi căn một dòng, rồi so sánh (nhãn chỉ nêu một lần)."""
    lines = [attribute.label.capitalize() + ":"]
    for row in rows:
        facts = _build_facts(row)
        lines.append(f"- {facts['label']} [Tin {facts['listing_id']}]: {facts[attribute.column]}")
    return "\n".join(lines + _comparison_lines({attribute.column}, rows))


def _listing_blocks(rows: Sequence[dict], columns: set[str], topics: list[Topic]) -> list[str]:
    """Mỗi "Căn N" một khối: tiêu đề, địa chỉ cũ+mới, thuộc tính, rồi trích mô tả theo vế."""
    blocks = []
    for row in rows:
        facts = _build_facts(row)
        address = facts["address"]
        lines = [f"{facts['label']} [Tin {facts['listing_id']}]" + (
                     f" {row['title']}" if row.get("title") else ""),
                 "- " + (address if address != MISSING else f"địa chỉ: {MISSING}")]
        lines += [f"- {a.label}: {facts[a.column]}" for a in ATTRIBUTES
                  if a.column in columns and a.column != "address"]
        for label, keywords, normalize in topics:
            excerpt = _excerpt(row, keywords, normalize)
            lines.append(f'- {label}: "{excerpt}"' if excerpt else f"- {label}: {MISSING} mục này")
        blocks.append("\n".join(lines))
    return blocks


def _excerpt(row: dict, keywords: set[str], normalize: Callable[[str], str]) -> str | None:
    """Tiêu đề/câu mô tả khớp nhiều từ khóa nhất (nguyên văn; vế nhiều từ phải khớp ít nhất một
    nửa, tối thiểu 2), cắt ở ranh giới từ."""
    need = 1 if len(keywords) == 1 else max(2, -(-len(keywords) // 2))
    texts = [row.get("title") or "", *re.split(r"(?<=[.!?])\s+|\n+", row.get("description") or "")]
    best, hits = None, need - 1
    for text in texts:
        count = len(keywords & {normalize(w) for w in re.findall(r"\w+", text.lower())})
        if count > hits:
            best, hits = text.strip(), count
    if best and len(best) > DESCRIPTION_CHARS:
        best = best[:DESCRIPTION_CHARS].rsplit(" ", 1)[0] + "…"
    return best


def _build_facts(row: dict) -> dict:
    """Facts của một tin, mọi giá trị đã định dạng sẵn; cột NULL ghi "tin không ghi"."""
    # Địa chỉ cũ và mới do code nối, không trộn tên phường/quận của hai địa chỉ
    address = "; ".join(
        f"{label}: {row[column]}"
        for label, column in (("địa chỉ cũ", "old_address"), ("địa chỉ mới", "new_address"))
        if row.get(column)
    )
    values = {**row, "address": address or None}
    facts = {"label": f"Căn {row['position']}", "listing_id": row["listing_id"]}
    for attribute in ATTRIBUTES:
        value = values.get(attribute.column)
        text = MISSING if value is None else attribute.render(value)
        if value is not None and attribute.name_column:
            text = f"{values.get(attribute.name_column) or 'không rõ tên'}, cách {text}"
        facts[attribute.column] = text
    return facts


def _comparison_lines(columns: set[str], rows: Sequence[dict], ranking: bool = False) -> list[str]:
    """Hai tin: câu so sánh; từ ba tin hoặc `ranking`: xếp hạng từ thấp đến cao. Thuộc tính mọi
    tin bằng nhau thì bỏ (không có gì để so)."""
    lines = []
    for attribute in ATTRIBUTES:
        if not attribute.bigger or attribute.column not in columns:
            continue
        values = sorted((attribute.shown(r[attribute.column]), r["position"]) for r in rows
                        if r.get(attribute.column) is not None)
        if len(values) < 2 or values[0][0] == values[-1][0]:
            continue
        render, label = attribute.render, attribute.label
        if ranking or len(rows) > 2:
            lines.append(f"- {label} từ thấp đến cao: " + ", ".join(
                f"Căn {position} ({render(value)})" for value, position in values))
            continue
        (low, lo), (high, hi) = values[0], values[-1]
        text = (f"Căn {hi} ({render(high)}) {attribute.bigger} Căn {lo} ({render(low)}), "
                f"chênh {render(high - low)}")
        lines.append("- " + text if len(columns) == 1 else f"- {label}: {text}")
    return lines
