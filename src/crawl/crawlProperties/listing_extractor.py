"""Extract Batdongsan.com.vn listing fields from captured detail HTML."""
from __future__ import annotations

import argparse
import json
import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Iterable


OUTPUT_FIELDS = (
    "transaction_type",
    "province_old",
    "district_old",
    "old_ward",
    "new_ward",
    "new_city",
    "old_address",
    "old_address_detail",
    "new_address",
    "latitude",
    "longitude",
    "property_type",
    "area",
    "frontage",
    "bedrooms",
    "bathrooms",
    "road_width",
    "legal",
    "interior",
    "floors",
    "price",
    "price_per_m2",
    "posting_date",
    "expiration_date",
    "listing_id",
    "listing_url",
    "title",
    "description",
)

SPEC_FIELD_MAP = {
    "khoảng giá": "price",
    "mức giá": "price",
    "diện tích": "area",
    "mặt tiền": "frontage",
    "số phòng ngủ": "bedrooms",
    "phòng ngủ": "bedrooms",
    "số phòng tắm, vệ sinh": "bathrooms",
    "số phòng vệ sinh": "bathrooms",
    "đường vào": "road_width",
    "pháp lý": "legal",
    "nội thất": "interior",
    "số tầng": "floors",
}


class _Node:
    __slots__ = ("tag", "attrs", "children", "parent")

    def __init__(self, tag: str, attrs: dict[str, str], parent: "_Node | None" = None):
        self.tag = tag
        self.attrs = attrs
        self.children: list[_Node | str] = []
        self.parent = parent

    @property
    def classes(self) -> set[str]:
        return set(self.attrs.get("class", "").split())

    def text(self, separator: str = " ") -> str:
        parts: list[str] = []

        def visit(node: _Node | str) -> None:
            if isinstance(node, str):
                parts.append(node)
                return
            if node.tag == "br":
                parts.append("\n" if separator == "\n" else separator)
                return
            for child in node.children:
                visit(child)

        visit(self)
        joined = "".join(parts) if separator == "\n" else separator.join(parts)
        if separator == "\n":
            return "\n".join(_clean_text(line) for line in joined.splitlines() if _clean_text(line))
        return _clean_text(joined)


class _TreeParser(HTMLParser):
    _VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = _Node("document", {})
        self.stack = [self.root]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node = _Node(tag.lower(), {k.lower(): v or "" for k, v in attrs}, self.stack[-1])
        self.stack[-1].children.append(node)
        if tag.lower() not in self._VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag.lower() not in self._VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                return

    def handle_data(self, data: str) -> None:
        self.stack[-1].children.append(data)


def _clean_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _walk(node: _Node) -> Iterable[_Node]:
    for child in node.children:
        if isinstance(child, _Node):
            yield child
            yield from _walk(child)


def _find(root: _Node, *, tag: str | None = None, class_name: str | None = None,
          attrs: dict[str, str] | None = None) -> _Node | None:
    for node in _walk(root):
        if tag is not None and node.tag != tag:
            continue
        if class_name is not None and class_name not in node.classes:
            continue
        if attrs and any(node.attrs.get(k) != v for k, v in attrs.items()):
            continue
        return node
    return None


def _find_all(root: _Node, *, tag: str | None = None, class_name: str | None = None) -> list[_Node]:
    return [node for node in _walk(root)
            if (tag is None or node.tag == tag) and (class_name is None or class_name in node.classes)]


def _child_text(root: _Node, class_name: str) -> str | None:
    node = _find(root, class_name=class_name)
    value = node.text() if node else ""
    return value or None


def _address_component(address: str | None, kind: str) -> str | None:
    patterns = {
        "ward": r"(?:Phường|Xã|Thị trấn)\s+[^,()]+",
        "district": r"(?:Quận|Huyện)\s+[^,()]+",
    }
    match = re.search(patterns[kind], address or "", re.IGNORECASE)
    return match.group(0).strip() if match else None


def _old_address_detail(address: str | None) -> str | None:
    """Return the old address portion before its district-level component."""
    if not address:
        return None
    parts = [_clean_text(part) for part in address.split(",")]
    district_index = next(
        (
            index
            for index, part in enumerate(parts)
            if re.match(r"^(?:Quận|Huyện|Thành phố\s+Thủ Đức)\b", part, re.IGNORECASE)
        ),
        None,
    )
    if district_index is None:
        return None
    value = ", ".join(part for part in parts[:district_index] if part)
    return value or None


