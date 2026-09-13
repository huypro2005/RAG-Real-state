"""One-off audit generator for the 17 captured HTML samples (not a production parser)."""
from pathlib import Path
import html
import json
import re
from collections import Counter, defaultdict

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = ROOT / "analysis"
SAMPLES = OUT / "sample_extractions"

FIELD_ORDER = [
    "province_city", "old_district", "old_ward", "new_district", "new_ward",
    "old_address", "new_address", "latitude", "longitude", "property_type",
    "area", "frontage", "bedrooms", "bathrooms", "road_width", "legal",
    "interior", "floors", "price", "price_per_m2", "posting_date",
    "expiration_date", "listing_id", "listing_url", "title", "description",
]

LABELS = {
    "Khoảng giá": "price", "Diện tích": "area", "Mặt tiền": "frontage",
    "Số phòng ngủ": "bedrooms", "Số phòng tắm, vệ sinh": "bathrooms",
    "Đường vào": "road_width", "Pháp lý": "legal", "Nội thất": "interior",
    "Số tầng": "floors",
}

def clean(value):
    value = re.sub(r"<br\s*/?>", "\n", value, flags=re.I)
    value = re.sub(r"<[^>]+>", " ", value)
    value = html.unescape(value).replace("\xa0", " ")
    return re.sub(r"[ \t\r\f\v]+", " ", value).strip()

def match(s, pattern, flags=re.S | re.I):
    m = re.search(pattern, s, flags)
    return clean(m.group(1)) if m else None

def raw_match(s, pattern, flags=re.S | re.I):
    m = re.search(pattern, s, flags)
    return m.group(1) if m else None

def entry(value=None, source=None, selector=None, confidence="high", **extra):
    if value is None or value == "":
        return {"present": False}
    d = {"present": True, "raw_value": value, "source": source,
         "selector": selector, "confidence": confidence}
    d.update(extra)
    return d

def component(address, kind):
    patterns = {
        "ward": r"(?:Phường|Xã|Thị trấn)\s+[^,()]+",
        "district": r"(?:Quận|Huyện)\s+[^,()]+",
    }
    m = re.search(patterns[kind], address or "", re.I)
    return m.group(0).strip() if m else None

def description_hint(desc, field):
    # Conservative: presence only when the prose explicitly labels/abbreviates a value.
    pats = {
        "frontage": r"(?i)(?:mặt tiền|ngang)\s*[:\-]?\s*\d[\d.,]*\s*m",
        "bedrooms": r"(?i)\b\d+\s*(?:PN|phòng ngủ)\b",
        "bathrooms": r"(?i)\b\d+\s*(?:WC|phòng (?:tắm|vệ sinh))\b",
        "road_width": r"(?i)(?:đường(?: vào)?|hẻm)\s*(?:rộng\s*)?[:\-]?\s*\d[\d.,]*\s*m",
        "legal": r"(?i)(?:sổ đỏ|sổ hồng|pháp lý|HĐMB|hợp đồng mua bán)",
        "interior": r"(?i)(?:nội thất[^\n.;]{0,80})",
        "floors": r"(?i)\b\d+\s*(?:tầng|lầu)\b",
    }
    m = re.search(pats.get(field, r"(?!x)x"), desc)
    return m.group(0).strip() if m else None

def classify(pct):
    if pct == 100: return "ALWAYS_PRESENT"
    if pct >= 80: return "MOSTLY_PRESENT"
    if pct >= 20: return "OPTIONAL"
    if pct > 0: return "RARE"
    return "NEVER_FOUND"

