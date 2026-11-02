"""Client OpenAI dùng chung cho TurnInterpreter (gợi ý) và FieldExtractor (dự đoán giá)."""

import httpx
from openai import AsyncOpenAI, DefaultAsyncHttpxClient

from app.core.config import Settings


def openai_client(settings: Settings) -> AsyncOpenAI:
    """Client OpenAI không giữ kết nối keep-alive (mỗi lượt có thể chạy trong event loop riêng)."""
    key = settings.openai_api_key
    return AsyncOpenAI(
        api_key=key.get_secret_value() if key else None,
        http_client=DefaultAsyncHttpxClient(limits=httpx.Limits(max_keepalive_connections=0)),
    )
