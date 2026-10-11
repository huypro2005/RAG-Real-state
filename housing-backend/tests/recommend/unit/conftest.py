"""Fixture chung cho unit test mode recommendation (không gọi OpenAI).

Test cần DB đọc DATABASE_URL (vd. housing_dev); không đặt thì tự skip. Không dùng
pytest-asyncio: mỗi test tự chạy coroutine bằng asyncio.run. Marker `llm` do
tests/recommend/conftest.py đăng ký.
"""

import asyncio
import os

import pytest
from fakes import FakeEmbeddingClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.services.recommendation.search import HybridSearch


@pytest.fixture
def run_db():
    """run_db(lambda session: coroutine) -> kết quả; mỗi lần một engine mới trên DATABASE_URL."""
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("chưa đặt DATABASE_URL (vd. ...@localhost:5432/housing_dev)")

    def run(make_coroutine):
        async def main():
            engine = create_async_engine(url)
            try:
                async with AsyncSession(engine) as session:
                    return await make_coroutine(session)
            finally:
                await engine.dispose()

        return asyncio.run(main())

    return run


@pytest.fixture
def make_search():
    def make(session, client=None, rerank_enabled=False) -> HybridSearch:
        return HybridSearch(session, client or FakeEmbeddingClient(), rerank_enabled)

    return make
