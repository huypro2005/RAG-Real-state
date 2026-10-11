"""Test bộ kịch bản recommendation (docs/tasks/hybrid-search.md mục 6, 7).

- Không cần OpenAI: hình dạng ``scenarios.json`` và kỳ vọng dữ liệu bằng oracle SQL.
- ``pytest -m llm``: chạy hệ thống thật qua ``POST /api/v1/recommend/chat`` — từng kịch bản
  (tiêu chí cứng mỗi lượt) và bảng trích điều kiện từng câu (so toàn bộ trường).
"""

import json
from collections import Counter
from datetime import date

import psycopg
import pytest
from oracle import SqlOracle
from run_eval import (
    CATEGORY_QUOTA,
    EXTRA_SCENARIOS_PATH,
    HERE,
    SEARCH_STATUSES,
    RecommendEval,
    SystemNotReady,
)

SCENARIOS = RecommendEval.load_scenarios()
EXTRA = RecommendEval.load_scenarios(EXTRA_SCENARIOS_PATH)
EXTRACTION_CASES = json.loads((HERE / "extraction_cases.json").read_text(encoding="utf-8"))
HARD_FIELDS = ("price_min", "price_max", "area_min", "area_max", "bedrooms_min")
LIST_FIELDS = ("property_types", "district_names", "new_ward_names", "near_pois")
# Tiêu chí phải đạt trên từng lượt; [S3] chấm theo tổng (>= 95%) trong run_eval.py.
PER_TURN_CRITERIA = ("S1", "S2", "S4", "S5", "S6", "S8", "S9", "S14", "S15", "X1", "X2", "X3")


@pytest.fixture(scope="module")
def harness():
    try:
        oracle = SqlOracle()
    except psycopg.OperationalError as exc:
        pytest.skip(f"không kết nối được DB oracle: {exc}")
    harness = RecommendEval(oracle=oracle)
    yield harness
    harness.close()


@pytest.fixture(scope="module")
def extra_harness():
    try:
        oracle = SqlOracle()
    except psycopg.OperationalError as exc:
        pytest.skip(f"không kết nối được DB oracle: {exc}")
    harness = RecommendEval(oracle=oracle, extra=True)
    yield harness
    harness.close()


def test_scenarios_follow_spec_allocation():
    counts = Counter(sc["category"] for sc in SCENARIOS)
    assert counts == CATEGORY_QUOTA
    assert [sc["id"] for sc in SCENARIOS] == [f"C{i:02d}" for i in range(1, 51)]
    assert all(2 <= len(sc["turns"]) <= 6 and sc["as_of"] == "2026-09-22" for sc in SCENARIOS)
    assert sum(len(sc["turns"]) for sc in SCENARIOS) >= 150


def test_search_turns_have_full_expectations():
    for sc in SCENARIOS:
        for i, turn in enumerate(sc["turns"], 1):
            if turn["expect_status"] in SEARCH_STATUSES:
                assert "expect_constraints" in turn and "min_results" in turn, (sc["id"], i)
            if turn["expect_status"] == "answered":
                assert "expect_refs" in turn, (sc["id"], i)


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda sc: sc["id"])
def test_oracle_agrees_with_expectations(harness, scenario):
    as_of = date.fromisoformat(scenario["as_of"])
    for i, turn in enumerate(scenario["turns"], 1):
        if turn["expect_status"] not in SEARCH_STATUSES:
            continue
        n = harness.oracle.count(turn["expect_constraints"], as_of)
        if turn["expect_status"] == "ok":
            assert n >= 1 and turn["min_results"] == min(5, n), (i, n)
        else:
            assert n == 0, (i, n)


@pytest.mark.llm
@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda sc: sc["id"])
def test_conversation(harness, scenario):
    try:
        records = harness.run([scenario["id"]])
    except SystemNotReady as exc:
        pytest.fail(f"CHƯA CÓ HỆ THỐNG — {exc}")
    failures = [
        f"lượt {r['turn']} [{code}]: {'; '.join(e for e in r['errors'] if e.startswith(code))}"
        for r in records for code, (passed, total) in r["checks"].items()
        if code in PER_TURN_CRITERIA and passed < total
    ]
    assert not failures, "\n".join(failures)


@pytest.mark.llm
@pytest.mark.parametrize("case", EXTRACTION_CASES, ids=lambda c: c["text"][:40])
def test_extraction_full_fields(harness, case):
    try:
        harness.connect()
    except SystemNotReady as exc:
        pytest.fail(f"CHƯA CÓ HỆ THỐNG — {exc}")
    result = harness.send(None, case["text"], "2026-09-22")
    expected = {key: None for key in HARD_FIELDS} | {key: [] for key in LIST_FIELDS}
    expected |= case["expect"]
    wrong = harness.wrong_fields(expected, result.get("constraints") or {},
                                 case.get("expect_soft"))
    assert not wrong, wrong


def test_extra_scenarios_shape():
    """Bộ hồi quy từ lỗi khách thật: 2-4 lượt, có kỳ vọng; không lẫn vào bộ 50."""
    assert not {sc["id"] for sc in EXTRA} & {sc["id"] for sc in SCENARIOS}
    assert len(SCENARIOS) == 50
    for sc in EXTRA:
        assert 2 <= len(sc["turns"]) <= 4 and sc["category"].startswith("extra_"), sc["id"]
        for i, turn in enumerate(sc["turns"], 1):
            if turn["expect_status"] in SEARCH_STATUSES:
                assert "min_results" in turn and "expect_constraints" in turn, (sc["id"], i)


@pytest.mark.parametrize("scenario", EXTRA, ids=lambda sc: sc["id"])
def test_extra_oracle_agrees(extra_harness, scenario):
    as_of = date.fromisoformat(scenario["as_of"])
    for i, turn in enumerate(scenario["turns"], 1):
        if turn["expect_status"] == "ok":
            n = extra_harness.oracle.count(turn["expect_constraints"], as_of)
            assert n >= 1 and turn["min_results"] == min(5, n), (i, n)


@pytest.mark.llm
@pytest.mark.parametrize("scenario", EXTRA, ids=lambda sc: sc["id"])
def test_extra_conversation(extra_harness, scenario):
    try:
        records = extra_harness.run([scenario["id"]])
    except SystemNotReady as exc:
        pytest.fail(f"CHƯA CÓ HỆ THỐNG — {exc}")
    failures = [
        f"lượt {r['turn']} [{code}]: {'; '.join(e for e in r['errors'] if e.startswith(code))}"
        for r in records for code, (passed, total) in r["checks"].items()
        if code in PER_TURN_CRITERIA and passed < total
    ]
    assert not failures, chr(10).join(failures)
