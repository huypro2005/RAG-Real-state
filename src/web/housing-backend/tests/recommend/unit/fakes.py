"""Đối tượng giả dùng chung cho unit test (thay API embedding, TurnInterpreter)."""

from datetime import date

from app.services.recommendation.schemas import ConstraintDelta, TurnPlan

AS_OF = date(2026, 9, 22)  # dữ liệu crawl đến 21/09/2026 (spec mục 3)
VECTOR_DIM = 1024


class FakeEmbeddingClient:
    """Thay EmbeddingClient: trả vector cố định, hoặc ném lỗi để thử phương án dự phòng."""

    def __init__(self, embed_error: Exception | None = None,
                 rerank_error: Exception | None = None):
        self.embed_error = embed_error
        self.rerank_error = rerank_error
        self.rerank_calls = 0

    async def embed(self, query: str) -> list[float]:
        if self.embed_error:
            raise self.embed_error
        return [1 / VECTOR_DIM**0.5] * VECTOR_DIM

    async def rerank(self, query: str, documents: list[str]) -> list[float]:
        self.rerank_calls += 1
        if self.rerank_error:
            raise self.rerank_error
        return [float(i) for i in range(len(documents))]  # đảo ngược thứ tự ban đầu


class FakeInterpreter:
    """Trả lần lượt các TurnPlan dựng sẵn; ghi lại message/context đã nhận."""

    def __init__(self, plans: list[TurnPlan]):
        self.plans = list(plans)
        self.calls: list[tuple[str, dict]] = []

    async def interpret(self, message: str, context: dict) -> TurnPlan:
        self.calls.append((message, context))
        return self.plans.pop(0)


def plan(intent: str = "search", clear: list[str] | None = None, **fields) -> TurnPlan:
    """TurnPlan viết gọn: plan("refine", price_max=3000, district_names=["Quận 7"])."""
    return TurnPlan(intent=intent, set_fields=ConstraintDelta(**fields), clear_fields=clear or [])