def _new_city(address: str | None) -> str | None:
    if not address:
        return None
    parts = [_clean_text(part) for part in address.split(",")]
    for part in reversed(parts):
        city = re.sub(r"\s+mới$", "", part, flags=re.IGNORECASE).strip()
        if city and not re.match(r"^(?:Phường|Xã|Thị trấn)\b", city, re.IGNORECASE):
            return city
    return None


def _number(value: str | None) -> int | float | None:
    """Remove display units and parse a Vietnamese-formatted number."""
    match = re.search(r"\d[\d.,]*", value or "")
    if not match:
        return None
    number = match.group(0).rstrip(".,")
    if "," in number and "." in number:
        decimal_separator = "," if number.rfind(",") > number.rfind(".") else "."
        thousands_separator = "." if decimal_separator == "," else ","
        number = number.replace(thousands_separator, "").replace(decimal_separator, ".")
    elif "," in number:
        number = number.replace(",", ".")
    elif number.count(".") > 1:
        number = number.replace(".", "")
    parsed = float(number)
    return int(parsed) if parsed.is_integer() else parsed


def _price(value: str | None) -> int | float | None:
    """Convert a price to millions of VND."""
    if not value or "thỏa thuận" in value.lower():
        return None
    lowered = value.lower()
    billion = re.search(r"(\d[\d.,]*)\s*tỷ", lowered)
    million = re.search(r"(\d[\d.,]*)\s*(?:triệu|tr)\b", lowered)
    if billion and million and billion.start() < million.start():
        billion_value = _number(billion.group(1)) or 0
        million_value = _number(million.group(1)) or 0
        total = float(billion_value) * 1000 + float(million_value)
        return int(total) if total.is_integer() else total
    number = _number(value)
    if number is None:
        return None
    result = float(number) * 1000 if "tỷ" in lowered else float(number)
    return int(result) if result.is_integer() else result


def _normalize_fields(result: dict[str, Any]) -> None:
    result["price"] = _price(result["price"])
    result["price_per_m2"] = _price(result["price_per_m2"])
    for field in (
        "area",
        "frontage",
        "bedrooms",
        "bathrooms",
        "road_width",
        "floors",
    ):
        result[field] = _number(result[field])


def listing_skip_reason(result: dict[str, Any]) -> str | None:
    """Return why a listing must not be saved, or None when it is valid."""
    if result.get("price") is None:
        return "Thiếu giá"
    if result.get("area") is None:
        return "Thiếu diện tích"
    return None


def _description_fallback(description: str, field: str) -> str | None:
    patterns = {
        "frontage": r"(?:mặt tiền|ngang)\s*[:\-]?\s*\d[\d.,]*\s*m",
        "bedrooms": r"\b\d+\s*(?:PN|phòng ngủ)\b",
        "bathrooms": r"\b\d+\s*(?:WC|phòng (?:tắm|vệ sinh))\b",
        "road_width": r"(?:đường(?: vào)?|hẻm)\s*(?:rộng\s*)?[:\-]?\s*\d[\d.,]*\s*m",
        "legal": r"(?:sổ đỏ|sổ hồng|pháp lý|HĐMB|hợp đồng mua bán)[^\n.;]{0,80}",
        "interior": r"nội thất[^\n.;]{0,80}",
        "floors": r"\b\d+\s*(?:tầng|lầu)\b",
    }
    match = re.search(patterns[field], description, re.IGNORECASE)
    return _clean_text(match.group(0)) if match else None


