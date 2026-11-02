"""P11 (không rò rỉ) và quy tắc chọn mô hình: chạy trên bảng tổng hợp, không DB."""
from types import SimpleNamespace

import numpy as np
import pandas as pd

from src.prediction_server.services.training.trainer import PriceModelTrainer
from src.prediction_server.tests.conftest import feature_frame, make_table


def result(name, model, features, mean, std):
    return {"name": name, "model": model, "features": features, "cv_r2_mean": mean,
            "cv_r2_std": std, "n_features": 11 if features else 9}


def test_pick_prefers_simpler_model_within_one_std():
    results = [result("xgboost", "xgboost", "", 0.840, 0.01),
               result("extra_trees", "extra_trees", "", 0.835, 0.01),
               result("random_forest", "random_forest", "", 0.700, 0.01)]
    winner = PriceModelTrainer.pick(results)
    assert winner["name"] == "extra_trees" and winner["tie_break"] is True


def test_pick_takes_best_when_gap_exceeds_std():
    results = [result("xgboost", "xgboost", "", 0.86, 0.01),
               result("extra_trees", "extra_trees", "", 0.80, 0.01)]
    assert PriceModelTrainer.pick(results)["name"] == "xgboost"


def test_test_split_never_influences_the_model(settings):
    """Đổi nhãn VÀ đặc trưng của các dòng test (kể cả ô thiếu) không được đổi model."""
    trainer = PriceModelTrainer(settings)
    table = make_table()
    _, test = trainer.split(table)
    altered = table.copy()
    altered.loc[test.index, "giá/m2"] *= 5
    altered.loc[test.index, ["mặt tiền", "phòng ngủ", "số tầng"]] = 999.0
    original = trainer.train_table(table).bundle["pipeline"]
    changed = trainer.train_table(altered).bundle["pipeline"]
    probe = feature_frame(table).fillna(5.0)
    assert np.allclose(original.predict(probe), changed.predict(probe))


def test_imputer_medians_come_from_train_only(settings):
    trainer = PriceModelTrainer(settings)
    table = make_table()
    train, _ = trainer.split(table)
    bundle = trainer.train_table(table).bundle
    expected = trainer.trim(train)[bundle["features"]].median().to_numpy()
    assert np.allclose(bundle["pipeline"]["imputer"].statistics_, expected)


def ids(frame):
    return set(frame["listing_id"])


def test_split_is_fixed_per_listing_across_retrains(settings):
    """Thêm dòng mới vào bảng thì không tin cũ nào đổi phía train/test."""
    trainer = PriceModelTrainer(settings)
    old = make_table(400)
    new = pd.concat([old, make_table(150, seed=1, first_id=400)], ignore_index=True)
    old_train, old_test = trainer.split(old)
    new_train, new_test = trainer.split(new)
    assert ids(old_test) <= ids(new_test) and ids(old_train) <= ids(new_train)
    assert ids(new_train).isdisjoint(ids(new_test))
    assert 0.1 < len(new_test) / len(new) < 0.3


def test_old_model_has_no_advantage_on_new_test(settings):
    """Model cũ chưa từng thấy test mới (không dòng test mới nào nằm trong train của nó)."""
    trainer = PriceModelTrainer(settings)
    old = make_table(400)
    new = pd.concat([old, make_table(150, seed=1, first_id=400)], ignore_index=True)
    old_train, _ = trainer.split(old)
    _, new_test = trainer.split(new)
    assert ids(old_train).isdisjoint(ids(new_test))
    bundle = trainer.train_table(old).bundle
    fair = SimpleNamespace(pipeline=bundle["pipeline"], split_rule=bundle["split_rule"])
    assert trainer.train_table(new, active=fair).baseline is not None


def test_model_trained_with_old_random_split_gets_no_baseline(settings):
    """Model cũ không có split_rule: đo lại trên test mới là thiên vị nên bỏ baseline."""
    trainer = PriceModelTrainer(settings)
    table = make_table(400)
    pipeline = trainer.train_table(table).bundle["pipeline"]
    legacy = SimpleNamespace(pipeline=pipeline, split_rule=None)
    assert trainer.train_table(table, active=legacy).baseline is None
