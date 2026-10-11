"""Harness chấm mode recommendation theo docs/tasks/hybrid-search.md (mục 6, 7).

Ví dụ (chạy từ ``housing-backend/housing-backend``)::

    python tests/recommend/run_eval.py --oracle            # chỉ oracle, không gọi hệ thống
    python tests/recommend/run_eval.py --oracle --write-min-results
    python tests/recommend/run_eval.py                     # chạy đủ 50 kịch bản qua API
    python tests/recommend/run_eval.py --ids C03,C17 --via service

Hệ thống được gọi qua giao diện spec mục 5: ``POST /api/v1/recommend/chat`` (TestClient,
mặc định) hoặc ``RecommendationService.chat`` (``--via service``). Oracle là SQL độc lập
trong ``oracle.py``; không import hàm lọc của hệ thống.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import re
import sys
import time
from datetime import date
from pathlib import Path

from oracle import RELAX_PRICE_FACTOR, SqlOracle

HERE = Path(__file__).resolve().parent
BACKEND_ROOT = HERE.parents[1]
REPO_ROOT = BACKEND_ROOT.parents[1]
SCENARIOS_PATH = HERE / "scenarios.json"
REPORT_PATH = HERE / "report.md"
EXTRA_SCENARIOS_PATH = HERE / "scenarios_extra.json"
EXTRA_REPORT_PATH = HERE / "report_extra.md"
MISSING = "tin không ghi"
CHAT_PATH = "/api/v1/recommend/chat"
EVAL_DATABASE_URL = "postgresql+asyncpg://postgres:123456789@localhost:5432/housing_dev"

CATEGORY_QUOTA = {
    "progressive": 8, "refine": 7, "relax": 5, "switch_area": 4, "detail_compare": 7,
    "price_units": 3, "new_address": 3, "soft_semantic": 4, "no_results_recover": 3,
    "reset": 2, "out_of_scope_mid": 3, "injection": 1,
}
SEARCH_STATUSES = ("ok", "no_results")
# (mã, ngưỡng tỉ lệ đạt, mô tả) — [S7] chấm tay, [S13] dùng p95.
CRITERIA = [
    ("S1", 1.0, "Không tin nào vi phạm điều kiện cứng cộng dồn"),
    ("S2", 1.0, "status đúng kỳ vọng"),
    ("S3", 0.95, "Trường expect_constraints đúng"),
    ("S4", 1.0, "Lượt ok có >= min_results tin"),
    ("S5", 1.0, "answer không chứa ID/URL ngoài dữ liệu lượt đó"),
    ("S6", 1.0, "Chỉ tin còn hạn tại as_of"),
    ("S8", 1.0, "referenced_ids đúng tin được hỏi"),
    ("S9", 1.0, "Không rò state sau reset / giữa hội thoại"),
    ("S14", 1.0, "relax_options khớp oracle"),
    ("S15", 1.0, "Không 2 tin cùng nhóm đăng lại trong Top 5"),
    ("X1", 1.0, "Câu trả lời đủ ý (expect_answer_all / expect_answer_not)"),
    ("X2", 1.0, "Câu hỏi 'nhất' trả đúng căn theo DB (expect_superlative)"),
    ("X3", 1.0, "Chi tiết tin có đủ thuộc tính DB (expect_detail_complete)"),
]
ANSWER_TOKEN = re.compile(r"\{(\w+)@(\d+)(?::([^}]*))?\}")
UNIT_COLUMNS = ("area", "bedrooms", "bathrooms", "floors", "frontage", "road_width")
P95_LIMIT_S = 8.0
# Ước tính chi phí gpt-4o-mini: 2 lần gọi/lượt, giá USD cho 1 triệu token.
TOKENS_IN_PER_CALL, TOKENS_OUT_PER_CALL = 2000, 300
PRICE_IN_PER_M, PRICE_OUT_PER_M = 0.15, 0.60
REF_PATTERN = re.compile(r"\{ref:(\d+)\}")
ID_PATTERN = re.compile(r"\[Tin\s*([0-9A-Za-z_-]+)\]|\b(\d{8})\b")
URL_PATTERN = re.compile(r"https?://[^\s)\]>\"']+")
TY_PATTERN = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*(?:tỷ|ty)\b"
    r"(?:[ \t]*(\d{1,3})\b(?!\s*(?:m|%|km|phòng|pn|tầng))(?:\s*(?:triệu|trieu))?)?",
    re.IGNORECASE)
TRIEU_PATTERN = re.compile(
    r"(\d{1,3}(?:\.\d{3})+|\d+(?:[.,]\d+)?)\s*(?:triệu|trieu|tr)\b", re.IGNORECASE)
PRICE_TOLERANCE = 0.01
# Câu hỏi bổ sung soạn sẵn của hệ thống có ví dụ "dưới 3 tỷ": không phải số liệu tin.
EXAMPLE_TEXT = "ví dụ: dưới 3 tỷ"
ID_FIELDS = {"district_names": "district_ids", "new_ward_names": "new_ward_ids"}
RELAX_FIELDS = ("near_pois", "price_max", "property_types", "location")


def money_mentions(text: str) -> list[tuple[str, float]]:
    """Tách số tiền trong câu trả lời, đổi sang triệu: "3 tỷ 6", "2,5 tỷ", "1.500 triệu"."""
    found = []
    for m in TY_PATTERN.finditer(text):
        head, tail = m.group(1).replace(",", "."), m.group(2)
        value = float(head) * 1000
        if tail and "." not in head:
            value += int(tail) * 10 ** (3 - len(tail))
        found.append((m.group(0), value))
    rest = TY_PATTERN.sub(" ", text)
    for m in TRIEU_PATTERN.finditer(rest):
        raw = m.group(1)
        number = raw.replace(".", "") if re.fullmatch(r"\d{1,3}(?:\.\d{3})+", raw) else raw
        found.append((m.group(0), float(number.replace(",", "."))))
    return found


def number_text(value: float) -> str:
    """53.0 -> '53', 46.6 -> '46,6' (cùng cách người đọc thấy số trong câu trả lời)."""
    return f"{value:g}".replace(".", ",")


def money_text(million: float) -> str:
    """2800 -> '2,8 tỷ', 900 -> '900 triệu'."""
    value, unit = (million / 1000, "tỷ") if million >= 1000 else (million, "triệu")
    return f"{value:.3f}".rstrip("0").rstrip(".").replace(".", ",") + f" {unit}"


def _poi_key(poi: dict) -> tuple[str, int]:
    return poi["poi_type"], int(poi["max_distance_m"])


class SystemNotReady(RuntimeError):
    """Hệ thống recommendation chưa được cài đặt hoặc chưa mở giao diện spec mục 5."""


class RecommendEval:
    """Chạy kịch bản hội thoại, chấm từng lượt bằng oracle SQL và ghi report."""

    def __init__(self, via: str = "api", oracle: SqlOracle | None = None,
                 extra: bool = False) -> None:
        self.via = via
        self.oracle = oracle or SqlOracle()
        self.scenarios_path = EXTRA_SCENARIOS_PATH if extra else SCENARIOS_PATH
        self.report_path = EXTRA_REPORT_PATH if extra else REPORT_PATH
        self.scenarios = self.load_scenarios(self.scenarios_path)
        self._client = None
        self._service = None

    @staticmethod
    def load_scenarios(path: Path = SCENARIOS_PATH) -> list[dict]:
        return json.loads(path.read_text(encoding="utf-8"))

    def close(self) -> None:
        if self._client is not None:
            self._client.__exit__(None, None, None)
        self.oracle.close()

    # ------------------------------------------------------------------ oracle
    def oracle_table(self) -> list[dict]:
        """Đếm tin thỏa cho mọi lượt tìm kiếm; ``problem`` khác rỗng là kịch bản sai."""
        rows = []
        for sc in self.scenarios:
            as_of = date.fromisoformat(sc["as_of"])
            for i, turn in enumerate(sc["turns"], 1):
                if turn["expect_status"] not in SEARCH_STATUSES:
                    continue
                expected = turn.get("expect_constraints", {})
                n = self.oracle.count(expected, as_of)
                row = {"id": sc["id"], "turn": i, "status": turn["expect_status"],
                       "count": n, "min_results": min(5, n), "problem": ""}
                if turn["expect_status"] == "ok" and n == 0:
                    row["problem"] = "lượt ok nhưng oracle = 0"
                if turn["expect_status"] == "no_results":
                    row["min_results"] = 0
                    row["relax"] = self.oracle.relax_counts(expected, as_of)
                    if n:
                        row["problem"] = "lượt no_results nhưng oracle > 0"
                if "min_results" in turn and turn["min_results"] != row["min_results"]:
                    row["problem"] += f" min_results lưu {turn['min_results']} != oracle"
                rows.append(row)
        return rows

    def write_min_results(self, rows: list[dict]) -> None:
        """Ghi ``min_results`` vào scenarios.json, giữ định dạng mỗi lượt một dòng."""
        by_turn = {(r["id"], r["turn"]): r["min_results"] for r in rows}
        for sc in self.scenarios:
            for i, turn in enumerate(sc["turns"], 1):
                if (sc["id"], i) in by_turn:
                    turn["min_results"] = by_turn[(sc["id"], i)]
        blocks = []
        for sc in self.scenarios:
            head = json.dumps({k: v for k, v in sc.items() if k != "turns"}, ensure_ascii=False)
            turns = ",\n".join("  " + json.dumps(t, ensure_ascii=False) for t in sc["turns"])
            blocks.append(head[:-1] + ', "turns": [\n' + turns + "\n]}")
        self.scenarios_path.write_text("[\n" + ",\n".join(blocks) + "\n]\n", encoding="utf-8")

    # ------------------------------------------------------------------ system
    def connect(self) -> None:
        """Nạp hệ thống thật; thiếu thì ném ``SystemNotReady`` với thông báo rõ ràng."""
        if self._client or self._service:
            return
        os.environ["DATABASE_URL"] = os.environ.get("EVAL_DATABASE_URL", EVAL_DATABASE_URL)
        self._load_root_env()
        sys.path.insert(0, str(BACKEND_ROOT))
        try:
            if self.via == "service":
                from app.services.recommendation.service import RecommendationService
                self._service = RecommendationService()
                return
            from fastapi.testclient import TestClient

            from app.main import app
        except ImportError as exc:
            raise SystemNotReady(f"chưa có hệ thống: không import được ({exc})") from exc
        except TypeError as exc:
            raise SystemNotReady(f"RecommendationService() không khởi tạo được: {exc}") from exc
        if "post" not in app.openapi().get("paths", {}).get(CHAT_PATH, {}):
            raise SystemNotReady(f"chưa có hệ thống: app chưa có route POST {CHAT_PATH}")
        self._client = TestClient(app).__enter__()

    @staticmethod
    def _load_root_env() -> None:
        """Nạp OPENAI_*/EMBEDDING_* từ ``.env`` gốc nếu chưa có (không in giá trị)."""
        env_file = REPO_ROOT / ".env"
        if not env_file.exists():
            return
        for line in env_file.read_text(encoding="utf-8").splitlines():
            key, sep, value = line.partition("=")
            if sep and not line.lstrip().startswith("#") and key.strip() != "DATABASE_URL":
                os.environ.setdefault(key.strip(), value.strip().strip('"'))

    def send(self, conversation_id: str | None, message: str, as_of: str) -> dict:
        payload = {"mode": "recommendation", "message": message, "as_of": as_of}
        if conversation_id:
            payload["conversation_id"] = conversation_id
        if self._service is not None:
            result = self._service.chat(
                conversation_id, message, as_of=date.fromisoformat(as_of))
            if asyncio.iscoroutine(result):
                result = asyncio.run(result)
            return result.model_dump(mode="json")
        response = self._client.post(CHAT_PATH, json=payload)
        if response.status_code != 200:
            return {"status": f"http_{response.status_code}", "error": response.text[:300]}
        return response.json()

    # ------------------------------------------------------------------ chạy + chấm
    def run(self, ids: list[str] | None = None, replay: dict | None = None) -> list[dict]:
        """Chạy các kịch bản, trả về bản ghi chấm của từng lượt.

        ``replay`` ((id, lượt) -> bản ghi cũ) chấm lại kết quả đã lưu, không gọi hệ thống.
        """
        if replay is None:
            self.connect()
        records, prev_final = [], {}
        for sc in self.scenarios:
            if ids and sc["id"] not in ids:
                continue
            conv_id, last_ids, state, after_reset = None, [], {}, False
            for i, turn in enumerate(sc["turns"], 1):
                message = REF_PATTERN.sub(
                    lambda m, ids_=last_ids: self._ref(ids_, int(m.group(1))), turn["user"])
                started = time.perf_counter()
                old = replay.get((sc["id"], i)) if replay is not None else None
                result = old["result"] if old else self.send(conv_id, message, sc["as_of"])
                latency = old["latency"] if old else time.perf_counter() - started
                rec = {"id": sc["id"], "category": sc["category"], "turn": i, "user": message,
                       "expect": turn, "result": result, "latency": latency,
                       "checks": {}, "errors": []}
                conv_id = result.get("conversation_id", conv_id)
                state = turn.get("expect_constraints", state)
                after_reset = after_reset or (
                    sc["category"] == "reset" and turn["expect_status"] == "need_clarification")
                self._grade(rec, sc, state, last_ids, prev_final if i == 1 else None,
                            after_reset)
                if result.get("status") in SEARCH_STATUSES:
                    last_ids = [h["listing_id"] for h in result.get("listings", [])]
                records.append(rec)
            prev_final = records[-1]["result"].get("constraints") or {} if records else {}
        return records

    @staticmethod
    def _ref(last_ids: list[str], pos: int) -> str:
        return last_ids[pos - 1] if 0 < pos <= len(last_ids) else f"<thiếu căn {pos}>"

    def _grade(self, rec: dict, sc: dict, state: dict, last_ids: list[str],
               prev_final: dict | None, after_reset: bool) -> None:
        """Chấm một lượt; ``checks[code]`` là (số đạt, số kiểm)."""
        exp, res, checks, errors = rec["expect"], rec["result"], rec["checks"], rec["errors"]
        as_of = date.fromisoformat(sc["as_of"])
        hits = res.get("listings") or []
        hit_ids = [h["listing_id"] for h in hits]
        actual = res.get("constraints") or {}

        status_ok = res.get("status") == exp["expect_status"]
        checks["S2"] = (int(status_ok), 1)
        if not status_ok:
            errors.append(f"S2 status {res.get('status')} != {exp['expect_status']}")

        if "expect_constraints" in exp:
            wrong = self.wrong_fields(exp["expect_constraints"], actual, exp.get("expect_soft"))
            total = len(exp["expect_constraints"]) + bool(exp.get("expect_soft"))
            checks["S3"] = (total - len(wrong), total)
            errors += [f"S3 {w}" for w in wrong]

        if exp["expect_status"] == "ok":
            need = exp.get("min_results", 1)
            checks["S4"] = (int(len(hits) >= need), 1)
            if len(hits) < need:
                errors.append(f"S4 {len(hits)} tin < min_results {need}")

        if hits:
            bad = self.oracle.violations(hit_ids, state, as_of)
            s1 = {k: v["s1"] for k, v in bad.items() if v["s1"]}
            s6 = {k: v["s6"] for k, v in bad.items() if v["s6"]}
            checks["S1"] = (int(not s1), 1)
            checks["S6"] = (int(not s6), 1)
            errors += [f"S1 tin {k} vi phạm {v}" for k, v in s1.items()]
            errors += [f"S6 tin {k} {v}" for k, v in s6.items()]
            dups = self.oracle.duplicate_pairs(hit_ids)
            checks["S15"] = (int(not dups), 1)
            errors += [f"S15 cặp tin đăng lại {a}/{b}" for a, b in dups]

        self._grade_grounding(rec, hits)
        if "expect_refs" in exp:
            self._grade_refs(rec, last_ids)
        self._grade_answer(rec, last_ids)
        if res.get("status") == "no_results":
            self._grade_relax(rec, state, as_of)
        self._grade_leak(rec, prev_final, after_reset)

    def wrong_fields(self, expected: dict, actual: dict, expect_soft: bool | None) -> list[str]:
        """Liệt kê trường sai so với kỳ vọng (tên quận/phường đổi sang ID qua oracle)."""
        wrong = []
        for key, want in expected.items():
            got = actual.get(ID_FIELDS.get(key, key))
            if key in ID_FIELDS:
                ok = sorted(got or []) == self.oracle.ids_for(expected, key)
            elif key == "near_pois":
                ok = sorted(map(_poi_key, got or [])) == sorted(map(_poi_key, want))
            elif isinstance(want, list):
                ok = sorted(got or []) == sorted(want)
            else:
                ok = (got is None and want is None) or (
                    got is not None and want is not None and math.isclose(got, want, abs_tol=0.5))
            if not ok:
                wrong.append(f"{key}: kỳ vọng {want}, thực tế {got}")
        if expect_soft and not actual.get("soft_query"):
            wrong.append("soft_query: kỳ vọng có sở thích mềm, thực tế rỗng")
        return wrong

    def _grade_grounding(self, rec: dict, hits: list[dict]) -> None:
        """[S5] ID/URL chấm tự động; giá lệch > 1% so với đầu vào ⇒ danh sách chấm tay."""
        res = rec["result"]
        answer = res.get("answer") or ""
        allowed = {h["listing_id"] for h in hits} | set(res.get("referenced_ids") or [])
        facts = self.oracle.listing_facts(sorted(allowed))
        # Mã tin đăng lại (similar_ids) và mã người dùng tự gõ cũng là dữ liệu của lượt này.
        allowed |= {sid for h in hits for sid in h.get("similar_ids") or []}
        allowed |= {a or b for a, b in ID_PATTERN.findall(rec["user"])}
        urls = {f["url"] for f in facts.values() if f["url"]} | {
            h.get("listing_url") for h in hits if h.get("listing_url")}
        cited = {a or b for a, b in ID_PATTERN.findall(answer)}
        bad_ids = sorted(cited - allowed)
        bad_urls = [u.rstrip(".,;:") for u in URL_PATTERN.findall(answer)
                    if u.rstrip(".,;:") not in urls]
        rec["checks"]["S5"] = (int(not bad_ids and not bad_urls), 1)
        rec["errors"] += [f"S5 ID lạ {i}" for i in bad_ids] + [f"S5 URL lạ {u}" for u in bad_urls]
        inputs = self._money_inputs(res, facts)
        texts = [f["text"] for f in facts.values()] + sorted(urls) + [EXAMPLE_TEXT]
        rec["price_review"] = [
            text for text, value in money_mentions(answer)
            if not any(abs(value - k) <= PRICE_TOLERANCE * k for k in inputs)
            and not any(text in source for source in texts)]

    @staticmethod
    def _money_inputs(res: dict, facts: dict) -> list[float]:
        """Mọi số tiền (triệu) có trong dữ liệu đưa vào lượt này (§9 #9)."""
        constraints = res.get("constraints") or {}
        values = [f[k] for f in facts.values() for k in ("price", "price_per_m2") if f[k]]
        values += [h["price"] for h in res.get("listings") or [] if h.get("price")]
        values += [constraints[k] for k in ("price_min", "price_max") if constraints.get(k)]
        if constraints.get("price_max") and any(
                o.get("field") == "price_max" for o in res.get("relax_options") or []):
            values.append(constraints["price_max"] * RELAX_PRICE_FACTOR)
        return values

    def _grade_refs(self, rec: dict, last_ids: list[str]) -> None:
        """[S8] referenced_ids khớp vị trí được hỏi; tham chiếu sai ⇒ rỗng; không trả tin."""
        res, refs = rec["result"], rec["expect"]["expect_refs"]
        want = sorted(last_ids[p - 1] for p in refs if p <= len(last_ids))
        if len(want) < len(refs):
            rec["errors"].append(
                f"S8 lượt trước chỉ có {len(last_ids)} tin, không đủ vị trí {refs}")
        got = sorted(res.get("referenced_ids") or [])
        ok = got == want and len(want) == len(refs) and not res.get("listings")
        rec["checks"]["S8"] = (int(ok), 1)
        if not ok:
            rec["errors"].append(f"S8 referenced_ids {got} != {want} (listings phải rỗng)")

    def _expand(self, text: str, last_ids: list[str], rows: dict[str, dict]) -> str:
        """Thay ``{cột@vị_trí:đơn_vị}`` bằng giá trị DB của tin ở vị trí đó."""
        def replace(match: re.Match) -> str:
            column, position, unit = match.group(1), int(match.group(2)), match.group(3)
            row = rows.get(last_ids[position - 1]) if 0 < position <= len(last_ids) else None
            value = row.get(column) if row else None
            if value is None:
                return MISSING
            if column in UNIT_COLUMNS:
                return f"{number_text(value)} {unit or ''}".strip()
            return str(value)
        return ANSWER_TOKEN.sub(replace, text)

    def _grade_answer(self, rec: dict, last_ids: list[str]) -> None:
        """[X1] đủ ý, [X2] 'nhất' đúng căn, [X3] chi tiết đủ thuộc tính."""
        exp, res = rec["expect"], rec["result"]
        answer = (res.get("answer") or "").lower()
        rows = self.oracle.row_values(last_ids) if last_ids else {}
        errors = []
        for need in exp.get("expect_answer_all", []):
            options = [need] if isinstance(need, str) else need
            options = [self._expand(o, last_ids, rows).lower() for o in options]
            if not any(o in answer for o in options):
                errors.append(f"X1 thiếu {options}")
        errors += [f"X1 không được chứa {bad!r}" for bad in exp.get("expect_answer_not", [])
                   if bad.lower() in answer]
        if "expect_answer_all" in exp or "expect_answer_not" in exp:
            rec["checks"]["X1"] = (int(not errors), 1)
            rec["errors"] += errors
        if "expect_superlative" in exp:
            self._grade_superlative(rec, last_ids, rows)
        if "expect_detail_complete" in exp:
            self._grade_detail(rec, last_ids, rows)

    @staticmethod
    def _grade_superlative(rec: dict, last_ids: list[str], rows: dict[str, dict]) -> None:
        """'Căn nào rộng nhất/rẻ nhất/gần chợ nhất': referenced_ids chỉ gồm căn tối ưu theo DB."""
        spec = rec["expect"]["expect_superlative"]
        values = {i: rows[i][spec["column"]] for i in last_ids
                  if i in rows and rows[i][spec["column"]] is not None}
        best = (max if spec["mode"] == "max" else min)(values.values()) if values else None
        winners = {i for i, v in values.items() if v == best}
        got = set(rec["result"].get("referenced_ids") or [])
        ok = bool(got) and got <= winners
        rec["checks"]["X2"] = (int(ok), 1)
        if not ok:
            rec["errors"].append(f"X2 referenced_ids {sorted(got)}, đúng theo DB {sorted(winners)}")

    @staticmethod
    def _grade_detail(rec: dict, last_ids: list[str], rows: dict[str, dict]) -> None:
        """Mọi thuộc tính có trong DB của tin được hỏi phải xuất hiện trong câu trả lời."""
        answer = (rec["result"].get("answer") or "").lower()
        missing = []
        for position in rec["expect"]["expect_refs"]:
            row = rows.get(last_ids[position - 1]) if position <= len(last_ids) else None
            if row is None:
                missing.append(f"không có căn {position} để so DB")
                continue
            wanted = {"giá": money_text(row["price"]), "link": row["listing_url"]}
            for column, unit in (("area", "m²"), ("bedrooms", "phòng ngủ"),
                                 ("bathrooms", "phòng tắm"), ("floors", "tầng")):
                if row[column] is not None:
                    wanted[column] = f"{number_text(row[column])} {unit}"
            for column in ("frontage", "road_width"):
                if row[column] is not None:
                    wanted[column] = f"{number_text(row[column])} m"
            for column in ("legal", "interior"):
                if row[column]:
                    wanted[column] = row[column]
            for column in ("posted_at", "expired_at"):
                if row[column] is not None:
                    wanted[column] = row[column].strftime("%d/%m/%Y")
            missing += [f"căn {position} thiếu {name} ({text})" for name, text in wanted.items()
                        if text.lower() not in answer]
        rec["checks"]["X3"] = (int(not missing), 1)
        rec["errors"] += [f"X3 {m}" for m in missing]

    def _grade_relax(self, rec: dict, state: dict, as_of: date) -> None:
        """[S14] relax_options = đúng các phương án oracle đếm được > 0 (§9 #5).

        So theo từng ``field`` dạng đa tập ``result_count``: ``near_pois`` có thể nhiều option
        (mỗi POI một), các field khác tối đa một.
        """
        oracle = self.oracle.relax_counts(state, as_of)
        want = {field: sorted(n for n in counts if n > 0) for field, counts in oracle.items()}
        got: dict[str, list] = {}
        for opt in rec["result"].get("relax_options") or []:
            got.setdefault(opt.get("field"), []).append(opt.get("result_count"))
        errors = [f"S14 field không hợp lệ {f}" for f in got if f not in RELAX_FIELDS]
        for field in RELAX_FIELDS:
            expect, actual = want.get(field, []), sorted(got.get(field, []), key=str)
            if expect != actual:
                errors.append(f"S14 {field}: result_count {actual}, oracle {expect}")
        rec["checks"]["S14"] = (int(not errors), 1)
        rec["errors"] += errors
        rec["relax_oracle"] = want

    def _grade_leak(self, rec: dict, prev_final: dict | None, after_reset: bool) -> None:
        """[S9] trường bị xóa sau reset phải rỗng; lượt đầu không mang điều kiện hội thoại trước."""
        actual = rec["result"].get("constraints") or {}
        leaks = []
        expected = rec["expect"].get("expect_constraints", {})
        if after_reset:
            for key, want in expected.items():
                field = ID_FIELDS.get(key, key)
                if want in (None, []) and actual.get(field) not in (None, []):
                    leaks.append(f"{field}={actual.get(field)} sau reset")
        if prev_final:
            names = {field: key for key, field in ID_FIELDS.items()}
            for field, value in prev_final.items():
                if value not in (None, [], "") and actual.get(field) == value and (
                        names.get(field, field) not in expected):
                    leaks.append(f"{field}={value} rò từ hội thoại trước")
        if after_reset or prev_final is not None:
            rec["checks"]["S9"] = (int(not leaks), 1)
            rec["errors"] += [f"S9 {x}" for x in leaks]

    # ------------------------------------------------------------------ báo cáo
    @staticmethod
    def summarize(records: list[dict]) -> dict:
        """Tổng hợp điểm từng tiêu chí, p95 và chi phí ước tính."""
        scores = {}
        for code, threshold, desc in CRITERIA:
            done = [r["checks"][code] for r in records if code in r["checks"]]
            if code.startswith("X") and not done:
                continue  # tiêu chí bổ sung chỉ hiện khi kịch bản dùng tới
            passed, total = sum(p for p, _ in done), sum(t for _, t in done)
            rate = passed / total if total else 1.0
            scores[code] = {"desc": desc, "threshold": threshold, "passed": passed,
                            "total": total, "ok": rate >= threshold}
        lat = sorted(r["latency"] for r in records)
        p95 = lat[max(0, math.ceil(0.95 * len(lat)) - 1)] if lat else 0.0
        calls = 2 * len(records)
        cost = calls * (TOKENS_IN_PER_CALL * PRICE_IN_PER_M
                        + TOKENS_OUT_PER_CALL * PRICE_OUT_PER_M) / 1e6
        return {"scores": scores, "p95": p95, "cost": cost, "turns": len(records)}

    def write_report(self, records: list[dict], path: Path | None = None) -> dict:
        path = path or self.report_path
        summary = self.summarize(records)
        passed = all(s["ok"] for s in summary["scores"].values()) and (
            summary["p95"] <= P95_LIMIT_S)
        verdict = "PASS" if passed else "FAIL"
        p95_ok = "có" if summary["p95"] <= P95_LIMIT_S else "KHÔNG"
        lines = [
            f"# Báo cáo recommendation — {time.strftime('%Y-%m-%d')}", "",
            f"KẾT LUẬN: {verdict} ({summary['turns']} lượt, [S7] chấm tay bên dưới)", "",
            "| Tiêu chí | Ngưỡng | Kết quả | Đạt? |", "|---|---|---|---|",
        ]
        for code, s in summary["scores"].items():
            lines.append(f"| [{code}] {s['desc']} | {s['threshold']:.0%} | "
                         f"{s['passed']}/{s['total']} | {'có' if s['ok'] else 'KHÔNG'} |")
        lines.append(f"| [S13] p95 thời gian/lượt | <= {P95_LIMIT_S:.0f} s | "
                     f"{summary['p95']:.2f} s | {p95_ok} |")
        lines += [
            "",
            (f"Chi phí ước tính: ~{summary['cost']:.3f} USD (2 lần gọi gpt-4o-mini/lượt, "
             f"{TOKENS_IN_PER_CALL}+{TOKENS_OUT_PER_CALL} token/lần)."),
            "", "## CASE FAIL", "",
            "| ID | Nhóm | Lượt | Câu hỏi | Kỳ vọng | Thực tế | Lỗi |",
            "|---|---|---|---|---|---|---|",
        ]
        for r in records:
            if r["errors"]:
                res = r["result"]
                lines.append(
                    f"| {r['id']} | {r['category']} | {r['turn']} | {r['user'][:80]} | "
                    f"{r['expect']['expect_status']} | {res.get('status')}, "
                    f"{len(res.get('listings') or [])} tin | {'; '.join(r['errors'])[:400]} |")
        lines += ["", "## [S7] Top 5 sở thích mềm (chấm tay: số tin phù hợp/5 + lý do)", ""]
        for r in records:
            if r["category"] == "soft_semantic" and r["expect"].get("expect_soft"):
                lines.append(f"### {r['id']} lượt {r['turn']}: {r['user']}")
                lines += [f"- [Tin {h['listing_id']}] {h.get('title')} — điểm: ? — lý do: ?"
                          for h in r["result"].get("listings") or []]
                lines.append("")
        lines += ["## Giá trong answer cần xem tay ([S5])", ""]
        lines += [f"- {r['id']} lượt {r['turn']}: {', '.join(r['price_review'])}"
                  for r in records if r.get("price_review")]
        lines += ["", "## Thay đổi bộ test", "", "(chưa có)", ""]
        path.write_text("\n".join(lines), encoding="utf-8")
        # Bản ghi đầy đủ từng lượt (answer, listings) để chấm tay [S5]/[S7].
        path.with_name(path.stem.replace("report", "last_run") + ".json").write_text(
            json.dumps(records, ensure_ascii=False, indent=1), encoding="utf-8")
        return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--ids", help="Danh sách ID kịch bản, vd. C01,C07")
    parser.add_argument("--via", choices=("api", "service"), default="api")
    parser.add_argument("--oracle", action="store_true", help="Chỉ chạy oracle, in min_results")
    parser.add_argument("--write-min-results", action="store_true")
    parser.add_argument("--extra", action="store_true",
                        help="Chạy scenarios_extra.json (hồi quy từ lỗi khách thật), báo cáo riêng")
    parser.add_argument("--regrade", action="store_true",
                        help="Chấm lại last_run.json, không gọi hệ thống")
    args = parser.parse_args()
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    harness = RecommendEval(via=args.via, extra=args.extra)
    try:
        if args.oracle:
            rows = harness.oracle_table()
            print(f"{'ID':<5}{'lượt':>5}  {'kỳ vọng':<11}{'oracle':>7}{'min':>5}  ghi chú")
            for r in rows:
                note = r["problem"] or (f"relax {r['relax']}" if "relax" in r else "")
                print(f"{r['id']:<5}{r['turn']:>5}  {r['status']:<11}{r['count']:>7}"
                      f"{r['min_results']:>5}  {note}")
            if args.write_min_results:
                harness.write_min_results(rows)
            return int(any(r["problem"] for r in rows))
        ids = args.ids.split(",") if args.ids else None
        replay = None
        if args.regrade:
            last_run = harness.report_path.stem.replace("report", "last_run") + ".json"
            old = json.loads(harness.report_path.with_name(last_run).read_text(encoding="utf-8"))
            replay = {(r["id"], r["turn"]): r for r in old}
        try:
            records = harness.run(ids, replay)
        except SystemNotReady as exc:
            print(f"CHƯA CÓ HỆ THỐNG — {exc}", file=sys.stderr)
            return 2
        summary = harness.write_report(records)
        for code, s in summary["scores"].items():
            print(f"[{code}] {s['passed']}/{s['total']} {'OK' if s['ok'] else 'FAIL'}")
        print(f"[S13] p95 {summary['p95']:.2f}s; report: {harness.report_path}")
        return 0
    finally:
        harness.close()


if __name__ == "__main__":
    sys.exit(main())