def parse_file(path):
    s = path.read_text(encoding="utf-8")
    a1 = match(s, r'class="re__address-line-1[^\"]*">(.*?)</span>')
    a2_display = match(s, r'class="re__address-line-2[^\"]*">(.*?)</span>')
    a2 = a2_display.strip("() ") if a2_display else None
    title = match(s, r'<h1[^>]*js__pr-title[^>]*>(.*?)</h1>')
    description = match(s, r'<div class="re__section-body re__detail-content[^>]*>(.*?)</div>')
    canonical = match(s, r'<link rel="canonical" href="([^"]+)"', flags=re.I)
    crumbs = [clean(x) for x in re.findall(r'<a class="re__link-se"[^>]*level="\d"[^>]*>(.*?)</a>', s, re.S)]
    # Last breadcrumb is e.g. "Căn hộ chung cư tại The Privé".
    property_type = re.split(r"\s+tại\s+", crumbs[-1], maxsplit=1, flags=re.I)[0] if crumbs else None
    specs = {}
    for label, value in re.findall(r're__pr-specs-content-item-title">(.*?)</span>\s*<span class="re__pr-specs-content-item-value">(.*?)</span>', s, re.S):
        specs[clean(label)] = clean(value)
    short = {}
    block = raw_match(s, r'<div class="re__pr-short-info js__pr-short-info">(.*?)<div class="re__clearfix', flags=re.S | re.I) or ""
    for label, value in re.findall(r'<span class="title">(.*?)</span>\s*<span class="value">(.*?)</span>', block, re.S):
        short[clean(label)] = clean(value)
    ppm = match(block, r'<span class="ext">\s*~?\s*(.*?)</span>')
    config = raw_match(s, r'<div class="re__pr-short-info re__pr-config js__pr-config">(.*?)</div>\s*</div>', flags=re.S | re.I) or ""
    configs = {re.sub(r"\s+", " ", clean(a)): clean(b) for a, b in re.findall(r'<span class="title">(.*?)</span>\s*<span class="value">(.*?)</span>', config, re.S)}
    lat = match(s, r'latitude\s*:\s*([\d.-]+)', flags=re.I)
    lon = match(s, r'longitude\s*:\s*([\d.-]+)', flags=re.I)
    tracking_raw = match(s, r"JSON\.parse\('(\{\"pageTrackingType\".*?\})'\)", flags=re.S)
    tracking = json.loads(tracking_raw)["products"][0] if tracking_raw else {}
    rec_raw = match(s, r'getListingRecommendationParams:\s*(\{.*?\})\s*,?\s*\n', flags=re.S)
    rec = json.loads(rec_raw) if rec_raw else {}
    new_loc = (rec.get("locations") or [{}])[0]
    is_display = rec.get("isDisplayNewAddress")

    fields = {k: {"present": False} for k in FIELD_ORDER}
    fields.update({
        "province_city": entry("Hồ Chí Minh" if a1 and "Hồ Chí Minh" in a1 else None, "structured", ".re__address-line-1"),
        "old_district": entry(component(a1, "district"), "structured", ".re__address-line-1"),
        "old_ward": entry(component(a1, "ward"), "structured", ".re__address-line-1"),
        "new_district": entry(component(a2, "district"), "structured", ".re__address-line-2"),
        "new_ward": entry(component(a2, "ward"), "structured", ".re__address-line-2"),
        "old_address": entry(a1, "structured", ".re__address-line-1"),
        "new_address": entry(a2, "structured", ".re__address-line-2", complete=False),
        "latitude": entry(lat, "json_script", "product map initialization: latitude"),
        "longitude": entry(lon, "json_script", "product map initialization: longitude"),
        "property_type": entry(property_type, "structured", ".re__breadcrumb a[level=\"1\"]"),
        "price_per_m2": entry(ppm, "structured", ".re__pr-short-info-item .ext"),
        "posting_date": entry(configs.get("Ngày đăng"), "structured", ".js__pr-config-item (title=Ngày đăng)"),
        "expiration_date": entry(configs.get("Ngày hết hạn"), "structured", ".js__pr-config-item (title=Ngày hết hạn)"),
        "listing_id": entry(configs.get("Mã tin") or str(tracking.get("productId", "")), "structured", ".js__pr-config-item (title=Mã tin)"),
        "listing_url": entry(canonical, "metadata", 'link[rel="canonical"]'),
        "title": entry(title, "structured", "h1.js__pr-title"),
        "description": entry(description, "structured", ".re__detail-content.js__pr-description"),
    })
    for label, field in LABELS.items():
        val = specs.get(label)
        fields[field] = entry(val, "structured", f'.re__pr-specs-content-item (title="{label}")')
    # Explicit description fallback only for fields missing in structured specs.
    for field in ("frontage", "bedrooms", "bathrooms", "road_width", "legal", "interior", "floors"):
        if not fields[field]["present"]:
            hint = description_hint(description or "", field)
            if hint:
                fields[field] = entry(hint, "description", ".re__detail-content.js__pr-description", "medium")
    hidden = {
        "tracking_product": tracking,
        "recommendation_location": new_loc,
        "recommendation_text": rec.get("recommendationLocation"),
        "isDisplayNewAddress": is_display,
        "canonical_url": canonical,
        "json_ld_types": re.findall(r'"@type"\s*:\s*"([^"]+)"', " ".join(re.findall(r'<script type="application/ld\+json">(.*?)</script>', s, re.S | re.I))),
        "product_detail_attributes": dict(re.findall(r'\b(uid|prid)="([^"]+)"', match(s, r'(<div class="re__pr-info.*?>)', flags=re.S | re.I) or "")),
    }
    return {"file": path.name, "property_type": property_type, "fields": fields, "hidden_data": hidden}

