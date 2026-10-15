"""Chạy 20 ca khách hàng thật của mode dự đoán qua API thật và chấm giá bằng dữ liệu thật.

    PYTHONPATH=. python tests/prediction/run_realistic.py [http://localhost:8013] [số lần/ca]
        [--ids R01,R07]

Mỗi ca chạy REPEAT lần (mỗi lần một conversation_id mới); một lần sai là FAIL. Giá/m² dự đoán
phải nằm trong [P10, P90] của tin đăng cùng quận + loại + diện tích gần giống ở DB housing_dev
(chỉ đọc), nhóm < 10 mẫu thì nới dần (ghi chú). data/price_training.csv (bản sao data.csv của
đồ án 1) chỉ để đối chiếu thêm; thiếu file thì bỏ phần đối chiếu, không crash.
Lượt có "side_answer" (câu hỏi/what-if) không phải khối kết quả: chỉ kiểm giá giữ nguyên và,
với "what_if", số "trước" trong câu "Giá/m² trước → sau" bằng giá của lượt trước.
Oracle không import code hệ thống. Ghi realistic_report.md và realistic_results.json.
"""

import argparse
import json
import os
import re
import statistics
import time
import unicodedata
from pathlib import Path

import httpx
import numpy as np
import pandas as pd
import psycopg

HERE = Path(__file__).parent
CASES_PATH = HERE / "realistic_cases.json"
REPORT_PATH = HERE / "realistic_report.md"
RESULTS_PATH = HERE / "realistic_results.json"
CSV_PATH = HERE.parents[1] / "data/price_training.csv"  # scripts/train_price_model.py chép sang
DB_URL = os.environ.get(
    "ORACLE_DB_URL", "postgresql://postgres:123456789@localhost:5432/housing_dev"
)

MIN_GROUP = 10
EDGE_TOLERANCE = 0.03  # sai số lấy mẫu của oracle: lệch ≤ 3% quanh [P10,P90] là PASS (biên)
PRICE_TOLERANCE = 0.02  # hai lần chạy cùng hội thoại lệch giá quá mức này là không ổn định
AREA_BAND = (0.6, 1.6)
CENTER = (10.7769, 106.7009)
KEYS = ("property_type", "district", "area", "bedrooms", "frontage", "floors")
REQUIRED = ("property_type", "district", "area")
# Tên loại ở DB / mã loại ở data.csv theo tên người dùng thấy
DB_TYPES = {"căn hộ chung cư": "Căn hộ chung cư", "nhà riêng": "Nhà riêng",
            "nhà biệt thự, liền kề": "Nhà biệt thự, liền kề", "nhà mặt phố": "Nhà mặt phố",
            "bán đất": "Bán đất"}
CSV_TYPES = {"căn hộ chung cư": 0, "nhà riêng": 2, "nhà biệt thự, liền kề": 3,
             "nhà mặt phố": 4, "bán đất": 7}
CSV_DISTRICTS = [  # mã 0-23 theo retrain.py của đồ án 1
    "bình chánh", "bình tân", "bình thạnh", "cần giờ", "củ chi", "gò vấp", "hóc môn", "nhà bè",
    "phú nhuận", "quận 1", "quận 10", "quận 11", "quận 12", "quận 2", "quận 3", "quận 4",
    "quận 5", "quận 6", "quận 7", "quận 8", "quận 9", "thủ đức", "tân bình", "tân phú"]
QUESTIONS = {"loại nhà đất nào": "property_type", "quận/huyện nào": "district",
             "Diện tích bao nhiêu": "area", "chưa xác định được vị trí": "district"}
# Từ chỉ loại nhà/đệm: địa chỉ chỉ gồm các từ này (và tên quận) thì không phải địa chỉ
GENERIC_WORDS = {
    "chung", "cu", "can", "ho", "nha", "rieng", "biet", "thu", "lien", "ke", "mat", "pho", "tien",
    "dat", "nen", "trong", "hem", "villa", "o", "tai", "khu", "duong", "xe", "hoi", "cua", "toi",
    "minh",
}
UNCONFIRMED = "CHƯA xác nhận bằng Goong (dùng tâm quận)"
OPTIONAL_LABELS = {"phòng ngủ": "bedrooms", "mặt tiền": "frontage", "số tầng": "floors"}


def plain(text: str) -> str:
    """Chữ thường, bỏ dấu, gộp khoảng trắng."""
    text = unicodedata.normalize("NFD", text.lower().replace("đ", "d"))
    return re.sub(r"\s+", " ", "".join(c for c in text if unicodedata.category(c) != "Mn")).strip()


