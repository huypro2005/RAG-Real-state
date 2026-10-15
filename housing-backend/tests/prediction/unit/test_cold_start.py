"""Khởi động nguội: nhiều request đồng thời không được tạo nhiều service (mất state hội thoại)."""

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.api import deps
from app.main import app
from app.services.prediction.schemas import PredictionTurn
from app.services.recommendation.schemas import ChatTurnResult, SearchConstraints
from app.services.recommendation.service import ConversationStore

CLIENTS = 8
BUILD_SECONDS = 0.05  # đủ lâu để các request đồng thời cùng thấy cache còn trống
built = []


class SlowPredictionChat:
    """Giả PredictionChat: dựng chậm, nhớ số lượt của từng hội thoại trong chính nó."""

    def __init__(self, extractor, predictor, geocoder):
        time.sleep(BUILD_SECONDS)
        built.append("prediction")
        self.predictor, self.geocoder = predictor, geocoder
        self.turns = {}

    async def turn(self, conversation_id, message):
        self.turns[conversation_id] = self.turns.get(conversation_id, 0) + 1
        return PredictionTurn(conversation_id=conversation_id, status="ready",
                              answer=f"turn {self.turns[conversation_id]}")


class SlowRecommendationService:
    def __init__(self, engine, valuer=None):
        time.sleep(BUILD_SECONDS)
        built.append("recommendation")
        self.store, self.turns = ConversationStore(), {}

    async def chat(self, conversation_id, message, as_of):
        self.turns[conversation_id] = self.turns.get(conversation_id, 0) + 1
        return ChatTurnResult(conversation_id=conversation_id, status="ok",
                              constraints=SearchConstraints(),
                              answer=f"turn {self.turns[conversation_id]}")


@pytest.fixture
def cold_client(monkeypatch):
    monkeypatch.setattr(deps, "PredictionChat", SlowPredictionChat)
    monkeypatch.setattr(deps, "RecommendationService", SlowRecommendationService)
    monkeypatch.setattr(deps, "PricePredictor", SimpleNamespace(load=lambda: None))
    monkeypatch.setattr(deps, "openai_client", lambda settings: None)
    for cached in (deps._build_prediction_chat, deps._build_recommendation_service):
        cached.cache_clear()
    built.clear()
    with TestClient(app) as client:
        yield client
    for cached in (deps._build_prediction_chat, deps._build_recommendation_service):
        cached.cache_clear()


@pytest.mark.parametrize("mode", ["prediction", "recommendation"])
def test_parallel_first_requests_share_one_service_and_keep_state(cold_client, mode):
    start = threading.Barrier(CLIENTS)

    def conversation(index):
        answers = []
        start.wait()  # cả 8 hội thoại cùng bắt đầu lúc server còn nguội
        for message in ("lượt một", "lượt hai"):
            body = {"mode": mode, "message": message, "conversation_id": f"c{index}"}
            answers.append(cold_client.post("/api/v1/chat", json=body).json()["answer"])
        return answers

    with ThreadPoolExecutor(CLIENTS) as pool:
        results = list(pool.map(conversation, range(CLIENTS)))
    assert results == [["turn 1", "turn 2"]] * CLIENTS
    assert built.count("prediction") == 1 and built.count("recommendation") == 1
