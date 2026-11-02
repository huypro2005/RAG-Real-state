"""P9, P10: quy tắc retrain và thăng hạng model (hàm thuần, không DB)."""
from types import SimpleNamespace

import pytest

from src.prediction_server.services.training.policy import RetrainPolicy


@pytest.fixture
def policy(settings):
    return RetrainPolicy(settings)


def outcome(r2_log, mae, baseline):
    return SimpleNamespace(metrics={"r2_log": r2_log, "mae": mae}, baseline=baseline)


def test_retrain_when_no_model(policy):
    assert policy.should_retrain(1000, None, has_model=False)[0]


def test_skip_below_threshold_and_retrain_above(policy):
    assert not policy.should_retrain(2000, 1990, True)[0]   # 10 tin mới < min(200, 5%)
    assert policy.should_retrain(2000, 1900, True)[0]       # 100 tin >= 5% của 2000
    assert policy.should_retrain(10000, 9800, True)[0]      # 200 tin mới
    ok, reason = policy.should_retrain(2000, 1990, True)
    assert not ok and "ngưỡng" in reason


def test_skip_when_too_few_listings(policy):
    assert not policy.should_retrain(10, None, False)[0]


def test_promote_without_active_model(policy):
    assert policy.should_promote(outcome(0.8, 30, None), None)[0]


def test_not_promoted_when_worse_on_same_test(policy):
    baseline = {"r2_log": 0.80, "mae": 30}
    ok, reason = policy.should_promote(outcome(0.79, 30, baseline), {"r2_log": 0.80})
    assert not ok and reason.startswith("not_promoted")


def test_tie_on_same_test_is_promoted_not_blocked(policy):
    baseline = {"r2_log": 0.80, "mae": 30}
    assert policy.should_promote(outcome(0.80, 30, baseline), {"r2_log": 0.80})[0]


def test_promote_when_better_and_mae_not_much_worse(policy):
    baseline = {"r2_log": 0.80, "mae": 30}
    assert policy.should_promote(outcome(0.82, 30.5, baseline), {"r2_log": 0.80})[0]


def test_not_promoted_when_mae_regresses_too_much(policy):
    baseline = {"r2_log": 0.80, "mae": 30}
    ok, reason = policy.should_promote(outcome(0.83, 40, baseline), {"r2_log": 0.80})
    assert not ok and "MAE" in reason


def test_legacy_active_model_is_replaced_once_by_the_fixed_split_lineage(policy):
    """Model cũ không có luật chia mới (baseline None): không so được, kích hoạt model mới."""
    ok, reason = policy.should_promote(outcome(0.70, 99, None), {"r2_log": 0.83, "mae": 30})
    assert ok and "Chuyển giao" in reason


def test_force_still_requires_enough_listings(policy):
    ok, reason = policy.enough_data(10)
    assert not ok and "cần >=" in reason and policy.enough_data(5000)[0]