def haversine_km(lat, lon):
    lat1, lon1, lat2, lon2 = map(np.radians, (lat, lon, *CENTER))
    a = (np.sin((lat2 - lat1) / 2) ** 2
         + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2)
    return 6371 * 2 * np.arcsin(np.sqrt(a))


def summarize(values, source: str, note: str = "") -> dict:
    arr = np.asarray(values, dtype=float)
    p10, p25, p50, p75, p90 = np.percentile(arr, [10, 25, 50, 75, 90])
    return {"n": len(arr), "p10": p10, "p25": p25, "median": p50, "p75": p75, "p90": p90,
            "source": source, "note": note}


class Reference:
    """Khoảng giá/m² tham chiếu từ tin đăng DB (chính) và data.csv (đối chiếu)."""

    def __init__(self):
        self.conn = psycopg.connect(DB_URL, autocommit=True)
        self.conn.read_only = True
        self.csv = pd.read_csv(CSV_PATH) if CSV_PATH.exists() else None
        self._distances: dict[str, np.ndarray] = {}

    def _db(self, district, kind, area=None) -> list[float]:
        sql = ("SELECT price_per_m2 FROM listings WHERE district_old = %s AND property_type = %s "
               "AND price_per_m2 > 0 AND area > 0 AND transaction_type = 'Bán'")
        args = [district, DB_TYPES[kind]]
        if area:
            sql += " AND area BETWEEN %s AND %s"
            args += [area * AREA_BAND[0], area * AREA_BAND[1]]
        return [row[0] for row in self.conn.execute(sql, args).fetchall()]

    def _csv(self, district, kind, area=None) -> list[float]:
        if self.csv is None:
            return []
        df = self.csv
        mask = ((df["địa chỉ"] == CSV_DISTRICTS.index(district.lower()))
                & (df["loại nhà đất"] == CSV_TYPES[kind]))
        if area:
            mask &= df["diện tích"].between(area * AREA_BAND[0], area * AREA_BAND[1])
        return df.loc[mask, "giá/m2"].dropna().tolist()

    def _district_any_type(self, district) -> list[float]:
        sql = ("SELECT price_per_m2 FROM listings WHERE district_old = %s AND price_per_m2 > 0 "
               "AND transaction_type = 'Bán'")
        return [row[0] for row in self.conn.execute(sql, [district]).fetchall()]

    def price(self, district: str, kind: str, area: float) -> dict:
        """Nhóm so sánh đầu tiên đủ MIN_GROUP mẫu; luôn kèm số liệu data.csv để đối chiếu."""
        csv_band = self._csv(district, kind, area)
        csv_info = summarize(csv_band, "csv", "csv cùng diện tích") if len(csv_band) else None
        tiers = [
            (self._db(district, kind, area), "DB", "DB cùng quận+loại+diện tích 0,6-1,6x"),
            (self._db(district, kind), "DB", "THƯA: nới ra mọi diện tích của quận+loại (DB)"),
            (csv_band, "csv", "THƯA: DB thưa, dùng data.csv cùng quận+loại+diện tích"),
            (self._csv(district, kind), "csv", "THƯA: data.csv quận+loại, mọi diện tích"),
            (self._district_any_type(district), "DB", "RẤT THƯA: cả quận, mọi loại (DB)"),
        ]
        for values, source, note in tiers:
            if len(values) >= MIN_GROUP:
                return summarize(values, source, note) | {"csv": csv_info}
        return summarize(tiers[-1][0], "DB", "RẤT THƯA: <10 mẫu kể cả cả quận") | {"csv": csv_info}

    def distance_range(self, district: str) -> tuple[float, float]:
        """Khoảng cách tới trung tâm hợp lý của quận: P2-P98 của tin đăng ± 1 km."""
        if district not in self._distances:
            rows = self.conn.execute(
                "SELECT latitude, longitude FROM listings WHERE district_old = %s "
                "AND latitude IS NOT NULL AND NOT ('coords_outside_hcm' = ANY(quality_flags))",
                [district]).fetchall()
            lat, lon = np.array(rows).T
            self._distances[district] = haversine_km(lat, lon)
        low, high = np.percentile(self._distances[district], [2, 98])
        return max(0.0, low - 1), high + 1


