import logging
import threading
from functools import lru_cache
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import engine, get_session
from app.repositories.listing_repo import ListingRepository
from app.repositories.poi_repo import PoiRepository
from app.services.prediction.chat import PredictionChat
from app.services.prediction.extractor import FieldExtractor
from app.services.prediction.geocoder import Geocoder
from app.services.prediction.predictor import PricePredictor
from app.services.recommendation.service import RecommendationService, openai_client

logger = logging.getLogger(__name__)

SessionDep = Annotated[AsyncSession, Depends(get_session)]


def get_listing_repo(session: SessionDep) -> ListingRepository:
    return ListingRepository(session)


def get_poi_repo(session: SessionDep) -> PoiRepository:
    return PoiRepository(session)


# Dependency đồng bộ chạy trong threadpool: lru_cache KHÔNG khoá khi khởi tạo, nên khởi động nguội
# với nhiều request đồng thời sẽ tạo nhiều đối tượng và state hội thoại nằm rải rác ở các bản sao.
_init_lock = threading.Lock()


@lru_cache
def _build_recommendation_service() -> RecommendationService:
    return RecommendationService(engine=engine)


def get_recommendation_service() -> RecommendationService:
    """Một service cho cả tiến trình: ConversationStore bên trong sống qua nhiều request."""
    with _init_lock:
        return _build_recommendation_service()


@lru_cache
def _build_prediction_chat() -> PredictionChat:
    """Một PredictionChat cho cả tiến trình: nạp model một lần, state hội thoại sống qua request."""
    settings = get_settings()
    goong_key = settings.goong_api_key
    return PredictionChat(
        extractor=FieldExtractor(openai_client(settings), settings.openai_model),
        predictor=PricePredictor.load(),
        geocoder=Geocoder(goong_key.get_secret_value() if goong_key else None, engine),
    )


def get_prediction_chat() -> PredictionChat | None:
    """None nếu chưa train model: chỉ mode prediction báo lỗi, mode recommendation vẫn chạy."""
    try:
        with _init_lock:
            return _build_prediction_chat()
    except FileNotFoundError:
        logger.warning("Chưa có models/price_rf.joblib; chạy scripts/train_price_model.py")
        return None


ListingRepoDep = Annotated[ListingRepository, Depends(get_listing_repo)]
PoiRepoDep = Annotated[PoiRepository, Depends(get_poi_repo)]
RecommendationServiceDep = Annotated[
    RecommendationService, Depends(get_recommendation_service)
]
PredictionChatDep = Annotated[PredictionChat | None, Depends(get_prediction_chat)]
