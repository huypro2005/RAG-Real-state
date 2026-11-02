"""FastAPI app của Prediction Server (mỏng: dựng app, vòng đời, lỗi DB, gắn router).

Chạy (tại thư mục gốc dự án, .venv gốc):
    python -m uvicorn src.prediction_server.main:app --port 8100
"""
from contextlib import asynccontextmanager

import psycopg
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from src.prediction_server.api.router import api_router
from src.prediction_server.core.container import Container
from src.prediction_server.core.settings import ServerSettings, get_settings


def create_app(settings: ServerSettings | None = None) -> FastAPI:
    """Nhận settings để test dựng app với cấu hình riêng."""
    container = Container(settings or get_settings())

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        container.runner.start()
        yield
        container.runner.stop()

    app = FastAPI(title="Prediction Server", lifespan=lifespan)
    app.state.container = container

    @app.exception_handler(psycopg.errors.UndefinedTable)
    async def schema_missing(_: Request, __: Exception) -> JSONResponse:
        return JSONResponse({"detail": "db_schema_missing: chạy alembic upgrade head"}, 503)

    @app.exception_handler(psycopg.OperationalError)
    async def db_down(_: Request, error: Exception) -> JSONResponse:
        return JSONResponse({"detail": f"Không kết nối được database: {error}"}, 503)

    app.include_router(api_router)
    return app


app = create_app()