class RealisticRunner:
    """Chạy các ca, chấm từng lượt, viết báo cáo."""

    def __init__(self, base_url: str, repeat: int):
        self.client = httpx.Client(base_url=base_url, timeout=120)
        self.repeat = repeat
        self.reference = Reference()
        self.ranges: dict[tuple, dict] = {}
        self.changes: list[dict] = []

    # ---------- chạy ----------
    def run_case(self, case: dict) -> dict:
        runs = [self._converse(case) for _ in range(self.repeat)]
        issues = [f"[lần {i + 1}] {msg}" for i, run in enumerate(runs) for msg in run["issues"]]
        warnings = [w for run in runs for w in run["warnings"]]
        for run in runs[1:]:
            found, notes = self._compare_runs(runs[0], run)
            issues += found
            warnings += notes
        verdicts = {t["price_check"]["verdict"] for run in runs for t in run["turns"]
                    if t["price_check"]}
        status = "FAIL" if issues else (
            "KNOWN-LIMIT" if "LIMIT" in verdicts else "PASS-biên" if "EDGE" in verdicts else "PASS")
        has_address = any(spec.get("address_has") for spec in case["turns"])
        unconfirmed = has_address and any(
            t["price_check"] and t["price_check"]["source"] == "tâm quận"
            for run in runs for t in run["turns"])
        return {"id": case["id"], "persona": case["persona"], "tags": case["tags"],
                "pass": not issues, "status": status, "goong_unconfirmed": unconfirmed,
                "issues": issues, "warnings": warnings, "runs": runs}

    @staticmethod
    def _compare_runs(first: dict, other: dict) -> tuple[list[str], list[str]]:
        """Hai lần chạy phải cùng status + fields; giá lệch > PRICE_TOLERANCE là lỗi."""
        issues, notes = [], []
        for number, (a, b) in enumerate(zip(first["turns"], other["turns"], strict=False), 1):
            ra, rb = a["reply"], b["reply"]
            fields = [{k: v for k, v in r["fields"].items() if k != "address"} for r in (ra, rb)]
            if (ra["status"], fields[0]) != (rb["status"], fields[1]):
                issues.append(f"KHÔNG ỔN ĐỊNH lượt {number}: {ra['status']} {fields[0]} "
                              f"vs {rb['status']} {fields[1]}")
            pa, pb = ra["prediction"], rb["prediction"]
            if pa and pb and pa["price_per_m2"] != pb["price_per_m2"]:
                gap = abs(pa["price_per_m2"] / pb["price_per_m2"] - 1)
                message = (f"lượt {number}: giá hai lần chạy khác nhau {pa['price_per_m2']} vs "
                           f"{pb['price_per_m2']} ({gap:.1%}; địa chỉ {ra['fields']['address']!r} "
                           f"vs {rb['fields']['address']!r})")
                (issues if gap > PRICE_TOLERANCE else notes).append(
                    ("KHÔNG ỔN ĐỊNH " if gap > PRICE_TOLERANCE else "") + message)
        if len(first["turns"]) != len(other["turns"]):
            issues.append("KHÔNG ỔN ĐỊNH: số lượt chạy được khác nhau")
        return issues, notes

    def _converse(self, case: dict) -> dict:
        conversation_id, previous, said = None, None, []
        turns, issues, warnings = [], [], []
        for number, spec in enumerate(case["turns"], 1):
            body = {"mode": "prediction", "message": spec["user"]}
            if conversation_id:
                body["conversation_id"] = conversation_id
            started = time.perf_counter()
            response = self.client.post("/api/v1/chat", json=body)
            elapsed = time.perf_counter() - started
            if response.status_code != 200:
                issues.append(f"lượt {number}: HTTP {response.status_code} {response.text[:200]}")
                break
            reply = response.json()
            if conversation_id and reply["conversation_id"] != conversation_id:
                issues.append(f"lượt {number}: conversation_id đổi giữa chừng")
            conversation_id = reply["conversation_id"]
            said.append(spec["user"])
            found, notes, check = self._check_turn(number, spec, reply, previous, said)
            issues += found
            warnings += notes
            turns.append({"user": spec["user"], "reply": reply, "seconds": round(elapsed, 2),
                          "price_check": check})
            previous = reply
        return {"turns": turns, "issues": issues, "warnings": warnings,
                "conversation_id": conversation_id}

    # ---------- chấm ----------
    def _check_turn(self, number, spec, reply, previous, said):
        tag, issues, warnings = f"lượt {number} ({spec['user']!r})", [], []
        fields = reply["fields"]

        def fail(message):
            issues.append(f"{tag}: {message}")

        if reply["status"] != spec["status"]:
            fail(f"status {reply['status']!r}, mong {spec['status']!r}")
        if reply["mode"] != "prediction":
            fail(f"mode {reply['mode']!r}")
        if not spec.get("fields_free"):
            self._check_fields(spec.get("fields", {}), spec.get("warn", {}), fields, fail,
                               warnings, tag)
        missing = [k for k in REQUIRED if fields.get(k) is None]
        if reply["missing"] != missing:
            fail(f"missing {reply['missing']} không khớp fields (mong {missing})")
        if missing and (reply["prediction"] or reply["status"] == "predicted"):
            fail(f"dự đoán khi thiếu trường bắt buộc {missing}")
        if reply["status"] in ("collecting", "ready") and reply["prediction"]:
            fail("còn kết quả dự đoán cũ trong lượt chưa dự đoán")
        self._check_answer(spec, reply, said, fail, lambda m: warnings.append(f"{tag}: {m}"))
        check = None
        if spec.get("side_answer"):  # câu hỏi/what-if: không có khối kết quả để chấm giá
            self._check_side_answer(spec, reply, previous, fail)
        elif reply["status"] == "predicted" and reply["prediction"]:
            check = self._check_prediction(spec, reply, previous, fail, warnings, tag)
        return issues, warnings, check

    @staticmethod
    def _check_side_answer(spec, reply, previous, fail):
        """Kết quả cũ giữ nguyên; what-if thì số "trước" phải là giá của lượt trước."""
        before = previous and previous["prediction"]
        if spec.get("same_prediction") and reply["prediction"] != before:
            fail("giá thay đổi dù khách chỉ hỏi/giả định")
        if spec.get("what_if"):
            found = re.search(r"Giá/m² trước → sau: ([\d.]+) → ([\d.]+)", reply["answer"])
            if not found or not before or float(found[1]) != round(before["price_per_m2"], 2):
                fail(f"what-if thiếu/không khớp 'trước → sau': {reply['answer'][:150]!r}")
            elif float(found[2]) <= 0:
                fail(f"what-if giá sau không hợp lệ: {found[2]}")

    @staticmethod
    def _check_fields(expected, warn, fields, fail, warnings, tag):
        for key in KEYS:
            want, got = expected.get(key), fields.get(key)
            allowed = want if isinstance(want, list) else [want]
            if got in allowed:
                continue
            if got in warn.get(key, []):
                warnings.append(f"{tag}: {key}={got!r} hơi khác kỳ vọng {allowed} (mơ hồ ngôn ngữ)")
            elif want is None or (isinstance(want, list) and all(w is None for w in want)):
                fail(f"BỊA/GHI THỪA {key}={got!r}, khách không nói")
            else:
                fail(f"fields.{key}={got!r}, mong {allowed}")

    @staticmethod
    def _check_answer(spec, reply, said, fail, warn):
        answer, fields = reply["answer"], reply["fields"]
        asked = {field for marker, field in QUESTIONS.items() if marker in answer}
        for field in asked:
            if fields.get(field) is not None:
                fail(f"HỎI LẠI trường đã có: hỏi {field} nhưng fields.{field}={fields[field]!r}")
        if spec.get("asks") and spec["asks"] not in asked:
            fail(f"phải hỏi {spec['asks']!r}, câu trả lời: {answer[:150]!r}")
        if spec.get("asks_any") and not asked:
            fail(f"phải hỏi một trường bắt buộc, câu trả lời: {answer[:150]!r}")
        offer = re.search(r"có thể thêm (.+?) để", answer)
        for label in (offer.group(1).split(", ") if offer else []):
            if fields.get(OPTIONAL_LABELS.get(label, "")) is not None:
                fail(f"mời bổ sung {label!r} dù đã có {fields[OPTIONAL_LABELS[label]]!r}")
        for needle in spec.get("answer_has", []):
            if needle not in answer:
                fail(f"câu trả lời thiếu {needle!r}")
        for needle in spec.get("answer_hasnt", []):
            if needle in answer:
                fail(f"câu trả lời không được chứa {needle!r}")
        address = fields.get("address")
        if spec.get("address_has") and plain(spec["address_has"]) not in plain(address or ""):
            fail(f"địa chỉ {address!r} thiếu {spec['address_has']!r}")
        if address and plain(address) != plain(fields.get("district") or "") and (
            plain(address) not in plain(" ".join(said))
        ):
            fail(f"BỊA địa chỉ {address!r}: khách chưa từng nói")
        if address and plain(address) != plain(fields.get("district") or ""):
            words = set(plain(address).split())
            district_words = set(plain(fields.get("district") or "").split())
            if not words - GENERIC_WORDS - district_words:
                fail(f"ĐỊA CHỈ RÁC {address!r}: chỉ là từ chỉ loại nhà, không phải địa chỉ "
                     "(sẽ được đem đi geocode)")
            elif words & GENERIC_WORDS - {"khu", "duong", "pho"}:
                warn(f"địa chỉ {address!r} lẫn từ chỉ loại nhà (làm kết quả geocode/giá đổi)")

    def _check_prediction(self, spec, reply, previous, fail, warnings, tag) -> dict:
        prediction, fields = reply["prediction"], reply["fields"]
        price, total, area = prediction["price_per_m2"], prediction["total_price"], fields["area"]
        if abs(price * area - total) > 0.06:
            fail(f"giá/m² x diện tích = {price * area:.2f} != tổng {total}")
        for text in (f"{price:.2f} triệu VND/m²", f"{total:.1f} triệu VND", fields["district"]):
            if text not in reply["answer"]:
                fail(f"câu trả lời không khớp số liệu, thiếu {text!r}")
        if not prediction["price_per_m2_low"] <= price <= prediction["price_per_m2_high"]:
            fail("giá/m² ngoài khoảng tham khảo của chính mô hình")
        if spec.get("same_prediction") and (
            not previous or not previous["prediction"] or previous["prediction"] != prediction
        ):
            fail("giá thay đổi dù khách chỉ hỏi lại/giải thích")
        key = (fields["district"], fields["property_type"], area)
        ref = self.ranges.setdefault(key, self.reference.price(*key))
        verdict = self._verdict(price, ref)
        detail = (f"GIÁ/M² {price:.1f} so với [P10,P90] = [{ref['p10']:.1f}, {ref['p90']:.1f}] "
                  f"(median {ref['median']:.1f}, n={ref['n']}, {ref['note']})")
        if verdict == "EDGE":
            warnings.append(f"{tag}: PASS (biên, dung sai {EDGE_TOLERANCE:.0%}): {detail}")
        elif verdict == "OUT" and spec.get("known_limit") and "Lưu ý" in reply["answer"]:
            verdict = "LIMIT"
            warnings.append(f"{tag}: KNOWN-LIMIT (FAIL giá / PASS cảnh báo): {detail}")
        elif verdict == "OUT":
            fail(f"NGOÀI [P10,P90]: {detail}")
        low_d, high_d = self.reference.distance_range(fields["district"])
        if not low_d <= prediction["distance_to_center_km"] <= high_d:
            fail(f"khoảng cách tới trung tâm {prediction['distance_to_center_km']} km ngoài "
                 f"khoảng hợp lý của {fields['district']} [{low_d:.1f}, {high_d:.1f}] km")
        if "THƯA" in ref["note"]:
            warnings.append(f"{tag}: nhóm so sánh thưa ({ref['note']}, n={ref['n']})")
        return {"key": list(key), "price": price, "total": total, "verdict": verdict,
                "iqr": ref["p25"] <= price <= ref["p75"], "ref": ref,
                "source": "tâm quận" if "dùng tâm quận" in reply["answer"] else "Goong",
                "distance": prediction["distance_to_center_km"]}

    @staticmethod
    def _verdict(price: float, ref: dict) -> str:
        """IN trong [P10,P90]; EDGE lệch ≤ EDGE_TOLERANCE ngoài biên; còn lại OUT."""
        if ref["p10"] <= price <= ref["p90"]:
            return "IN"
        if ref["p10"] * (1 - EDGE_TOLERANCE) <= price <= ref["p90"] * (1 + EDGE_TOLERANCE):
            return "EDGE"
        return "OUT"

    @staticmethod
    def _range_text(info: dict | None) -> str:
        if not info:
            return "không có mẫu"
        return (f"{info['p10']:.0f} - {info['median']:.0f} - {info['p90']:.0f} "
                f"(n={info['n']})")

    def _price_rows(self, results: list[dict]) -> list[str]:
        header = ("| Ca | Quận | Loại | m² | Dự đoán/m² | Tổng (tr) | DB P10 - median - P90 | "
                  "data.csv P10 - median - P90 | Nhóm so sánh | km | Kết quả |")
        rows = [header, "|---|---|---|---|---|---|---|---|---|---|---|"]
        for r in results:
            for turn in r["runs"][0]["turns"]:
                c = turn["price_check"]
                if not c:
                    continue
                ref = c["ref"]
                db_text = self._range_text(ref) if ref["source"] == "DB" else "-"
                verdict = c["verdict"] + (" (IQR)" if c["iqr"] else "")
                rows.append(
                    f"| {r['id']} | {c['key'][0]} | {c['key'][1]} | {c['key'][2]:g} | "
                    f"{c['price']} | {c['total']} | {db_text} | {self._range_text(ref['csv'])} | "
                    f"{ref['note']} | {c['distance']} | {verdict} |")
        return rows

    def write_report(self, results: list[dict]) -> str:
        counts = {k: sum(r["status"] == k for r in results)
                  for k in ("PASS", "PASS-biên", "KNOWN-LIMIT", "FAIL")}
        passed = [r for r in results if r["pass"]]
        seconds = [t["seconds"] for r in results for run in r["runs"] for t in run["turns"]]
        lines = [
            "# Báo cáo kiểm thử thực tế mode dự đoán giá\n",
            (f"**KẾT QUẢ: {len(passed)}/{len(results)} ca không FAIL {counts}** "
             f"(mỗi ca chạy {self.repeat} lần, "
             f"một lần sai là FAIL). Số lượt API: {len(seconds)}, trung bình "
             f"{statistics.mean(seconds):.2f}s/lượt, p95 {np.percentile(seconds, 95):.2f}s.\n"),
            "| Ca | Mô tả | Kết quả | Số lỗi | Số cảnh báo | Ghi chú Goong |",
            "|---|---|---|---|---|---|",
        ]
        lines += [f"| {r['id']} | {r['persona']} | {r['status']} | "
                  f"{len(r['issues'])} | {len(set(r['warnings']))} | "
                  f"{UNCONFIRMED if r['goong_unconfirmed'] else ''} |"
                  for r in results]
        lines += ["", "## Chấm giá/m² theo dữ liệu thật (lần chạy 1)", ""]
        lines += self._price_rows(results)
        lines += ["", "(IQR: giá nằm cả trong [P25,P75] của nhóm so sánh)", "",
                  "## Thay đổi bộ test", ""]
        lines += [f"- {c['id']}: {c['what']}. Lý do: {c['why']}" for c in self.changes]
        lines += ["", "## Cảnh báo (không tính FAIL)", ""]
        for r in results:
            for warning in sorted(set(r["warnings"])):
                lines.append(f"- {r['id']}: {warning}")
        lines += ["", "## Ca FAIL", ""]
        for r in (r for r in results if not r["pass"]):
            lines += [f"### {r['id']} — {r['persona']}", ""]
            lines += [f"- {issue}" for issue in r["issues"]]
            failed_run = next((run for run in r["runs"] if run["issues"]), r["runs"][0])
            lines += ["", "Hội thoại thực tế của lần chạy lỗi:", "", "```text"]
            for turn in failed_run["turns"]:
                reply = turn["reply"]
                lines += [f"KHÁCH: {turn['user']}", f"BOT [{reply['status']}] {reply['summary']}",
                          *(f"    {line}" for line in reply["answer"].splitlines()), ""]
            lines.append("```\n")
        if not any(not r["pass"] for r in results):
            lines.append("Không có ca FAIL.")
        return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("base_url", nargs="?", default="http://localhost:8013")
    parser.add_argument("repeat", nargs="?", type=int, default=2)
    parser.add_argument("--ids", default="")
    args = parser.parse_args()
    data = json.loads(CASES_PATH.read_text("utf-8"))
    cases = data["cases"]
    if args.ids:
        cases = [c for c in cases if c["id"] in args.ids.split(",")]
    runner = RealisticRunner(args.base_url, args.repeat)
    runner.changes = data["changes"]
    results = []
    for case in cases:
        result = runner.run_case(case)
        results.append(result)
        print(f"{result['id']} {result['status']} - {case['persona']}")
        for issue in result["issues"]:
            print(f"    {issue}")
    REPORT_PATH.write_text(runner.write_report(results), "utf-8")
    RESULTS_PATH.write_text(json.dumps(results, ensure_ascii=False, indent=1, default=str), "utf-8")
    failed = [r["id"] for r in results if not r["pass"]]
    print(f"\n{len(results) - len(failed)}/{len(results)} ca PASS; FAIL: {failed or 'không'}")
    return int(bool(failed))


if __name__ == "__main__":
    raise SystemExit(main())
