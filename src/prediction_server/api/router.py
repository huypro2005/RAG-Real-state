"""Gom mọi router của API v1."""
from fastapi import APIRouter

from src.prediction_server.api.routers import health, ingest, jobs, models, predict, retrain

api_router = APIRouter()
for module in (health, predict, ingest, jobs, retrain, models):
    api_router.include_router(module.router)
