import logging
from datetime import date
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from openai import OpenAIError
from pydantic import BaseModel, Field

from app.api.deps import (
    ListingRepoDep,
    PoiRepoDep,
    PredictionChatDep,
    RecommendationServiceDep,
    SessionDep,
)
from app.schemas.listing import ListingOut
from app.schemas.poi import NearbyPoiOut, PoiType
from app.services.map import ChatSupport
from app.services.recommendation.schemas import POI_NAMES, ChatRequest, ChatTurnResult
from app.services.recommendation.service import RecommendationService

logger = logging.getLogger(__name__)

router = APIRouter()

MAX_MAP_LISTINGS = 10
ASSISTANT_DOWN = "Trợ lý tạm thời không phản hồi, bạn thử lại sau nhé."


def _assistant_unavailable(log_message: str) -> HTTPException:
    """503 khi gọi OpenAI lỗi; chi tiết chỉ ghi log. Gọi bên trong khối `except`."""
    logger.exception(log_message)
    return HTTPException(status_code=503, detail=ASSISTANT_DOWN)


class ResetRequest(BaseModel):
    conversation_id: str


class ModeChatRequest(BaseModel):
    """Body của POST /chat: client chọn mode, backend không đoán."""

    mode: Literal["recommendation", "prediction"]
    conversation_id: str | None = Field(default=None, max_length=100)
    message: str = Field(min_length=1, max_length=20_000)
    as_of: date | None = None  # chỉ mode recommendation dùng (cố định "hôm nay" khi test)


@router.get("/listings/{listing_id}", response_model=ListingOut, tags=["listings"])
async def get_listing(listing_id: str, repo: ListingRepoDep):
    listing = await repo.get(listing_id)
    if listing is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy tin")
    return listing


@router.get("/pois/nearby", response_model=list[NearbyPoiOut], tags=["pois"])
async def get_nearby_pois(
    repo: PoiRepoDep,
    lat: float = Query(ge=-90, le=90),
    lon: float = Query(ge=-180, le=180),
    radius_m: float = Query(1000, gt=0, le=10_000),
    poi_type: PoiType | None = None,
    limit: int = Query(50, ge=1, le=200),
):
    return await repo.nearby(lon, lat, radius_m, poi_type, limit)


async def _recommendation_turn(
    service: RecommendationService, conversation_id: str | None, message: str,
    as_of: date | None,
) -> ChatTurnResult:
    """Một lượt chat gợi ý; lỗi OpenAI thành 503 (dùng chung cho /chat và /recommend/chat)."""
    try:
        return await service.chat(conversation_id, message, as_of)
    except OpenAIError as error:
        raise _assistant_unavailable("TurnInterpreter gọi OpenAI lỗi") from error


@router.post("/chat", tags=["chat"])
async def chat(
    request: ModeChatRequest,
    recommendation: RecommendationServiceDep,
    prediction: PredictionChatDep,
):
    """Một lượt hội thoại, điều phối theo `mode`: recommendation (gợi ý nhà) hoặc prediction."""
    if request.mode == "recommendation":
        result = await _recommendation_turn(recommendation, request.conversation_id,
                                            request.message, request.as_of)
        return {**result.model_dump(mode="json"), "mode": "recommendation"}
    if prediction is None:
        raise HTTPException(503, "Mô hình định giá chưa được huấn luyện")
    try:
        return await prediction.turn(request.conversation_id, request.message)
    except OpenAIError as error:
        raise _assistant_unavailable("FieldExtractor gọi OpenAI lỗi") from error


@router.post("/reset", tags=["chat"])
async def reset(
    request: ResetRequest, recommendation: RecommendationServiceDep, prediction: PredictionChatDep
):
    """Xoá hội thoại ở cả hai mode ("Làm lại từ đầu")."""
    if prediction is not None:
        prediction.reset(request.conversation_id)
    return ChatSupport(store=recommendation.store).reset(request.conversation_id)


@router.post("/recommend/chat", response_model=ChatTurnResult, tags=["recommend"])
async def recommend_chat(request: ChatRequest, service: RecommendationServiceDep):
    """Một lượt hội thoại gợi ý nhà; không gửi conversation_id thì tạo hội thoại mới."""
    return await _recommendation_turn(
        service, request.conversation_id, request.message, request.as_of
    )


@router.post("/recommend/reset", tags=["recommend"])
async def recommend_reset(request: ResetRequest, service: RecommendationServiceDep):
    """Xoá state hội thoại ("Tìm lại từ đầu" trên giao diện)."""
    return ChatSupport(store=service.store).reset(request.conversation_id)


@router.get("/recommend/map", tags=["recommend"])
async def recommend_map(
    session: SessionDep,
    ids: str = Query(min_length=1, description="listing_id cách nhau bởi dấu phẩy, theo thứ tự"),
    radius_m: float = Query(2000, gt=0, le=10_000),
    poi_types: str = "truong_hoc,benh_vien,cho",
):
    """GeoJSON: tin đã gợi ý (đánh số theo thứ tự `ids`) và POI quanh chúng."""
    listing_ids = list(dict.fromkeys(i.strip() for i in ids.split(",") if i.strip()))
    types = [t.strip() for t in poi_types.split(",") if t.strip()]
    if not listing_ids or len(listing_ids) > MAX_MAP_LISTINGS:
        raise HTTPException(422, f"ids cần từ 1 đến {MAX_MAP_LISTINGS} mã tin")
    if invalid := [t for t in types if t not in POI_NAMES]:
        raise HTTPException(422, f"poi_types không hợp lệ: {', '.join(invalid)}")
    return await ChatSupport(session=session).geojson(listing_ids, radius_m, types)
