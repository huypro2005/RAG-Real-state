"""Đăng ký marker ``llm``: test gọi OpenAI chỉ chạy khi chọn rõ bằng ``pytest -m llm``."""

import pytest


def pytest_configure(config):
    config.addinivalue_line("markers", "llm: gọi hệ thống thật (OpenAI); chạy bằng pytest -m llm")


def pytest_collection_modifyitems(config, items):
    if "llm" in (config.option.markexpr or ""):
        return
    skip = pytest.mark.skip(reason="cần OpenAI; chạy bằng pytest -m llm")
    for item in items:
        if "llm" in item.keywords:
            item.add_marker(skip)