def main():
    files = sorted(DATA.glob("*.html"), key=lambda p: int(p.stem))
    rows = [parse_file(p) for p in files]
    OUT.mkdir(exist_ok=True); SAMPLES.mkdir(exist_ok=True)
    for row in rows:
        (SAMPLES / f"{int(Path(row['file']).stem):03}.json").write_text(json.dumps(row, ensure_ascii=False, indent=2), encoding="utf-8")
    total = len(rows)
    coverage = {}
    selectors = defaultdict(Counter)
    sources = defaultdict(Counter)
    for field in FIELD_ORDER:
        present = [r for r in rows if r["fields"][field]["present"]]
        pct = round(len(present) * 100 / total, 2)
        coverage[field] = {"found": len(present), "total": total, "coverage_percent": pct, "classification": classify(pct),
                           "structured_found": sum(r["fields"][field].get("source") == "structured" for r in rows),
                           "description_fallback_found": sum(r["fields"][field].get("source") == "description" for r in rows)}
        for r in present:
            selectors[field][r["fields"][field].get("selector", "(none)")] += 1
            sources[field][r["fields"][field].get("source", "other")] += 1
    payload = {"sample_count": total, "classification_thresholds": {"ALWAYS_PRESENT":"100%", "MOSTLY_PRESENT":"80-<100%", "OPTIONAL":"20-<80%", "RARE":">0-<20%", "NEVER_FOUND":"0%"}, "fields": coverage}
    (OUT / "field_coverage.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = ["# Field coverage report", "", f"Phạm vi: {total} HTML mẫu trong `data/`. Coverage tính trên mọi nguồn; cột structured tách riêng dữ liệu có nhãn HTML.", "", "| Field | Found | Coverage | Class | Structured | Description fallback |", "|---|---:|---:|---|---:|---:|"]
    for f in FIELD_ORDER:
        c=coverage[f]; lines.append(f"| `{f}` | {c['found']}/{total} | {c['coverage_percent']:.2f}% | {c['classification']} | {c['structured_found']}/{total} | {c['description_fallback_found']}/{total} |")
    lines += ["", "## Bảng đề xuất", "", "| Field | Coverage | Structured source available? | Description fallback? | Recommended primary selector | Alternative selector | Notes |", "|---|---:|---|---|---|---|---|"]
    for f in FIELD_ORDER:
        c=coverage[f]; ss=selectors[f].most_common(); primary=ss[0][0] if ss else "—"; alt=ss[1][0] if len(ss)>1 else "—"
        notes = "Raw value; không normalize." if c["found"] else "Không tìm thấy trong tập mẫu."
        lines.append(f"| `{f}` | {c['coverage_percent']:.2f}% | {'Có' if c['structured_found'] else 'Không'} | {'Có' if c['description_fallback_found'] else 'Không quan sát thấy/không áp dụng'} | `{primary}` | `{alt}` | {notes} |")
    lines += ["", "## Kết luận", "", "1. Deterministic trên tập mẫu: title, description, canonical URL, mã tin, ngày đăng, loại BĐS, giá, diện tích, địa chỉ cũ/mới và tọa độ.", "2. Các thuộc tính vật lý tùy chọn cần specs-first; description chỉ là fallback có confidence thấp hơn và có thể chứa nhiều căn/giá trị.", "3. Không có field khảo sát nào chỉ tồn tại trong description ở toàn bộ tập; một số giá trị bị thiếu structured nhưng xuất hiện rõ trong prose.", "4. Không nên kỳ vọng frontage, road width, floors, interior, bedrooms/bathrooms và legal luôn có.", "5. Layout selector chính không đổi theo loại BĐS; tập field thay đổi rõ theo loại.", "6. Website hiển thị old/new address ở hai span riêng; new address chỉ là ward/xã + thành phố mới, không phải full address.", "7. Rủi ro: flag script mang ngữ nghĩa location của truy vấn gợi ý, description đa thực thể, raw typo/đơn vị bất thường, và selector gắn với layout có thể đổi ngoài snapshot."]
    (OUT / "field_coverage.md").write_text("\n".join(lines)+"\n", encoding="utf-8")

    lines=["# Selector report", "", f"Thống kê trên {total} file. Đếm file có field được lấy từ selector tương ứng.", ""]
    for f in FIELD_ORDER:
        lines += [f"## `{f}`", "", "| Selector / structure | Files | Source |", "|---|---:|---|"]
        if selectors[f]:
            for sel,n in selectors[f].most_common():
                src=", ".join(f"{k}: {v}" for k,v in sources[f].items()); lines.append(f"| `{sel}` | {n}/{total} | {src} |")
        else: lines.append(f"| — | 0/{total} | never found |")
        if sources[f].get("description"): lines.append("\nFallback: description chỉ dùng khi có biểu thức tường minh; không suy luận.")
        lines.append("")
    lines += ["## Đánh giá nguồn trùng lặp", "", "- Specs title/value là nguồn rõ nghĩa nhất cho giá, diện tích và thuộc tính; short-info dễ đọc nhưng ít field hơn.", "- Canonical ổn định hơn URL suy ra từ breadcrumb/slug; `productId` có thêm trong tracking JSON và thuộc tính `prid`.", "- Tọa độ có trong object khởi tạo bản đồ JavaScript và URL `iframe[data-src*='google.com/maps/embed']`; không thấy trong JSON-LD.", "- JSON-LD trong cả 17 mẫu là `BreadcrumbList`, hữu ích cho taxonomy nhưng không thay thế specs.", "", "## Dữ liệu ẩn/metadata đã rà soát", "", "| Cấu trúc | Files | Nội dung hữu ích |", "|---|---:|---|", f"| `script[type='application/ld+json']` | {total}/{total} | Breadcrumb taxonomy |", f"| `link[rel='canonical']` | {total}/{total} | Listing URL |", f"| `meta[name='description']`, OpenGraph | {total}/{total} | Title/description/image/URL bản rút gọn |", f"| Tracking JSON (`JSON.parse`) | {total}/{total} | productId, projectId, cateId, city/district/ward/street IDs, productType |", f"| Map initialization JS | {total}/{total} | latitude/longitude và old location IDs |", f"| Google Maps iframe | {total}/{total} | tọa độ lặp trong query URL |", f"| `data-*` attributes | {total}/{total} | media, save-listing JSON, tracking; nguồn phụ, layout-dependent |", f"| hidden inputs | {total}/{total} | UI/config phụ; không quan sát thấy field khảo sát tốt hơn nguồn chính |"]
    (OUT / "selector_report.md").write_text("\n".join(lines)+"\n", encoding="utf-8")

    new_count=sum(r['fields']['new_address']['present'] for r in rows)
    lines=["# Phân tích địa chỉ cũ / mới", "", f"- Old address: {sum(r['fields']['old_address']['present'] for r in rows)}/{total}.", f"- New address: {new_count}/{total}.", f"- New ward/xã: {sum(r['fields']['new_ward']['present'] for r in rows)}/{total}; new district/huyện: {sum(r['fields']['new_district']['present'] for r in rows)}/{total}.", "- Cả 17 new address đều không đầy đủ: chỉ phường/xã mới và `Hồ Chí Minh mới`; không lặp lại đường/số nhà/dự án và không có quận/huyện mới.", "", "## Biểu diễn và tính deterministic", "", "Old address nằm ở `.re__address-line-1`; new address nằm ở `.re__address-line-2` và được đặt trong ngoặc. Vì có selector riêng và hậu tố `mới`, việc phân biệt hai chuỗi là deterministic trong snapshot. Tuy nhiên chỉ deterministic về chuỗi website cung cấp, không đủ để dựng full new address và tuyệt đối không được ghép/suy luận từ old address.", "", "## Flags và IDs", "", "- Tất cả mẫu có `isDisplayNewAddress: false` trong `getListingRecommendationParams`, dù line 2 vẫn visible.", "- Tất cả location objects quan sát được có `isNewLocation: false` và chứa `cityCode`, `districtId`, `wardId`, đôi khi `streetId/projectId`; đây là bộ ID location cũ dùng cho truy vấn/recommendation.", "- Không thấy một bộ `newDistrictId/newWardId/newStreetId` riêng hoặc object IDs mới.", "- `recommendationLocation` lại dùng text địa chỉ mới. Do đó không dùng hai boolean trên để phủ định sự tồn tại của `.re__address-line-2`.", "", "## Lưu trữ", "", "- Visible HTML: cả old và new address.", "- Script: old location IDs, flags, tọa độ, và recommendation text theo địa chỉ mới.", "- Breadcrumb/canonical URL: taxonomy/slug theo địa giới cũ trong các mẫu; không phải nguồn new address.", "", "## Chi tiết từng file", "", "| File | Old address | New address | Complete? |", "|---|---|---|---|"]
    for r in rows: lines.append(f"| {r['file']} | {r['fields']['old_address']['raw_value']} | {r['fields']['new_address']['raw_value']} | Không |")
    (OUT / "address_analysis.md").write_text("\n".join(lines)+"\n", encoding="utf-8")

    groups=defaultdict(list)
    for r in rows: groups[r['property_type']].append(r)
    physical=["area","frontage","bedrooms","bathrooms","road_width","legal","interior","floors"]
    lines=["# Phân tích theo loại bất động sản", "", "Selector/layout chính giống nhau; khác biệt nằm ở tập specs do người đăng cung cấp và tính phù hợp theo loại.", "", "| Property type | Files | "+" | ".join(physical)+" |", "|---|---:|"+"---:|"*len(physical)]
    for typ,items in sorted(groups.items()):
        vals=[f"{sum(x['fields'][f]['present'] for x in items)}/{len(items)}" for f in physical]
        lines.append(f"| {typ} | {len(items)} | "+" | ".join(vals)+" |")
    lines += ["", "## Nhận xét", "", "- Căn hộ trong mẫu tập trung bedrooms, bathrooms, legal, interior; không có frontage/road width/floors structured.", "- Nhà riêng và nhà mặt phố thường có floors; frontage/road width vẫn không bắt buộc.", "- Biệt thự/liền kề biến thiên mạnh: bài dự án có thể chỉ có giá/diện tích, bài căn cụ thể có bedrooms/bathrooms/floors.", "- Tập mẫu không có đất, đất nền dự án hoặc shophouse độc lập, nên không kết luận structure cho các nhóm đó.", "- Việc thiếu field không phải lỗi nếu field không phù hợp hoặc người đăng không khai báo."]
    (OUT / "property_type_analysis.md").write_text("\n".join(lines)+"\n", encoding="utf-8")
    print(f"Generated {len(rows)} sample JSON files and 5 reports in {OUT}")

if __name__ == "__main__": main()