def extract_listing(html_text: str) -> dict[str, Any]:
    """Return one raw listing record from an HTML string."""
    parser = _TreeParser()
    parser.feed(html_text)
    root = parser.root
    result: dict[str, Any] = {field: None for field in OUTPUT_FIELDS}

    canonical = _find(root, tag="link", attrs={"rel": "canonical"})
    result["listing_url"] = canonical.attrs.get("href") or None if canonical else None

    title = _find(root, tag="h1", class_name="js__pr-title")
    result["title"] = title.text() or None if title else None

    old_address = _child_text(root, "re__address-line-1")
    new_address = _child_text(root, "re__address-line-2")
    if new_address:
        new_address = new_address.strip().removeprefix("(").removesuffix(")").strip()
    result.update({
        "old_address": old_address,
        "old_address_detail": _old_address_detail(old_address),
        "new_address": new_address,
        "old_ward": _address_component(old_address, "ward"),
        "new_ward": _address_component(new_address, "ward"),
        "new_city": _new_city(new_address),
    })

    breadcrumbs = sorted(
        (node for node in _find_all(root, tag="a", class_name="re__link-se") if node.attrs.get("level")),
        key=lambda node: int(node.attrs["level"]) if node.attrs["level"].isdigit() else 999,
    )
    if breadcrumbs:
        breadcrumb_by_level = {node.attrs.get("level"): node.text() for node in breadcrumbs}
        first = breadcrumb_by_level.get("1", breadcrumbs[0].text())
        if re.search(r"\bcho thuê\b", first, re.IGNORECASE):
            result["transaction_type"] = "Cho thuê"
        elif re.search(r"\bbán\b", first, re.IGNORECASE):
            result["transaction_type"] = "Bán"
        result["province_old"] = breadcrumb_by_level.get("2")
        result["district_old"] = breadcrumb_by_level.get("3")
        property_breadcrumb = breadcrumb_by_level.get("4", breadcrumbs[-1].text())
        result["property_type"] = re.split(
            r"\s+tại\s+", property_breadcrumb, maxsplit=1, flags=re.IGNORECASE
        )[0] or None
    if result["transaction_type"] is None and result["listing_url"]:
        path = result["listing_url"].lower()
        result["transaction_type"] = "Cho thuê" if "/cho-thue-" in path else ("Bán" if "/ban-" in path else None)

    description_node = _find(root, class_name="re__detail-content")
    result["description"] = description_node.text("\n") or None if description_node else None

    for item in _find_all(root, class_name="re__pr-specs-content-item"):
        label = _child_text(item, "re__pr-specs-content-item-title")
        value = _child_text(item, "re__pr-specs-content-item-value")
        field = SPEC_FIELD_MAP.get((label or "").lower())
        if field and value and result[field] is None:
            result[field] = value

    short_info = _find(root, class_name="js__pr-short-info")
    if short_info:
        for item in _find_all(short_info, class_name="js__pr-short-info-item"):
            label = (_child_text(item, "title") or "").lower()
            value = _child_text(item, "value")
            if "khoảng giá" in label or "mức giá" in label:
                if result["price"] is None:
                    result["price"] = value
                if result["price_per_m2"] is None:
                    result["price_per_m2"] = _child_text(item, "ext")
            elif "diện tích" in label and result["area"] is None:
                result["area"] = value
            elif "phòng ngủ" in label and result["bedrooms"] is None:
                result["bedrooms"] = value

    config = _find(root, class_name="js__pr-config")
    if config:
        config_map = {"ngày đăng": "posting_date", "ngày hết hạn": "expiration_date", "mã tin": "listing_id"}
        for item in _find_all(config, class_name="js__pr-config-item"):
            label = (_child_text(item, "title") or "").lower()
            field = config_map.get(label)
            if field:
                result[field] = _child_text(item, "value")

    # Coordinates are raw string values from the listing's map initialization.
    latitude = re.search(r"\blatitude\s*:\s*([+-]?\d+(?:\.\d+)?)", html_text, re.IGNORECASE)
    longitude = re.search(r"\blongitude\s*:\s*([+-]?\d+(?:\.\d+)?)", html_text, re.IGNORECASE)
    result["latitude"] = latitude.group(1) if latitude else None
    result["longitude"] = longitude.group(1) if longitude else None

    # Structured data remains authoritative. Description fallback is conservative.
    if result["description"]:
        for field in ("frontage", "bedrooms", "bathrooms", "road_width", "legal", "interior", "floors"):
            if result[field] is None:
                result[field] = _description_fallback(result["description"], field)

    _normalize_fields(result)

    return result


def extract_listing_file(path: str | Path) -> dict[str, Any]:
    """Extract one UTF-8 HTML file."""
    return extract_listing(Path(path).read_text(encoding="utf-8"))


def extract_directory(input_dir: str | Path, output_file: str | Path) -> list[dict[str, Any]]:
    """Extract every .html file in a directory and write one JSON array."""
    input_path = Path(input_dir)

    def sort_key(path: Path) -> tuple[int, int | str]:
        return (0, int(path.stem)) if path.stem.isdigit() else (1, path.name)

    records = [extract_listing_file(path) for path in sorted(input_path.glob("*.html"), key=sort_key)]
    Path(output_file).write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    return records


def main() -> None:
    cli = argparse.ArgumentParser(description="Extract raw Batdongsan listing HTML")
    cli.add_argument("input", help="HTML file or directory containing HTML files")
    cli.add_argument("-o", "--output", required=True, help="Output JSON path")
    args = cli.parse_args()
    source = Path(args.input)
    if source.is_dir():
        extract_directory(source, args.output)
    else:
        record = extract_listing_file(source)
        Path(args.output).write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
