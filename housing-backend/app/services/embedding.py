"""Client gọi API embedding/rerank trên Kaggle (dùng cho hội thoại gợi ý)."""

import httpx

from app.core.config import Settings


class EmbeddingClient:
    """Gọi API Kaggle cho MỘT câu hỏi timeout ngắn, thử lại 1 lần: một lượt chat phải xong
    trong vài giây ([S13]). Test thay bằng client giả có embed/rerank."""

    TIMEOUT_SECONDS = 5.0
    ATTEMPTS = 2

    def __init__(self, settings: Settings):
        key = settings.embedding_api_key
        self.base_url = (settings.embedding_api_url or "").rstrip("/")
        self.headers = {"X-API-Key": key.get_secret_value() if key else ""}
        self.model_name = settings.embedding_model_name
        self.dim = settings.embedding_dim

    async def embed(self, query: str) -> list[float]:
        """Vector của câu hỏi; lỗi nếu server trả sai model hoặc số chiều."""
        body = await self._post("/embed", {"texts": [query]})
        vector = body["embeddings"][0]
        if body.get("model") != self.model_name or len(vector) != self.dim:
            raise ValueError(f"API trả model {body.get('model')!r}, {len(vector)} chiều")
        return vector

    async def rerank(self, query: str, documents: list[str]) -> list[float]:
        """Điểm liên quan của từng document (cần endpoint /rerank trên server)."""
        body = await self._post("/rerank", {"query": query, "documents": documents})
        scores = body["scores"]
        if len(scores) != len(documents):
            raise ValueError("số điểm rerank khác số document")
        return scores

    async def _post(self, path: str, payload: dict) -> dict:
        """POST JSON; thử lại khi lỗi mạng/5xx."""
        if not self.base_url:
            raise RuntimeError("chưa cấu hình EMBEDDING_API_URL")
        async with httpx.AsyncClient(timeout=self.TIMEOUT_SECONDS) as client:
            for attempt in range(self.ATTEMPTS):
                try:
                    response = await client.post(
                        self.base_url + path, json=payload, headers=self.headers
                    )
                    response.raise_for_status()
                    return response.json()
                except (httpx.TransportError, httpx.HTTPStatusError) as error:
                    status = getattr(getattr(error, "response", None), "status_code", 500)
                    if attempt == self.ATTEMPTS - 1 or status < 500:  # 4xx thử lại cũng vô ích
                        raise
